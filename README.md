# colophon

The short "how to use this" for each of your services, programs and devices,
served to agents and to people. The page at the back of the book: what the
thing is, where it lives, how to connect to it, and nothing else.

This repo holds the server, the CLI, the web UI and the skills. The content is
in a separate git repo, the entries repo, which only the server writes to.

## Before you start

- **Keep it on a private network.** There is no login: anyone who can reach
  the server can read and change every page. Run it on a LAN, a tailnet or
  behind a VPN, never open to the internet.
- **You need** python 3.11+ and git. The server also needs libcairo, to turn
  SVG icons into PNGs.
- **The deploy steps assume** a Linux server you reach over ssh, running
  colophon as a systemd user service, with the entries repo on GitHub (`gh`
  adds its deploy key). The server itself runs anywhere python does; only the
  Makefile's prod targets make these assumptions.
- **Pointer skills are for Claude Code.** Everything else works for any agent
  or person over HTTP and the CLI.

## Try it locally

In one terminal, a server with a throwaway entries repo in `./var`:

```sh
make install && make test      # venv and the suite
make dev                       # a local server on 127.0.0.1:8796
```

In another, the CLI. `colophon init` runs inside the project's own git
folder; here a scratch one stands in for it:

```sh
make cli-install                         # links colophon into ~/.local/bin
export COLOPHON_URL=http://127.0.0.1:8796
cp assets/app-icon.png /tmp/icon.png
mkdir /tmp/demo && cd /tmp/demo && git init -q
colophon init --title Demo --summary "A demo service" --kind service \
  --access api --icon /tmp/icon.png
printf '## What it is\n\nA demo.\n\n## Quick start\n\nCall it.\n' \
  | colophon add demo-api --type skill --summary "Use the demo API" \
      --trigger "The demo API. Use when a task needs the demo."
colophon list                  # the index
colophon get demo              # the project and its docs
colophon get demo/demo-api     # one doc
```

Then open http://127.0.0.1:8796 for the web UI.

## Run it for real

1. Copy `local.mk.example` to `local.mk` and `colophon.conf.example` to
   `colophon.conf`, and fill them in. Git ignores both.
2. Follow [docs/operations.md](docs/operations.md): a deploy key for the
   entries repo, the first setup on the server, its settings, then
   `make deploy`. Every later update is `make deploy`.
3. On each machine that uses it, run `make cli-install` from a checkout with
   your `colophon.conf`. For Claude Code, link `.claude/skills/colophon` and
   `.claude/skills/colophon-write` into `~/.claude/skills`, and run
   `colophon skills sync` after adding skill docs.

## More

- [SPEC.md](SPEC.md): the design.
- [docs/](docs/README.md): status, development, operations, roadmap.
- [LICENSE](LICENSE): MIT.
