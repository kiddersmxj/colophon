# AGENTS.md: colophon

Colophon serves the how-to for each of the owner's things. This repo is the
code; the content lives in a separate entries repo and is written only by the
server.

> Claude Code reads `CLAUDE.md`; that file is a symlink to this one. Keep
> editing `AGENTS.md`.

## The rules

- **Never show a guessed fact.** Every fact Colophon displays or serves comes
  from a real source (the service directory's data, the stored profile, git)
  or is not shown. Never build one from a name, give it a default, or infer
  it. There are no exceptions.
- **SPEC.md is the agreed design.** Build to it. A real gap gets the smallest
  sensible choice, recorded in SPEC.md under "Choices made while building".
- **Never commit to the entries repo, and never push test content to it.**
  Tests use a scratch repo and a scratch bare remote; `make dev` uses a local
  repo with pushing off.
- **The CLI and `colophon/core` stay standard library only**, so the CLI runs
  on any machine's python.
- **No sudo in the data path.** The server is a user service under the
  deploying user; `make lint-sudo` fails if sudo appears in the Makefile or
  the unit.
- **Nothing owner-specific is committed.** Hosts, addresses and repos go in
  the ignored `local.mk` and the server's env file on the prod host.
- **Projects never mention Colophon.** Nothing the CLI does may write to a
  project except the `.colophon` marker, which git ignores globally.
- **Pointer skills are generated.** Change the generator in `core/skill.py`,
  never a skill on disk. `skills sync` must never touch a skill it did not make.
- **Colophon's own skills** are `.claude/skills/colophon` and
  `colophon-write`. Keep them true when the CLI or the API changes.

## Docs

Keep these current as part of each change:

- `docs/README.md`: the status table.
- `docs/development.md`: layout, commands, conventions.
- `docs/operations.md`: deployment, endpoints, gotchas with their symptoms.
- `docs/roadmap.md`: what is missing, in order.

## Commits

Commit each finished step, staging paths by name, and push to origin main.
Another agent may be working in this tree (art in `art/` and `assets/`); never
stage what is not yours.
