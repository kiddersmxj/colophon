"""Turn whatever image a caller or roster has into an icon colophon accepts.

roster keeps icons as each machine sent them, mostly SVG or ICO, and projects'
own icons are often not square. The entry's icon is always a square PNG, so
the server converts: SVG is rendered, ICO takes its largest image, anything
Pillow reads is accepted, and a non-square image is padded onto a transparent
square. A PNG that already passes is stored byte for byte.

Server only: the CLI and core stay standard library, so the CLI sends the file
as it is and the server does this.
"""

from __future__ import annotations

import gzip
import io

from ..core import Invalid
from ..core import icon as icon_mod

SVG_SIDE = 512      # an SVG is rendered so its longer side is this
TARGET_MAX = 1024   # a bigger raster is scaled down to this
FALLBACK = 512      # and to this if the PNG is still over the size limit


def is_svg(data: bytes) -> bool:
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)[:4096]
        except (OSError, EOFError):
            return False
    head = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    return head.startswith(b"<") and b"<svg" in head


def _render_svg(data: bytes):
    import cairosvg
    from PIL import Image

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    try:
        # Render once at natural size to learn the aspect, then at SVG_SIDE.
        probe = Image.open(io.BytesIO(cairosvg.svg2png(bytestring=data)))
        w, h = probe.size
        scale = SVG_SIDE / max(w, h, 1)
        png = cairosvg.svg2png(bytestring=data, output_width=max(1, round(w * scale)),
                               output_height=max(1, round(h * scale)))
        return Image.open(io.BytesIO(png))
    except Exception as e:  # cairosvg raises many kinds on bad input
        raise Invalid(f"the icon is an SVG colophon could not render: {e}") from None


def _open_raster(data: bytes):
    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(io.BytesIO(data))
        if img.format == "ICO":
            # Pillow opens the largest size by default; say so to be sure.
            sizes = img.info.get("sizes") or img.ico.sizes()
            if sizes:
                img.size = max(sizes, key=lambda s: s[0] * s[1])
        img.load()
        return img
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as e:
        raise Invalid(f"the icon must be an image (PNG, SVG, ICO, JPEG, WebP...): {e}") from None


def _square_png(img) -> bytes:
    from PIL import Image

    img = img.convert("RGBA")
    w, h = img.size
    side = max(w, h)
    if side > TARGET_MAX:
        img.thumbnail((TARGET_MAX, TARGET_MAX), Image.LANCZOS)
        w, h = img.size
        side = max(w, h)
    if side < icon_mod.MIN_SIDE:
        f = icon_mod.MIN_SIDE / side
        img = img.resize((max(1, round(w * f)), max(1, round(h * f))), Image.LANCZOS)
        w, h = img.size
        side = max(w, h, icon_mod.MIN_SIDE)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    out = _encode(canvas)
    if len(out) > icon_mod.MAX_BYTES and side > FALLBACK:
        canvas.thumbnail((FALLBACK, FALLBACK), Image.LANCZOS)
        out = _encode(canvas)
    return out


def _encode(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def normalize(data: bytes) -> bytes:
    """A square PNG icon from any image, or Invalid saying why not."""
    if not data:
        return icon_mod.validate(data)  # the "icon is required" message
    try:
        return icon_mod.validate(data)
    except Invalid:
        pass
    img = _render_svg(data) if is_svg(data) else _open_raster(data)
    return icon_mod.validate(_square_png(img))
