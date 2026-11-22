# Working on colophon

Design and the reasoning behind it: [../SPEC.md](../SPEC.md).

## Layout

```
colophon/core/        shared by server and CLI; standard library only
  profile.py          project.toml fields, validation, merge, writing TOML; the access points
  doc.py              doc types (the registry), a doc's fields, body checks by type
  guide.py            the six sections, their order, the empty template
  icon.py             square PNG, 32 to 2048 px, at most 1 MB
  marker.py           the .colophon file: write, read, find upwards
  skill.py            the generated pointer skill and its "generated" mark
colophon/server/      FastAPI, on the prod host
  api.py              the HTTP surface, reads and writes
  store.py            the entries checkout: projects and docs; validate, write, commit,
                      push; moves; the startup migration of the old layout; seen.json
  roster.py           facts and icons from the optional service directory, cached
  iconconv.py         any image (SVG, ICO, non-square) to a square PNG; Pillow, cairosvg
  identity.py         who a write is from: whois, tailscale serve headers, or local
  render.py           markdown and JSON for agents, the index, search
  config.py           paths, ports, addresses, from COLOPHON_* variables
  templates/          the web UI: grid, project page, doc page, editing
  static/             style.css, placeholder logo for a checkout with no assets/
colophon/cli.py       the colophon command
bin/colophon          runs the CLI from this checkout; `make cli-install` links it
assets/               logo and favicons (see assets/README.md)
.claude/skills/       colophon and colophon-write
infra/systemd/        colophon.service, a user unit on the prod host
tests/                pytest; every test uses a scratch repo and a scratch bare remote
local.mk.example      the owner's settings; copy to local.mk, which git ignores
```

## Commands

`make help` lists all of them.

| | |
|---|---|
| `make install` / `make test` / `make lint` | venv; the suite; suite plus the sudo check |
| `make dev` | server on `127.0.0.1:8796`, entries in `./var/entries` (a local repo, pushing off) |
| `make cli-install` | link `bin/colophon` to `~/.local/bin/colophon` |
| `bin/colophon --server http://127.0.0.1:8796 ...` | the CLI against a dev server |
| `make deploy` and `prod-*` | see [operations.md](operations.md) |

## Conventions

- The CLI and `colophon/core` use the standard library only, so the CLI runs on
  any machine's python 3.11+. Server dependencies are the `server` extra.
- Tests never touch the real entries repo. The fixtures make a scratch repo
  and a bare remote in `tmp_path`; the CLI tests run against the app in process
  and with git's global config hidden. Pointer skills always go to a scratch
  folder.
- Every write path is validated in full before the disk is touched. A git
  failure part way through rolls the touched folders back to HEAD.
- The server's own routes start with `_` or carry a file suffix, which no name
  can, so only `index`, `search` and `health` are reserved project names, and
  `icon`, `history`, `profile`, `seen` and `docs` reserved doc names.
- A new doc type is one entry in `TYPES` in `core/doc.py`: its sections and
  whether it makes a pointer skill. Nothing else names the types.
- A new access point is one line in `ACCESS` in `core/profile.py`: its name
  and badge label. Validation, the CLI, the badges and the filter read it.
- Tests that touch the migration build the old layout by hand in a scratch
  repo (`tests/test_migrate.py`).
