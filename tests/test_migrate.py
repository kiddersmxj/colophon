"""The move from one flat entry per thing to projects with docs: done by the
server at startup, in one commit, with each guide's history kept and every
pointer skill keeping its name and description."""

from __future__ import annotations

import base64
import subprocess

from fastapi.testclient import TestClient

from colophon.server import api, config
from conftest import GUIDE, FakeRoster, make_png, whois_none

DASH = chr(0x2014)  # one real trigger had these; it must survive as is

# The seven skills that moved in from hand-written skills, as the old layout
# held them. Their names and triggers must survive untouched.
SEVEN = {
    "jukebox": "Find songs and mixes in a music library. Use when asked: songs, stems.",
    "jukebox-artist": "Publish a service's own mixes into a music library. Use when publishing.",
    "assistant": "Ask a chat model through the assistant service. Use when a service needs ChatGPT.",
    "notify": "Watch for a notification on your phone or laptop. Use when waiting for one.",
    "console-agent": "Attach a service to the console as an agent. Use when a service should appear in the console.",
    "ledger-ward": "Make a service use Claude Code through the ledger. Use when a service runs `claude`.",
    "ledger-estate": f"Make a service use the GPU box {DASH} models, speech {DASH} through its queue. Use when.",
}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def old_layout(root):
    """Write the old layout by hand and commit it, as colophon-entries was."""
    git(root, "init", "-q", "-b", "main")
    for name, trigger in SEVEN.items():
        d = root / name
        d.mkdir()
        (d / "entry.toml").write_text(
            f'name = "{name}"\ntitle = "{name.title()}"\nsummary = "About {name}"\n'
            f'kind = "service"\nrepo = "~/devel/{name}"\n'
            f'trigger = "{trigger}"\nwritten_against = "abcdef1234"\nupdated = 2026-11-19\n')
        (d / "guide.md").write_text(GUIDE + f"\n{name} text.\n")
        (d / "icon.png").write_bytes(make_png())
    card = root / "lamp"
    card.mkdir()
    (card / "entry.toml").write_text('name = "lamp"\ntitle = "Lamp"\nsummary = "A lamp"\n'
                                     'kind = "device"\nupdated = 2026-11-19\n')
    (card / "icon.png").write_bytes(make_png())
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "old")


def app_on(tmp_path, store):
    cfg = config.Config(entries_dir=store.root, state_dir=store.state_dir,
                        public_url="https://colophon.test", assets_dir=tmp_path / "assets")
    return TestClient(api.create_app(cfg, store=store, roster=FakeRoster(), who=whois_none))


MIGRATE = "migrate: each entry becomes a project, its guide a doc"


def test_startup_migrates_once_keeping_text_names_and_triggers(tmp_path, store, remote):
    old_layout(store.root)
    client = app_on(tmp_path, store)

    assert git(store.root, "log", "--format=%s").splitlines() == [MIGRATE, "old"]
    assert git(store.root, "status", "--porcelain") == ""

    for name, trigger in SEVEN.items():
        assert not (store.root / name / "entry.toml").exists()
        d = store.get_doc(name, name)
        assert d.meta["type"] == "skill" and d.meta["trigger"] == trigger
        assert d.meta["written_against"] == "abcdef1234"
        assert d.body == GUIDE + f"\n{name} text.\n"
        assert "trigger" not in store.get(name).profile
        # the doc's history reaches back to the guide it was
        hist = client.get(f"/{name}/{name}/history").json()
        assert [h["subject"] for h in hist] == [MIGRATE, "old"]

    assert store.get("lamp").docs == []
    skills = {s["name"]: s["description"] for s in client.get("/skills.json").json()}
    assert skills == SEVEN

    # a second start finds nothing to do
    app_on(tmp_path, store)
    assert len(git(store.root, "log", "--format=%s").splitlines()) == 2


def test_regrouping_after_migration_keeps_pointer_skills(tmp_path, store):
    """The live regrouping: docs move under their projects, the emptied
    projects go, and every pointer skill keeps its name and description."""
    old_layout(store.root)
    client = app_on(tmp_path, store)
    before = {s["name"]: client.get(f"/{s['project']}/{s['name']}/skill.md").text
              for s in client.get("/skills.json").json()}

    for name in ("ledger", "console"):
        prof = {"name": name, "title": name.title(), "summary": "s", "kind": "service"}
        r = client.post("/", json={"profile": prof, "icon": base64.b64encode(make_png()).decode()})
        assert r.status_code == 201
    for doc, to in (("jukebox-artist", "jukebox"), ("ledger-ward", "ledger"),
                    ("ledger-estate", "ledger"), ("console-agent", "console")):
        assert client.post(f"/{doc}/{doc}/move", json={"to": to}).status_code == 200
        assert client.delete(f"/{doc}").status_code == 200

    groups = {p["name"]: [d["name"] for d in p["docs"]] for p in client.get("/index.json").json()}
    assert groups == {"ledger": ["ledger-estate", "ledger-ward"], "jukebox": ["jukebox", "jukebox-artist"],
                      "assistant": ["assistant"], "lamp": [], "notify": ["notify"],
                      "console": ["console-agent"]}
    after = client.get("/skills.json").json()
    assert {s["name"] for s in after} == set(SEVEN)
    for s in after:
        text = client.get(f"/{s['project']}/{s['name']}/skill.md").text
        # same name and description lines; only the address of the doc moved
        assert text.splitlines()[:4] == before[s["name"]].splitlines()[:4]
        assert f"https://colophon.test/{s['project']}/{s['name']}.md" in text


def test_migration_is_pushed(tmp_path, store, remote):
    old_layout(store.root)
    app_on(tmp_path, store)
    out = subprocess.run(["git", "--git-dir", str(remote), "log", "--format=%s", "main"],
                         capture_output=True, text=True).stdout.splitlines()
    assert out == [MIGRATE, "old"]
