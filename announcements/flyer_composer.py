"""Professional birthday flyer PNGs for WhatsApp. Never draws turning age."""

from __future__ import annotations

import math
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

LAYOUT_SQUARE = "square"
LAYOUT_STORY = "story"


def _parse_hex(value, fallback):
    raw = (value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def _mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _darken(color, amount=0.28):
    return _mix(color, (8, 10, 16), amount)


def _lighten(color, amount=0.22):
    return _mix(color, (255, 255, 255), amount)


def _load_font(size, *, bold=False, elegant=False):
    if elegant:
        names = (
            "georgia.ttf",
            "Georgia.ttf",
            "times.ttf",
            "timesbd.ttf" if bold else "times.ttf",
            "DejaVuSerif-Bold.ttf" if bold else "DejaVuSerif.ttf",
            "LiberationSerif-Bold.ttf" if bold else "LiberationSerif-Regular.ttf",
        )
    elif bold:
        names = (
            "segoeuib.ttf",
            "arialbd.ttf",
            "calibrib.ttf",
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
        )
    else:
        names = (
            "segoeui.ttf",
            "arial.ttf",
            "calibri.ttf",
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
        )
    windir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    linux_dirs = (
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/share/fonts/truetype/liberation"),
        Path("/usr/share/fonts/truetype/msttcorefonts"),
    )
    for name in names:
        for folder in (windir, *linux_dirs):
            path = folder / name
            if path.is_file():
                return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_height(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _vertical_gradient(size, top, bottom):
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    last = max(height - 1, 1)
    for y in range(height):
        pixels[0, y] = _mix(top, bottom, y / last)
    return strip.resize((width, height), Image.Resampling.BILINEAR)


def _radial_glow(size, color, strength=0.55):
    width, height = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    glow = Image.new("L", size, 0)
    gdraw = ImageDraw.Draw(glow)
    cx, cy = width // 2, int(height * 0.38)
    radius = int(min(width, height) * 0.42)
    for i in range(12, 0, -1):
        r = int(radius * (i / 8.0))
        alpha = int(40 * strength * (i / 12.0))
        gdraw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha)
    glow = glow.filter(ImageFilter.GaussianBlur(radius=48))
    tint = Image.new("RGBA", size, color + (255,))
    overlay.paste(tint, (0, 0), glow)
    return overlay


def _vignette(size, amount=150):
    width, height = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    inset = int(min(width, height) * 0.04)
    draw.rounded_rectangle(
        (inset, inset, width - inset, height - inset),
        radius=int(min(width, height) * 0.04),
        fill=255,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(radius=55))
    shade = Image.new("RGBA", size, (0, 0, 0, amount))
    inv = ImageOps.invert(mask)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(shade, (0, 0), inv)
    return out


def _draw_star(draw, cx, cy, radius, fill, points=4):
    coords = []
    for i in range(points * 2):
        angle = math.pi / 2 + i * math.pi / points
        r = radius if i % 2 == 0 else radius * 0.38
        coords.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(coords, fill=fill)


def _draw_corner_flourish(draw, x, y, size, color, flip_x=False, flip_y=False):
    """Gold corner bracket with a small diamond."""
    sx = -1 if flip_x else 1
    sy = -1 if flip_y else 1
    thick = max(3, size // 18)
    arm = size
    draw.line((x, y, x + sx * arm, y), fill=color, width=thick)
    draw.line((x, y, x, y + sy * arm), fill=color, width=thick)
    inner = size * 0.62
    draw.line((x + sx * 10, y + sy * 10, x + sx * inner, y + sy * 10), fill=color, width=2)
    draw.line((x + sx * 10, y + sy * 10, x + sx * 10, y + sy * inner), fill=color, width=2)
    dx = x + sx * (size * 0.22)
    dy = y + sy * (size * 0.22)
    diamond = [
        (dx, dy - 7),
        (dx + 7, dy),
        (dx, dy + 7),
        (dx - 7, dy),
    ]
    draw.polygon(diamond, fill=color)


def _draw_side_ornament(draw, x, y0, y1, color):
    mid = (y0 + y1) / 2
    draw.line((x, y0, x, y1), fill=color, width=2)
    _draw_star(draw, x, mid, 11, color, points=4)


def _circle_portrait(source, diameter):
    img = ImageOps.exif_transpose(source).convert("RGB")
    img = ImageOps.fit(img, (diameter, diameter), Image.Resampling.LANCZOS)
    mask = Image.new("L", (diameter, diameter), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, diameter - 1, diameter - 1), fill=255)
    out = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    out.paste(img, (0, 0))
    out.putalpha(mask)
    return out


def _initials(member):
    first = (member.first_name or "").strip()[:1].upper()
    last = (member.last_name or "").strip()[:1].upper()
    return (first + last) or "?"


def _open_member_photo(member):
    if not getattr(member, "allow_birthday_photo", False):
        return None
    picture = getattr(member, "profile_picture", None)
    if not picture:
        return None
    try:
        if not picture.name:
            return None
        picture.open("rb")
        try:
            return Image.open(picture)
        finally:
            picture.close()
    except (OSError, ValueError, FileNotFoundError):
        return None


def _open_logo(denomination):
    logo = getattr(denomination, "logo", None) if denomination else None
    if not logo or not getattr(logo, "name", ""):
        return None
    try:
        logo.open("rb")
        try:
            return Image.open(logo).convert("RGBA")
        finally:
            logo.close()
    except (OSError, ValueError, FileNotFoundError):
        return None


def _resolve_denomination(church):
    denomination = getattr(
        getattr(getattr(church, "district", None), "zone", None),
        "conference",
        None,
    )
    denomination = getattr(denomination, "denomination", None) if denomination else None
    if denomination is None:
        from church_system.denomination_scope import get_church_denomination

        denomination = get_church_denomination(church)
    return denomination


def _draw_centered(draw, text, y, font, fill, width, max_width=None):
    limit = max_width or (width - 120)
    lines = _wrap_text(draw, text, font, limit)
    for line in lines[:3]:
        lw = _text_width(draw, line, font)
        draw.text(((width - lw) / 2, y), line, font=font, fill=fill)
        y += int(_text_height(draw, line, font) * 1.25) + 8
    return y


def render_birthday_flyer_png(*, member, church, occurrence_date, layout=LAYOUT_SQUARE) -> bytes:
    """Return PNG bytes. Caption/age must not be drawn on the image."""
    story = layout == LAYOUT_STORY
    width, height = (1080, 1920) if story else (1080, 1080)
    denomination = _resolve_denomination(church)

    primary = _parse_hex(getattr(denomination, "primary_color", None), (30, 58, 95))
    accent = _parse_hex(getattr(denomination, "accent_color", None), (212, 175, 55))
    highlight = _parse_hex(getattr(denomination, "highlight_color", None), (14, 116, 144))
    cream = (248, 243, 232)
    ink = _darken(primary, 0.45)

    canvas = _vertical_gradient(
        (width, height),
        _darken(primary, 0.12),
        _mix(_darken(primary, 0.55), highlight, 0.18),
    ).convert("RGBA")
    glow = _radial_glow((width, height), _lighten(highlight, 0.15), strength=0.7)
    canvas = Image.alpha_composite(canvas, glow)
    draw = ImageDraw.Draw(canvas)

    margin = 42 if story else 36
    frame = (margin, margin, width - margin, height - margin)
    draw.rounded_rectangle(frame, radius=28, outline=accent, width=3)
    draw.rounded_rectangle(
        (margin + 10, margin + 10, width - margin - 10, height - margin - 10),
        radius=22,
        outline=_mix(accent, cream, 0.35),
        width=1,
    )
    flourish = 86 if story else 72
    _draw_corner_flourish(draw, margin + 28, margin + 28, flourish, accent)
    _draw_corner_flourish(draw, width - margin - 28, margin + 28, flourish, accent, flip_x=True)
    _draw_corner_flourish(draw, margin + 28, height - margin - 28, flourish, accent, flip_y=True)
    _draw_corner_flourish(
        draw, width - margin - 28, height - margin - 28, flourish, accent, flip_x=True, flip_y=True
    )
    if story:
        _draw_side_ornament(draw, margin + 26, 340, height - 280, _mix(accent, cream, 0.2))
        _draw_side_ornament(draw, width - margin - 26, 340, height - 280, _mix(accent, cream, 0.2))

    star_fill = _mix(accent, (255, 255, 255), 0.25)
    _draw_star(draw, 160, 168 if story else 150, 16, star_fill)
    _draw_star(draw, width - 160, 168 if story else 150, 16, star_fill)
    _draw_star(draw, 210, height - (210 if story else 168), 12, star_fill)
    _draw_star(draw, width - 210, height - (210 if story else 168), 12, star_fill)

    logo = _open_logo(denomination)
    church_name = (church.name or "Our church").strip()
    church_font = _load_font(26, bold=True)
    kicker_font = _load_font(20, elegant=True)
    title_font = _load_font(58 if story else 52, elegant=True, bold=True)
    name_font = _load_font(68 if story else 58, elegant=True, bold=True)
    date_font = _load_font(28, elegant=True)
    blessing_font = _load_font(26, elegant=True)
    footer_font = _load_font(20)
    initial_font = _load_font(92 if story else 78, elegant=True, bold=True)

    header_y = margin + 48
    if logo is not None:
        badge = 96
        logo = logo.copy()
        logo.thumbnail((badge, badge), Image.Resampling.LANCZOS)
        lx = (width - logo.width) // 2
        canvas.paste(logo, (lx, header_y), logo if logo.mode == "RGBA" else None)
        header_y += logo.height + 18
    header = church_name.upper()
    hw = _text_width(draw, header[:48], church_font)
    draw.text(((width - hw) / 2, header_y), header[:48], font=church_font, fill=cream)
    header_y += 40
    rule_w = 220
    draw.line(
        ((width - rule_w) / 2, header_y, (width + rule_w) / 2, header_y),
        fill=accent,
        width=2,
    )
    _draw_star(draw, width / 2, header_y, 8, accent)

    kicker = "CELEBRATING A PRECIOUS LIFE"
    kw = _text_width(draw, kicker, kicker_font)
    draw.text(((width - kw) / 2, header_y + 28), kicker, font=kicker_font, fill=_mix(accent, cream, 0.35))
    title = "Happy Birthday"
    tw = _text_width(draw, title, title_font)
    draw.text(((width - tw) / 2, header_y + 58), title, font=title_font, fill=cream)

    portrait_d = 520 if story else 360
    cx = (width - portrait_d) // 2
    cy = header_y + (200 if story else 118)
    outer = 22
    mid = 12
    draw.ellipse(
        (cx - outer, cy - outer, cx + portrait_d + outer, cy + portrait_d + outer),
        outline=accent,
        width=6,
    )
    draw.ellipse(
        (cx - mid, cy - mid, cx + portrait_d + mid, cy + portrait_d + mid),
        outline=cream,
        width=3,
    )
    photo = _open_member_photo(member)
    if photo is not None:
        portrait = _circle_portrait(photo, portrait_d)
        canvas.paste(portrait, (cx, cy), portrait)
    else:
        draw.ellipse((cx, cy, cx + portrait_d, cy + portrait_d), fill=_lighten(primary, 0.12))
        initials = _initials(member)
        iw = _text_width(draw, initials, initial_font)
        ih = _text_height(draw, initials, initial_font)
        draw.text(
            (cx + (portrait_d - iw) / 2, cy + (portrait_d - ih) / 2 - 8),
            initials,
            font=initial_font,
            fill=cream,
        )

    display_name = (member.full_name or "").strip() or "Church family"
    name_y = cy + portrait_d + (56 if story else 36)
    name_y = _draw_centered(draw, display_name, name_y, name_font, cream, width, width - 160)

    date_label = occurrence_date.strftime("%A · %B %d").replace(" 0", " ")
    dw = _text_width(draw, date_label, date_font)
    dh = _text_height(draw, date_label, date_font)
    pad_x, pad_y = 36, 14
    chip_top = name_y + 10
    chip = (
        (width - dw) / 2 - pad_x,
        chip_top,
        (width + dw) / 2 + pad_x,
        chip_top + dh + pad_y * 2,
    )
    draw.rounded_rectangle(chip, radius=28, fill=_mix(ink, primary, 0.2), outline=accent, width=2)
    draw.text(((width - dw) / 2, chip_top + pad_y), date_label, font=date_font, fill=cream)
    content_bottom = chip[3]

    quote_font = _load_font(28, elegant=True)
    if story:
        quote = "Your life is a gift. We thank God for you."
        q_lines = _wrap_text(draw, quote, quote_font, width - 280)
        q_h = sum(_text_height(draw, line, quote_font) + 12 for line in q_lines) + 48
        panel = (150, content_bottom + 70, width - 150, content_bottom + 70 + q_h)
        draw.rounded_rectangle(panel, radius=20, outline=_mix(accent, cream, 0.25), width=2)
        draw.rounded_rectangle(
            (panel[0] + 10, panel[1] + 10, panel[2] - 10, panel[3] - 10),
            radius=14,
            outline=_mix(accent, cream, 0.12),
            width=1,
        )
        qy = panel[1] + 28
        for line in q_lines:
            qw = _text_width(draw, line, quote_font)
            draw.text(((width - qw) / 2, qy), line, font=quote_font, fill=_mix(cream, accent, 0.2))
            qy += _text_height(draw, line, quote_font) + 12
        content_bottom = panel[3]

    blessing = "May the Lord bless you and keep you."
    footer_top = content_bottom + (70 if story else 48)
    if footer_top > height - 160:
        footer_top = height - 160
    draw.line((width * 0.28, footer_top, width * 0.72, footer_top), fill=accent, width=1)
    _draw_star(draw, width / 2, footer_top, 7, accent)
    bw = _text_width(draw, blessing, blessing_font)
    draw.text(((width - bw) / 2, footer_top + 24), blessing, font=blessing_font, fill=cream)
    footer = "With love from your church family"
    fw = _text_width(draw, footer, footer_font)
    draw.text(((width - fw) / 2, footer_top + 68), footer, font=footer_font, fill=_mix(cream, accent, 0.35))
    if story:
        brand_y = height - margin - 58
        draw.line((width * 0.32, brand_y - 18, width * 0.68, brand_y - 18), fill=_mix(accent, cream, 0.2), width=1)
        brand = church_name.upper()[:40]
        bw2 = _text_width(draw, brand, footer_font)
        draw.text(((width - bw2) / 2, brand_y), brand, font=footer_font, fill=_mix(cream, accent, 0.4))

    canvas = Image.alpha_composite(canvas, _vignette((width, height), amount=110))
    buffer = BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
