from audit.context import bind_audit_request, clear_audit_request


class AuditRequestMiddleware:
    """Expose the current request to emit_event without changing finance call sites."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        bind_audit_request(request)
        try:
            return self.get_response(request)
        finally:
            clear_audit_request()
