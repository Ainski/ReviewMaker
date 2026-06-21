"""Rasterize an HTML poster to PNG via headless Chrome, then trim margins (PIL).

Uses the system browser (no new pip dependency); Google Fonts load at render
time via --virtual-time-budget.
"""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageChops

_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_chrome():
    for c in _CANDIDATES:
        if os.path.exists(c):
            return c
    return shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")


def _autocrop(png_path, pad=24):
    im = Image.open(png_path).convert("RGB")
    bg = Image.new("RGB", im.size, im.getpixel((0, 0)))
    bbox = ImageChops.difference(im, bg).getbbox()
    if bbox:
        l, t, r, b = bbox
        im.crop((max(0, l - pad), max(0, t - pad),
                 min(im.width, r + pad), min(im.height, b + pad))).save(png_path)


def rasterize_html(html, png_path, *, width=1240, height=2600, scale=2):
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError("no chrome/chromium binary found for rasterize")
    os.makedirs(os.path.dirname(png_path) or ".", exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        html_path = f.name
    try:
        subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--force-device-scale-factor={scale}", f"--window-size={width},{height}",
             "--virtual-time-budget=8000", f"--screenshot={png_path}", f"file://{html_path}"],
            check=True, capture_output=True, timeout=90)
    finally:
        os.unlink(html_path)
    _autocrop(png_path)
    return png_path
