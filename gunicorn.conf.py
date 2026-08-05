"""Gunicorn configuration for ChurchHub production / staging.

VPS (Nginx on same host): bind 127.0.0.1 so only the reverse proxy can reach Gunicorn.
Docker/Render: set GUNICORN_BIND=0.0.0.0:8000 (or PORT).
"""

import os

# Prefer explicit bind; default loopback for self-host defense in depth.
_bind = os.environ.get("GUNICORN_BIND", "").strip()
if not _bind:
    _port = os.environ.get("PORT", "8000")
    _host = os.environ.get("GUNICORN_HOST", "127.0.0.1")
    _bind = f"{_host}:{_port}"
bind = _bind

workers = int(os.environ.get("GUNICORN_WORKERS") or os.environ.get("WEB_CONCURRENCY") or "2")
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.environ.get("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.environ.get("GUNICORN_KEEPALIVE", "5"))
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "50"))
preload_app = os.environ.get("GUNICORN_PRELOAD", "false").lower() in ("true", "1", "yes")

accesslog = os.environ.get("GUNICORN_ACCESS_LOG", "-")
errorlog = os.environ.get("GUNICORN_ERROR_LOG", "-")
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")
capture_output = True

worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
# Only trust X-Forwarded-* from the local Nginx proxy by default.
forwarded_allow_ips = os.environ.get("GUNICORN_FORWARDED_ALLOW_IPS", "127.0.0.1")
proxy_allow_from = os.environ.get("GUNICORN_PROXY_ALLOW_FROM", "127.0.0.1")
