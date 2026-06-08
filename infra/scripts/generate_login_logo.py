"""Generate the committed dhis2w-utils wordmark PNGs via Pillow.

Run when you want to re-brand (palette change, new font, different text).
Output lands in `infra/login-customization/{logo_front,logo_banner}.png` —
both committed to git so the seed script can upload them without having to
regenerate on every build.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parents[1] / "login-customization"

# Claude-theme peach — matches `mortenoh/mkdocs-claude-theme`.
PEACH = (212, 162, 127, 255)


def _load_font(size: int) -> Any:
    """Find a serif-ish font — Georgia first (matches mkdocs-claude-theme)."""
    for candidate in (
        "/System/Library/Fonts/Supplemental/Georgia.ttc",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_wordmark(path: Path, *, width: int, height: int, text: str = "dhis2w-utils") -> None:
    """Render `text` centred on a transparent canvas with the peach accent.

    Auto-shrinks the font until the text fits within 85% of the canvas width
    so no glyph touches the edges (the login-app's upper-right slot has zero
    internal padding, so an edge-to-edge wordmark reads as "clipped" even
    when the image is fully visible).
    """
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    max_text_width = int(width * 0.85)
    font_size = int(height * 0.6)
    font = _load_font(font_size)
    while font_size > 8:
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_text_width:
            break
        font_size -= 2
        font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (width - text_width) // 2 - bbox[0]
    y = (height - text_height) // 2 - bbox[1]
    draw.text((x, y), text, fill=PEACH, font=font)
    image.save(path, "PNG")
    print(f"wrote {path.relative_to(Path.cwd())} ({width}x{height}, font={font_size}px)")


def draw_monogram(path: Path, *, size: int = 64, text: str = "d2") -> None:
    """Render a square monogram suitable for a small icon (OIDC button, favicon).

    The wordmark scales unreadably small at 24x24 — a two-letter monogram
    stays legible.
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Rounded-square background in peach.
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.2), fill=PEACH)
    font = _load_font(int(size * 0.55))
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]
    draw.text((x, y), text, fill=(14, 14, 14, 255), font=font)
    image.save(path, "PNG")
    print(f"wrote {path.relative_to(Path.cwd())} ({size}x{size} monogram)")


def main() -> None:
    """Regenerate the committed brand assets.

    - `logo_front.png`: 64x64 "d2" monogram. DHIS2's login-app renders it in
      two places — the upper-right slot (at native 64x64) and the OIDC button
      icon (scaled to 24x24). A square monogram stays legible at both sizes;
      a wordmark would clip in the corner and be unreadable on the button.
    - `logo_banner.png`: 300x60 wordmark for the authenticated top menu
      (plenty of horizontal room there, wordmark is the right shape).
    """
    OUT.mkdir(parents=True, exist_ok=True)
    draw_monogram(OUT / "logo_front.png", size=64)
    draw_wordmark(OUT / "logo_banner.png", width=300, height=60)


if __name__ == "__main__":
    main()
