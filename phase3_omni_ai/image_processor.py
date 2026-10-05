"""Pillow helpers for loading, normalizing, and capturing chart screenshots."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageGrab, ImageOps


MAX_IMAGE_EDGE = 3_072
MAX_IMAGE_PIXELS = 50_000_000


def process_chart_image(source: str | Path | Image.Image) -> Image.Image:
    """Return a safe, RGB, downscaled copy suitable for Gemini image input."""
    if isinstance(source, Image.Image):
        opened = source.copy()
    else:
        image_path = Path(source).expanduser()
        if not image_path.is_file():
            raise FileNotFoundError(f"Chart screenshot does not exist: {image_path}")
        opened = Image.open(image_path)

    try:
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ValueError("Image exceeds the configured pixel limit.")
        oriented = ImageOps.exif_transpose(opened)
        rgba = oriented.convert("RGBA")
        rgb = Image.new("RGB", rgba.size, "#05070A")
        rgb.paste(rgba, mask=rgba.getchannel("A"))
        rgb.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
        return rgb.copy()
    finally:
        opened.close()


def capture_chart_screenshot(
    bbox: tuple[int, int, int, int] | None = None,
) -> Image.Image:
    """Capture the desktop or a screen region; requires OS screen-capture access."""
    try:
        try:
            screenshot = ImageGrab.grab(bbox=bbox, all_screens=True)
        except TypeError:
            screenshot = ImageGrab.grab(bbox=bbox)
    except OSError as exc:
        raise RuntimeError(f"Desktop capture is unavailable: {exc}") from exc
    return process_chart_image(screenshot)
