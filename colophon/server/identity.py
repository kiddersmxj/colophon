"""Who is writing: the caller's tailnet identity, when there is one.

When colophon is fronted by `tailscale serve` (or anything that behaves like
it), the proxy reaches colophon on loopback and adds, on every request:

    X-Forwarded-For         the caller's tailnet address
    Tailscale-User-Login    the person, e.g. you@example.com
    Tailscale-User-Name     their display name

The user headers are left out when the caller is a tagged node, which has no
person. The machine is never in a header, so colophon asks tailscaled who owns
the forwarded address (`tailscale whois`, against COLOPHON_TAILSCALE_SOCKET
when set, then the host's default tailscaled), which also covers tagged nodes.
Whois is the tailnet's own record; the headers are the fallback when it cannot
be asked.

A request with none of this did not come through such a proxy: it is local
development, or something on the host itself. It is recorded as local, under
the host's name.
"""

from __future__ import annotations

import email.header
import ipaddress
import json
import os
import shutil
import socket
import subprocess
from collections.abc import Mapping

from .store import Caller


def _decode(value: str | None) -> str:
    """Header values with non-ASCII names arrive RFC 2047 encoded."""
    if not value:
        return ""
    try:
        parts = email.header.decode_header(value)
        return "".join(p.decode(c or "utf-8") if isinstance(p, bytes) else p for p, c in parts).strip()
    except (ValueError, LookupError):
        return value.strip()


def _tailnet_ip(value: str | None) -> str | None:
    if not value:
        return None
    first = value.split(",")[0].strip()
    try:
        ip = ipaddress.ip_address(first)
    except ValueError:
        return None
    if ip in ipaddress.ip_network("100.64.0.0/10") or ip in ipaddress.ip_network("fd7a:115c:a1e0::/48"):
        return str(ip)
    return None


def whois(ip: str, socket_path: str = "") -> dict | None:
    """The tailnet's record for the node at ip, asked of the configured socket, then the host."""
    exe = shutil.which("tailscale")
    if not exe:
        return None
    attempts = []
    if socket_path and os.path.exists(socket_path):
        attempts.append([exe, f"--socket={socket_path}", "whois", "--json", ip])
    attempts.append([exe, "whois", "--json", ip])
    for cmd in attempts:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if r.returncode == 0:
            try:
                return json.loads(r.stdout)
            except ValueError:
                continue
    return None


def caller(headers: Mapping[str, str], socket_path: str = "", who=whois) -> Caller:
    h = {k.lower(): v for k, v in headers.items()}
    ip = _tailnet_ip(h.get("x-forwarded-for"))
    login = _decode(h.get("tailscale-user-login"))
    name = _decode(h.get("tailscale-user-name"))
    machine = ""
    tags: list[str] = []
    if ip:
        info = who(ip, socket_path) or {}
        node = info.get("Node") or {}
        user = info.get("UserProfile") or {}
        machine = node.get("ComputedName") or (node.get("Name") or "").split(".")[0]
        tags = node.get("Tags") or []
        if not tags:
            login = user.get("LoginName") or login
            name = user.get("DisplayName") or name
    if ip or login:
        if tags and not login:
            login = f"{tags[0].removeprefix('tag:')}@tagged"
            name = tags[0]
        # git needs an email, so a caller with no login is named by its address.
        # A machine the tailnet did not name is left blank, never made up.
        return Caller(login=login or f"{ip}@tailnet", name=name or login or ip,
                      machine=machine or ip, source="tailnet")
    host = socket.gethostname()
    user = os.environ.get("USER") or "local"
    return Caller(login=f"{user}@{host}", name=os.environ.get("COLOPHON_LOCAL_AUTHOR", user),
                  machine=host, source="local")
