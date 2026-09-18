"""
Utility script to generate the Universal File Converter application icon (ICO & PNG).
Produces high-resolution multi-size Windows ICO (16x16 to 256x256) and 1024x1024 PNG.
"""

from __future__ import annotations

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter


def generate_app_icons(output_dir: Path | None = None) -> tuple[Path, Path]:
    if output_dir is None:
        output_dir = Path(__file__).resolve().parent

    output_dir.mkdir(parents=True, exist_ok=True)
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 48
    corner_radius = 190
    bg_box = [margin, margin, size - margin, size - margin]

    # Gradient background
    base_bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base_draw = ImageDraw.Draw(base_bg)
    for y in range(margin, size - margin):
        t = (y - margin) / (size - 2 * margin)
        r = int(15 + (42 - 15) * t)
        g = int(23 + (40 - 23) * t)
        b = int(42 + (125 - 42) * t)
        base_draw.line([(margin, y), (size - margin, y)], fill=(r, g, b, 255), width=1)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(bg_box, radius=corner_radius, fill=255)
    img.paste(base_bg, (0, 0), mask=mask)

    # Border glow
    draw.rounded_rectangle(bg_box, radius=corner_radius, outline=(99, 102, 241, 230), width=16)
    inner_box = [margin + 14, margin + 14, size - margin - 14, size - margin - 14]
    draw.rounded_rectangle(inner_box, radius=corner_radius - 14, outline=(129, 140, 248, 70), width=6)

    # Back Document (Source file)
    doc1_x, doc1_y = 230, 230
    doc1_w, doc1_h = 320, 430
    doc1_radius = 32

    shadow1 = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s1_draw = ImageDraw.Draw(shadow1)
    s1_draw.rounded_rectangle([doc1_x + 10, doc1_y + 16, doc1_x + doc1_w + 10, doc1_y + doc1_h + 16], radius=doc1_radius, fill=(0, 0, 0, 110))
    shadow1 = shadow1.filter(ImageFilter.GaussianBlur(16))
    img.alpha_composite(shadow1)

    doc1_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d1_draw = ImageDraw.Draw(doc1_img)
    d1_draw.rounded_rectangle([doc1_x, doc1_y, doc1_x + doc1_w, doc1_y + doc1_h], radius=doc1_radius, fill=(224, 231, 255, 250), outline=(199, 210, 254, 255), width=6)
    d1_draw.rounded_rectangle([doc1_x + 24, doc1_y + 28, doc1_x + doc1_w - 24, doc1_y + 90], radius=16, fill=(99, 102, 241, 255))
    d1_draw.rounded_rectangle([doc1_x + 24, doc1_y + 120, doc1_x + doc1_w - 70, doc1_y + 144], radius=8, fill=(165, 180, 252, 255))
    d1_draw.rounded_rectangle([doc1_x + 24, doc1_y + 164, doc1_x + doc1_w - 24, doc1_y + 188], radius=8, fill=(199, 210, 254, 255))
    d1_draw.rounded_rectangle([doc1_x + 24, doc1_y + 208, doc1_x + doc1_w - 50, doc1_y + 232], radius=8, fill=(199, 210, 255, 255))
    img.alpha_composite(doc1_img)

    # Front Document (Target file)
    doc2_x, doc2_y = 470, 360
    doc2_w, doc2_h = 320, 430
    doc2_radius = 32

    shadow2 = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    s2_draw = ImageDraw.Draw(shadow2)
    s2_draw.rounded_rectangle([doc2_x + 12, doc2_y + 20, doc2_x + doc2_w + 12, doc2_y + doc2_h + 20], radius=doc2_radius, fill=(0, 0, 0, 140))
    shadow2 = shadow2.filter(ImageFilter.GaussianBlur(20))
    img.alpha_composite(shadow2)

    doc2_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d2_draw = ImageDraw.Draw(doc2_img)
    d2_draw.rounded_rectangle([doc2_x, doc2_y, doc2_x + doc2_w, doc2_y + doc2_h], radius=doc2_radius, fill=(255, 255, 255, 255), outline=(226, 232, 240, 255), width=6)
    d2_draw.rounded_rectangle([doc2_x + 24, doc2_y + 28, doc2_x + doc2_w - 24, doc2_y + 90], radius=16, fill=(16, 185, 129, 255))
    for row_y in [doc2_y + 124, doc2_y + 174, doc2_y + 224, doc2_y + 274]:
        d2_draw.rounded_rectangle([doc2_x + 24, row_y, doc2_x + 110, row_y + 32], radius=6, fill=(226, 232, 240, 255))
        d2_draw.rounded_rectangle([doc2_x + 126, row_y, doc2_x + doc2_w - 24, row_y + 32], radius=6, fill=(241, 245, 249, 255))
    img.alpha_composite(doc2_img)

    # Central Conversion Badge
    badge_x, badge_y = 512, 512
    badge_r = 136

    badge_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bs_draw = ImageDraw.Draw(badge_shadow)
    bs_draw.ellipse([badge_x - badge_r + 6, badge_y - badge_r + 14, badge_x + badge_r + 6, badge_y + badge_r + 14], fill=(0, 0, 0, 180))
    badge_shadow = badge_shadow.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(badge_shadow)

    badge_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(badge_img)
    b_draw.ellipse([badge_x - badge_r, badge_y - badge_r, badge_x + badge_r, badge_y + badge_r], fill=(24, 21, 62, 255), outline=(99, 102, 241, 255), width=8)

    # Dual circular arrows
    arc_r = 74
    arc_w = 18
    arc_box = [badge_x - arc_r, badge_y - arc_r, badge_x + arc_r, badge_y + arc_r]

    # Arc 1 (top): 215 to 335 degrees
    b_draw.arc(arc_box, start=215, end=335, fill=(6, 182, 212, 255), width=arc_w)
    rad1 = math.radians(342)
    hx1 = badge_x + arc_r * math.cos(rad1)
    hy1 = badge_y + arc_r * math.sin(rad1)
    b_draw.polygon([
        (hx1 + 14, hy1 + 18),
        (hx1 - 18, hy1 + 32),
        (hx1 - 4, hy1 - 14)
    ], fill=(6, 182, 212, 255))

    # Arc 2 (bottom): 35 to 155 degrees
    b_draw.arc(arc_box, start=35, end=155, fill=(165, 180, 252, 255), width=arc_w)
    rad2 = math.radians(162)
    hx2 = badge_x + arc_r * math.cos(rad2)
    hy2 = badge_y + arc_r * math.sin(rad2)
    b_draw.polygon([
        (hx2 - 14, hy2 - 18),
        (hx2 + 18, hy2 - 32),
        (hx2 + 4, hy2 + 14)
    ], fill=(165, 180, 252, 255))

    img.alpha_composite(badge_img)

    png_path = output_dir / "app_icon.png"
    img.save(png_path, format="PNG")

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    ico_images = [img.resize(s, Image.Resampling.LANCZOS) for s in ico_sizes]
    ico_path = output_dir / "app_icon.ico"
    ico_images[-1].save(ico_path, format="ICO", sizes=ico_sizes)

    return ico_path, png_path


if __name__ == "__main__":
    ico, png = generate_app_icons()
    print(f"Generated icons:\n  {ico}\n  {png}")
