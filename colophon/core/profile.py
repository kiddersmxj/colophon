"""A project's profile: project.toml, its fields and its rules."""

from __future__ import annotations

import datetime as dt
import re
import tomllib

from . import Invalid

# What a thing is. A service runs and listens; a program is something you run.
# How it is reached (a CLI, an API) is access, below, never a kind. A stored
# kind no longer listed (api and cli were, until 2026-11-19) still reads and
# shows as stored; only a write must pick a listed one.
KINDS = ("service", "program", "app", "device", "library")

# Access points: how a project is reached, as many as it has. kind says what
# the thing is; these say how to use it. The registry: name and its label on
# a badge. A new one is one line here; order here is the order shown.
ACCESS = {
    "cli": "CLI",
    "api": "API",
    "mcp": "MCP",
    "web": "Web",
}

# Lowercase, stable, and safe as a folder, a URL segment and a skill name.
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# Paths the server answers itself. Its other routes start with "_" or carry
# a file suffix, which no name can, so this list stays short: an entry for a
# thing called roster or status must be possible.
RESERVED = {"index", "search", "health"}

# Field order in project.toml, and the type each must have.
FIELDS: dict[str, type] = {
    "name": str,
    "title": str,
    "summary": str,
    "kind": str,
    "access": list,
    "repo": str,
    "remote": str,
    "machine": str,
    "roster": str,
    "updated": dt.date,
}
REQUIRED = ("name", "title", "summary", "kind")
# What a caller may set. name is fixed at creation; updated is the server's.
SETTABLE = tuple(f for f in FIELDS if f not in ("name", "updated"))

SUMMARY_MAX = 200
SHA = re.compile(r"^[0-9a-f]{7,40}$")


def check_name(name: str) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise Invalid(f"name {name!r}: lowercase letters, digits and hyphens, "
                      "starting with a letter or digit, at most 40")
    if name in RESERVED:
        raise Invalid(f"name {name!r} is reserved")
    return name


def coerce(field: str, value, fields: dict | None = None):
    """A value given as text (CLI, form) turned into the field's type."""
    want = (fields or FIELDS).get(field)
    if want is bool and isinstance(value, str):
        low = value.strip().lower()
        if low in ("true", "yes", "1", "on"):
            return True
        if low in ("false", "no", "0", "off"):
            return False
        raise Invalid(f"{field} is true or false, not {value!r}")
    if want is list and isinstance(value, str):
        return [v.strip().lower() for v in value.replace(" ", ",").split(",") if v.strip()]
    if want is dt.date and isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            raise Invalid(f"{field} is a date, YYYY-MM-DD") from None
    return value


def typed(p: dict, fields: dict, problems: list[str]) -> dict:
    """p's known fields, coerced to their types; problems collected, not raised."""
    out: dict = {}
    for key in p:
        if key not in fields:
            problems.append(f"unknown field {key!r} (fields: {', '.join(fields)})")
    for key, want in fields.items():
        if key not in p or p[key] is None:
            continue
        try:
            value = coerce(key, p[key], fields)
        except Invalid as e:
            problems.append(str(e))
            continue
        if want is str and isinstance(value, str):
            value = value.strip()
            if value == "":
                continue  # an empty optional field is the same as no field
        if want is list and value == []:
            continue
        if want is list and isinstance(value, list) and not all(isinstance(v, str) for v in value):
            problems.append(f"{key} must be a list of names")
            continue
        if not isinstance(value, want) or (want is dt.date and isinstance(value, dt.datetime)):
            problems.append(f"{key} must be {want.__name__}")
            continue
        out[key] = value
    return out


def validate(p: dict) -> dict:
    """The profile, checked and normalised. Raises Invalid with every problem."""
    problems: list[str] = []
    out = typed(p, FIELDS, problems)
    for key in REQUIRED:
        if key not in out:
            problems.append(f"{key} is required")
    if "name" in out:
        try:
            check_name(out["name"])
        except Invalid as e:
            problems.append(str(e))
    if "kind" in out and out["kind"] not in KINDS:
        problems.append(f"kind {out['kind']!r} is not one of {', '.join(KINDS)}"
                        "set one with --kind")
    if "access" in out:
        bad = [a for a in out["access"] if a not in ACCESS]
        if bad:
            problems.append(f"access {', '.join(map(repr, bad))} is not one of {', '.join(ACCESS)}")
        else:
            out["access"] = [a for a in ACCESS if a in out["access"]]
    for key in ("title", "summary"):
        if key in out and "\n" in out[key]:
            problems.append(f"{key} must be one line")
    if len(out.get("summary", "")) > SUMMARY_MAX:
        problems.append(f"summary is over {SUMMARY_MAX} characters; it is one line in the index")
    # A roster service may be called anything roster allows, reserved words included.
    if "roster" in out and not NAME.match(out["roster"]):
        problems.append(f"roster {out['roster']!r} is not a service name")
    if problems:
        raise Invalid("; ".join(problems))
    return out


def merge(current: dict, changes: dict, fields: dict | None = None,
          settable: tuple | None = None, required: tuple | None = None) -> dict:
    """current with changes applied. None or "" clears an optional field."""
    fields, settable, required = fields or FIELDS, settable or SETTABLE, required or REQUIRED
    for key in changes:
        if key not in settable:
            raise Invalid(f"{key!r} cannot be set" if key in fields else f"unknown field {key!r}")
    out = dict(current)
    for key, value in changes.items():
        if value is None or value == "" or value == []:
            if key in required:
                raise Invalid(f"{key} is required and cannot be cleared")
            out.pop(key, None)
        else:
            out[key] = value
    return out


def _toml_str(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dumps(p: dict, fields: dict | None = None) -> str:
    """TOML text, fields in their fixed order, keys aligned."""
    width = max(len(k) for k in p)
    lines = []
    for key in fields or FIELDS:
        if key not in p:
            continue
        v = p[key]
        if isinstance(v, bool):
            text = "true" if v else "false"
        elif isinstance(v, dt.date):
            text = v.isoformat()
        elif isinstance(v, list):
            text = "[" + ", ".join(_toml_str(str(x)) for x in v) + "]"
        else:
            text = _toml_str(str(v))
        lines.append(f"{key.ljust(width)} = {text}")
    return "\n".join(lines) + "\n"


def loads(text: str, what: str = "project.toml") -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise Invalid(f"{what} does not parse: {e}") from None


def as_json(p: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in p.items()}
