"""The six-section template a doc's body follows, and its checks."""

from __future__ import annotations

import re

from . import Invalid

SECTIONS = (
    "What it is",
    "Where",
    "Auth",
    "Quick start",
    "Reference",
    "Rules and gotchas",
)
REQUIRED = ("What it is",)
MAX_BYTES = 64 * 1024

FENCE = re.compile(r"^\s{0,3}(```|~~~)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

TEMPLATE = "\n\n".join(f"## {s}\n" for s in SECTIONS)


def headings(text: str) -> list[tuple[int, str, int]]:
    """(level, title, line number) of each heading outside code fences."""
    out = []
    fence = None
    for n, line in enumerate(text.splitlines(), 1):
        m = FENCE.match(line)
        if m:
            if fence is None:
                fence = m.group(1)
            elif m.group(1) == fence:
                fence = None
            continue
        if fence:
            continue
        h = HEADING.match(line)
        if h:
            out.append((len(h.group(1)), h.group(2), n))
    return out


def template(sections: tuple[str, ...] = SECTIONS) -> str:
    return "\n\n".join(f"## {s}\n" for s in sections)


def validate(text: str, sections: tuple[str, ...] = SECTIONS,
             required: tuple[str, ...] = REQUIRED) -> str:
    """A doc's body, checked. Raises Invalid naming every problem."""
    if not isinstance(text, str):
        raise Invalid("the doc is text")
    if len(text.encode()) > MAX_BYTES:
        raise Invalid(f"the doc is over {MAX_BYTES // 1024} KB; a doc is a tldr page, "
                      "the rest belongs in the project's own docs")
    text = text.replace("\r\n", "\n").strip() + "\n"
    problems: list[str] = []
    seen: list[str] = []
    lines = text.splitlines()
    first_h2 = None
    for level, title, n in headings(text):
        if level == 1:
            problems.append(f"line {n}: no '# {title}' heading; the title comes from the doc's title")
        elif level == 2:
            if first_h2 is None:
                first_h2 = n
            if title not in sections:
                problems.append(f"line {n}: '## {title}' is not a section "
                                f"(sections: {', '.join(sections)})")
            elif title in seen:
                problems.append(f"line {n}: '## {title}' appears twice")
            elif seen and sections.index(title) < sections.index(seen[-1]):
                problems.append(f"line {n}: '## {title}' comes before '## {seen[-1]}' "
                                "in the template")
            else:
                seen.append(title)
    before = lines[: (first_h2 - 1) if first_h2 else len(lines)]
    if any(line.strip() for line in before):
        problems.append(f"text before the first section; start with '## {sections[0]}'")
    for s in required:
        if s not in seen:
            problems.append(f"'## {s}' is required")
    if problems:
        raise Invalid("; ".join(problems))
    return text
