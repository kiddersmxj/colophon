# colophon

The short "how to use this" for each of your services, programs and devices,
served to agents and to people. The page at the back of the book: what the
thing is, where it lives, how to connect to it, and nothing else.

This repo holds the server, the CLI, the web UI and the skills. The content is
in a separate git repo, the entries repo, which only the server writes to.

```sh
make install && make test      # venv and the suite
make dev                       # a local server on :8796
make cli-install               # colophon on PATH
export COLOPHON_URL=http://127.0.0.1:8796
colophon list                  # the index
colophon get jukebox           # a project and its docs
colophon get jukebox/jukebox-artist   # one doc
```

To run it for real, copy `local.mk.example` to `local.mk` and
`colophon.conf.example` to `colophon.conf`, fill them in, and follow
[docs/operations.md](docs/operations.md).

- [SPEC.md](SPEC.md): the design.
- [docs/](docs/README.md): status, development, operations, roadmap.
