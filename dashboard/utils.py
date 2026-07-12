"""Dashboard URL and redirect helpers."""


def safe_internal_redirect(url, fallback):
    """
    Return *url* only when it is a same-origin relative path.

    Rejects empty values, scheme-relative URLs (//…), and absolute URLs
    to prevent open redirects. *fallback* may be a URL name or path.
    """
    if not url or not isinstance(url, str):
        return fallback
    candidate = url.strip()
    if not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate
