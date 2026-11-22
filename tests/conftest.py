"""Shared fixtures. Every test works in a scratch git repo with a scratch bare
remote; nothing here can reach the real colophon-entries."""

from __future__ import annotations

import struct
import subprocess
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from colophon.server import api, config
from colophon.server.roster import Roster
from colophon.server.store import Caller, Store


def make_png(w: int = 64, h: int | None = None) -> bytes:
    h = w if h is None else h

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    raw = b"".join(b"\x00" + b"\x1f\x5f\xd1" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


@pytest.fixture(autouse=True)
def _scratch_skills_dir(tmp_path: Path, monkeypatch):
    """No test may write to the real ~/.claude/skills, whatever it runs."""
    from colophon import cli
    monkeypatch.setattr(cli, "SKILLS_DIR", tmp_path / "home-skills")
    monkeypatch.setattr(cli, "SKILLS_HOST", "")
    # Nor read the checkout's own settings, which would point at a real server.
    monkeypatch.setattr(cli, "CONFIG_FILE", tmp_path / "colophon.conf")
    monkeypatch.delenv("COLOPHON_URL", raising=False)


@pytest.fixture
def png() -> bytes:
    return make_png()


@pytest.fixture
def remote(tmp_path: Path) -> Path:
    """A scratch bare repo standing in for colophon-entries on GitHub."""
    path = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(path)], check=True)
    return path


@pytest.fixture
def store(tmp_path: Path, remote: Path) -> Store:
    s = Store(tmp_path / "entries", tmp_path / "state", remote=str(remote))
    s.ensure()
    return s


@pytest.fixture
def caller() -> Caller:
    return Caller(login="alex@example.com", name="Alex", machine="laptop")


class FakeRoster(Roster):
    def __init__(self, services=None, icons=None, down=False):
        self.rows = services or []
        self.icons = icons or {}
        self.down = down
        super().__init__("http://roster.invalid", token="t", fetch=self._fake)

    def _fake(self, path, auth=False):
        if self.down:
            raise OSError("connection refused")
        if path == "/services":
            return self.rows
        if path == "/read/icons":
            import base64
            return {k: {"data": base64.b64encode(v).decode()} for k, v in self.icons.items()}
        raise OSError(path)


ROSTER_ROWS = [{"service": "jukebox", "node": "jukebox", "host": "server-1", "runtime": "native",
                "expose": "https", "sensitive": True, "registered": True,
                "url": "https://jukebox.example.lan"}]


@pytest.fixture
def fake_roster():
    return FakeRoster(ROSTER_ROWS, icons={"jukebox": make_png(128)})


def whois_none(ip, socket_path=""):
    return None


@pytest.fixture
def app_client(tmp_path, store, fake_roster):
    cfg = config.Config(entries_dir=store.root, state_dir=store.state_dir,
                        public_url="https://colophon.test", assets_dir=tmp_path / "assets")
    app = api.create_app(cfg, store=store, roster=fake_roster, who=whois_none)
    return TestClient(app)


TS_HEADERS = {"Tailscale-User-Login": "you@example.com",
              "Tailscale-User-Name": "Alex Example",
              "X-Forwarded-For": "100.101.102.103"}

GUIDE = """## What it is

A music library over HTTP.

## Where

`https://jukebox.example.lan`

## Quick start

```sh
curl -s https://jukebox.example.lan/v1/tracks
# a comment, not a heading
```

## Rules and gotchas

- Do not read the repo.
"""
