"""The content: a checkout of colophon-entries, one folder per project.

    <project>/project.toml      the profile
    <project>/icon.png
    <project>/docs/<doc>.toml   a doc's fields (type, title, summary, trigger...)
    <project>/docs/<doc>.md     its body

Every write is validated in full before anything touches the disk, is made
under one lock, becomes one commit with the caller as author, and is pushed to
origin. A push that fails leaves the commit in place; the next write, or the
retry at startup, pushes it.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from ..core import Invalid
from ..core import doc as doc_mod
from ..core import profile as profile_mod
from . import iconconv

BRANCH = "main"
PROFILE = "project.toml"
DOCS = "docs"
# The layout before projects had docs: one entry.toml and an optional guide.md.
OLD_PROFILE = "entry.toml"
OLD_GUIDE = "guide.md"


class NotFound(LookupError):
    pass


class Conflict(Exception):
    pass


@dataclass(frozen=True)
class Caller:
    login: str           # tailnet login, or a local stand-in
    name: str            # display name
    machine: str         # the device the request came from
    source: str = "tailnet"   # tailnet | local

    @property
    def author(self) -> str:
        return f"{self.name} <{self.login}>"


# The server's own commits (a migration, a push retry). Set COLOPHON_COMMIT_EMAIL
# to an address of yours; the default only says where it came from.
SERVER_EMAIL = os.environ.get("COLOPHON_COMMIT_EMAIL", "colophon@localhost")
SERVER_CALLER = Caller(login=SERVER_EMAIL, name="Colophon",
                       machine="colophon", source="local")


@dataclass
class Doc:
    project: str
    meta: dict
    body: str

    @property
    def name(self) -> str:
        return self.meta["name"]

    @property
    def type(self) -> doc_mod.DocType:
        return doc_mod.TYPES.get(self.meta["type"]) or doc_mod.DocType(self.meta["type"])

    @property
    def title(self) -> str:
        return doc_mod.title(self.meta)


@dataclass
class Project:
    profile: dict
    icon_path: Path
    docs: list[Doc]

    @property
    def name(self) -> str:
        return self.profile["name"]

    def doc(self, name: str) -> Doc:
        for d in self.docs:
            if d.name == name:
                return d
        raise NotFound(f"{self.name}/{name}")


@dataclass
class WriteResult:
    name: str
    commit: str | None
    pushed: bool | None   # None: nothing to push to
    changed: bool = True
    notes: list[str] = field(default_factory=list)

    def as_json(self) -> dict:
        return {"name": self.name, "commit": self.commit, "pushed": self.pushed,
                "changed": self.changed, "notes": self.notes}


def _unstamped(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "updated"}


class Store:
    def __init__(self, root: Path, state_dir: Path, remote: str = "", push: bool = True):
        self.root = Path(root)
        self.state_dir = Path(state_dir)
        self.remote = remote
        self.push_enabled = push
        self.lock = threading.Lock()
        self.push_error: str | None = None
        self._seen_lock = threading.Lock()

    # -- git -----------------------------------------------------------------

    def git(self, *args: str, check: bool = True, timeout: int = 60) -> subprocess.CompletedProcess:
        env = {**os.environ,
               "GIT_COMMITTER_NAME": "Colophon",
               "GIT_COMMITTER_EMAIL": SERVER_EMAIL,
               "GIT_TERMINAL_PROMPT": "0"}
        r = subprocess.run(["git", "-C", str(self.root), *args], capture_output=True,
                           text=True, env=env, timeout=timeout)
        if check and r.returncode:
            raise RuntimeError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[-400:]}")
        return r

    def ensure(self) -> None:
        """A checkout to work in: cloned from the remote, or a new local repo."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        if (self.root / ".git").exists():
            return
        self.root.parent.mkdir(parents=True, exist_ok=True)
        if self.remote:
            r = subprocess.run(["git", "clone", "-q", self.remote, str(self.root)],
                               capture_output=True, text=True, timeout=120)
            if r.returncode:
                raise RuntimeError(f"could not clone {self.remote}: {r.stderr.strip()}")
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.git("init", "-q")
        # An empty clone has no branch yet; the first commit makes main.
        if self.git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode:
            self.git("symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")

    def has_origin(self) -> bool:
        return self.git("remote", "get-url", "origin", check=False).returncode == 0

    def push(self) -> bool | None:
        """Push main to origin. None when there is no origin or pushing is off."""
        if not self.push_enabled or not self.has_origin():
            return None
        if self.git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode:
            return None
        r = self.git("push", "-q", "origin", f"HEAD:refs/heads/{BRANCH}", check=False, timeout=90)
        if r.returncode:
            self.push_error = (r.stderr or r.stdout).strip()[-400:]
            return False
        self.push_error = None
        return True

    def head(self) -> str | None:
        r = self.git("rev-parse", "--short", "HEAD", check=False)
        return r.stdout.strip() if r.returncode == 0 else None

    # -- reading ---------------------------------------------------------------

    def _dir(self, name: str) -> Path:
        profile_mod.check_name(name)
        return self.root / name

    def exists(self, name: str) -> bool:
        try:
            return (self._dir(name) / PROFILE).is_file()
        except Invalid:
            return False

    def _read_doc(self, project: str, toml_path: Path) -> Doc | None:
        body = toml_path.with_suffix(".md")
        try:
            meta = profile_mod.loads(toml_path.read_text(), toml_path.name)
        except Invalid:
            return None
        if meta.get("name") != toml_path.stem or not body.is_file():
            return None
        return Doc(project=project, meta=meta, body=body.read_text())

    def get(self, name: str) -> Project:
        if not self.exists(name):
            raise NotFound(name)
        d = self._dir(name)
        prof = profile_mod.loads((d / PROFILE).read_text())
        docs = []
        if (d / DOCS).is_dir():
            for t in sorted((d / DOCS).glob("*.toml"), key=lambda t: t.stem):
                doc = self._read_doc(name, t)
                if doc:
                    docs.append(doc)
        return Project(profile=prof, icon_path=d / "icon.png", docs=docs)

    def get_doc(self, project: str, name: str) -> Doc:
        try:
            doc_mod.check_name(name)
        except Invalid:
            raise NotFound(f"{project}/{name}") from None
        return self.get(project).doc(name)

    def all(self) -> list[Project]:
        out = []
        if not self.root.is_dir():
            return out
        for d in sorted(self.root.iterdir()):
            if d.is_dir() and (d / PROFILE).is_file():
                try:
                    out.append(self.get(d.name))
                except (Invalid, NotFound):
                    continue
        return out

    def skills(self) -> list[Doc]:
        """Every doc whose type makes a pointer skill, across all projects."""
        return [d for p in self.all() for d in p.docs if d.type.pointer]

    def find_skill(self, name: str) -> Doc | None:
        for d in self.skills():
            if d.name == name:
                return d
        return None

    _LOG = "%H%x1f%h%x1f%an%x1f%ae%x1f%aI%x1f%s%x1f%(trailers:key=Via,valueonly,separator=%x2C)%x1e"

    def _log(self, *pathspec: str, limit: int, follow: bool = False) -> list[dict]:
        args = ["log", f"-n{limit}", f"--format={self._LOG}"]
        if follow:
            args.append("--follow")
        r = self.git(*args, "--", *pathspec, check=False)
        out = []
        for rec in r.stdout.split("\x1e"):
            rec = rec.strip("\n")
            if not rec:
                continue
            sha, short, an, ae, date, subject, via = (rec.split("\x1f") + [""] * 7)[:7]
            out.append({"commit": sha, "short": short, "author": an, "login": ae,
                        "machine": via.strip() or None, "date": date, "subject": subject})
        return out

    def history(self, name: str, limit: int = 50) -> list[dict]:
        if not self.exists(name):
            raise NotFound(name)
        return self._log(f"{name}/", limit=limit)

    def doc_history(self, project: str, name: str, limit: int = 50) -> list[dict]:
        """Commits to the doc: its body followed through moves (so the guide it
        was before projects had docs counts too), and its fields."""
        self.get_doc(project, name)
        base = f"{project}/{DOCS}/{name}"
        seen, out = set(), []
        for c in self._log(f"{base}.md", limit=limit, follow=True) + self._log(f"{base}.toml", limit=limit):
            if c["commit"] not in seen:
                seen.add(c["commit"])
                out.append(c)
        out.sort(key=lambda c: c["date"], reverse=True)
        return out[:limit]

    # -- writing ---------------------------------------------------------------

    def _commit(self, paths: list[str], subject: str, caller: Caller) -> WriteResult:
        name = subject.split(":", 1)[0]
        self.git("add", "-A", "--", *paths)
        if self.git("diff", "--cached", "--quiet", "--", *paths, check=False).returncode == 0:
            return WriteResult(name=name, commit=self.head(), pushed=None, changed=False)
        body = f"{subject}\n" + (f"\nVia: {caller.machine}\n" if caller.machine else "")
        self.git("commit", "-q", f"--author={caller.author}", "-m", body, "--", *paths)
        commit = self.head()
        pushed = self.push()
        res = WriteResult(name=name, commit=commit, pushed=pushed)
        if pushed is False:
            res.notes.append("committed but the push failed; it is retried on the next write")
        return res

    def _rollback(self, paths: list[str]) -> None:
        self.git("reset", "-q", "--", *paths, check=False)
        if self.git("rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0:
            self.git("checkout", "-q", "HEAD", "--", *paths, check=False)
        self.git("clean", "-fdq", "--", *paths, check=False)

    def _write(self, subject: str, caller: Caller, files: dict[str, bytes | None],
               paths: list[str] | None = None) -> WriteResult:
        """files maps paths under the root to new content, or None to remove."""
        paths = paths or sorted({f.split("/", 1)[0] + "/" for f in files})
        try:
            for fname, data in files.items():
                path = self.root / fname
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(path.suffix + ".part")
                    tmp.write_bytes(data)
                    tmp.replace(path)
            return self._commit(paths, subject, caller)
        except Exception:
            self._rollback(paths)
            raise

    @staticmethod
    def _stamp(d: dict) -> dict:
        return {**d, "updated": dt.date.today()}

    def _profile_file(self, name: str, prof: dict) -> dict[str, bytes]:
        return {f"{name}/{PROFILE}": profile_mod.dumps(self._stamp(prof)).encode()}

    def _doc_files(self, project: str, meta: dict, body: str | None) -> dict[str, bytes]:
        base = f"{project}/{DOCS}/{meta['name']}"
        files = {f"{base}.toml": profile_mod.dumps(self._stamp(meta), doc_mod.FIELDS).encode()}
        if body is not None:
            files[f"{base}.md"] = body.encode()
        return files

    def _check_skill_name_free(self, name: str, project: str) -> None:
        """Pointer skills are named after their doc, so a skill doc's name is
        unique across every project."""
        other = self.find_skill(name)
        if other and other.project != project:
            raise Conflict(f"a skill called {name} already exists, in {other.project}; "
                           "skill names are unique across projects")

    # projects

    def create(self, prof: dict, icon: bytes, caller: Caller) -> WriteResult:
        prof = profile_mod.validate(_unstamped(prof))
        icon = iconconv.normalize(icon)
        with self.lock:
            name = prof["name"]
            if self.exists(name):
                raise Conflict(f"{name} already exists")
            files = {**self._profile_file(name, prof), f"{name}/icon.png": icon}
            return self._write(f"{name}: create", caller, files)

    def update_profile(self, name: str, changes: dict, caller: Caller, replace: bool = False) -> WriteResult:
        with self.lock:
            cur = self.get(name).profile
            if replace:
                for key in changes:
                    if key not in profile_mod.SETTABLE:
                        raise Invalid(f"{key!r} cannot be set")
                new = {"name": name, **changes}
            else:
                new = profile_mod.merge(cur, changes)
            new = profile_mod.validate(_unstamped(new))
            if _unstamped(cur) == new:
                return WriteResult(name=name, commit=self.head(), pushed=None, changed=False)
            fields = sorted(k for k in set(cur) | set(new)
                            if k != "updated" and cur.get(k) != new.get(k))
            return self._write(f"{name}: profile " + ", ".join(fields), caller,
                               self._profile_file(name, new))

    def put_icon(self, name: str, data: bytes, caller: Caller) -> WriteResult:
        data = iconconv.normalize(data)
        with self.lock:
            prof = _unstamped(self.get(name).profile)
            return self._write(f"{name}: icon", caller,
                               {f"{name}/icon.png": data, **self._profile_file(name, prof)})

    def delete_project(self, name: str, caller: Caller) -> WriteResult:
        with self.lock:
            p = self.get(name)
            if p.docs:
                raise Conflict(f"{name} still has docs ({', '.join(d.name for d in p.docs)}); "
                               "move or remove them first")
            files = {f"{name}/{PROFILE}": None, f"{name}/icon.png": None}
            return self._write(f"{name}: removed", caller, files)

    # docs

    def create_doc(self, project: str, meta: dict, body: str, caller: Caller,
                   written_against: str | None = None) -> WriteResult:
        if written_against:
            meta = {**meta, "written_against": written_against}
        meta = doc_mod.validate(_unstamped(meta))
        body = doc_mod.validate_body(body, meta["type"])
        with self.lock:
            p = self.get(project)
            if any(d.name == meta["name"] for d in p.docs):
                raise Conflict(f"{project}/{meta['name']} already exists")
            if doc_mod.TYPES[meta["type"]].pointer:
                self._check_skill_name_free(meta["name"], project)
            res = self._write(f"{project}/{meta['name']}: create {meta['type']}", caller,
                              self._doc_files(project, meta, body))
        if written_against:
            self.record_seen(project, written_against, {meta["name"]: 0})
        return res

    def update_doc(self, project: str, name: str, changes: dict, caller: Caller) -> WriteResult:
        with self.lock:
            cur = self.get_doc(project, name)
            new = profile_mod.merge(cur.meta, changes, doc_mod.FIELDS, doc_mod.SETTABLE,
                                    doc_mod.REQUIRED)
            # A type with no pointer skill keeps no trigger.
            t = doc_mod.TYPES.get(new.get("type", ""))
            if t and not t.pointer:
                new.pop("trigger", None)
            new = doc_mod.validate(_unstamped(new))
            if new["type"] != cur.meta["type"]:
                doc_mod.validate_body(cur.body, new["type"])
                if t and t.pointer:
                    self._check_skill_name_free(name, project)
            if _unstamped(cur.meta) == new:
                return WriteResult(name=f"{project}/{name}", commit=self.head(), pushed=None,
                                   changed=False)
            fields = sorted(k for k in set(cur.meta) | set(new)
                            if k != "updated" and cur.meta.get(k) != new.get(k))
            return self._write(f"{project}/{name}: " + ", ".join(fields), caller,
                               self._doc_files(project, new, None))

    def put_body(self, project: str, name: str, text: str, caller: Caller,
                 written_against: str | None = None) -> WriteResult:
        with self.lock:
            cur = self.get_doc(project, name)
            text = doc_mod.validate_body(text, cur.meta["type"])
            meta = _unstamped(cur.meta)
            if written_against:
                meta["written_against"] = written_against
            meta = doc_mod.validate(meta)
            if cur.body == text and meta.get("written_against") == cur.meta.get("written_against"):
                return WriteResult(name=f"{project}/{name}", commit=self.head(), pushed=None,
                                   changed=False)
            res = self._write(f"{project}/{name}: body", caller, self._doc_files(project, meta, text))
        if written_against:
            self.record_seen(project, written_against, {name: 0})
        return res

    def delete_doc(self, project: str, name: str, caller: Caller) -> WriteResult:
        with self.lock:
            self.get_doc(project, name)
            base = f"{project}/{DOCS}/{name}"
            return self._write(f"{project}/{name}: removed", caller,
                               {f"{base}.toml": None, f"{base}.md": None})

    def move_doc(self, project: str, name: str, to: str, caller: Caller) -> WriteResult:
        """Move a doc to another project, as a rename so its history follows."""
        with self.lock:
            self.get_doc(project, name)
            target = self.get(to)
            if to == project:
                return WriteResult(name=f"{project}/{name}", commit=self.head(), pushed=None,
                                   changed=False)
            if any(d.name == name for d in target.docs):
                raise Conflict(f"{to}/{name} already exists")
            src, dst = f"{project}/{DOCS}/{name}", f"{to}/{DOCS}/{name}"
            (self.root / to / DOCS).mkdir(parents=True, exist_ok=True)
            paths = [f"{project}/", f"{to}/"]
            try:
                for ext in (".md", ".toml"):
                    self.git("mv", f"{src}{ext}", f"{dst}{ext}")
                return self._commit(paths, f"{to}/{name}: moved from {project}", caller)
            except Exception:
                self._rollback(paths)
                raise

    def retry_push(self) -> bool | None:
        with self.lock:
            return self.push()

    # -- the layout before projects had docs ------------------------------------

    def migrate(self, caller: Caller = SERVER_CALLER) -> WriteResult | None:
        """Turn every old entry (entry.toml, maybe guide.md) into a project of
        the same name. Its guide becomes a doc of the same name, moved with git
        so the doc's history reaches back to the guide: a skill when it had a
        trigger, else a guide. One commit for the lot. None when there is
        nothing to migrate."""
        with self.lock:
            old = sorted(d for d in self.root.iterdir()
                         if d.is_dir() and (d / OLD_PROFILE).is_file() and not (d / PROFILE).exists()) \
                if self.root.is_dir() else []
            if not old:
                return None
            paths = [f"{d.name}/" for d in old]
            try:
                for d in old:
                    o = profile_mod.loads((d / OLD_PROFILE).read_text(), OLD_PROFILE)
                    prof = {k: v for k, v in o.items() if k in profile_mod.FIELDS}
                    files = {f"{d.name}/{PROFILE}": profile_mod.dumps(prof).encode()}
                    if (d / OLD_GUIDE).is_file():
                        meta = {"name": d.name, "type": "skill" if o.get("trigger") else "guide",
                                "title": o.get("title"), "summary": o.get("summary"),
                                "trigger": o.get("trigger"),
                                "written_against": o.get("written_against"),
                                "updated": o.get("updated")}
                        meta = {k: v for k, v in meta.items() if v is not None}
                        (d / DOCS).mkdir(exist_ok=True)
                        self.git("mv", f"{d.name}/{OLD_GUIDE}", f"{d.name}/{DOCS}/{d.name}.md")
                        files[f"{d.name}/{DOCS}/{d.name}.toml"] = \
                            profile_mod.dumps(meta, doc_mod.FIELDS).encode()
                    for fname, data in files.items():
                        (self.root / fname).write_bytes(data)
                    self.git("rm", "-q", f"{d.name}/{OLD_PROFILE}")
                return self._commit(paths, "migrate: each entry becomes a project, its guide a doc",
                                    caller)
            except Exception:
                self._rollback(paths)
                raise

    # -- what projects report: not content, so not in git -----------------------

    @property
    def _seen_path(self) -> Path:
        return self.state_dir / "seen.json"

    def seen(self) -> dict:
        try:
            return json.loads(self._seen_path.read_text())
        except (OSError, ValueError):
            return {}

    def seen_for(self, project: str) -> dict | None:
        s = self.seen().get(project)
        if not isinstance(s, dict) or not isinstance(s.get("behind"), dict):
            return None
        return s

    def record_seen(self, project: str, commit: str, behind: dict | None) -> dict:
        """The project's commit, and how many commits it is past each doc's
        written_against."""
        if not profile_mod.SHA.match(commit or ""):
            raise Invalid("commit is a commit hash")
        behind = behind or {}
        if not isinstance(behind, dict) or not all(
                isinstance(k, str) and (v is None or (isinstance(v, int) and v >= 0))
                for k, v in behind.items()):
            raise Invalid("behind maps each doc to a count of commits")
        with self._seen_lock:
            data = self.seen()
            prev = data.get(project) if isinstance(data.get(project), dict) else {}
            merged = dict(prev.get("behind") or {}) if isinstance(prev.get("behind"), dict) else {}
            merged.update(behind)
            data[project] = {"commit": commit, "behind": merged,
                             "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds")}
            self.state_dir.mkdir(parents=True, exist_ok=True)
            tmp = self._seen_path.with_suffix(".part")
            tmp.write_text(json.dumps(data, indent=1, sort_keys=True))
            tmp.replace(self._seen_path)
            return data[project]
