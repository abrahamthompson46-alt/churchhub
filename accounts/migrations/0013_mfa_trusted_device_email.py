import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_mfa_enforcement"),
    ]

    operations = [
        migrations.AlterField(
            model_name="useractivitylog",
            name="action",
            field=models.CharField(
                choices=[
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("PASSWORD_CHANGE", "Password Change"),
                    ("ROLE_CHANGE", "Role Change"),
                    ("CHURCH_ASSIGN", "Church Assignment"),
                    ("USER_CREATE", "User Created"),
                    ("USER_DEACTIVATE", "User Deactivated"),
                    ("USER_ACTIVATE", "User Activated"),
                    ("INVITE_SENT", "Invitation Sent"),
                    ("INVITE_ACCEPTED", "Invitation Accepted"),
                    ("INVITE_REVOKED", "Invitation Revoked"),
                    ("INVITE_RESENT", "Invitation Resent"),
                    ("PROFILE_UPDATE", "Profile Updated"),
                    ("EMAIL_CHANGE", "Email Changed"),
                    ("SCOPE_CHANGE", "Organization Scope Changed"),
                    ("MFA_ENROLL", "MFA Enrolled"),
                    ("MFA_VERIFY", "MFA Verified"),
                    ("MFA_RECOVERY", "MFA Recovery Code Used"),
                    ("MFA_EMAIL", "MFA Email Code Used"),
                    ("MFA_TRUSTED_DEVICE", "MFA Trusted Device Login"),
                ],
                max_length=30,
            ),
        ),
        migrations.CreateModel(
            name="TrustedDevice",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("token_hash", models.CharField(db_index=True, max_length=64)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                ("user_agent", models.CharField(blank=True, default="", max_length=300)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="trusted_devices",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-last_used_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "expires_at"],
                        name="accounts_tr_user_id_7b8e0a_idx",
                    ),
                    models.Index(
                        fields=["token_hash", "expires_at"],
                        name="accounts_tr_token_h_1c2d3e_idx",
                    ),
                ],
            },
        ),
    ]
