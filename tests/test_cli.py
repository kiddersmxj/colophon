"""The CLI against the real app in process: init writes the marker, add and
push record the commit a doc was written against, skills sync writes pointer
skills and leaves hand-written ones alone."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from colophon import cli
from colophon.core import marker
from colophon.core import skill as skill_mod
from conftest import GUIDE, make_png


@pytest.fixture
def run(app_client, monkeypatch, tmp_path):
    """Run the CLI with its HTTP going to the in-process app, and git blind to
    this machine's own config (its global excludes would hide .colophon)."""
    (tmp_path / "gitconfig").write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))

    def call(self, method, path, body=None, ctype=None, timeout=None):
        headers = {"Content-Type": ctype} if ctype else {}
        r = app_client.request(method, path, content=body, headers=headers)
        return r.status_code, r.content

    monkeypatch.setattr(cli.Client, "call", call)
    monkeypatch.setattr(cli, "tty", lambda: False)

    def go(*argv, cwd: Path):
        monkeypatch.chdir(cwd)
        return cli.main(["--server", "https://colophon.test", *argv])

    return go


@pytest.fixture
def project(tmp_path) -> Path:
    p = tmp_path / "home" / "devel" / "jukebox"
    p.mkdir(parents=True)
    g = ["git", "-C", str(p)]
    subprocess.run([*g, "init", "-q", "-b", "main"], check=True)
    subprocess.run([*g, "remote", "add", "origin", "git@github.com:you/jukebox.git"], check=True)
    (p / "README").write_text("x")
    subprocess.run([*g, "add", "README"], check=True)
    subprocess.run([*g, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one"], check=True)
    (p / "icon.png").write_bytes(make_png(128))
    return p


def commit(p: Path, msg: str) -> None:
    subprocess.run(["git", "-C", str(p), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "--allow-empty", "-m", msg], check=True)


TRIGGER = "Find songs and mixes. Use when asked: songs, stems."


def init(run, project):
    args = ["init", "--title", "Jukebox", "--summary", "Music library", "--kind", "service",
            "--icon", "icon.png"]
    return run(*args, cwd=project)


def add(run, project, doc="jukebox", type="skill", trigger=TRIGGER, file="g.md"):
    (project / "g.md").write_text(GUIDE)
    args = ["add", doc, file, "--type", type, "--summary", f"{doc} doc"]
    if trigger:
        args += ["--trigger", trigger]
    return run(*args, cwd=project)


def test_init_creates_project_and_writes_marker(run, project, store, capsys):
    rc = init(run, project)
    assert rc == 0, capsys.readouterr().err
    assert (project / ".colophon").read_text() == "project: jukebox\nserver: https://colophon.test\n"
    prof = store.get("jukebox").profile
    assert prof["remote"] == "git@github.com:you/jukebox.git"
    # A roster service with the same name is not taken to be this project.
    assert "roster" not in prof and "machine" not in prof
    err = capsys.readouterr().err
    assert "pass --roster jukebox" in err
    # git does not ignore .colophon in this scratch repo, so the CLI says so
    assert "global excludes" in err


def test_init_with_roster_takes_machine_from_roster(run, project, store, capsys):
    rc = run("init", "--title", "Jukebox", "--summary", "Music library", "--kind", "service",
             "--roster", "jukebox", "--icon", "icon.png", cwd=project)
    assert rc == 0, capsys.readouterr().err
    prof = store.get("jukebox").profile
    assert prof["roster"] == "jukebox" and prof["machine"] == "server-1"


def test_init_quiet_when_marker_ignored(run, project, tmp_path, capsys):
    (tmp_path / "excludes").write_text(".colophon\n")
    (tmp_path / "gitconfig").write_text(f"[core]\n\texcludesFile = {tmp_path / 'excludes'}\n")
    init(run, project)
    assert "global excludes" not in capsys.readouterr().err
    assert "colophon" not in (project / ".gitignore").read_text() if (project / ".gitignore").exists() else True


def test_init_without_icon_is_refused(run, tmp_path, store, capsys):
    p = tmp_path / "gadget"
    p.mkdir()
    rc = run("init", "--title", "Gadget", "--summary", "s", "--kind", "device", cwd=p)
    assert rc == 1
    assert "icon is required" in capsys.readouterr().err
    assert not (p / ".colophon").exists() and not store.exists("gadget")


def test_init_links_existing_project(run, project, tmp_path):
    init(run, project)
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert run("init", "jukebox", cwd=other) == 0
    assert marker.loads((other / ".colophon").read_text())["project"] == "jukebox"


def test_old_marker_still_works(run, project, store, capsys):
    init(run, project)
    (project / ".colophon").write_text("entry: jukebox\nserver: https://colophon.test\n")
    capsys.readouterr()
    assert run("get", cwd=project) == 0
    assert capsys.readouterr().out.startswith("# Jukebox (jukebox)")


def test_add_records_written_against_and_stale_counts(run, project, store, capsys):
    init(run, project)
    assert add(run, project) == 0
    head = subprocess.run(["git", "-C", str(project), "rev-parse", "HEAD"], capture_output=True,
                          text=True).stdout.strip()
    assert store.get_doc("jukebox", "jukebox").meta["written_against"] == head[:12]
    commit(project, "two")
    commit(project, "three")
    capsys.readouterr()
    assert run("stale", cwd=project) == 0
    assert "jukebox/jukebox: 2 commits since it was written" in capsys.readouterr().out
    assert store.seen()["jukebox"]["behind"] == {"jukebox": 2}


def test_add_skill_without_trigger_refused(run, project, store, capsys):
    init(run, project)
    assert add(run, project, trigger=None) == 1
    assert "--trigger" in capsys.readouterr().err
    assert add(run, project, doc="setup", type="guide", trigger=None) == 0
    assert [d.meta["type"] for d in store.get("jukebox").docs] == ["guide"]


def test_push_updates_body_and_bad_body_refused(run, project, store, capsys):
    init(run, project)
    add(run, project)
    (project / "g2.md").write_text(GUIDE + "\nMore.\n")
    assert run("push", "jukebox", "g2.md", cwd=project) == 0
    assert store.get_doc("jukebox", "jukebox").body.endswith("More.\n")
    (project / "bad.md").write_text("# Title\n\n## What it is\n\nx\n")
    capsys.readouterr()
    assert run("push", "jukebox", "bad.md", cwd=project) == 1
    assert "the title comes from the doc" in capsys.readouterr().err


def test_set_get_and_doc_fields(run, project, capsys):
    init(run, project)
    add(run, project, doc="jukebox-artist")
    assert run("set", "summary", "A better summary", cwd=project) == 0
    assert run("set", "summary", "Publish mixes", "--doc", "jukebox-artist", cwd=project) == 0
    assert run("set", "trigger", "x", cwd=project) == 1  # a doc field, without --doc
    capsys.readouterr()
    assert run("get", cwd=project) == 0
    out = capsys.readouterr().out
    assert "A better summary" in out
    assert "- jukebox-artist (skill): Publish mixes https://colophon.test/jukebox/jukebox-artist.md" in out
    assert run("get", "jukebox/jukebox-artist", cwd=project) == 0
    assert "## Quick start" in capsys.readouterr().out
    assert run("set", "kind", "spaceship", cwd=project) == 1


def test_mv_and_rm(run, project, tmp_path, store):
    init(run, project)
    add(run, project, doc="jukebox-artist")
    other = tmp_path / "artist"
    other.mkdir()
    (other / "icon.png").write_bytes(make_png(64))
    run("init", "artist", "--title", "A", "--summary", "s", "--kind", "program", "--icon", "icon.png", cwd=other)
    assert run("mv", "jukebox-artist", "artist", cwd=project) == 0
    assert [d.name for d in store.get("artist").docs] == ["jukebox-artist"]
    assert run("delete", "artist", cwd=project) == 1  # it still has a doc
    assert run("rm", "artist/jukebox-artist", cwd=project) == 0
    assert store.get("artist").docs == []
    assert run("delete", "artist", cwd=project) == 0
    assert not store.exists("artist")


def test_skills_sync_writes_pointers_and_spares_hand_written(run, project, tmp_path, capsys):
    init(run, project)
    add(run, project)
    add(run, project, doc="setup", type="guide", trigger=None)
    skills = tmp_path / "skills"
    (skills / "dmm").mkdir(parents=True)
    (skills / "dmm" / "SKILL.md").write_text("---\nname: dmm\n---\nhand written\n")
    (skills / "gone").mkdir()
    (skills / "gone" / "SKILL.md").write_text(skill_mod.pointer("gone", "x", "Gone", "Use when.", "x"))

    assert run("skills", "sync", "--dir", str(skills), cwd=tmp_path) == 0
    text = (skills / "jukebox" / "SKILL.md").read_text()
    assert text.startswith(f'---\nname: jukebox\ndescription: "{TRIGGER}"\n---\n')
    assert "curl -s https://colophon.test/jukebox/jukebox.md" in text
    assert not (skills / "setup").exists()
    assert (skills / "dmm" / "SKILL.md").read_text().endswith("hand written\n")
    assert not (skills / "gone").exists()

    capsys.readouterr()
    run("skills", "sync", "--dir", str(skills), cwd=tmp_path)
    assert "1 unchanged" in capsys.readouterr().out
    assert run("skills", "get", "jukebox", cwd=tmp_path) == 0
    assert "name: jukebox" in capsys.readouterr().out


def test_skills_sync_skips_symlinked_and_hand_written_of_same_name(tmp_path):
    target = tmp_path / "skills"
    real = tmp_path / "dotfiles" / "jukebox"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text("hand written\n")
    target.mkdir()
    (target / "jukebox").symlink_to(real)
    done = cli.sync_skills([{"name": "jukebox", "project": "jukebox"}], lambda r: "new", target)
    assert done["skipped"] == ["jukebox"]
    assert (real / "SKILL.md").read_text() == "hand written\n"


def test_skills_sync_refuses_off_host_without_dir(run, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "SKILLS_HOST", "workstation")
    monkeypatch.setattr(cli.socket, "gethostname", lambda: "server")
    assert run("skills", "sync", cwd=tmp_path) == 1
    assert "skills get" in capsys.readouterr().err


def test_skills_sync_never_touches_the_real_skills_dir(run, tmp_path):
    # The autouse fixture points SKILLS_DIR into tmp_path for every test.
    assert str(cli.SKILLS_DIR).startswith(str(tmp_path.parent))


def test_skills_get_unknown(run, project, capsys):
    init(run, project)
    add(run, project, doc="setup", type="guide", trigger=None)
    assert run("skills", "get", "setup", cwd=project) == 1
    assert "no skill" in capsys.readouterr().err


def test_history_of_project_and_doc(run, project, capsys):
    init(run, project)
    add(run, project, doc="jukebox-artist")
    capsys.readouterr()
    assert run("history", cwd=project) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0].endswith("jukebox/jukebox-artist: create skill") and len(out) == 2
    assert run("history", "jukebox/jukebox-artist", cwd=project) == 0
    assert capsys.readouterr().out.strip().endswith("jukebox/jukebox-artist: create skill")
    assert run("history", "jukebox/nope", cwd=project) == 1
    assert "no doc jukebox/nope" in capsys.readouterr().err


def test_add_from_folder_with_no_commits_says_so(run, tmp_path, store, capsys):
    p = tmp_path / "fresh"
    p.mkdir()
    subprocess.run(["git", "-C", str(p), "init", "-q", "-b", "main"], check=True)
    (p / "icon.png").write_bytes(make_png(64))
    assert run("init", "--title", "Fresh", "--summary", "s", "--kind", "program", "--icon", "icon.png",
               cwd=p) == 0
    err = capsys.readouterr().err
    assert "no git remote here" in err and "~" not in err.split("(")[0]
    assert add(run, p, doc="setup", type="guide", trigger=None) == 0
    assert "no commits" in capsys.readouterr().err
    assert "written_against" not in store.get_doc("fresh", "setup").meta


def test_add_without_title_gets_a_readable_one(run, project, store):
    init(run, project)
    add(run, project, doc="jukebox-artist")
    assert store.get_doc("jukebox", "jukebox-artist").meta["title"] == "Jukebox artist"


def test_init_and_set_access(run, project, store, capsys):
    args = ["init", "--title", "Jukebox", "--summary", "Music", "--kind", "service",
            "--icon", "icon.png"]
    assert run(*args, "--access", "ftp", cwd=project) == 1
    assert "ftp" in capsys.readouterr().err and not store.exists("jukebox")
    assert run(*args, "--access", "api,cli", cwd=project) == 0
    assert store.get("jukebox").profile["access"] == ["cli", "api"]
    assert run("set", "access", "cli,api,web", cwd=project) == 0
    assert store.get("jukebox").profile["access"] == ["cli", "api", "web"]
    assert run("set", "access", "", cwd=project) == 0
    assert "access" not in store.get("jukebox").profile


def test_init_asks_for_access(run, project, store, monkeypatch):
    monkeypatch.setattr(cli, "tty", lambda: True)
    answers = iter(["sdk", "cli, mcp"])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    assert run("init", "--title", "Jukebox", "--summary", "Music", "--kind", "service",
               "--icon", "icon.png", cwd=project) == 0
    assert store.get("jukebox").profile["access"] == ["cli", "mcp"]


def test_server_and_skills_host_from_the_user_config(tmp_path, monkeypatch):
    (tmp_path / "colophon.conf").write_text("# mine\nserver: https://docs.example.lan/\nskills_host: laptop\n")
    args = cli.parser().parse_args(["list"])
    assert cli.server_for(args, cli.Here(tmp_path)) == "https://docs.example.lan"
    assert cli.user_config()["skills_host"] == "laptop"


def test_no_server_anywhere_says_so(tmp_path):
    args = cli.parser().parse_args(["list"])
    with pytest.raises(cli.Failed, match="no server"):
        cli.server_for(args, cli.Here(tmp_path))
