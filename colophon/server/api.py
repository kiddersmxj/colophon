"""The HTTP surface. Reads come as HTML for people and markdown or JSON for
agents; writes are JSON or raw bodies and each one is a commit."""

from __future__ import annotations

import base64
import binascii
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.concurrency import run_in_threadpool

from ..core import Invalid
from ..core import doc as doc_mod
from ..core import profile as profile_mod
from ..core import skill as skill_mod
from . import config as config_mod
from . import identity, render
from .roster import Roster
from .store import Conflict, NotFound, Store

log = logging.getLogger("colophon")
HERE = Path(__file__).resolve().parent
MD = "text/markdown; charset=utf-8"

# The logo and favicons, from assets/ (see assets/README.md); first match
# wins. The placeholders in static/ stand in when a checkout has no assets.
LOGO_NAMES = ("logo.svg", "logo.png")
FAVICON_ICO = ("favicon/favicon.ico", "favicon.ico")
FAVICON_SVG = ("favicon/favicon.svg", "favicon.svg")
APPLE_TOUCH = ("favicon/apple-touch-icon.png",)
MEDIA = {".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}


def create_app(cfg: config_mod.Config | None = None, store: Store | None = None,
               roster: Roster | None = None, who=identity.whois) -> FastAPI:
    cfg = cfg or config_mod.load()
    store = store or Store(cfg.entries_dir, cfg.state_dir, cfg.entries_remote, cfg.push)
    store.ensure()
    migrated = store.migrate()
    if migrated and migrated.changed:
        log.info("migrated old entries to projects and docs in %s", migrated.commit)
    roster = roster or Roster(cfg.roster_url, cfg.roster_token)
    if store.push() is False:
        log.warning("push at startup failed: %s", store.push_error)

    app = FastAPI(title="Colophon", docs_url="/_docs", redoc_url=None, openapi_url="/_openapi.json")
    app.state.store, app.state.roster, app.state.cfg = store, roster, cfg
    app.mount("/_static", StaticFiles(directory=HERE / "static"), name="static")
    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape())
    env.filters["md"] = render.html

    def page(template: str, **ctx) -> HTMLResponse:
        return HTMLResponse(env.get_template(template).render(
            logo_url="/_brand/logo", public_url=cfg.public_url, **ctx))

    def err(status: int, message: str) -> JSONResponse:
        return JSONResponse({"error": message}, status_code=status)

    @app.exception_handler(Invalid)
    async def _invalid(_req, e: Invalid):
        return err(422, str(e))

    @app.exception_handler(NotFound)
    async def _missing(_req, e: NotFound):
        return err(404, f"no project or doc {e.args[0]!r}")

    @app.exception_handler(Conflict)
    async def _conflict(_req, e: Conflict):
        return err(409, str(e))

    def caller(request: Request):
        return identity.caller(request.headers, cfg.tailscale_socket, who=who)

    def get(name: str):
        try:
            profile_mod.check_name(name)
        except Invalid:
            raise NotFound(name) from None
        return store.get(name)

    def get_doc(name: str, doc: str):
        return store.get_doc(name, doc)

    def machine_of(project) -> str | None:
        facts = roster.facts(project.profile.get("roster"))
        if facts and facts.get("registered") and facts.get("machine"):
            return facts["machine"]
        return project.profile.get("machine")

    def fill_from_roster(prof: dict) -> dict:
        """machine is filled from roster when the project has a node."""
        facts = roster.facts(prof.get("roster"))
        if facts and facts.get("registered") and facts.get("machine"):
            return {**prof, "machine": facts["machine"]}
        return prof

    def write_result(res, status: int = 200) -> JSONResponse:
        return JSONResponse(res.as_json(), status_code=status)

    # -- brand -------------------------------------------------------------

    def asset(names: tuple[str, ...], fallback: str) -> FileResponse:
        for n in names:
            p = cfg.assets_dir / n
            if p.is_file():
                return FileResponse(p, media_type=MEDIA.get(p.suffix, "application/octet-stream"),
                                    headers={"Cache-Control": "max-age=300"})
        p = HERE / "static" / fallback
        return FileResponse(p, media_type=MEDIA[p.suffix])

    @app.get("/_brand/logo", include_in_schema=False)
    def logo():
        return asset(LOGO_NAMES, "placeholder-logo.svg")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return asset(FAVICON_ICO, "placeholder-favicon.svg")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon_svg():
        return asset(FAVICON_SVG, "placeholder-favicon.svg")

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    def apple_touch():
        return asset(APPLE_TOUCH, "placeholder-favicon.svg")

    # -- service -----------------------------------------------------------

    @app.get("/health")
    def health():
        projects = store.all()
        return {"ok": True, "projects": len(projects), "docs": sum(len(p.docs) for p in projects),
                "head": store.head(),
                "push_error": store.push_error, "roster": roster.error}

    @app.get("/_roster/{service}")
    def roster_facts(service: str):
        """What roster knows about a service, for `colophon init`."""
        facts = roster.facts(service) or {}
        facts["icon"] = bool(facts.get("registered") and roster.icon(service))
        return facts

    @app.get("/_roster/{service}/icon")
    def roster_icon(service: str):
        data = roster.icon(service)
        if not data:
            return err(404, "roster has no usable icon for this service")
        return Response(data, media_type="image/png")

    # -- index and search ----------------------------------------------------

    def rows():
        return [{**render.index_row(p, cfg.public_url), "machine": machine_of(p)} for p in store.all()]

    @app.get("/", response_class=HTMLResponse)
    def home():
        rs = rows()
        kinds = sorted({r["kind"] for r in rs})
        machines = sorted({r["machine"] for r in rs if r["machine"]})
        used = {a for r in rs for a in r["access"] or []}
        access = {a: label for a, label in profile_mod.ACCESS.items() if a in used}
        return page("index.html", rows=rs, kinds=kinds, machines=machines, access=access,
                    labels=profile_mod.ACCESS)

    @app.get("/index.md")
    def index_md():
        return PlainTextResponse(render.index_md(store.all(), cfg.public_url), media_type=MD)

    @app.get("/index.json")
    def index_json():
        return rows()

    @app.get("/skills.json")
    def skills_json():
        """Every doc that makes a pointer skill, for `colophon skills sync`."""
        return [render.skill_row(d, cfg.public_url) for d in store.skills()]

    @app.get("/search")
    def search(request: Request, q: str = ""):
        found = render.search(store.all(), q)
        if "application/json" in (request.headers.get("accept") or ""):
            return [render.index_row(p, cfg.public_url) for p in found]
        return PlainTextResponse(render.index_md(found, cfg.public_url, f"Search: {q}"), media_type=MD)

    @app.get("/search.json")
    def search_json(q: str = ""):
        return [render.index_row(p, cfg.public_url) for p in render.search(store.all(), q)]

    # -- one project ---------------------------------------------------------

    @app.get("/{name}.md")
    def project_md(name: str):
        try:
            p = get(name)
        except NotFound:
            # A pointer skill's name is its doc's, so /<skill>.md finds the doc
            # even where no project has that name.
            d = store.find_skill(name) if profile_mod.NAME.match(name) else None
            if d is None:
                raise
            return PlainTextResponse(render.doc_md(store.get(d.project), d, cfg.public_url),
                                     media_type=MD)
        return PlainTextResponse(render.project_md(p, roster.facts(p.profile.get("roster")),
                                                   cfg.public_url), media_type=MD)

    @app.get("/{name}.json")
    def project_json(name: str):
        p = get(name)
        return render.project_json(p, roster.facts(p.profile.get("roster")),
                                   store.seen_for(name), cfg.public_url)

    @app.get("/{name}/icon")
    def project_icon(name: str):
        p = get(name)
        return FileResponse(p.icon_path, media_type="image/png", headers={"Cache-Control": "no-cache"})

    @app.get("/{name}/history")
    def project_history(name: str):
        get(name)
        return store.history(name)

    @app.get("/{name}/history.md")
    def project_history_md(name: str):
        p = get(name)
        return PlainTextResponse(render.history_md(f"{p.profile['title']} ({name})", store.history(name)),
                                 media_type=MD)

    @app.get("/{name}", response_class=HTMLResponse)
    def project_page(name: str):
        p = get(name)
        facts = roster.facts(p.profile.get("roster"))
        return page("project.html", pr=p, p=p.profile, facts=facts, lines=render.facts_lines(p, facts),
                    history=store.history(name, limit=20), kinds=profile_mod.KINDS,
                    access=profile_mod.ACCESS,
                    types=list(doc_mod.TYPES), templates={t: doc_mod.template(t) for t in doc_mod.TYPES})

    # -- one doc ---------------------------------------------------------------

    @app.get("/{name}/{doc}.md")
    def doc_md(name: str, doc: str):
        p = get(name)
        return PlainTextResponse(render.doc_md(p, get_doc(name, doc), cfg.public_url), media_type=MD)

    @app.get("/{name}/{doc}.json")
    def doc_json(name: str, doc: str):
        p = get(name)
        return render.doc_json(p, get_doc(name, doc), store.seen_for(name), cfg.public_url)

    @app.get("/{name}/{doc}/skill.md")
    def doc_skill(name: str, doc: str):
        get(name)
        d = get_doc(name, doc)
        if not d.type.pointer:
            return err(404, f"{name}/{doc} is a {d.meta['type']}; only skills have a pointer skill")
        return PlainTextResponse(skill_mod.pointer(d.name, name, d.title, d.meta["trigger"],
                                                   cfg.public_url), media_type=MD)

    @app.get("/{name}/{doc}/history")
    def doc_history(name: str, doc: str):
        get(name)
        get_doc(name, doc)
        return store.doc_history(name, doc)

    @app.get("/{name}/{doc}/history.md")
    def doc_history_md(name: str, doc: str):
        get(name)
        d = get_doc(name, doc)
        return PlainTextResponse(render.history_md(f"{d.title} ({name}/{doc})",
                                                   store.doc_history(name, doc)), media_type=MD)

    @app.get("/{name}/{doc}", response_class=HTMLResponse)
    def doc_page(name: str, doc: str):
        p = get(name)
        d = get_doc(name, doc)
        seen = store.seen_for(name)
        behind = (seen or {}).get("behind", {}).get(doc) if seen else None
        stale = {"behind": behind, "at": seen["at"]} if behind and d.meta.get("written_against") else None
        return page("doc.html", pr=p, p=p.profile, d=d, m=d.meta, stale=stale,
                    history=store.doc_history(name, doc, limit=20),
                    sections=d.type.sections, types=list(doc_mod.TYPES))

    # -- writes ------------------------------------------------------------

    # The handlers read the body here, then do the rest in a worker thread:
    # whois, roster and git all block, and must not hold the event loop.

    @app.post("/", status_code=201)
    async def create(request: Request):
        body = await _json(request)

        def work():
            prof = body.get("profile")
            if not isinstance(prof, dict):
                raise Invalid('send {"profile": {...}, "icon": "<base64 PNG>"}')
            icon = _b64(body.get("icon"))
            if not icon and prof.get("roster"):
                icon = roster.icon(prof["roster"]) or b""
            return store.create(fill_from_roster(prof), icon, caller(request))

        return write_result(await run_in_threadpool(work), 201)

    @app.put("/{name}/profile")
    async def put_profile(name: str, request: Request, replace: bool = False):
        changes = await _json(request)

        def work():
            get(name)
            ch = changes
            if replace:
                ch = fill_from_roster(ch)
            elif ch.get("roster") and not ch.get("machine"):
                filled = fill_from_roster({"roster": ch["roster"]})
                if "machine" in filled:
                    ch = {**ch, "machine": filled["machine"]}
            return store.update_profile(name, ch, caller(request), replace)

        return write_result(await run_in_threadpool(work))

    @app.put("/{name}/icon")
    async def put_icon(name: str, request: Request):
        data = await request.body()

        def work():
            get(name)
            return store.put_icon(name, data, caller(request))

        return write_result(await run_in_threadpool(work))

    @app.delete("/{name}")
    def delete_project(name: str, request: Request):
        get(name)
        return write_result(store.delete_project(name, caller(request)))

    @app.post("/{name}/seen")
    async def post_seen(name: str, request: Request):
        """A project reports its current commit and how far it is past each
        doc's written_against. Kept outside git: it is not content."""
        get(name)
        body = await _json(request)
        return store.record_seen(name, body.get("commit", ""), body.get("behind"))

    @app.post("/{name}/docs", status_code=201)
    async def create_doc(name: str, request: Request, written_against: str | None = None):
        body = await _json(request)

        def work():
            get(name)
            meta, text = body.get("doc"), body.get("body")
            if not isinstance(meta, dict) or not isinstance(text, str):
                raise Invalid('send {"doc": {"name", "type", "summary", ...}, "body": "<markdown>"}')
            return store.create_doc(name, meta, text, caller(request), written_against)

        return write_result(await run_in_threadpool(work), 201)

    @app.put("/{name}/{doc}/meta")
    async def put_doc_meta(name: str, doc: str, request: Request):
        changes = await _json(request)

        def work():
            get(name)
            get_doc(name, doc)
            return store.update_doc(name, doc, changes, caller(request))

        return write_result(await run_in_threadpool(work))

    @app.post("/{name}/{doc}/move")
    async def move_doc(name: str, doc: str, request: Request):
        body = await _json(request)

        def work():
            get(name)
            get_doc(name, doc)
            to = body.get("to")
            if not isinstance(to, str):
                raise Invalid('send {"to": "<project>"}')
            get(to)
            return store.move_doc(name, doc, to, caller(request))

        return write_result(await run_in_threadpool(work))

    @app.put("/{name}/{doc}")
    async def put_body(name: str, doc: str, request: Request, written_against: str | None = None):
        try:
            text = (await request.body()).decode("utf-8")
        except UnicodeDecodeError:
            raise Invalid("the doc must be UTF-8 text") from None

        def work():
            get(name)
            get_doc(name, doc)
            return store.put_body(name, doc, text, caller(request), written_against)

        return write_result(await run_in_threadpool(work))

    @app.delete("/{name}/{doc}")
    def delete_doc(name: str, doc: str, request: Request):
        get(name)
        get_doc(name, doc)
        return write_result(store.delete_doc(name, doc, caller(request)))

    return app


async def _json(request: Request) -> dict:
    try:
        body = await request.json()
    except ValueError:
        raise Invalid("the body must be JSON") from None
    if not isinstance(body, dict):
        raise Invalid("the body must be a JSON object")
    return body


def _b64(value) -> bytes:
    if not value:
        return b""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError, TypeError):
        raise Invalid("icon must be base64") from None


def main() -> None:
    import uvicorn

    cfg = config_mod.load()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(cfg), host=cfg.bind, port=cfg.port, log_level="info",
                proxy_headers=False)
