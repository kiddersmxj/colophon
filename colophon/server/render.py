"""Projects and docs as markdown and JSON for agents, and the pieces the HTML
pages share."""

from __future__ import annotations

from markdown_it import MarkdownIt

from ..core import doc as doc_mod
from ..core import profile as profile_mod
from .store import Doc, Project

# Raw HTML in a doc is shown as text, never run: docs are written by agents.
_md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False}).enable("table")


def html(text: str) -> str:
    return _md.render(text)


def _date(v) -> str:
    return v.isoformat() if hasattr(v, "isoformat") else str(v or "")


def facts_lines(project: Project, facts: dict | None) -> list[tuple[str, str]]:
    """(label, value) pairs for a project's header, roster first."""
    p = project.profile
    out: list[tuple[str, str]] = [("kind", p["kind"])]
    if p.get("access"):
        out.append(("access", ", ".join(p["access"])))
    if facts and facts.get("registered"):
        out.append(("address", facts["address"] or ""))
        out.append(("machine", facts.get("machine") or p.get("machine", "")))
        out.append(("roster", ", ".join(x for x in (facts["service"], facts.get("tag"),
                                                    "sensitive" if facts.get("sensitive") else "") if x)))
    else:
        if p.get("machine"):
            out.append(("machine", p["machine"]))
        if p.get("roster"):
            if facts is None:
                out.append(("roster", p["roster"]))
            else:
                why = "not registered" if facts.get("available") else "roster did not answer"
                out.append(("roster", f"{p['roster']} ({why})"))
    if p.get("repo"):
        out.append(("repo", p["repo"]))
    if p.get("remote"):
        out.append(("remote", p["remote"]))
    out.append(("updated", _date(p.get("updated"))))
    return [(k, v) for k, v in out if v]


def doc_url(public_url: str, d: Doc) -> str:
    return f"{public_url}/{d.project}/{d.name}"


def doc_line(d: Doc, public_url: str) -> str:
    return f"{d.name} ({d.meta['type']}): {d.meta['summary']} {doc_url(public_url, d)}.md"


def project_md(project: Project, facts: dict | None, public_url: str) -> str:
    p = project.profile
    lines = [f"# {p['title']} ({p['name']})", "", p["summary"], ""]
    lines += [f"- {k}: {v}" for k, v in facts_lines(project, facts)]
    lines += ["", "## Docs", ""]
    if project.docs:
        lines += [f"- {doc_line(d, public_url)}" for d in project.docs]
    else:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def doc_md(project: Project, d: Doc, public_url: str) -> str:
    p = project.profile
    lines = [f"# {d.title} ({d.project}/{d.name})", "", d.meta["summary"], "",
             f"- type: {d.meta['type']}",
             f"- project: {p['title']}, {public_url}/{p['name']}.md",
             f"- updated: {_date(d.meta.get('updated'))}", "",
             d.body.rstrip()]
    return "\n".join(lines) + "\n"


def history_md(heading: str, commits: list[dict]) -> str:
    """Commits, newest first: one line each, short hash, date, who and from where."""
    lines = [f"# History: {heading}", ""]
    for c in commits:
        who = c["author"] + (f" on {c['machine']}" if c.get("machine") else "")
        lines.append(f"- {c['short']} {c['date'][:10]} {who}: {c['subject']}")
    if not commits:
        lines.append("No commits.")
    return "\n".join(lines) + "\n"


def doc_row(d: Doc, public_url: str) -> dict:
    m = d.meta
    return {"name": m["name"], "type": m["type"], "title": d.title, "summary": m["summary"],
            "url": f"{doc_url(public_url, d)}.md",
            **({"skill": m["name"]} if d.type.pointer else {})}


def doc_json(project: Project, d: Doc, seen: dict | None, public_url: str) -> dict:
    url = doc_url(public_url, d)
    behind = (seen or {}).get("behind", {}).get(d.name) if seen else None
    return {
        "project": project.name,
        "doc": profile_mod.as_json(d.meta),
        "body": d.body,
        "seen": {"commit": seen["commit"], "at": seen["at"], "behind": behind} if seen else None,
        "links": {
            "page": url,
            "markdown": f"{url}.md",
            "project": f"{public_url}/{project.name}.md",
            "history": f"{url}/history",
            "history_md": f"{url}/history.md",
            **({"skill": f"{url}/skill.md"} if d.type.pointer else {}),
        },
    }


def project_json(project: Project, facts: dict | None, seen: dict | None, public_url: str) -> dict:
    name = project.name
    return {
        "profile": profile_mod.as_json(project.profile),
        "roster": facts,
        "docs": [{**profile_mod.as_json(d.meta), "title": d.title,
                  "url": f"{doc_url(public_url, d)}.md"} for d in project.docs],
        "seen": seen,
        "links": {
            "page": f"{public_url}/{name}",
            "markdown": f"{public_url}/{name}.md",
            "icon": f"{public_url}/{name}/icon",
            "history": f"{public_url}/{name}/history",
            "history_md": f"{public_url}/{name}/history.md",
        },
    }


def index_row(project: Project, public_url: str) -> dict:
    p = project.profile
    return {"name": p["name"], "title": p["title"], "kind": p["kind"],
            "access": p.get("access"), "summary": p["summary"],
            "machine": p.get("machine"), "roster": p.get("roster"),
            "updated": profile_mod.as_json(p).get("updated"),
            "docs": [doc_row(d, public_url) for d in project.docs]}


def skill_row(d: Doc, public_url: str) -> dict:
    return {"name": d.name, "project": d.project, "description": d.meta["trigger"],
            "url": f"{doc_url(public_url, d)}/skill.md"}


def index_md(projects: list[Project], public_url: str, heading: str = "Colophon") -> str:
    lines = [f"# {heading}", "",
             f"Projects: name (kind; access points): summary. A project is at {public_url}/<project>.md, "
             f"its docs at {public_url}/<project>/<doc>.md.", ""]
    for pr in projects:
        p = pr.profile
        how = "; " + ", ".join(p["access"]) if p.get("access") else ""
        lines.append(f"- {p['name']} ({p['kind']}{how}): {p['summary']}")
        lines += [f"  - {doc_line(d, public_url)}" for d in pr.docs]
    if not projects:
        lines.append("(nothing found)")
    return "\n".join(lines) + "\n"


def search(projects: list[Project], q: str) -> list[Project]:
    """Projects matching every word, in their profile or any of their docs."""
    words = [w for w in q.lower().split() if w]
    if not words:
        return []
    scored = []
    for pr in projects:
        p = pr.profile
        head = " ".join([*(str(p.get(k, "")) for k in ("name", "title", "kind", "machine", "roster")),
                         *p.get("access", []),
                         *(d.name for d in pr.docs)]).lower()
        body = " ".join([p.get("summary", ""),
                         *(" ".join([doc_mod.title(d.meta), d.meta.get("summary", ""),
                                     d.meta.get("trigger", ""), d.body]) for d in pr.docs)]).lower()
        if not all(w in head or w in body for w in words):
            continue
        score = sum(3 if w in head else 1 for w in words) + (5 if q.lower().strip() == p["name"] else 0)
        scored.append((-score, p["name"], pr))
    return [pr for _, _, pr in sorted(scored, key=lambda t: (t[0], t[1]))]
