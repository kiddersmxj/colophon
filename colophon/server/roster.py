"""Roster facts: a service's address, node, tag and machine, read from an
optional service directory ("roster"). Never typed into an entry.

The directory is any HTTP service that answers:

    GET /services     a list of {service, url, node, tag, host, expose,
                      sensitive}; no token
    GET /read/icons   {service: {data: <base64 image>}}; a bearer token

Without COLOPHON_ROSTER_URL the feature is off: entries show only what their
own profile says. Without a token, colophon cannot offer the directory's icon
and asks for a file instead. The directory being down never breaks a read:
the facts are left out and the page says so.
"""

from __future__ import annotations

import base64
import json
import threading
import time
import urllib.error
import urllib.request

from ..core import Invalid
from . import iconconv

TTL = 60          # seconds a good answer is kept
FAIL_TTL = 15     # seconds before asking again after a failure
TIMEOUT = 3


class Roster:
    def __init__(self, base_url: str, token: str = "", fetch=None):
        self.base = base_url.rstrip("/")
        self.token = token
        self._fetch = fetch or self._http
        self._lock = threading.Lock()
        self._services: dict | None = None
        self._at = 0.0
        self._ok = False
        self.error: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base)

    def _http(self, path: str, auth: bool = False):
        req = urllib.request.Request(self.base + path)
        if auth:
            req.add_header("Authorization", f"Bearer {self.token}")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read())

    def services(self) -> dict | None:
        """{service: record}, or None when roster cannot be read."""
        if not self.enabled:
            return None
        with self._lock:
            age = time.monotonic() - self._at
            if self._at and age < (TTL if self._ok else FAIL_TTL):
                return self._services
            try:
                rows = self._fetch("/services")
                self._services = {r["service"]: r for r in rows if isinstance(r, dict) and r.get("service")}
                self._ok, self.error = True, None
            except (OSError, ValueError, urllib.error.URLError, KeyError, TypeError) as e:
                # Keep the last good answer through a blip; say why it is old.
                self._ok = False
                self.error = f"roster did not answer: {e}"
            self._at = time.monotonic()
            return self._services

    def facts(self, service: str | None) -> dict | None:
        """What an entry shows for its roster service, or None."""
        if not service or not self.enabled:
            return None
        rows = self.services()
        if rows is None:
            return {"service": service, "available": False, "error": self.error}
        r = rows.get(service)
        if r is None:
            return {"service": service, "available": True, "registered": False}
        return {
            "service": service,
            "available": True,
            "registered": True,
            "address": r.get("url"),
            "node": r.get("node"),
            "tag": r.get("tag"),
            "machine": r.get("host"),
            "expose": r.get("expose"),
            "sensitive": bool(r.get("sensitive")),
            "stale": not self._ok,
        }

    def icon(self, service: str) -> bytes | None:
        """roster's icon for a service as a square PNG, converted from whatever
        roster holds (often SVG or ICO), when there is one and it is an image."""
        if not self.token or not self.enabled:
            return None
        try:
            icons = self._fetch("/read/icons", auth=True)
            data = base64.b64decode((icons.get(service) or {}).get("data") or "")
            return iconconv.normalize(data) if data else None
        except (OSError, ValueError, urllib.error.URLError, Invalid, AttributeError):
            return None
