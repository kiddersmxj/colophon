"""Icons in other formats become square PNGs on the server."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from colophon.core import Invalid, icon
from colophon.server import iconconv
from conftest import ROSTER_ROWS, FakeRoster, make_png

SVG = (b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="40" height="20">'
       b'<rect width="40" height="20" fill="#c33"/></svg>')


def ico(*sizes) -> bytes:
    buf = io.BytesIO()
    Image.new("RGBA", (256, 256), (0, 128, 255, 255)).save(buf, format="ICO", sizes=list(sizes))
    return buf.getvalue()


def square(data: bytes) -> tuple[int, int]:
    w, h = icon.validate(data) and icon.size(data)
    assert w == h
    return w, h


def test_valid_png_is_kept_byte_for_byte():
    assert iconconv.normalize(make_png(64)) == make_png(64)


def test_svg_is_rendered_and_padded():
    out = iconconv.normalize(SVG)
    assert square(out) == (512, 512)
    img = Image.open(io.BytesIO(out)).convert("RGBA")
    assert img.getpixel((256, 10))[3] == 0          # padding above is transparent
    assert img.getpixel((256, 256))[:3] == (204, 51, 51)


def test_ico_takes_largest_image():
    assert square(iconconv.normalize(ico((16, 16), (48, 48), (128, 128)))) == (128, 128)


def test_non_square_png_is_padded():
    assert square(iconconv.normalize(make_png(48, 64))) == (64, 64)


def test_tiny_and_huge_are_scaled():
    assert square(iconconv.normalize(make_png(16))) == (32, 32)
    assert square(iconconv.normalize(make_png(3000, 1500))) == (1024, 1024)


def test_not_an_image_is_refused():
    with pytest.raises(Invalid, match="must be an image"):
        iconconv.normalize(b"GIF89a")
    with pytest.raises(Invalid, match="icon is required"):
        iconconv.normalize(b"")
    with pytest.raises(Invalid, match="SVG"):
        iconconv.normalize(b"<svg xmlns='http://www.w3.org/2000/svg'><rect")


def test_roster_svg_icon_is_offered_as_png():
    r = FakeRoster(ROSTER_ROWS, icons={"jukebox": SVG})
    assert square(r.icon("jukebox")) == (512, 512)


def test_api_accepts_svg_icon(app_client):
    import base64
    prof = {"name": "thing", "title": "Thing", "summary": "s", "kind": "program"}
    r = app_client.post("/", json={"profile": prof, "icon": base64.b64encode(SVG).decode()})
    assert r.status_code == 201, r.text
    assert square(app_client.get("/thing/icon").content) == (512, 512)
    r = app_client.put("/thing/icon", content=ico((48, 48)))
    assert r.status_code == 200 and r.json()["changed"]
    assert square(app_client.get("/thing/icon").content) == (48, 48)
