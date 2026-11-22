"""Where the server keeps things and how it is reached."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The repo's assets/, where the logo and favicon land. In a checkout or an
# editable install this is beside the package.
_REPO_ASSETS = Path(__file__).resolve().parents[2] / "assets"


@dataclass(frozen=True)
class Config:
    # A checkout of colophon-entries. Only this server writes to it.
    entries_dir: Path
    # Small state that is not content: the last commit each project reported.
    state_dir: Path
    # Cloned into entries_dir when it is missing. Empty means a local repo only.
    entries_remote: str = ""
    # Push to origin after every commit.
    push: bool = True
    bind: str = "127.0.0.1"
    port: int = 8796
    # The address agents and pointer skills use. Empty means this server's
    # own bind address, which is only right for local use.
    public_url: str = ""
    # An optional service directory (see roster.py). Empty turns it off.
    roster_url: str = ""
    roster_token: str = ""
    # A tailscaled socket to ask who a caller is. Empty uses the default one.
    tailscale_socket: str = ""
    assets_dir: Path = _REPO_ASSETS


def _flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    return default if v is None else v.strip().lower() not in ("0", "false", "no", "off", "")


def load() -> Config:
    bind = os.environ.get("COLOPHON_BIND", "127.0.0.1")
    port = int(os.environ.get("COLOPHON_PORT", "8796"))
    return Config(
        entries_dir=Path(os.environ.get("COLOPHON_ENTRIES_DIR", "var/entries")).resolve(),
        state_dir=Path(os.environ.get("COLOPHON_STATE_DIR", "var/state")).resolve(),
        entries_remote=os.environ.get("COLOPHON_ENTRIES_REMOTE", ""),
        push=_flag("COLOPHON_PUSH", True),
        bind=bind,
        port=port,
        public_url=(os.environ.get("COLOPHON_PUBLIC_URL") or f"http://{bind}:{port}").rstrip("/"),
        roster_url=os.environ.get("COLOPHON_ROSTER_URL", "").rstrip("/"),
        roster_token=os.environ.get("COLOPHON_ROSTER_TOKEN", ""),
        tailscale_socket=os.environ.get("COLOPHON_TAILSCALE_SOCKET", ""),
        assets_dir=Path(os.environ.get("COLOPHON_ASSETS_DIR", str(_REPO_ASSETS))).resolve(),
    )
