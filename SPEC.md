# Colophon

Colophon holds the short "how to use this" for each of your services, programs and
devices, and serves it to agents and to people. It is the page at the back of the book:
what the thing is, where it lives, how to connect to it, and nothing else.

## Never a guessed fact

Colophon never shows a derived or guessed fact. Every fact it displays or
serves comes from a source: the service directory's own data, the profile as it was stored,
or git. If the source does not say it, Colophon does not show it. No fact is
built from a name, filled with a default, or inferred from another fact.
Cosmetic defaults that state nothing about the thing are allowed: a doc's
title from its name, the brand placeholder logo, the name `colophon init`
suggests from the folder.

## What it is not

- **Not the project's docs.** Specs, roadmaps, operations notes and design reasoning
  stay in each project's own repo. Colophon only has what someone *using* the thing
  needs.
- **Not monitoring.** No health checks and no status. A project links to its own
  monitoring for live state.
- **Not visible in any project.** No project mentions Colophon in its code, docs,
  README, agent instructions or ignore file. The only local trace is a marker file
  that git never sees (see below).

## Two repos

| Repo | Holds |
|------|-------|
| `colophon` | The server, CLI, web UI, skills and this spec |
| `colophon-entries` (the entries repo, any name) | The content: one folder per project. Only the server writes to it |

They are separate so content changes never need a code change and every project has
its own plain git history. Agents and people never commit to the entries repo
directly. Every write goes through the API, and the server makes the commit.

## Projects and docs

A **project** is one thing someone might use: a program, a service, an API, a
CLI, an app, a device. It does not have to be a repo. **Docs** sit under a
project, as many as it needs, each with a type.

```
colophon-entries/
  jukebox/
    project.toml             the profile, always present
    icon.png                 always present
    docs/
      jukebox.toml           a doc's fields
      jukebox.md             its body
      jukebox-artist.toml
      jukebox-artist.md
```

Every project has an icon: the project's own logo or app icon. A project with
no real logo of its own uses another real image it already ships, such as the
avatar it sends notifications with; an icon is never invented.
The server refuses to create a project without an icon.
`colophon init` takes the icon the service directory already holds for the
service when there is one, and otherwise asks for a file. Docs have no icon of their own.

The web UI shows an icon at 56 pixels on a grid card and 88 on the project's
page (64 on a narrow screen), and rounds its corners itself. That is app icon
size, not tab size: give Colophon the full mark, not the cropped close-up a
project keeps for its 16 to 32 pixel favicon.

A project with no docs is still useful: a page saying what the thing is and
where it lives, right for web UIs and things only the owner uses.

### Profile

```toml
name     = "jukebox"                 # folder name, lowercase, stable
title    = "Jukebox"
summary  = "A music library: songs, mixes and their stems over HTTP"
kind     = "service"                 # service | program | app | device | library
access   = ["cli", "api", "web"]     # optional; every access point it really has
repo     = "~/devel/jukebox"         # optional; where it is developed
remote   = "git@github.com:you/jukebox.git"   # optional
machine  = "server-1"                # optional; filled from the directory when it has a node
roster   = "jukebox"                 # optional; the service's name in the directory
updated  = 2026-11-19
```

`kind` says what the thing is: a `service` runs and listens, a `program` is
something you run. `access` says how it is reached, as many as it has: `cli`, `api`, `mcp`, `web` (a UI for people). A service with a CLI is
`kind = "service"` with `access = ["cli", "api"]`. The access points are a
registry in the code, a name and a badge label each, so a new one (an `sdk`, a
`socket`) is one line there. Like every fact, an access point is listed only
when its source shows it: a CLI entry point in the packaging, an API router, an
MCP server, a web UI that is served. No default, and none inferred from `kind`.

Directory facts (address, tag, machine) are read from the service directory,
not typed in. A project with a `roster` name shows them on every read. Facts that belong to
one doc only, such as a second machine it runs on, go in that doc's body.

### The service directory

An optional service that knows where each service runs. The profile field and the
code call it `roster`, after the first directory Colophon was used with; stored
profiles keep that name. Any HTTP service that answers this will do:

```
GET /services       a list of {service, url, node, tag, host, expose, sensitive}; no token
GET /read/icons     {service: {data: <base64 image>}}; a bearer token
```

With `COLOPHON_ROSTER_URL` set, a project with a `roster` name shows the address,
machine, tag and whether it is sensitive on every read, and `colophon init` can take
the service's icon (with a reader token in `COLOPHON_ROSTER_TOKEN`). With it unset,
the feature is off: a project shows only what its own profile says, and its `roster`
name is shown as stored. The directory being down never breaks a read: the facts are
left out and the page says so.

### Docs

```toml
name     = "jukebox-artist"          # unique in the project; a skill's is unique everywhere
type     = "skill"                   # skill | guide
title    = "Jukebox artist"          # optional; defaults to the name made readable
summary  = "Publish a service's own mixes under its own artist"
trigger  = "Publish a service's own mixes ... Use when ..."   # skills only
written_against = "a1b2c3d"          # repo commit the doc was last written against
updated  = 2026-11-19
```

The type decides what a doc needs and gets:

| type | trigger | pointer skill | for |
|---|---|---|---|
| skill | required | yes, named after the doc | a surface another program or agent uses: an API, a CLI, a connection, a protocol |
| guide | none | no | a how-to worth keeping that nothing reaches for by trigger |

Types are a registry in the code, each naming its body sections and whether it
makes a pointer skill, so a new type is one entry there and nothing else is
reshaped.

`trigger` becomes the description of the doc's pointer skill, so it says what
the thing is and when to reach for it, never how to use it.

### Body template

A doc's body uses these sections, in this order, and drops any that do not
apply. Both types use the same six for now.

1. **What it is**: two or three lines.
2. **Where**: address, machine, how it is reached.
3. **Auth**: what a caller needs, or "none".
4. **Quick start**: the smallest thing that works.
5. **Reference**: commands, endpoints, fields.
6. **Rules and gotchas**: what must not be done, and failures with their symptoms.

The model for length and tone is a tldr page, not a manual. Most docs should fit
on one screen. Anything longer belongs in the project's own docs, with the doc
pointing to the endpoint that serves it (such as an OpenAPI page), never to a
file in the repo.

## The marker file

A folder that is a Colophon project has a `.colophon` file at its root naming
the project:

```
project: jukebox
server: https://colophon.example.lan
```

The CLI writes it when a project is created or linked. An agent checks for this
file instead of asking the API. It names the project, never a doc, so one
marker covers every doc the project has. Markers from before docs existed said
`entry:`; the CLI still reads them.

It is ignored through the global git excludes file on each machine, which lists
`.colophon` once for every repo. No project's own ignore file
mentions it. A folder that is not a repo simply has the file.

## Pointer skills

Each skill doc gets a generated Claude skill under the doc's name. Its
description is the doc's `trigger`, so Claude reaches for it exactly as it did
for the old hand-written skill. Its body says only: fetch this doc from
Colophon and follow it, with its address, `/<project>/<doc>.md`.

The how-to therefore exists in one place. The only copied text is the trigger, which
rarely changes, and a slightly old trigger still leads to the current doc.

`colophon skills sync` writes pointer skills straight into `~/.claude/skills` on the
machine where agents run. When `COLOPHON_SKILLS_HOST` or `colophon.conf`'s `skills_host:` names one machine, sync writes
there only, so no other machine collects stray copies. Anywhere else, a pointer skill
can be pulled by hand with `colophon skills get <name>` or from `GET /<project>/<doc>/skill.md`. Pointer
skills are never edited by hand. Guides get no pointer skill.

### What moves in

A hand-written skill that is a service's how-to becomes a skill doc, replaced by a
pointer skill of the same name and description. It sits under its project: a music
library with two such skills (`jukebox`, `jukebox-artist`) is one project holding both.

Skills that are procedures, safety rules or ways of working rather than a service's
how-to stay ordinary skills: a recovery runbook, an access request procedure, a
handoff routine.

A kept skill's thing may still have a project in Colophon so it is listed.

## Colophon's own skills

- **colophon**: find a project and fetch its docs. Its description carries the broad
  trigger: use whenever a task touches one of the owner's services, devices or tools,
  or names one the agent does not recognise. Reading the index is one small request.
- **colophon-write**: create or link a project, write the marker file, and write or
  update the profile and docs. It holds the judgment about what needs documenting:
  a user-facing change to an API, CLI or connection updates the doc that covers it;
  a UI-only change rarely needs anything.

Plus one line in the owner's global agent instructions, which is what makes an agent think
of it at all:

> When a project has a `.colophon` file and this session changed how someone uses or
> connects to it, update its Colophon docs with the colophon-write skill. Never
> mention Colophon inside the project.

## Server

Runs on one host, behind whatever gives it its address (a reverse proxy, or
`tailscale serve` on a tailnet), at `COLOPHON_PUBLIC_URL`. It holds a checkout of
the entries repo, commits each write, and pushes.

### Reads

Every page is available as HTML for people and as plain markdown or JSON for agents.

```
GET /index.md                      every project, one line each, its docs indented under it
GET /index.json
GET /<project>                     web page: the profile and its docs
GET /<project>.md                  profile, directory facts, one line per doc with its URL
GET /<project>.json
GET /<project>/icon
GET /<project>/history             commits touching the project
GET /<project>/history.md          the same, one line per commit
GET /<project>/<doc>               web page
GET /<project>/<doc>.md            the doc, with a short header naming its project
GET /<project>/<doc>.json
GET /<project>/<doc>/skill.md      the generated pointer skill, skills only
GET /<project>/<doc>/history       commits touching the doc, through moves
GET /<project>/<doc>/history.md    the same, one line per commit
GET /skills.json                   every skill doc: name, project, description
GET /search?q=
```

### Writes

```
POST   /                           create a project (profile and icon)
PUT    /<project>/profile          replace or merge profile fields
PUT    /<project>/icon
DELETE /<project>                  only once it has no docs
POST   /<project>/docs             add a doc (fields and body)
PUT    /<project>/<doc>            replace the body
PUT    /<project>/<doc>/meta       merge the doc's fields
POST   /<project>/<doc>/move       move it to another project
DELETE /<project>/<doc>
```

The server validates the profile, the doc's fields and the body's section headings,
serialises writes, and commits each one with the caller as author. When the server is
fronted by `tailscale serve`, the caller is the tailnet identity Tailscale gives it
(person and machine), so history shows who changed what from where. Without that, a
write is recorded as local, under the host's name.

### Access

Private network only (a tailnet or a LAN), with no auth beyond reaching it. If it
is ever opened up, reads go out through a tunnel and writes stay on the private
network.

## CLI

```
colophon list                          the index
colophon get [<project>[/<doc>]]       a project, or one doc, as markdown
colophon search <words>
colophon history [<project>[/<doc>]]   commits to a project, or one doc
colophon init [<project>]              create or link a project for this folder; writes .colophon
colophon set <field> <value> [--doc d] a project field, or a doc's
colophon icon <file>
colophon add <doc> [file] --type ...   add a doc (skill needs --trigger)
colophon edit <doc>                    open a doc in $EDITOR, push on save
colophon push <doc> [file]             replace a doc's body from a file or stdin
colophon mv <doc> <project>            move a doc
colophon rm <doc>                      remove a doc
colophon delete <project>              remove a project with no docs
colophon stale                         in a project: commits since each doc was written
colophon skills sync                   regenerate pointer skills into ~/.claude/skills
colophon skills get <name>             print one pointer skill, to install elsewhere by hand
```

Inside a folder with a `.colophon` file, commands default to that project, and a
doc is named `<doc>`; anywhere else it is `<project>/<doc>`.

The CLI has no built-in server. It uses `--server`, then `$COLOPHON_URL`, then the
marker's `server`, then the `server:` line of `colophon.conf` in the checkout (read at
run time, so it holds in scripts, services and shells that skip the user's
profile), and refuses with "no server" when none is set.

## Staleness

Each doc records the repo commit it was written against. `colophon stale` counts
commits since then in the local repo, per doc. Whenever the CLI runs in a project it
reports the current commit and each doc's count to the server, so the web UI can show
"about 40 commits behind" on a doc from the last time anyone looked. It is a hint for
the owner, not a prompt that nags agents.

## Web UI

A grid of projects with icons, filter by kind, access point and machine. Each
card and each project page marks its access points with small badges. A project's
page shows its profile, directory facts and history, and lists its docs with their type and one-line
summary. A doc's page renders it with its facts and history alongside. Editing in the
browser uses the same write API. It should be good to look at, with no headlines,
taglines or explaining text.

## Decided

- **Host**: one machine, as a user service.
- **Directory facts**: read from the service directory's API, when there is one.
- **Reach**: every machine on the private network reaches it, with no per-machine
  access list, so agents on any machine can read and write.
- **Entries repo**: a private GitHub repo, pushed by the server after each commit.
- **Server language**: Python.
- **No `api` or `cli` kind** (2026-11-19): they said how a thing is reached,
  which is access. `program` took their place. A profile still
  storing an old kind reads and shows as stored; the next write must pick a
  listed kind, and the edit form offers no default for it.

## Choices made while building

Gaps the design left open, closed with the smallest choice that works.

- **Staleness reports**: the CLI sends `POST /<project>/seen` with the project's
  commit and, per doc, how many commits it is past `written_against`. The
  server keeps this in its own state, not in the entries repo: it is not content
  and must not make a commit every time someone runs the CLI.
- **written_against**: `PUT /<project>/<doc>?written_against=<sha>` (or the same
  on `POST /<project>/docs`) sets it in the same commit as the body. The CLI
  fills it from the project's HEAD.
- **Trigger**: a skill cannot be written without one, since its pointer skill
  needs it; a guide carries none, and turning a skill into a guide drops it.
  One line, at most 1024 characters, the cap on a skill description.
- **Skill names**: unique across all projects, because each is a pointer
  skill's name in one flat skills folder. Guide names need only be unique in
  their project.
- **Body checks**: `## What it is` is required; the other five sections are
  optional but must keep their order; no `#` title, no text before the first
  section; `###` is free. Headings in code blocks do not count.
- **Icon**: a square PNG, 32 to 2048 pixels, at most 1 MB. The server converts
  whatever it is given or finds in the directory: SVG is rendered, ICO gives its
  largest image, and a non-square image is padded onto a transparent square.
  The conversion is server side, so the CLI stays standard library.
- **Names**: lowercase letters, digits and hyphens, at most 40. Only `index`,
  `search` and `health` are reserved for projects; `icon`, `history`,
  `profile`, `seen` and `docs` for docs. The server's other routes start with
  `_` (`/_roster/<service>`, `/_static/`, `/_brand/logo`, `/_docs`) or have a
  file suffix, so no name can collide with them.
- **Profile writes** merge by default; `null` or `""` clears an optional field;
  `?replace=true` replaces the whole profile.
- **Search**: `/search?q=` answers markdown like the index; `/search.json?q=`
  answers JSON.
- **Caller**: when fronted by `tailscale serve`, the person and machine come
  from `tailscale whois` of the forwarded address, falling back to the
  `Tailscale-User-*` headers. The person is the commit author; the machine is a `Via:` trailer in
  the commit message. A machine the tailnet does not name is left out of the
  commit, never written as a placeholder.
- **Directory service at `colophon init`**: from `--roster` or the project's own
  `.roster` file, nothing else. A directory service that only shares the project's
  name is mentioned in one line, not taken. `kind` has no default.
- **`colophon push`** and **`colophon add`** with no file read the body from stdin.
- **`skills sync`** never replaces or removes a skill it did not generate (it
  marks its own), and removes its own when the doc is no longer a skill.
- **Old pointer skills**: `GET /<skill>.md`, where no project has that name,
  serves the skill doc of that name, so a pointer skill written before docs
  existed still finds its doc until the next `skills sync`.
- **Migration**: the server turns the old layout (one `entry.toml` and an
  optional `guide.md` per thing) into projects at startup, in one commit: each
  entry becomes a project of the same name, and its guide a doc of the same
  name, moved with git so the doc's history reaches back to the guide. The
  regrouping into fewer projects was then done through the API, one commit per
  move, so each step is in the history.
- **Doc titles**: optional. Without one, the title is the name with spaces for
  hyphens and a capital first letter (`jukebox-artist` gives `Jukebox artist`).
  `colophon add` stores that default, so the doc's fields show it.
- **No commit to record**: pushing from a folder whose repo has no commits
  writes the body with no `written_against`, and the CLI says so in one line.
  `colophon init` says in one line when the folder has no git remote, since the
  profile's `repo` is then only a path on that machine.
- **Colophon's own doc is a guide.** A skill doc named `colophon` would clash
  with the hand-written `colophon` skill, which carries the broad trigger and
  stays, so `skills sync` would skip it every time. The doc became a guide on
  2026-11-19.
- **Access points**: stored in registry order, duplicates dropped. Text
  (`cli,api`, from the CLI or a form) is split on commas or spaces. An empty
  list clears the field. The index line is `name (kind; cli, api): summary`,
  and an index row's `access` is `null` when the profile states none. The grid
  offers a filter only for access points some project has; choosing several
  shows projects that have all of them.
- **Hosting**: a user service under the deploying user on the prod host, port
  8796, so nothing needs sudo. The entries repo is pushed with a deploy key
  for that repo alone.
- **Nothing owner-specific in the repo**: the CLI has no default server, the
  server's public URL defaults to its own bind address, the directory is off
  unless `COLOPHON_ROSTER_URL` is set, and `skills sync` writes on any machine
  unless `COLOPHON_SKILLS_HOST` names one. The owner's hosts and repos live in
  an ignored `local.mk`, and the server's settings in its env file on the
  prod host, written by `make prod-env`.
- **A config file in the checkout**: `colophon.conf` beside `bin/` (`server:`
  and `skills_host:` lines, ignored by git, `colophon.conf.example` committed)
  is read at run time, after the flag, the environment and the marker. An
  environment variable set in a shell profile is missed by scripts, services
  and non-interactive shells; a file is not. `make deploy` copies it to prod.
