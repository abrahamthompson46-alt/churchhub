"""Consistent flash messages across ChurchHub."""

from django.contrib import messages

TITLE_SEP = " || "


def _format(title, body):
    title = (title or "").strip()
    body = (body or "").strip()
    if title and body and title != body:
        return f"{title}{TITLE_SEP}{body}"
    return body or title


def flash_success(request, body, *, title="Success"):
    messages.success(request, _format(title, body))


def flash_error(request, body, *, title="Something went wrong"):
    messages.error(request, _format(title, body))


def flash_warning(request, body, *, title="Attention"):
    messages.warning(request, _format(title, body))


def flash_info(request, body, *, title="Notice"):
    messages.info(request, _format(title, body))


def flash_validation_errors(request, form, *, title="Please correct the following"):
    """Surface form errors as a single actionable flash message."""
    if not form or not form.errors:
        return
    parts = []
    for field, errs in form.errors.items():
        label = field.replace("_", " ").title() if field != "__all__" else "Form"
        for err in errs:
            parts.append(f"{label}: {err}")
    if parts:
        body = " ".join(parts[:3])
        if len(parts) > 3:
            body += f" (+{len(parts) - 3} more)"
        flash_error(request, body, title=title)


def flash_exception(request, exc, *, title="Something went wrong"):
    """User-safe error from an caught exception."""
    message = str(exc).strip() if exc else ""
    flash_error(request, message or "An unexpected error occurred. Please try again.", title=title)


def flash_denied(request, body="You do not have permission to open that page."):
    flash_warning(request, body, title="Access denied")
