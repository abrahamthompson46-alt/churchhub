"""Print production-readiness gaps without exposing secret values."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Check env/settings needed for a controlled production deploy. "
        "Does not print secret values. Host TLS, UFW, Fail2Ban, and restore "
        "drills remain operator steps."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit 1 when any recommended production item is missing.",
        )

    def handle(self, *args, **options):
        rows = []

        def note(ok, label, detail=""):
            rows.append((ok, label, detail))

        debug = bool(getattr(settings, "DEBUG", True))
        note(not debug, "DEBUG is False", f"DEBUG={debug}")
        note(bool((getattr(settings, "MFA_ENCRYPTION_KEY", "") or "").strip()), "MFA_ENCRYPTION_KEY set")
        note(bool((getattr(settings, "HEALTH_CHECK_TOKEN", "") or "").strip()), "CHURCHHUB_HEALTH_TOKEN set")
        note(bool((getattr(settings, "REDIS_URL", "") or "").strip()), "REDIS_URL set")
        public = (getattr(settings, "CHURCHHUB_PUBLIC_URL", "") or "").strip()
        note(public.startswith("https://"), "CHURCHHUB_PUBLIC_URL is https", public or "(empty)")
        beat = getattr(settings, "CELERY_BEAT_SCHEDULE", {}) or {}
        note("remind-birthday-desk-daily" in beat, "Celery Beat includes birthday reminder")
        note("purge-birthday-flyers-weekly" in beat, "Celery Beat includes flyer purge")
        note("database-backup-daily" in beat, "Celery Beat includes database backup")
        note(int(getattr(settings, "SESSION_ABSOLUTE_AGE", 0) or 0) > 0, "Absolute session age configured")
        note(int(getattr(settings, "SECURE_HSTS_SECONDS", 0) or 0) >= 31536000, "HSTS at least 1 year")

        missing = 0
        for ok, label, detail in rows:
            mark = "OK" if ok else "MISSING"
            if not ok:
                missing += 1
            extra = f" ({detail})" if detail else ""
            self.stdout.write(f"{mark}: {label}{extra}")

        self.stdout.write("")
        self.stdout.write(
            "Operator-only (this command cannot do them): TLS at the edge, "
            "UFW/Fail2Ban, offsite backup, manage.py migrate, "
            "manage.py reencrypt_mfa_secrets, manage.py restore_drill."
        )
        if options["strict"] and missing:
            raise CommandError(f"{missing} production check(s) failed.")
