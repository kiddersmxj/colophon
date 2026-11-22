# Operations

## What runs where

| host | unit | runs from | state |
|---|---|---|---|
| `PROD_HOST` | `colophon` (user service of the deploying user) | `~/prod/colophon/venv`, code checkout `~/prod/colophon/src` | entries checkout `~/prod/colophon/entries`; `~/prod/colophon/state` (700): `seen.json`, `colophon.env` (600) |

The server listens on `127.0.0.1:8796` on the prod host. Something in front
of it (a reverse proxy, `tailscale serve`) gives it the address in
`COLOPHON_URL`, which is also its public URL: pointer skills and markers carry
it.

The deploying user owns everything: code, venv, entries and state. Turn on
lingering for that user so the unit starts at boot. No step of a deploy uses
sudo, and `make lint-sudo` fails if one appears.

The entries checkout pushes to `ENTRIES_REPO` with a deploy key that reaches
that repo only, `~/.ssh/colophon-entries` on the prod host, set as the
checkout's `core.sshCommand`. The user's own GitHub key is never used for it.

## Settings

Your values go in `local.mk` (copy `local.mk.example`; git ignores it). The
prod targets refuse without `PROD_HOST` and `ENTRIES_REPO`.

| local.mk | for |
|---|---|
| `PROD_HOST` | the machine the server runs on, as ssh knows it |
| `COLOPHON_URL` | where the server is reached; written to the server as `COLOPHON_PUBLIC_URL` |
| `ENTRIES_REPO`, `ENTRIES_GH` | the entries repo, as a git URL and as `owner/name` for `gh` |
| `PROD_ROSTER_URL` | optional: the service directory (see SPEC.md) |
| `PROD_TAILSCALE_SOCKET` | optional: a tailscaled socket to ask who a caller is |

The server reads its own settings from `COLOPHON_*` variables. The unit sets
the paths and the port; `make prod-env` writes the rest into
`state/colophon.env`. A directory reader token, `COLOPHON_ROSTER_TOKEN`, is
added to that file by hand on the prod host; `prod-env` leaves other lines as
they are and prints only the names.

## Deploying, the first time

From a checkout with `local.mk` filled in, in order. None of these asks for a
password.

| step | what it does |
|---|---|
| `make prod-deploy-key` | makes the deploy key on the prod host and adds its public half to the entries repo with write access, through `gh` |
| `make prod-bootstrap` | checks python 3.11+, clones the code and the entries, makes the state dir and venv, and checks port 8796 is free |
| `make prod-env` | writes `COLOPHON_PUBLIC_URL` and the optional settings into the server's env file |
| `make deploy` | installs `origin/main`, installs the unit, starts it, prints `/health` |

Then point whatever fronts the server at `127.0.0.1:8796`, check it with
`make health`, and on each machine that uses it run `make cli-install`, copy
`colophon.conf.example` to `colophon.conf` with `server: <COLOPHON_URL>` (and
`skills_host: <hostname>` for the one machine that takes pointer skills;
`make deploy` copies it to prod), and link the two skills in `.claude/skills/` into
`~/.claude/skills`.

Every later update is `make deploy`, which refuses unless the tree is clean and
pushed.

## Endpoints

| | |
|---|---|
| `GET /`, `/<project>`, `/<project>/<doc>` | the web UI: grid of projects, a project's page with its docs, a doc's page; editing on each |
| `GET /index.md`, `/index.json` | every project, its docs under it |
| `GET /search?q=`, `/search.json?q=` | projects matching every word, docs included |
| `GET /<project>.md`, `/<project>.json` | profile, directory facts, one line per doc |
| `GET /<project>/<doc>.md`, `.json` | one doc |
| `GET /<project>/icon`, `/<project>/history` | icon; commits touching the project (JSON) |
| `GET /<project>/history.md`, `/<project>/<doc>/history.md` | the same history as one line per commit |
| `GET /<project>/<doc>/skill.md`, `/<project>/<doc>/history` | pointer skill (skills only); commits touching the doc, through moves |
| `GET /skills.json` | every skill doc, for `skills sync` |
| `GET /<skill>.md` | a skill doc by skill name when no project has that name (old pointer skills) |
| `POST /` | create a project: `{"profile": {...}, "icon": "<base64 image>"}`; icon may be left out when the directory has one |
| `PUT /<project>/profile` | merge fields (`null` or `""` clears); `?replace=true` replaces; `access` is a list or `"cli,api"`, `[]` clears |
| `PUT /<project>/icon` | raw image body (PNG, SVG, ICO...), stored as a square PNG |
| `DELETE /<project>` | only when it has no docs |
| `POST /<project>/docs` | add a doc: `{"doc": {...}, "body": "..."}`; `?written_against=<sha>` |
| `PUT /<project>/<doc>` | replace the body; `?written_against=<sha>` in the same commit |
| `PUT /<project>/<doc>/meta` | merge the doc's fields |
| `POST /<project>/<doc>/move` | `{"to": "<project>"}`, a git rename |
| `DELETE /<project>/<doc>` | remove a doc |
| `POST /<project>/seen` | `{"commit", "behind": {doc: n}}` from the CLI; kept in `state/seen.json`, not git |
| `GET /_roster/<service>`, `/_roster/<service>/icon` | directory facts and icon, for `colophon init` |
| `GET /health` | projects, docs, head, last push error, directory error |
| `GET /_docs` | OpenAPI |

A write answers `{"name", "commit", "pushed", "changed"}`. `changed: false`
means nothing differed and nothing was committed.

## Gotchas

- **A failed push does not fail the write.** The commit stays; the answer says
  `pushed: false`, `/health` shows `push_error`, and the next write or a
  restart pushes again. `make prod-status` shows the checkout ahead of origin.
- **Identity is only as good as loopback.** colophon trusts `X-Forwarded-For`
  and the `Tailscale-User-*` headers because only its front proxy should reach
  `127.0.0.1:8796`. Anything else running on the prod host could forge them.
  A write with neither is recorded as local, `<user>@<host>`.
- **The machine comes from whois.** `tailscale serve` never sends it in a
  header. colophon runs `tailscale whois` against `COLOPHON_TAILSCALE_SOCKET`
  when set, then the host's own tailscaled. If both fail, the history shows
  the caller's tailnet address instead of a machine name.
- **Directory icons need a reader token.** Without `COLOPHON_ROSTER_TOKEN`,
  `colophon init` asks for `--icon` for every new project. colophon converts
  any image the directory holds to a square PNG (SVG rendered at 512 px, ICO's
  largest image, non-square padded onto transparent). SVG needs libcairo on
  the prod host.
- **The directory being down only leaves facts out.** Reads still work; a
  project with a `roster` name says `roster did not answer`.
- **An old kind blocks other edits.** `api` and `cli` are no longer kinds. A
  profile still storing one reads fine, but any profile write answers
  `kind 'api' is not one of ...` until the kind is changed, and the edit form
  shows `api (choose a kind)`.
- **The marker file should be ignored globally.** List `.colophon` in the
  global git excludes file on each machine. A machine without it shows the
  file as untracked; the CLI warns.
- **Pointer skills and hand-written skills.** `colophon skills sync` writes to
  `~/.claude/skills`; with `COLOPHON_SKILLS_HOST` set it refuses on any other
  machine unless given `--dir`. It never replaces a skill it did not generate,
  including a symlink: it prints `skipped <name>: a hand-written skill is in
  the way`. No skill doc may share a name with a hand-written skill, which is
  why Colophon's own doc is a guide (the hand-written `colophon` skill holds
  that name).
- **`make deploy` waits up to 30 seconds for `/health`.** The server takes a
  few seconds to listen after the restart, so the deploy retries once a
  second. It fails only if nothing answers in that time.
- **The layout migration runs once, at startup.** A server started on a
  checkout that still has `entry.toml` folders converts them in one commit,
  `migrate: each entry becomes a project, its guide a doc`, and pushes it.
- **Port 8796 must be free.** `make prod-bootstrap` stops with "port 8796 is
  taken by something else" when another service has it: change the port in
  the unit and `PROD_PORT`.
