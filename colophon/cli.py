"""colophon: the command line. Standard library only.

Inside a folder with a .colophon file (or below one), commands default to
the project it names and its server.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .core import Invalid, marker
from .core import doc as doc_mod
from .core import profile as profile_mod
from .core import skill as skill_mod

# The one machine whose ~/.claude/skills takes pointer skills, so a sync
# elsewhere cannot leave stray copies: COLOPHON_SKILLS_HOST, or `skills_host:`
# in colophon.conf. Unset: any machine.
SKILLS_HOST = os.environ.get("COLOPHON_SKILLS_HOST", "")
# The checkout's own settings file (see user_config).
CONFIG_FILE = Path(__file__).resolve().parents[1] / "colophon.conf"
SKILLS_DIR = Path.home() / ".claude" / "skills"


class Failed(Exception):
    """Stop with this message and exit 1."""


# -- talking to the server -------------------------------------------------------


class Client:
    def __init__(self, server: str, timeout: float = 30):
        self.server = server.rstrip("/")
        self.timeout = timeout

    def call(self, method: str, path: str, body: bytes | None = None,
             ctype: str | None = None, timeout: float | None = None) -> tuple[int, bytes]:
        req = urllib.request.Request(self.server + path, data=body, method=method)
        if ctype:
            req.add_header("Content-Type", ctype)
        req.add_header("User-Agent", "colophon-cli")
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except (urllib.error.URLError, OSError) as e:
            raise Failed(f"cannot reach {self.server}: {getattr(e, 'reason', e)}") from None

    def ok(self, method: str, path: str, body: bytes | None = None, ctype: str | None = None) -> bytes:
        status, data = self.call(method, path, body, ctype)
        if status >= 400:
            try:
                msg = json.loads(data).get("error") or data.decode()
            except ValueError:
                msg = data.decode(errors="replace")
            raise Failed(f"{method} {path}: {status}: {msg}")
        return data

    def json(self, method: str, path: str, payload=None) -> object:
        body = json.dumps(payload).encode() if payload is not None else None
        return json.loads(self.ok(method, path, body, "application/json" if body else None))

    def text(self, path: str) -> str:
        return self.ok("GET", path).decode()

    def get_json(self, path: str) -> dict | None:
        """GET path as JSON, or None on a 404."""
        status, data = self.call("GET", path)
        if status == 404:
            return None
        if status >= 400:
            raise Failed(f"GET {path}: {status}")
        return json.loads(data)


# -- the project this is run in ----------------------------------------------------


def git(*args: str, cwd: Path | None = None) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


class Here:
    """The folder the CLI runs in, and the project its .colophon names."""

    def __init__(self, cwd: Path):
        self.cwd = cwd
        found = marker.find(cwd)
        self.marker_path = found[0] if found else None
        self.marker = found[1] if found else {}

    @property
    def root(self) -> Path:
        return self.marker_path.parent if self.marker_path else self.cwd

    @property
    def project(self) -> str | None:
        return self.marker.get("project")

    def head(self) -> str | None:
        return git("rev-parse", "HEAD", cwd=self.root)

    def behind(self, since: str | None) -> int | None:
        if not since:
            return None
        n = git("rev-list", "--count", f"{since}..HEAD", cwd=self.root)
        return int(n) if n and n.isdigit() else None


def user_config() -> dict[str, str]:
    """The owner's settings, read at run time so they hold in any shell, script
    or service: `colophon.conf` beside this checkout's `bin/` (git ignores it;
    `colophon.conf.example` shows the lines), with `server: <url>` and
    `skills_host: <hostname>`. Missing file, no settings."""
    try:
        text = CONFIG_FILE.read_text()
    except OSError:
        return {}
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        if sep and not key.lstrip().startswith("#"):
            out[key.strip()] = value.strip()
    return out


def server_for(args, here: Here) -> str:
    url = (args.server or os.environ.get("COLOPHON_URL") or here.marker.get("server")
           or user_config().get("server"))
    if not url:
        raise Failed("no server: pass --server, set COLOPHON_URL, or put `server: <url>` "
                     "in colophon.conf")
    return url.rstrip("/")


def need_project(args, here: Here) -> str:
    name = getattr(args, "project", None) or here.project
    if not name:
        raise Failed("no project named, and no .colophon here: pass --project or run `colophon init`")
    return name


def doc_ref(ref: str, args, here: Here) -> tuple[str, str]:
    """<doc> in this project, or <project>/<doc>."""
    if "/" in ref:
        project, _, doc = ref.partition("/")
        return project, doc
    return need_project(args, here), ref


def report_seen(client: Client, here: Here, project: dict | None = None) -> None:
    """Tell the server where this project is now, so the web UI can show how far
    each doc has fallen behind. Best effort: never fails a command."""
    if not here.project:
        return
    head = here.head()
    if not head:
        return
    try:
        if project is None:
            status, data = client.call("GET", f"/{here.project}.json", timeout=3)
            if status != 200:
                return
            project = json.loads(data)
        behind = {d["name"]: here.behind(d.get("written_against"))
                  for d in project.get("docs") or [] if d.get("written_against")}
        payload = json.dumps({"commit": head[:12], "behind": behind}).encode()
        client.call("POST", f"/{here.project}/seen", payload, "application/json", timeout=3)
    except (Failed, ValueError):
        pass


# -- helpers -----------------------------------------------------------------------


def tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    value = input(f"{label}{hint}: ").strip()
    return value or default


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", text.lower()).strip("-")
    return s[:40] or "project"


def home_path(p: Path) -> str:
    try:
        return "~/" + str(p.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(p.resolve())


def read_roster_file(folder: Path) -> dict:
    path = folder / ".roster"
    out: dict = {}
    if not path.is_file():
        return out
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        key, sep, value = line.partition(":")
        if sep:
            out[key.strip()] = value.strip()
    return out


def warn_if_not_ignored(folder: Path) -> None:
    if git("rev-parse", "--git-dir", cwd=folder) is None:
        return
    if git("check-ignore", "-q", marker.FILENAME, cwd=folder) is None:
        print(f"warning: git does not ignore {marker.FILENAME} here. It belongs in the global "
              "excludes file, never in this project's .gitignore.", file=sys.stderr)


def editor() -> list[str]:
    return (os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi").split()


# -- commands ----------------------------------------------------------------------


def cmd_list(args, here, client):
    sys.stdout.write(client.text("/index.md"))


def cmd_get(args, here, client):
    ref = args.ref or need_project(args, here)
    sys.stdout.write(client.text(f"/{ref}.md"))


def cmd_history(args, here, client):
    ref = args.ref or need_project(args, here)
    project, _, doc = ref.partition("/")
    path = f"/{project}/{doc}/history" if doc else f"/{project}/history"
    rows = client.get_json(path)
    if rows is None:
        raise Failed(f"no {'doc' if doc else 'project'} {ref}")
    for c in rows:
        who = c["author"] + (f" on {c['machine']}" if c.get("machine") else "")
        print(f"{c['short']}  {c['date'][:10]}  {who}: {c['subject']}")
    if not rows:
        print(f"{ref}: no commits")


def cmd_search(args, here, client):
    q = urllib.parse.quote(" ".join(args.words))
    sys.stdout.write(client.text(f"/search?q={q}"))


def check_access(text: str | None) -> list[str] | None:
    """--access cli,api as a list, checked against the registry."""
    if text is None:
        return None
    given = profile_mod.coerce("access", text)
    bad = [a for a in given if a not in profile_mod.ACCESS]
    if bad:
        raise Invalid(f"access {', '.join(bad)}: not one of {', '.join(profile_mod.ACCESS)}")
    return given


def cmd_init(args, here, client):
    folder = Path.cwd()
    mark = folder / marker.FILENAME
    name = args.name or (here.project if here.marker_path == mark else None) or slug(folder.name)
    profile_mod.check_name(name)
    args.access = check_access(args.access)

    if client.get_json(f"/{name}.json"):
        marker.write(folder, name, client.server)
        print(f"linked {folder} to {name}; wrote {marker.FILENAME}")
        warn_if_not_ignored(folder)
        return

    # The roster service comes from --roster or the project's own .roster file,
    # never from a service that happens to share the project's name.
    rf = read_roster_file(folder)
    roster_svc = args.roster or rf.get("service")
    facts = client.json("GET", f"/_roster/{roster_svc}") if roster_svc else {}
    if not roster_svc and client.json("GET", f"/_roster/{name}").get("registered"):
        print(f"note: roster has a service called {name}. If it is this project, "
              f"pass --roster {name}", file=sys.stderr)

    prof = {"name": name, "title": args.title, "summary": args.summary or rf.get("description"),
            "kind": args.kind, "access": args.access, "roster": roster_svc,
            "repo": home_path(folder) if git("rev-parse", "--git-dir", cwd=folder) else None,
            "remote": git("remote", "get-url", "origin", cwd=folder)}
    if tty():
        prof["title"] = prof["title"] or ask("Title", name.replace("-", " ").title())
        prof["summary"] = prof["summary"] or ask("Summary (one line: what it is)")
        while prof["kind"] not in profile_mod.KINDS:
            prof["kind"] = ask(f"Kind ({' | '.join(profile_mod.KINDS)})")
        while prof["access"] is None:
            given = ask(f"Access points it really has ({', '.join(profile_mod.ACCESS)}; "
                        "comma separated, blank for none)")
            try:
                prof["access"] = check_access(given)
            except Invalid as e:
                print(e, file=sys.stderr)
    missing = [f"--{k}" for k in ("title", "summary", "kind") if not prof.get(k)]
    if missing:
        raise Failed(f"creating {name} needs {', '.join(missing)}")

    icon = b""
    if args.icon:
        icon = Path(args.icon).expanduser().read_bytes()
    elif roster_svc and facts.get("icon"):
        print(f"using roster's icon for {roster_svc}")
    elif rf.get("icon") and (folder / rf["icon"]).is_file():
        icon = (folder / rf["icon"]).read_bytes()
        print(f"using {rf['icon']} from .roster")
    else:
        raise Failed("an icon is required: pass --icon FILE (PNG, SVG or ICO; the server makes it "
                     "a square PNG). Use the project's own logo or app icon")

    if prof["repo"] and not prof["remote"]:
        print(f"note: no git remote here, so the profile's repo is only a local path ({prof['repo']})",
              file=sys.stderr)

    payload = {"profile": {k: v for k, v in prof.items() if v},
               "icon": base64.b64encode(icon).decode() if icon else None}
    res = client.json("POST", "/", payload)
    marker.write(folder, name, client.server)
    print(f"created {name} ({res.get('commit')}); wrote {marker.FILENAME}")
    if res.get("pushed") is False:
        print("note: the server committed but could not push; it retries on the next write")
    warn_if_not_ignored(folder)


def _written_against(here: Here, project: str) -> str:
    if here.project != project:
        return ""
    head = here.head()
    if not head:
        print(f"note: {here.root} has no commits, so the doc records no commit it was written against",
              file=sys.stderr)
        return ""
    return f"?written_against={head[:12]}"


def _said(res: dict, what: str) -> str:
    if res.get("changed") is False:
        return f"{what}: no change"
    note = "; push failed, retried on the next write" if res.get("pushed") is False else ""
    return f"{what}: committed {res.get('commit')}{note}"


def _edit_text(name: str, original: str, check) -> str | None:
    """Open original in $EDITOR until check passes; None when nothing changed."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{name}.md"
        path.write_text(original)
        while True:
            subprocess.run([*editor(), str(path)], check=False)
            text = path.read_text()
            if text.strip() == original.strip():
                return None
            try:
                check(text)
                return text
            except (Invalid, Failed) as e:
                print(f"refused: {e}", file=sys.stderr)
                if not tty() or ask("Edit again? (y/n)", "y").lower() != "y":
                    raise Failed("doc not saved") from None


def _read_body(file: str | None) -> str | None:
    if file == "-" or (file is None and not sys.stdin.isatty()):
        return sys.stdin.read()
    if file:
        return Path(file).read_text()
    return None


def cmd_add(args, here, client):
    project, name = doc_ref(args.doc, args, here)
    doc_mod.check_name(name)
    meta = {"name": name, "type": args.type, "title": args.title or doc_mod.default_title(name),
            "summary": args.summary, "trigger": args.trigger}
    meta = {k: v for k, v in meta.items() if v}
    if doc_mod.TYPES[args.type].pointer and not meta.get("trigger"):
        raise Failed(f"a {args.type} needs --trigger: what it is and when to reach for it; "
                     "it becomes the pointer skill's description")
    doc_mod.validate(meta)
    text = _read_body(args.file)
    if text is None:
        if not tty():
            raise Failed("give the body as a file, or on stdin")
        text = _edit_text(name, doc_mod.template(args.type),
                          lambda t: doc_mod.validate_body(t, args.type))
        if text is None:
            raise Failed("no body written; nothing added")
    doc_mod.validate_body(text, args.type)
    res = client.json("POST", f"/{project}/docs{_written_against(here, project)}",
                      {"doc": meta, "body": text})
    print(_said(res, f"{project}/{name}"))


def cmd_edit(args, here, client):
    project, name = doc_ref(args.doc, args, here)
    d = client.get_json(f"/{project}/{name}.json")
    if d is None:
        raise Failed(f"no doc {project}/{name}; add it with `colophon add`")
    t = d["doc"]["type"]
    text = _edit_text(name, d["body"], lambda b: doc_mod.validate_body(b, t))
    if text is None:
        print("no change")
        return
    res = json.loads(client.ok("PUT", f"/{project}/{name}{_written_against(here, project)}",
                               text.encode(), "text/markdown"))
    print(_said(res, f"{project}/{name}"))


def cmd_push(args, here, client):
    project, name = doc_ref(args.doc, args, here)
    text = _read_body(args.file or "-")
    res = json.loads(client.ok("PUT", f"/{project}/{name}{_written_against(here, project)}",
                               text.encode(), "text/markdown"))
    print(_said(res, f"{project}/{name}"))


def cmd_set(args, here, client):
    field, value = args.field, args.value
    if args.doc:
        project, name = doc_ref(args.doc, args, here)
        if field not in doc_mod.SETTABLE:
            raise Failed(f"{field} cannot be set on a doc; fields: {', '.join(doc_mod.SETTABLE)}")
        if field == "written_against" and value and not profile_mod.SHA.match(value):
            sha = git("rev-parse", value, cwd=here.root)
            if not sha:
                raise Failed(f"{value} is not a commit here")
            value = sha[:12]
        res = client.json("PUT", f"/{project}/{name}/meta", {field: value})
        print(_said(res, f"{project}/{name} {field}"))
        return
    project = need_project(args, here)
    if field not in profile_mod.SETTABLE:
        raise Failed(f"{field} cannot be set on a project; fields: {', '.join(profile_mod.SETTABLE)}"
                     " (doc fields take --doc)")
    res = client.json("PUT", f"/{project}/profile", {field: value})
    print(_said(res, f"{project} {field}"))


def cmd_icon(args, here, client):
    project = need_project(args, here)
    data = Path(args.file).expanduser().read_bytes()
    res = json.loads(client.ok("PUT", f"/{project}/icon", data, "application/octet-stream"))
    print(_said(res, f"{project} icon"))


def cmd_rm(args, here, client):
    project, name = doc_ref(args.doc, args, here)
    res = client.json("DELETE", f"/{project}/{name}")
    print(_said(res, f"{project}/{name} removed"))


def cmd_delete(args, here, client):
    res = client.json("DELETE", f"/{args.project_name}")
    print(_said(res, f"{args.project_name} removed"))


def cmd_mv(args, here, client):
    project, name = doc_ref(args.doc, args, here)
    res = client.json("POST", f"/{project}/{name}/move", {"to": args.to})
    print(_said(res, f"{project}/{name} moved to {args.to}"))


def cmd_stale(args, here, client):
    if not here.project:
        raise Failed("run this in a project with a .colophon file")
    p = client.get_json(f"/{here.project}.json")
    if p is None:
        raise Failed(f"no project {here.project} on {client.server}")
    if not p.get("docs"):
        print(f"{here.project} has no docs; nothing to fall behind")
    for d in p.get("docs") or []:
        ref = f"{here.project}/{d['name']}"
        since = d.get("written_against")
        if not since:
            print(f"{ref}: does not record the commit it was written against")
            continue
        n = here.behind(since)
        if n is None:
            print(f"{ref}: written against {since[:9]}, which this checkout does not have")
        else:
            print(f"{ref}: {n} commit{'s' if n != 1 else ''} since it was written ({since[:9]})")
    report_seen(client, here, p)


def sync_skills(skills: list[dict], fetch, target: Path) -> dict[str, list[str]]:
    """Write a pointer skill for every skill doc into target. skills are rows
    of /skills.json; fetch(row) gives the SKILL.md text. Only skills colophon
    generated are ever replaced or removed; a hand-written one, or a symlink
    into another repo, is left alone and reported."""
    done: dict[str, list[str]] = {"written": [], "unchanged": [], "removed": [], "skipped": []}
    target.mkdir(parents=True, exist_ok=True)
    rows = {r["name"]: r for r in skills}
    for name in sorted(rows):
        d = target / name
        f = d / "SKILL.md"
        if d.is_symlink() or f.is_symlink() or (f.exists() and not skill_mod.is_generated(f.read_text())):
            done["skipped"].append(name)
            continue
        if d.exists() and not f.exists() and any(d.iterdir()):
            done["skipped"].append(name)
            continue
        text = fetch(rows[name])
        if f.exists() and f.read_text() == text:
            done["unchanged"].append(name)
            continue
        d.mkdir(exist_ok=True)
        f.write_text(text)
        done["written"].append(name)
    for d in sorted(target.iterdir()):
        f = d / "SKILL.md"
        if d.name in rows or d.is_symlink() or not d.is_dir() or f.is_symlink() or not f.is_file():
            continue
        if skill_mod.is_generated(f.read_text()) and [p.name for p in d.iterdir()] == ["SKILL.md"]:
            shutil.rmtree(d)
            done["removed"].append(d.name)
    return done


def _skill_path(row: dict) -> str:
    return f"/{row['project']}/{row['name']}/skill.md"


def cmd_skills(args, here, client):
    if args.action == "get":
        rows = [r for r in client.json("GET", "/skills.json") if r["name"] == args.name]
        if not rows:
            raise Failed(f"no skill called {args.name}")
        sys.stdout.write(client.text(_skill_path(rows[0])))
        return
    target = Path(args.dir).expanduser() if args.dir else SKILLS_DIR
    host = SKILLS_HOST or user_config().get("skills_host", "")
    if not args.dir and host and socket.gethostname() != host:
        raise Failed(f"pointer skills are installed on {host} only. Here, pull one by hand "
                     "with `colophon skills get <name>`, or pass --dir to write them somewhere")
    skills = client.json("GET", "/skills.json")
    done = sync_skills(skills, lambda r: client.text(_skill_path(r)), target)
    for key in ("written", "removed"):
        for n in done[key]:
            print(f"{key} {n}")
    for n in done["skipped"]:
        print(f"skipped {n}: a hand-written skill is in the way; remove it to let the pointer replace it",
              file=sys.stderr)
    print(f"{len(done['written'])} written, {len(done['unchanged'])} unchanged, "
          f"{len(done['removed'])} removed, {len(done['skipped'])} skipped, in {target}")


# -- wiring -------------------------------------------------------------------------


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="colophon", description="How to use each of your things.")
    p.add_argument("--server", help="server address (default: $COLOPHON_URL, then .colophon)")
    sub = p.add_subparsers(dest="command", required=True, metavar="command")

    def with_project(s):
        s.add_argument("--project", help="the project (default: the one .colophon names)")
        return s

    sub.add_parser("list", help="every project and its docs").set_defaults(fn=cmd_list)
    s = with_project(sub.add_parser("get", help="a project, or one doc, as markdown"))
    s.add_argument("ref", nargs="?", metavar="project[/doc]")
    s.set_defaults(fn=cmd_get)
    s = with_project(sub.add_parser("history", help="commits to a project, or one doc"))
    s.add_argument("ref", nargs="?", metavar="project[/doc]")
    s.set_defaults(fn=cmd_history)
    s = sub.add_parser("search", help="search projects and docs")
    s.add_argument("words", nargs="+")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("init", help="create or link a project for this folder; writes .colophon")
    s.add_argument("name", nargs="?")
    s.add_argument("--title")
    s.add_argument("--summary")
    s.add_argument("--kind", choices=profile_mod.KINDS,
                   help="what it is: a service runs and listens, a program is something you run")
    s.add_argument("--access", metavar="cli,api,...",
                   help=f"how it is reached, every one it has: {', '.join(profile_mod.ACCESS)}")
    s.add_argument("--roster", help="the roster service this project runs as (default: .roster, else none)")
    s.add_argument("--icon", help="an image (PNG, SVG, ICO...); the server makes it a square PNG")
    s.set_defaults(fn=cmd_init)

    s = with_project(sub.add_parser("set", help="set a project field, or a doc's with --doc; "
                                                "an empty value clears it"))
    s.add_argument("field")
    s.add_argument("value")
    s.add_argument("--doc", help="set this doc's field instead ([project/]doc)")
    s.set_defaults(fn=cmd_set)
    s = with_project(sub.add_parser("icon", help="replace the project's icon (PNG, SVG, ICO...)"))
    s.add_argument("file")
    s.set_defaults(fn=cmd_icon)

    s = with_project(sub.add_parser("add", help="add a doc; body from a file, stdin, or $EDITOR"))
    s.add_argument("doc", metavar="[project/]doc")
    s.add_argument("file", nargs="?")
    s.add_argument("--type", required=True, choices=list(doc_mod.TYPES))
    s.add_argument("--summary", required=True)
    s.add_argument("--title", help="default: the name with spaces for hyphens, capitalised")
    s.add_argument("--trigger", help="skills only: what it is and when to reach for it")
    s.set_defaults(fn=cmd_add)
    s = with_project(sub.add_parser("edit", help="open a doc in $EDITOR; save to push"))
    s.add_argument("doc", metavar="[project/]doc")
    s.set_defaults(fn=cmd_edit)
    s = with_project(sub.add_parser("push", help="replace a doc's body from a file, or stdin"))
    s.add_argument("doc", metavar="[project/]doc")
    s.add_argument("file", nargs="?")
    s.set_defaults(fn=cmd_push)
    s = with_project(sub.add_parser("rm", help="remove a doc"))
    s.add_argument("doc", metavar="[project/]doc")
    s.set_defaults(fn=cmd_rm)
    s = with_project(sub.add_parser("mv", help="move a doc to another project"))
    s.add_argument("doc", metavar="[project/]doc")
    s.add_argument("to", metavar="project")
    s.set_defaults(fn=cmd_mv)
    s = sub.add_parser("delete", help="remove a project that has no docs left")
    s.add_argument("project_name", metavar="project")
    s.set_defaults(fn=cmd_delete)
    sub.add_parser("stale", help="commits since each doc was written").set_defaults(fn=cmd_stale)

    s = sub.add_parser("skills", help="pointer skills")
    ssub = s.add_subparsers(dest="action", required=True, metavar="action")
    sy = ssub.add_parser("sync", help="write every pointer skill into ~/.claude/skills")
    sy.add_argument("--dir", help="write here instead (any machine)")
    g = ssub.add_parser("get", help="print one pointer skill")
    g.add_argument("name")
    s.set_defaults(fn=cmd_skills)
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    here = Here(Path.cwd())
    try:
        client = Client(server_for(args, here))
        args.fn(args, here, client)
    except (Failed, Invalid) as e:
        print(f"colophon: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    if args.command not in ("stale", "skills"):
        report_seen(client, here)
    return 0


if __name__ == "__main__":
    sys.exit(main())
