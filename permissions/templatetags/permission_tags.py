from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from permissions.services import user_has_permission

register = template.Library()


def _user_from_context(context):
    request = context.get("request")
    return getattr(request, "user", None)


@register.simple_tag(takes_context=True)
def can(context, codename):
    user = _user_from_context(context)
    if not user or not user.is_authenticated:
        return False
    return user_has_permission(user, codename)


@register.simple_tag(takes_context=True)
def can_any(context, *codenames):
    user = _user_from_context(context)
    if not user or not user.is_authenticated:
        return False
    return any(user_has_permission(user, code) for code in codenames)


@register.filter(name="has_perm")
def has_perm_filter(user, codename):
    """Usage: {% if request.user|has_perm:'manage_receipts' %}"""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user_has_permission(user, codename)


@register.simple_tag(takes_context=True)
def perm_btn(context, codename, href, label, css="btn btn-sm btn-outline-primary", icon=""):
    """
    Render a link button only if the user has *codename*.
    {% perm_btn "add_members" add_url "Add Member" "btn btn-primary btn-sm" "bi-person-plus" %}
    """
    user = _user_from_context(context)
    if not user or not user.is_authenticated:
        return ""
    if not user_has_permission(user, codename):
        return ""
    icon_html = format_html('<i class="bi {} me-1"></i>', icon) if icon else ""
    return format_html(
        '<a href="{}" class="{}">{}{}</a>',
        href,
        css,
        icon_html,
        label,
    )


@register.simple_tag(takes_context=True)
def perm_btn_any(context, codenames, href, label, css="btn btn-sm btn-outline-primary", icon=""):
    """codenames: comma-separated string. Renders if user has any of them."""
    user = _user_from_context(context)
    if not user or not user.is_authenticated:
        return ""
    codes = [c.strip() for c in str(codenames).split(",") if c.strip()]
    if not any(user_has_permission(user, c) for c in codes):
        return ""
    icon_html = format_html('<i class="bi {} me-1"></i>', icon) if icon else ""
    return format_html(
        '<a href="{}" class="{}">{}{}</a>',
        href,
        css,
        icon_html,
        label,
    )
