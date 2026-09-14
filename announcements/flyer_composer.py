"""Square birthday flyer PNG for WhatsApp groups. Never draws turning age."""

from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

FLYER_SIZE = 1080


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


def _load_font(size, *, bold=False):
    names = (
        ("arialbd.ttf", "DejaVuSans-Bold.ttf")
        if bold
        else ("arial.ttf", "DejaVuSans.ttf")
    )
    candidates = [
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / names[0],
        Path("/usr/share/fonts/truetype/dejavu") / names[1],
        Path("/usr/share/fonts/truetype/liberation")
        / ("LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


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
    if not getattr(member, "allow_birthday_photo", True):
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


def render_birthday_flyer_png(*, member, church, occurrence_date) -> bytes:
    """Return 1080×1080 PNG bytes. Caption/age must not be drawn on the image."""
    denomination = getattr(
        getattr(getattr(church, "district", None), "zone", None),
        "conference",
        None,
    )
    denomination = getattr(denomination, "denomination", None) if denomination else None
    if denomination is None:
        from church_system.denomination_scope import get_church_denomination

        denomination = get_church_denomination(church)

    primary = _parse_hex(getattr(denomination, "primary_color", None), (30, 58, 95))
    accent = _parse_hex(getattr(denomination, "accent_color", None), (201, 162, 39))
    highlight = _parse_hex(getattr(denomination, "highlight_color", None), (14, 116, 144))

    canvas = Image.new("RGB", (FLYER_SIZE, FLYER_SIZE), primary)
    draw = ImageDraw.Draw(canvas)

    draw.rectangle((0, 0, FLYER_SIZE, 28), fill=accent)
    draw.rectangle((0, FLYER_SIZE - 140, FLYER_SIZE, FLYER_SIZE), fill=(255, 255, 255))
    draw.ellipse((-220, 720, 280, 1220), fill=highlight)

    logo = _open_logo(denomination)
    if logo is not None:
        logo.thumbnail((120, 120), Image.Resampling.LANCZOS)
        canvas.paste(logo, (48, 56), logo if logo.mode == "RGBA" else None)

    title_font = _load_font(36, bold=True)
    name_font = _load_font(64, bold=True)
    church_font = _load_font(28, bold=True)
    date_font = _load_font(26)
    blessing_font = _load_font(30)
    footer_font = _load_font(22)
    initial_font = _load_font(72, bold=True)

    church_name = (church.name or "Our church").strip()
    header = church_name.upper()
    draw.text((200 if logo is not None else 48, 78), header[:42], font=church_font, fill=(255, 255, 255))
    draw.text((48, 170), "HAPPY BIRTHDAY", font=title_font, fill=accent)

    portrait_d = 420
    cx = (FLYER_SIZE - portrait_d) // 2
    cy = 250
    ring = 14
    draw.ellipse(
        (cx - ring, cy - ring, cx + portrait_d + ring, cy + portrait_d + ring),
        fill=accent,
    )
    photo = _open_member_photo(member)
    if photo is not None:
        portrait = _circle_portrait(photo, portrait_d)
        canvas.paste(portrait, (cx, cy), portrait)
    else:
        draw.ellipse((cx, cy, cx + portrait_d, cy + portrait_d), fill=(255, 255, 255))
        initials = _initials(member)
        iw = _text_width(draw, initials, initial_font)
        draw.text(
            (cx + (portrait_d - iw) / 2, cy + 155),
            initials,
            font=initial_font,
            fill=primary,
        )

    display_name = (member.full_name or "").strip() or "Church family"
    name_lines = _wrap_text(draw, display_name, name_font, FLYER_SIZE - 96)
    y = 700
    for line in name_lines[:2]:
        lw = _text_width(draw, line, name_font)
        draw.text(((FLYER_SIZE - lw) / 2, y), line, font=name_font, fill=(255, 255, 255))
        y += 72

    date_label = occurrence_date.strftime("%B %d").replace(" 0", " ")
    dw = _text_width(draw, date_label, date_font)
    draw.text(((FLYER_SIZE - dw) / 2, y + 8), date_label, font=date_font, fill=(255, 255, 255))

    blessing = "We celebrate you today. May God bless you."
    bw = _text_width(draw, blessing, blessing_font)
    draw.text(((FLYER_SIZE - bw) / 2, 970), blessing, font=blessing_font, fill=primary)
    footer = "Share this in your church WhatsApp group"
    fw = _text_width(draw, footer, footer_font)
    draw.text(((FLYER_SIZE - fw) / 2, 1020), footer, font=footer_font, fill=primary)

    buffer = BytesIO()
    canvas.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
