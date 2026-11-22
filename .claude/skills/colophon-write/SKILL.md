---
name: colophon-write
description: "Create, link or update a Colophon project or its docs: the profile, the icon, a skill or guide doc, and the project's .colophon marker. Use when a project has a .colophon file and this session changed how someone uses or connects to it, when asked to add something to Colophon or write a doc for it, or when a doc turned out to be wrong."
---

# colophon-write

Every write goes through the `colophon` CLI (or the server's API). The server
validates it, commits it with your identity as author (your tailnet identity
when it is fronted by `tailscale serve`), and pushes. Never commit to the
entries repo yourself.

The CLI is `colophon` where it has been installed; elsewhere run
`bin/colophon` from a colophon checkout. It finds the server from `--server`,
then `$COLOPHON_URL`, then the `.colophon` marker, then the `server:` line
of the checkout's `colophon.conf`, and refuses with "no server" when none is set: ask the owner for the address rather than guessing
one. Inside a folder with `.colophon` it defaults to that
project. A doc is named `<doc>` there, or `<project>/<doc>` from anywhere.

## The shape

- A **project** is one program, service, API or device: icon, title, summary,
  kind, access points, machine, roster (its name in the service directory),
  repo. It is what the grid shows.
- **kind** is what the thing is (service, program, app, device, library).
  **access** is how it is reached, every one it has: `cli`, `api`, `mcp`,
  `web` (a UI for people). A service with a CLI is kind `service`, access
  `cli,api`.
- **Docs** sit under a project, as many as it needs. Each has a type:
  - **skill**: has a trigger and gets a generated pointer skill named after
    the doc. For a surface another program or agent uses: an API, a CLI, a
    connection, a protocol.
  - **guide**: a how-to with no pointer skill. For anything worth writing
    down that an agent would not reach for by trigger.
- A project with no docs is fine: it says what the thing is and where it lives.

Facts specific to one doc (another machine, another port) go in that doc's
body, not in the project profile.

## Does this change need a write?

| The session changed | Write |
|---|---|
| An endpoint, command, flag, field, address, port or auth | Update the doc that covers it |
| How something is reached (new host, new name, moved into the directory) | Update the doc; directory facts update themselves |
| What the thing is for, its name or its kind | Update the project profile |
| Added or removed a CLI, an API, an MCP server or a web UI | `colophon set access ...` |
| A new surface others use | A new doc |
| Only a web UI, internals, refactors, tests | Nothing, usually |
| Something nobody outside the project touches | Nothing |

When in doubt, leave it. A doc that says less but is right beats one that
narrates every change.

## A new project

From the project's root:

```sh
colophon init --title "Jukebox" --summary "A music library: songs, mixes and stems over HTTP" \
  --kind service --access api,web --icon path/to/logo.png
```

- `kind` is one of service, program, app, device, library. A service runs
  and listens (it has a port, the directory may give it an address). A program is
  something you run and it exits, such as a CLI tool or a script. How it is
  reached goes in `--access`, not in the kind.
- `--access` lists every access point the project really has, and nothing
  else. Check each one this session before setting it:
  - `cli`: a command the project ships (a `[project.scripts]` entry, a `bin`
    in `package.json`, an installed `bin/` script). `python -m` for the
    server or a Makefile target is not one.
  - `api`: an HTTP router with endpoints meant for programs.
  - `mcp`: an MCP server the project runs.
  - `web`: a UI for people that is served, at the directory's address or another.
    A phone app is not `web`.
  Leave out what you could not check, and say so. On a terminal, init asks;
  a blank answer sets none.
- The name defaults to the folder's; give one as `colophon init <name>`.
- **An icon is required.** Use the project's own logo or app icon: its app
  icon, favicon, brand assets or art kit. If the service directory holds one,
  init uses it. PNG, SVG or ICO; the server makes it a square PNG. If the
  project has no logo of its own, use another real image it already ships
  (such as the avatar it sends notifications with). Never invent a logo.
- **Icons show at 56 pixels** on the grid and 88 on the project page (64 on a
  narrow screen), with the corners rounded by Colophon. That is app icon
  size, not tab size: use the project's full mark, never the cropped
  close-up made for a 16 to 32 pixel favicon.
- `repo` and `remote` come from this folder's git. The directory service
  comes only from `--roster` or the project's `.roster` file; init never
  assumes a directory service is this project because the names match, it
  only says so. Pass `--roster` only once the directory's `/services` shows
  the service runs this project. If init notes there is no git remote, `repo` is only a path on this
  machine; run `colophon set remote <url>` once the repo has one.
- If the project already exists, init only links this folder to it.

init writes `.colophon` (`project: <name>`). Git should ignore it through the global
excludes file on the machine. **Never add it to the project's own `.gitignore`**,
and never mention Colophon anywhere in the project. If the CLI warns that git
does not ignore the file, tell the owner rather than fixing it in the project.

## Adding a doc

```sh
colophon add jukebox-artist artist.md --type skill \
  --summary "Publish a service's own mixes under its own artist" \
  --title "Jukebox artist" \
  --trigger "Publish a service's own mixes into the music library. Use when a service needs to ..."
colophon add setup setup.md --type guide --summary "Set it up on a new machine"
```

With no file, `add` reads stdin, or opens `$EDITOR` on the template.

- `summary` is one line, shown beside the doc on the project page.
- `--title` is optional for both types. Without it the title is the name with
  spaces for hyphens and a capital first letter: `jukebox-artist` becomes
  `Jukebox artist`. Give one when that reads wrong, such as a brand or an
  acronym (`--title "Lights API"`).
- A skill's `trigger` becomes its pointer skill's description. It says what the
  thing is and when to reach for it, **never how to use it**. One line, under
  1024 characters. A skill's name is its pointer skill's name, so it is unique
  across every project and must never be renamed once agents rely on it.

## Writing the body

```sh
colophon edit jukebox-artist             # opens it in $EDITOR, pushes on save
colophon push jukebox-artist new.md      # or from a file, or stdin with no file
```

Sections, in this order, as `##` headings, dropping any that do not apply:

1. `## What it is`: two or three lines. Required.
2. `## Where`: address, machine, how it is reached.
3. `## Auth`: what a caller needs, or "none".
4. `## Quick start`: the smallest thing that works.
5. `## Reference`: commands, endpoints, fields.
6. `## Rules and gotchas`: what must not be done, and failures with their symptoms.

No `#` title (the doc's title gives it), nothing before the first section,
`###` inside a section as needed. The model is a tldr page: most docs fit on
one screen. Anything longer belongs in the project's own docs; point at the
endpoint that serves it (such as an OpenAPI page), never at a file in a repo.

Write from what the code does now, not from memory or from the old doc. Push
from inside the project so the doc records the commit it was written against;
`colophon stale` then shows how far the project has moved since. If the repo
has no commits yet, the CLI says the doc records none; push again after the
first commit.

## Pointer skills

A skill doc's pointer skill is written by `colophon skills sync`, into
`~/.claude/skills` on the machine where agents run. If `COLOPHON_SKILLS_HOST`
or a `skills_host:` line in the checkout's `colophon.conf` names a machine, it
installs only there. Run it there after adding a skill
doc, renaming one, or turning a guide into a skill. After `colophon rm`,
`colophon delete`, or turning a skill into a guide, the next sync removes the
stale pointer by itself; nothing else needs deleting.

Anywhere else, print one with `colophon skills get <name>` and install it by
hand. Sync never replaces a hand-written skill: if it prints `skipped <name>`,
a skill doc has the same name as a hand-written skill. Rename the doc or make
it a guide; do not delete the hand-written skill without asking the owner.

## Other writes

```sh
colophon set summary "..."                        # a project field; an empty value clears it
colophon set access cli,api,web                   # every access point it has; "" clears
colophon set summary "..." --doc jukebox-artist   # a doc's field (title, summary, trigger, type)
colophon icon logo.svg
colophon mv jukebox-artist other-project          # move a doc; its history follows
colophon rm setup                                 # remove a doc
colophon delete old-project                       # remove a project with no docs
colophon get                                      # read back what is there now
colophon history [<project>[/<doc>]]              # who changed what, newest first
```

A refusal (422) says exactly what is wrong. Fix that and push again; do not
work around it by renaming sections or trimming the trigger into nonsense.

## Rules

- Never commit to the entries repo, and never edit a pointer skill by hand:
  both are generated.
- Never mention Colophon inside a project.
- **Never guess a fact.** Every fact you write (a machine, address, port,
  command, kind, access point, remote, who can reach it) must come from a source you checked
  this session: the service directory's `/services` or its policy, the
  project's own git, its code or docs, or the running thing. If you cannot check it, leave it out.
  A doc that says less beats one that is wrong.
- Address, machine and tag come from the service directory; leave them out
  of the profile when the directory has the service.
