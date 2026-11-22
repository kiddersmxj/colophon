"""The write path end to end over HTTP: each write is one commit, authored
by the caller, pushed to the (scratch) remote. Projects hold docs."""

from __future__ import annotations

import base64
import subprocess

from conftest import GUIDE, TS_HEADERS, make_png

TRIGGER = "Find songs and mixes. Use when asked: songs."


def remote_log(remote, path=""):
    args = ["git", "--git-dir", str(remote), "log", "--format=%an <%ae>|%s|%(trailers:key=Via,valueonly)", "main"]
    if path:
        args += ["--", path]
    return [line for line in subprocess.run(args, capture_output=True, text=True).stdout.splitlines() if line]


def create(client, name="jukebox", **extra):
    prof = {"name": name, "title": name.title(), "summary": "A thing", "kind": "service", **extra}
    return client.post("/", json={"profile": prof, "icon": base64.b64encode(make_png()).decode()},
                       headers=TS_HEADERS)


def add_doc(client, project="jukebox", name="jukebox", type="skill", body=GUIDE, query="", **extra):
    meta = {"name": name, "type": type, "summary": f"{name} doc", **extra}
    if type == "skill":
        meta.setdefault("trigger", TRIGGER)
    return client.post(f"/{project}/docs{query}", json={"doc": meta, "body": body}, headers=TS_HEADERS)


def test_create_commits_and_pushes_with_caller(app_client, remote, store):
    r = create(app_client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["pushed"] is True and body["changed"] is True
    assert remote_log(remote) == ["Alex Example <you@example.com>|jukebox: create|100.101.102.103"]
    assert (store.root / "jukebox" / "icon.png").is_file()
    assert (store.root / "jukebox" / "project.toml").is_file()
    assert store.get("jukebox").docs == []


def test_create_without_icon_refused(app_client, store):
    prof = {"name": "thing", "title": "Thing", "summary": "s", "kind": "program"}
    r = app_client.post("/", json={"profile": prof})
    assert r.status_code == 422
    assert "icon is required" in r.json()["error"]
    assert not store.exists("thing")


def test_create_takes_roster_icon_and_machine(app_client, store):
    prof = {"name": "jukebox", "title": "Jukebox", "summary": "s", "kind": "service", "roster": "jukebox"}
    r = app_client.post("/", json={"profile": prof})
    assert r.status_code == 201, r.text
    assert store.get("jukebox").profile["machine"] == "server-1"


def test_create_twice_conflicts(app_client):
    assert create(app_client).status_code == 201
    assert create(app_client).status_code == 409


def test_docs_of_several_types_under_one_project(app_client, remote, store):
    create(app_client)
    assert add_doc(app_client, query="?written_against=a1b2c3d").status_code == 201
    assert add_doc(app_client, name="jukebox-artist").status_code == 201
    assert add_doc(app_client, name="setup", type="guide").status_code == 201
    assert [d.name for d in store.get("jukebox").docs] == ["jukebox", "jukebox-artist", "setup"]
    assert [line.split("|")[1] for line in remote_log(remote)] == [
        "jukebox/setup: create guide", "jukebox/jukebox-artist: create skill",
        "jukebox/jukebox: create skill", "jukebox: create"]
    j = app_client.get("/jukebox/jukebox.json").json()
    assert j["doc"]["written_against"] == "a1b2c3d" and j["seen"]["behind"] == 0
    assert app_client.get("/jukebox/setup/skill.md").status_code == 404


def test_skill_needs_trigger_and_body_is_checked(app_client, remote):
    create(app_client)
    before = remote_log(remote)
    r = add_doc(app_client, trigger="")
    assert r.status_code == 422 and "trigger" in r.json()["error"]
    r = add_doc(app_client, body="## Usage\n\nstuff\n")
    assert r.status_code == 422 and "not a section" in r.json()["error"]
    assert remote_log(remote) == before


def test_skill_names_are_unique_across_projects(app_client):
    create(app_client)
    create(app_client, "ledger")
    assert add_doc(app_client, name="ward").status_code == 201
    r = add_doc(app_client, project="ledger", name="ward")
    assert r.status_code == 409 and "unique" in r.json()["error"]
    assert add_doc(app_client, project="ledger", name="ward", type="guide").status_code == 201


def test_reserved_doc_names_refused(app_client):
    create(app_client)
    assert add_doc(app_client, name="icon").status_code == 422


def test_body_and_meta_updates(app_client, remote, store):
    create(app_client)
    add_doc(app_client)
    r = app_client.put("/jukebox/jukebox?written_against=abcdef1", content=GUIDE + "\nMore.\n")
    assert r.status_code == 200 and r.json()["changed"], r.text
    r = app_client.put("/jukebox/jukebox/meta", json={"summary": "Search and fetch"})
    assert r.status_code == 200 and r.json()["changed"]
    r = app_client.put("/jukebox/jukebox/meta", json={"summary": "Search and fetch"})
    assert r.json()["changed"] is False
    subjects = [line.split("|")[1] for line in remote_log(remote)][:2]
    assert subjects == ["jukebox/jukebox: summary", "jukebox/jukebox: body"]
    d = store.get_doc("jukebox", "jukebox")
    assert d.meta["written_against"] == "abcdef1" and d.body.endswith("More.\n")


def test_skill_becomes_guide_and_loses_trigger(app_client, store):
    create(app_client)
    add_doc(app_client)
    r = app_client.put("/jukebox/jukebox/meta", json={"type": "guide", "trigger": TRIGGER})
    assert r.status_code == 200, r.text
    assert "trigger" not in store.get_doc("jukebox", "jukebox").meta
    assert app_client.get("/skills.json").json() == []


def test_delete_doc_and_project(app_client, store):
    create(app_client)
    add_doc(app_client)
    r = app_client.delete("/jukebox")
    assert r.status_code == 409 and "still has docs" in r.json()["error"]
    assert app_client.delete("/jukebox/jukebox").status_code == 200
    assert app_client.get("/jukebox/jukebox.md").status_code == 404
    assert app_client.delete("/jukebox").status_code == 200
    assert not store.exists("jukebox")


def test_move_doc_keeps_its_history(app_client, store):
    create(app_client, "jukebox-artist")
    create(app_client)
    add_doc(app_client, project="jukebox-artist", name="jukebox-artist")
    app_client.put("/jukebox-artist/jukebox-artist", content=GUIDE + "\nv2\n")
    r = app_client.post("/jukebox-artist/jukebox-artist/move", json={"to": "jukebox"})
    assert r.status_code == 200, r.text
    assert [d.name for d in store.get("jukebox").docs] == ["jukebox-artist"]
    assert store.get("jukebox-artist").docs == []
    hist = [h["subject"] for h in app_client.get("/jukebox/jukebox-artist/history").json()]
    assert hist == ["jukebox/jukebox-artist: moved from jukebox-artist",
                    "jukebox-artist/jukebox-artist: body", "jukebox-artist/jukebox-artist: create skill"]


def test_put_icon_converts_and_validates(app_client):
    create(app_client)
    assert app_client.put("/jukebox/icon", content=b"GIF89a").status_code == 422
    r = app_client.put("/jukebox/icon", content=make_png(256))
    assert r.status_code == 200 and r.json()["changed"]
    assert app_client.get("/jukebox/icon").content == make_png(256)


def test_local_caller_without_tailnet_headers(app_client, remote):
    create(app_client)
    app_client.put("/jukebox/profile", json={"summary": "Changed"})
    author, subject, via = remote_log(remote)[0].split("|")
    assert "@" in author and subject == "jukebox: profile summary" and via


def test_reads(app_client):
    create(app_client, roster="jukebox")
    add_doc(app_client, summary="Search and fetch songs")
    add_doc(app_client, name="jukebox-artist", summary="Publish mixes")
    add_doc(app_client, name="setup", type="guide", summary="Set it up")

    md = app_client.get("/jukebox.md").text
    assert md.startswith("# Jukebox (jukebox)")
    assert "- address: https://jukebox.example.lan" in md
    assert "- jukebox-artist (skill): Publish mixes https://colophon.test/jukebox/jukebox-artist.md" in md
    assert "- setup (guide): Set it up https://colophon.test/jukebox/setup.md" in md
    assert "## Quick start" not in md

    doc = app_client.get("/jukebox/jukebox-artist.md").text
    assert doc.startswith("# Jukebox artist (jukebox/jukebox-artist)")  # title from the name
    assert "- project: Jukebox, https://colophon.test/jukebox.md" in doc and "## Quick start" in doc

    idx = app_client.get("/index.md").text
    assert "- jukebox (service): A thing" in idx
    assert "  - setup (guide): Set it up https://colophon.test/jukebox/setup.md" in idx
    row = app_client.get("/index.json").json()[0]
    assert row["machine"] == "server-1"
    assert [(d["name"], d["type"]) for d in row["docs"]] == [
        ("jukebox", "skill"), ("jukebox-artist", "skill"), ("setup", "guide")]
    pj = app_client.get("/jukebox.json").json()
    assert [d["name"] for d in pj["docs"]] == ["jukebox", "jukebox-artist", "setup"]

    skills = app_client.get("/skills.json").json()
    assert [(s["name"], s["project"]) for s in skills] == [("jukebox", "jukebox"), ("jukebox-artist", "jukebox")]
    skill = app_client.get("/jukebox/jukebox-artist/skill.md").text
    assert "name: jukebox-artist\n" in skill
    assert f'description: "{TRIGGER}"' in skill
    assert "curl -s https://colophon.test/jukebox/jukebox-artist.md" in skill

    # an old pointer skill fetched /<skill>.md; that still finds the doc
    assert "## Quick start" in app_client.get("/jukebox-artist.md").text

    assert "jukebox" in app_client.get("/search?q=music library").text
    assert "jukebox" in app_client.get("/search?q=publish mixes").text
    assert app_client.get("/search.json?q=nothing-like-this").json() == []

    page = app_client.get("/jukebox")
    assert page.status_code == 200 and "server-1" in page.text
    assert 'href="/jukebox/jukebox-artist"' in page.text and "Publish mixes" in page.text
    assert "<h2>Quick start</h2>" not in page.text
    dpage = app_client.get("/jukebox/jukebox-artist")
    assert dpage.status_code == 200 and "<h2>Quick start</h2>" in dpage.text
    home = app_client.get("/")
    assert home.status_code == 200 and "/jukebox/icon" in home.text and ">skill<" in home.text
    assert app_client.get("/nope.md").status_code == 404
    assert app_client.get("/jukebox/nope.md").status_code == 404
    assert app_client.get("/Bad Name").status_code == 404


def test_raw_html_in_doc_is_not_rendered(app_client):
    create(app_client)
    add_doc(app_client, body="## What it is\n\n<script>alert(1)</script>\n")
    assert "<script>alert(1)" not in app_client.get("/jukebox/jukebox").text


def test_roster_down_still_reads(tmp_path, store):
    from fastapi.testclient import TestClient

    from colophon.server import api, config
    from conftest import FakeRoster, whois_none

    cfg = config.Config(entries_dir=store.root, state_dir=store.state_dir, assets_dir=tmp_path)
    client = TestClient(api.create_app(cfg, store=store, roster=FakeRoster(down=True), who=whois_none))
    create(client, roster="jukebox")
    md = client.get("/jukebox.md").text
    assert "roster: jukebox (roster did not answer)" in md
    assert client.get("/jukebox").status_code == 200
    assert client.get("/_roster/jukebox").json()["available"] is False


def test_seen_is_recorded_outside_git(app_client, remote):
    create(app_client)
    add_doc(app_client, query="?written_against=abcdef1")
    r = app_client.post("/jukebox/seen", json={"commit": "abcdef2", "behind": {"jukebox": 40}})
    assert r.status_code == 200
    assert app_client.get("/jukebox/jukebox.json").json()["seen"]["behind"] == 40
    assert "40 commits behind" in app_client.get("/jukebox/jukebox").text
    assert len(remote_log(remote)) == 2
    assert app_client.post("/jukebox/seen", json={"commit": "nope"}).status_code == 422
    assert app_client.post("/jukebox/seen", json={"commit": "abcdef2", "behind": 3}).status_code == 422


def test_placeholder_brand_until_assets_land(app_client, tmp_path):
    assert app_client.get("/_brand/logo").headers["content-type"].startswith("image/svg")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "logo.png").write_bytes(make_png())
    assert app_client.get("/_brand/logo").headers["content-type"] == "image/png"


def test_browser_profile_form_with_nothing_changed_makes_no_commit(app_client, remote):
    create(app_client)
    form = {"title": "Jukebox", "summary": "A thing", "kind": "service", "repo": "",
            "remote": "", "roster": "", "machine": ""}
    r = app_client.put("/jukebox/profile", json=form)
    assert r.status_code == 200 and r.json()["changed"] is False
    assert len(remote_log(remote)) == 1


def test_history_as_markdown(app_client):
    create(app_client)
    add_doc(app_client)
    r = app_client.get("/jukebox/history.md")
    assert r.status_code == 200 and r.text.startswith("# History: Jukebox (jukebox)\n")
    assert "jukebox/jukebox: create skill" in r.text
    r = app_client.get("/jukebox/jukebox/history.md")
    assert r.status_code == 200 and "jukebox/jukebox: create skill" in r.text
    assert app_client.get("/jukebox/nope/history.md").status_code == 404


def test_tag_only_from_roster(tmp_path, store):
    """The tag is shown only when roster states it; it is never built from the name."""
    from fastapi.testclient import TestClient

    from colophon.server import api, config
    from conftest import ROSTER_ROWS, FakeRoster, whois_none

    cfg = config.Config(entries_dir=store.root, state_dir=store.state_dir, assets_dir=tmp_path)
    cases = ((ROSTER_ROWS, "- roster: jukebox, sensitive\n"),
             ([{**ROSTER_ROWS[0], "tag": "tag:music"}], "- roster: jukebox, tag:music, sensitive\n"))
    for i, (rows, want) in enumerate(cases):
        client = TestClient(api.create_app(cfg, store=store, roster=FakeRoster(rows), who=whois_none))
        if i == 0:
            create(client, roster="jukebox")
        md = client.get("/jukebox.md").text
        assert want in md
        assert "tag:svc-" not in md


def test_access_points_on_every_read(app_client, store):
    assert create(app_client, access=["api", "cli"]).status_code == 201
    assert create(app_client, name="plain").status_code == 201
    assert store.get("jukebox").profile["access"] == ["cli", "api"]
    assert 'access  = ["cli", "api"]' in (store.root / "jukebox" / "project.toml").read_text()

    assert "- access: cli, api" in app_client.get("/jukebox.md").text
    assert "access" not in app_client.get("/plain.md").text
    assert app_client.get("/jukebox.json").json()["profile"]["access"] == ["cli", "api"]
    rows = {r["name"]: r for r in app_client.get("/index.json").json()}
    assert rows["jukebox"]["access"] == ["cli", "api"] and rows["plain"]["access"] is None
    idx = app_client.get("/index.md").text
    assert "- jukebox (service; cli, api): A thing" in idx and "- plain (service): A thing" in idx
    assert [r["name"] for r in app_client.get("/search.json?q=api").json()] == ["jukebox"]

    home = app_client.get("/").text
    assert 'data-access="cli api"' in home and 'data-access="api"' in home
    assert '<span class="badge badge-access">CLI</span>' in home
    assert 'data-access="mcp"' not in home  # no filter for an access point nobody has
    page = app_client.get("/jukebox").text
    assert '<span class="badge badge-access">API</span>' in page
    assert 'value="mcp" >' in page and 'value="cli" checked>' in page


def test_access_set_and_cleared_through_profile(app_client, store):
    create(app_client)
    r = app_client.put("/jukebox/profile", json={"access": "web,mcp"}, headers=TS_HEADERS)
    assert r.status_code == 200, r.text
    assert store.get("jukebox").profile["access"] == ["mcp", "web"]
    r = app_client.put("/jukebox/profile", json={"access": ["ftp"]}, headers=TS_HEADERS)
    assert r.status_code == 422 and "ftp" in r.json()["error"]
    app_client.put("/jukebox/profile", json={"access": []}, headers=TS_HEADERS)
    assert "access" not in store.get("jukebox").profile


def test_old_kind_still_reads_and_must_change_on_write(app_client, store):
    """api and cli were kinds until 2026-11-19. A profile still storing one
    reads and shows as stored; a write must pick a listed kind."""
    assert create(app_client).status_code == 201
    toml = store.root / "jukebox" / "project.toml"
    text = toml.read_text()
    assert '"service"' in text
    toml.write_text(text.replace('"service"', '"api"'))
    assert "(api)" in app_client.get("/index.md").text
    assert app_client.get("/index.json").json()[0]["kind"] == "api"
    assert app_client.get("/jukebox.json").json()["profile"]["kind"] == "api"
    assert "jukebox" in app_client.get("/jukebox.md").text
    page = app_client.get("/jukebox")
    assert page.status_code == 200
    assert '<option value="" selected>api (choose a kind)</option>' in page.text
    assert app_client.get("/").status_code == 200
    r = app_client.put("/jukebox/profile", json={"summary": "new"}, headers=TS_HEADERS)
    assert r.status_code == 422 and "kind 'api' is not one of" in r.json()["error"]
    r = app_client.put("/jukebox/profile", json={"kind": "program"}, headers=TS_HEADERS)
    assert r.status_code == 200, r.text
    assert store.get("jukebox").profile["kind"] == "program"
