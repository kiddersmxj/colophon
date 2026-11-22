"""Docs: what sits under a project. Each doc has a type, and the type decides
what the doc needs and what it gets.

    <project>/docs/<doc>.toml   the doc's fields
    <project>/docs/<doc>.md     its body

A new type is one more entry in TYPES; nothing else is shaped around the two
that exist.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from . import Invalid, guide
from .profile import NAME, SHA, typed


@dataclass(frozen=True)
class DocType:
    name: str
    # The body's sections, in order, and those it must have.
    sections: tuple[str, ...] = guide.SECTIONS
    required: tuple[str, ...] = guide.REQUIRED
    # A pointer skill is generated for it, named after the doc, with the
    # trigger as its description. Such a type needs a trigger.
    pointer: bool = False


TYPES: dict[str, DocType] = {
    "skill": DocType("skill", pointer=True),
    "guide": DocType("guide"),
}

FIELDS: dict[str, type] = {
    "name": str,
    "type": str,
    "title": str,
    "summary": str,
    "trigger": str,
    "written_against": str,
    "updated": dt.date,
}
REQUIRED = ("name", "type", "summary")
SETTABLE = tuple(f for f in FIELDS if f not in ("name", "updated"))

# Paths under /<project>/ the server answers itself.
RESERVED = {"icon", "history", "profile", "seen", "docs"}

# A skill description is capped by Claude Code; a trigger becomes one.
TRIGGER_MAX = 1024
SUMMARY_MAX = 200


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise Invalid(f"doc name {name!r}: lowercase letters, digits and hyphens, "
                      "starting with a letter or digit, at most 40")
    if name in RESERVED:
        raise Invalid(f"doc name {name!r} is reserved")
    return name


def doctype(name: str) -> DocType:
    if name not in TYPES:
        raise Invalid(f"type {name!r} is not one of {', '.join(TYPES)}")
    return TYPES[name]


def validate(m: dict) -> dict:
    """A doc's fields, checked and normalised. Raises Invalid with every problem."""
    problems: list[str] = []
    out = typed(m, FIELDS, problems)
    for key in REQUIRED:
        if key not in out:
            problems.append(f"{key} is required")
    if "name" in out:
        try:
            check_name(out["name"])
        except Invalid as e:
            problems.append(str(e))
    t = TYPES.get(out.get("type", ""))
    if "type" in out and t is None:
        problems.append(f"type {out['type']!r} is not one of {', '.join(TYPES)}")
    for key in ("title", "summary", "trigger"):
        if key in out and "\n" in out[key]:
            problems.append(f"{key} must be one line")
    if len(out.get("summary", "")) > SUMMARY_MAX:
        problems.append(f"summary is over {SUMMARY_MAX} characters; it is one line on the project page")
    if len(out.get("trigger", "")) > TRIGGER_MAX:
        problems.append(f"trigger is over {TRIGGER_MAX} characters, the limit for a skill description")
    if t is not None:
        if t.pointer and not out.get("trigger"):
            problems.append(f"a {t.name} needs a trigger: it becomes the pointer skill's "
                            "description (what it is and when to use it)")
        if not t.pointer and out.get("trigger"):
            problems.append(f"a {t.name} has no pointer skill, so no trigger")
    if "written_against" in out and not SHA.match(out["written_against"]):
        problems.append("written_against is a commit hash")
    if problems:
        raise Invalid("; ".join(problems))
    return out


def validate_body(text: str, type_name: str) -> str:
    t = doctype(type_name)
    return guide.validate(text, t.sections, t.required)


def template(type_name: str) -> str:
    return guide.template(doctype(type_name).sections)


def default_title(name: str) -> str:
    """A readable title from a doc's name: music-library gives Music library."""
    words = name.replace("-", " ")
    return words[:1].upper() + words[1:]


def title(m: dict) -> str:
    return m.get("title") or default_title(m["name"])
