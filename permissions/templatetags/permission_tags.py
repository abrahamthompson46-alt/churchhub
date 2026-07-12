from django import template

from permissions.services import user_has_permission

register = template.Library()


@register.simple_tag(takes_context=True)
def can(context, codename):
    request = context.get("request")
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    return user_has_permission(user, codename)


@register.simple_tag(takes_context=True)
def can_any(context, *codenames):
    request = context.get("request")
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return False
    return any(user_has_permission(user, code) for code in codenames)
