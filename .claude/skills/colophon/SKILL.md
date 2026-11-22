---
name: colophon
description: "Look up how to use one of the owner's services, programs, APIs, CLIs or devices: what it is, where it lives, how to connect. Use whenever a task touches one of the owner's own tools or machines, or names one you do not recognise (a service, a host, a command, a device), before reading its repo or guessing."
---

# colophon

Colophon holds the short how-to for each of the owner's things. Read it from
the server; do not read the colophon or entries repos.

The server address is `$COLOPHON_URL`, or else the `server:` line of the
`.colophon` file at the project's root, or else the `server:` line of
`colophon.conf` in the colophon checkout the CLI runs from. No auth to read. Below, `$C` is that address:

```sh
C=${COLOPHON_URL:-$(sed -n 's/^server: //p' .colophon "$(dirname "$(readlink -f "$(command -v colophon)")")/../colophon.conf" 2>/dev/null | head -1)}
```

If neither is set, say so rather than guessing an address.

## Find the thing

```sh
curl -s "$C/index.md"          # every project and its docs
curl -s "$C/search?q=music"    # by words
```

Each project is one line, `name (kind; access points): summary`, with its
docs indented under it as `doc (type): summary URL`. Access points say how
it is reached: `cli`, `api`, `mcp`, `web`; a project lists only those it has.
The index is one small request; read it rather than guessing a name.

## Read it

```sh
curl -s "$C/<project>.md"        # profile and its list of docs
curl -s "$C/<project>/<doc>.md"  # one doc
```

The project page has the address, machine, directory facts and repo, then one
line per doc with its URL. Open the doc that fits the task and follow it, the
Rules and gotchas above all. Docs have sections: What it is, Where, Auth,
Quick start, Reference, Rules and gotchas.

A doc's type is **skill** (it has its own pointer skill under the same name)
or **guide** (a how-to with none). A project with no docs only says what the
thing is and where it lives.

`.json` beside any of these gives the same as data. `colophon get <project>`
and `colophon get <project>/<doc>` print them.

## Who changed it, and when

```sh
colophon history [<project>[/<doc>]]   # defaults to the .colophon project
curl -s "$C/<project>/history.md"
curl -s "$C/<project>/<doc>/history.md"
```

One line per commit, newest first: hash, date, who, from which machine, what.
A doc's history follows it through moves. Without `.md` the same comes as JSON.

## In a project

A folder with a `.colophon` file is a Colophon project; the file names it:

```
project: jukebox
server: https://colophon.example.lan
```

Check for that file instead of asking the server. If the session changes how
someone uses or connects to the thing, update its docs with the
`colophon-write` skill.

## Rules

- A doc is current; your memory of it is not. Fetch it each time.
- If a doc and the code disagree, the code is right and the doc is stale: say
  so, and fix the doc with `colophon-write` if this session owns the change.
- Never mention Colophon inside a project: not in its code, docs, README, agent
  instructions or ignore files.
