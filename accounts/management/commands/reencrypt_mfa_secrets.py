from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.mfa import decrypt_totp_secret, encrypt_totp_secret

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Re-encrypt enrolled TOTP secrets with the current MFA_ENCRYPTION_KEY "
        "(falls back to SECRET_KEY). Run after setting MFA_ENCRYPTION_KEY."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count secrets that would be rewritten without saving.",
        )

    def handle(self, *args, **options):
        dry = options["dry_run"]
        rewritten = 0
        skipped = 0
        qs = User.objects.exclude(mfa_secret="").exclude(mfa_secret__isnull=True)
        for user in qs.iterator():
            plaintext = decrypt_totp_secret(user.mfa_secret)
            if not plaintext:
                skipped += 1
                continue
            rewritten += 1
            if dry:
                continue
            user.mfa_secret = encrypt_totp_secret(plaintext)
            user.save(update_fields=["mfa_secret"])
        self.stdout.write(
            self.style.SUCCESS(
                f"MFA secrets rewritten: {rewritten}; undecryptable skipped: {skipped}; "
                f"dry_run={dry}"
            )
        )
