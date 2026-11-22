# colophon docs

| doc | for |
|---|---|
| [../SPEC.md](../SPEC.md) | what it is, and why it is built this way |
| [development.md](development.md) | layout, commands, conventions |
| [operations.md](operations.md) | how it is deployed, endpoints, gotchas |
| [roadmap.md](roadmap.md) | what is missing, in order |

## Status (2026-11-22)

| part | state |
|---|---|
| Server | FastAPI, a user service on the prod host's loopback (`127.0.0.1:8796` by default), reached through whatever fronts it |
| Model | one project per program, service, API or device, with docs under it; doc types `skill` (pointer skill) and `guide` (none), a registry so more can be added |
| Storage | a checkout of the entries repo, `<project>/project.toml`, `icon.png`, `docs/<doc>.toml` and `.md`; one commit per write, author is the caller, pushed after each commit; a failed push is retried on the next write and at startup |
| Validation | profile and doc fields, body sections and order, skill triggers, skill names unique across projects, square PNG icon (SVG, ICO and non-square images are converted); every problem named in one 422 |
| Caller identity | when fronted by `tailscale serve`: whois of the forwarded address, falling back to the `Tailscale-User-*` headers, machine recorded as a `Via:` trailer. Otherwise the write is recorded as local, under the host's name |
| Service directory | optional, off unless `COLOPHON_ROSTER_URL` is set. `GET /services` with no token, cached 60 s; the tag is shown only when the directory gives one; reads work with it down. Icons from `/read/icons` with a reader token, converted to square PNGs |
| CLI | every command in the spec, `history` included; stdlib only. Server from `--server`, then `$COLOPHON_URL`, then the `.colophon` marker, then the checkout's `colophon.conf`; refuses without one. Says when a push records no commit and when init finds no git remote |
| Marker file | `project: <name>`, written by `colophon init`; old `entry:` markers still read; meant to be ignored by the global git excludes file; the CLI warns when git does not ignore it |
| Pointer skills | generated from a skill doc's trigger, named after the doc; written into `~/.claude/skills` by `skills sync` on any machine, or only on `COLOPHON_SKILLS_HOST` (or `colophon.conf`'s `skills_host:`) when that is set; sync never touches a hand-written or symlinked skill |
| Access points | `access` in the profile: cli, api, mcp, web, a registry so more can be added; badges on cards and project pages, a filter in the grid |
| Web UI | grid of projects with filters by kind, access point, machine and words; project page with its docs, directory facts and history; doc page with staleness; in-browser editing on both |
| Logo and favicons | served from `assets/` |
| Skills | `colophon` and `colophon-write`, hand-written in `.claude/skills/`, to be linked into `~/.claude/skills` where agents run |
| Deployment | `make` targets read the owner's values from an ignored `local.mk`; `make prod-env` writes the server's settings into its env file on the prod host |
| Tests | 115 passing (`make test`) |
