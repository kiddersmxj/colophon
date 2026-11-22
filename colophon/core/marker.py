"""The .colophon marker at a project's root."""

from __future__ import annotations

from pathlib import Path

from . import Invalid
from .profile import check_name

FILENAME = ".colophon"


def dumps(project: str, server: str) -> str:
    check_name(project)
    return f"project: {project}\nserver: {server.rstrip('/')}\n"


def loads(text: str) -> dict:
    out = {}
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise Invalid(f"{FILENAME} line {n}: expected 'key: value'")
        out[key.strip()] = value.strip()
    # Markers written before projects had docs said "entry:".
    if "project" not in out and "entry" in out:
        out["project"] = out.pop("entry")
    if "project" not in out:
        raise Invalid(f"{FILENAME} has no 'project:' line")
    return out


def write(folder: Path, project: str, server: str) -> Path:
    path = Path(folder) / FILENAME
    path.write_text(dumps(project, server))
    return path


def find(start: Path) -> tuple[Path, dict] | None:
    """The nearest marker at or above start, and what it says."""
    here = Path(start).resolve()
    for folder in (here, *here.parents):
        path = folder / FILENAME
        if path.is_file():
            return path, loads(path.read_text())
    return None
