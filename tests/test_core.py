"""Validation of profiles, guides and icons; the marker file; pointer skills."""

from __future__ import annotations

import datetime as dt

import pytest

from colophon.core import Invalid, doc, guide, icon, marker, profile, skill
from conftest import GUIDE, make_png

BASE = {"name": "jukebox", "title": "Jukebox", "summary": "Music", "kind": "service"}


# -- profile ------------------------------------------------------------------


def test_profile_round_trips_in_field_order():
    p = profile.validate({**BASE, "summary": 'Say "hi"\\ok',
                          "updated": "2026-11-19"})
    text = profile.dumps(p)
    assert text.splitlines()[0].startswith("name ")
    assert text.splitlines()[-1] == "updated = 2026-11-19"
    back = profile.loads(text)
    assert back == {**p, "updated": dt.date(2026, 11, 19)}


def test_private_is_not_a_field():
    with pytest.raises(Invalid, match="unknown field 'private'"):
        profile.validate({**BASE, "private": True})


@pytest.mark.parametrize("change, message", [
    ({"kind": "toaster"}, "not one of"),
    ({"kind": "api"}, "not one of"),
    ({"kind": "cli"}, "not one of"),
    ({"name": "Jukebox"}, "lowercase"),
    ({"name": "index"}, "reserved"),
    ({"summary": "two\nlines"}, "one line"),
    ({"summary": "x" * 201}, "over 200"),
    ({"colour": "blue"}, "unknown field"),
    ({"trigger": "Use when."}, "unknown field"),
    ({"title": None}, "title is required"),
])
def test_profile_refusals(change, message):
    with pytest.raises(Invalid, match=message):
        profile.validate({**BASE, **change})


def test_names_of_fleet_services_are_not_reserved():
    for name in ("roster", "status", "lights", "static", "api"):
        assert profile.validate({**BASE, "name": name})["name"] == name


def test_profile_reports_every_problem_at_once():
    with pytest.raises(Invalid) as e:
        profile.validate({"name": "X", "kind": "toaster"})
    msg = str(e.value)
    assert "lowercase" in msg and "toaster" in msg and "title is required" in msg


def test_merge_clears_optional_and_guards_required():
    cur = profile.validate({**BASE, "repo": "~/devel/jukebox"})
    assert "repo" not in profile.merge(cur, {"repo": ""})
    with pytest.raises(Invalid, match="cannot be cleared"):
        profile.merge(cur, {"summary": None})
    with pytest.raises(Invalid, match="cannot be set"):
        profile.merge(cur, {"name": "other"})


# -- guide ----------------------------------------------------------------------


def test_good_guide_passes_and_code_fences_are_ignored():
    assert guide.validate(GUIDE).startswith("## What it is")


def test_template_is_a_valid_guide():
    guide.validate(guide.TEMPLATE)


@pytest.mark.parametrize("text, message", [
    ("## Where\n\nx\n", "'## What it is' is required"),
    ("intro\n\n## What it is\n\nx\n", "text before the first section"),
    ("# Jukebox\n\n## What it is\n", "title comes from the doc"),
    ("## What it is\n\n## Usage\n", "not a section"),
    ("## What it is\n\n## Auth\n\n## Where\n", "comes before"),
    ("## What it is\n\n## Auth\n\n## Auth\n", "appears twice"),
    ("## What it is\n\n" + "x" * 70000, "over 64 KB"),
])
def test_guide_refusals(text, message):
    with pytest.raises(Invalid, match=message):
        guide.validate(text)


def test_subsections_are_free():
    guide.validate("## What it is\n\nx\n\n## Reference\n\n### Endpoints\n\n### Fields\n")


# -- icon -------------------------------------------------------------------------


def test_icon_rules():
    assert icon.validate(make_png(64)) == make_png(64)
    with pytest.raises(Invalid, match="required"):
        icon.validate(b"")
    with pytest.raises(Invalid, match="PNG"):
        icon.validate(b"<svg/>" * 10)
    with pytest.raises(Invalid, match="square"):
        icon.validate(make_png(64, 32))
    with pytest.raises(Invalid, match="32 to 2048"):
        icon.validate(make_png(16))


# -- marker -------------------------------------------------------------------------


def test_marker_written_and_found_from_below(tmp_path):
    path = marker.write(tmp_path, "jukebox", "https://colophon.example.lan/")
    assert path.read_text() == "project: jukebox\nserver: https://colophon.example.lan\n"
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    found_path, data = marker.find(deep)
    assert found_path == path
    assert data == {"project": "jukebox", "server": "https://colophon.example.lan"}


def test_old_marker_still_reads():
    assert marker.loads("entry: ledger-ward\nserver: x\n")["project"] == "ledger-ward"


def test_marker_refuses_bad_content(tmp_path):
    with pytest.raises(Invalid):
        marker.loads("server: x\n")
    with pytest.raises(Invalid):
        marker.dumps("Not A Name", "x")
    assert marker.find(tmp_path) is None


# -- pointer skills -------------------------------------------------------------------


def test_pointer_skill_plain_trigger_stays_plain():
    text = skill.pointer("notify", "notify", "Notify", "Watch for a notification on your phone. Use when waiting.",
                         "https://colophon.example.lan/")
    lines = text.splitlines()
    assert lines[:4] == ["---", "name: notify",
                         "description: Watch for a notification on your phone. Use when waiting.", "---"]
    assert skill.is_generated(text)
    assert "curl -s https://colophon.example.lan/notify/notify.md" in text


@pytest.mark.parametrize("trigger", [
    "Things: with a colon. Use when asked.",
    "- starts like a list",
    "has a # comment marker",
    '"quoted" start',
    "ends with a colon:",
])
def test_pointer_skill_quotes_yaml_hazards(trigger):
    import json

    line = skill.pointer("x", "p", "X", trigger, "s").splitlines()[2]
    value = line.removeprefix("description: ")
    assert value.startswith('"') and json.loads(value) == trigger


def test_hand_written_skill_is_not_generated():
    assert not skill.is_generated("---\nname: dmm\n---\n# dmm\n")


# -- docs ---------------------------------------------------------------------------

DOC = {"name": "jukebox-artist", "type": "skill", "summary": "Publish mixes",
       "trigger": "Publish mixes. Use when a service publishes."}


def test_doc_types_are_a_registry():
    assert set(doc.TYPES) >= {"skill", "guide"}
    assert doc.TYPES["skill"].pointer and not doc.TYPES["guide"].pointer


def test_skill_needs_trigger_guide_takes_none():
    assert doc.validate(DOC)["type"] == "skill"
    with pytest.raises(Invalid, match="needs a trigger"):
        doc.validate({**DOC, "trigger": None})
    with pytest.raises(Invalid, match="no trigger"):
        doc.validate({**DOC, "type": "guide"})
    assert doc.validate({**DOC, "type": "guide", "trigger": None})["type"] == "guide"


@pytest.mark.parametrize("change, message", [
    ({"type": "poem"}, "not one of"),
    ({"name": "icon"}, "reserved"),
    ({"name": "Bad"}, "lowercase"),
    ({"trigger": "x" * 1025}, "skill description"),
    ({"written_against": "main"}, "commit hash"),
    ({"summary": None}, "summary is required"),
])
def test_doc_refusals(change, message):
    with pytest.raises(Invalid, match=message):
        doc.validate({**DOC, **change})


def test_doc_body_follows_its_type_sections():
    assert doc.validate_body(GUIDE, "skill").startswith("## What it is")
    doc.validate_body(doc.template("guide"), "guide")
    with pytest.raises(Invalid, match="not a section"):
        doc.validate_body("## What it is\n\n## Usage\n", "guide")


def test_doc_title_defaults_to_readable_name():
    assert doc.title({"name": "jukebox-artist"}) == "Jukebox artist"
    assert doc.title({"name": "x", "title": "X API"}) == "X API"


# -- access points ----------------------------------------------------------------


def test_access_is_a_list_in_registry_order_and_round_trips():
    p = profile.validate({**BASE, "access": ["web", "cli", "cli"]})
    assert p["access"] == ["cli", "web"]
    text = profile.dumps(p)
    assert 'access  = ["cli", "web"]' in text
    assert profile.loads(text)["access"] == ["cli", "web"]


def test_access_from_text():
    assert profile.validate({**BASE, "access": "API, cli"})["access"] == ["cli", "api"]
    assert "access" not in profile.validate({**BASE, "access": ""})
    assert "access" not in profile.validate({**BASE, "access": []})


@pytest.mark.parametrize("value, message", [
    (["cli", "ftp"], "'ftp' is not one of cli, api, mcp, web"),
    ([1], "list of names"),
    ("cli", None),
])
def test_access_refusals(value, message):
    if message is None:
        assert profile.validate({**BASE, "access": value})["access"] == ["cli"]
        return
    with pytest.raises(Invalid, match=message):
        profile.validate({**BASE, "access": value})


def test_access_merges_and_clears():
    cur = profile.validate({**BASE, "access": ["cli"]})
    assert profile.merge(cur, {"access": ["cli", "api"]})["access"] == ["cli", "api"]
    assert "access" not in profile.merge(cur, {"access": []})
    assert "access" not in profile.merge(cur, {"access": ""})
