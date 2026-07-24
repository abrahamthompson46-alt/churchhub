"""Template tags for ChurchHub UI helpers."""

from django import template

register = template.Library()

TAG_LABELS = {
    "success": "Success",
    "error": "Error",
    "danger": "Error",
    "warning": "Warning",
    "info": "Notice",
    "debug": "Debug",
}

TAG_BOOTSTRAP = {
    "success": "success",
    "error": "danger",
    "danger": "danger",
    "warning": "warning",
    "info": "info",
    "debug": "secondary",
}

TAG_ICONS = {
    "success": "check-circle-fill",
    "error": "exclamation-octagon-fill",
    "danger": "exclamation-octagon-fill",
    "warning": "exclamation-triangle-fill",
    "info": "info-circle-fill",
    "debug": "bug-fill",
}

TITLE_SEP = " || "


@register.filter
def alert_class(message_tags):
    """Map Django message tags to Bootstrap alert variant."""
    primary = (message_tags or "info").split()[0]
    return TAG_BOOTSTRAP.get(primary, "info")


@register.filter
def message_icon(message_tags):
    """Bootstrap icon for a message tag."""
    primary = (message_tags or "info").split()[0]
    return TAG_ICONS.get(primary, "info-circle-fill")


@register.filter
def message_title(message, message_tags):
    """Extract title from structured flash or derive from tag."""
    text = str(message)
    if TITLE_SEP in text:
        return text.split(TITLE_SEP, 1)[0].strip()
    primary = (message_tags or "info").split()[0]
    return TAG_LABELS.get(primary, "Notice")


@register.filter
def message_body(message):
    """Extract body from structured flash message."""
    text = str(message)
    if TITLE_SEP in text:
        return text.split(TITLE_SEP, 1)[1].strip()
    return text


@register.simple_tag(takes_context=True)
def money(context, amount, places=2):
    """Format amount as plain tabular number (no currency symbol).

    Currency is shown via page context / headers when needed — not inline
    glyphs in tables or KPI cards.
    """
    from django.contrib.humanize.templatetags.humanize import intcomma
    from django.template.defaultfilters import floatformat

    del context  # reserved for future locale/currency options
    try:
        return intcomma(floatformat(amount, places))
    except (TypeError, ValueError):
        return str(amount)
