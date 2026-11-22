"""icon.png: what an entry's icon must be."""

from __future__ import annotations

import struct

from . import Invalid

PNG = b"\x89PNG\r\n\x1a\n"
MAX_BYTES = 1024 * 1024
MIN_SIDE = 32
MAX_SIDE = 2048


def size(data: bytes) -> tuple[int, int]:
    """(width, height) from the PNG header."""
    if len(data) < 24 or not data.startswith(PNG) or data[12:16] != b"IHDR":
        raise Invalid("the icon must be a PNG")
    return struct.unpack(">II", data[16:24])


def validate(data: bytes) -> bytes:
    if not data:
        raise Invalid("an icon is required (a PNG): the project's own logo or app icon")
    if len(data) > MAX_BYTES:
        raise Invalid(f"the icon is over {MAX_BYTES // 1024} KB")
    w, h = size(data)
    if min(w, h) < MIN_SIDE or max(w, h) > MAX_SIDE:
        raise Invalid(f"the icon is {w}x{h}; each side must be {MIN_SIDE} to {MAX_SIDE} pixels")
    if w != h:
        raise Invalid(f"the icon is {w}x{h}; it must be square")
    return data
