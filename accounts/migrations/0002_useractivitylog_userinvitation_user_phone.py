# Generated manually for accounts enterprise upgrade

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["role", "is_active"], name="accounts_us_role_8a1f2c_idx"),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["church", "is_active"], name="accounts_us_church_4e9b1a_idx"),
        ),
        migrations.CreateModel(
            name="UserActivityLog",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("action", models.CharField(choices=[
                    ("LOGIN", "Login"), ("LOGOUT", "Logout"), ("PASSWORD_CHANGE", "Password Change"),
                    ("ROLE_CHANGE", "Role Change"), ("CHURCH_ASSIGN", "Church Assignment"),
                    ("USER_CREATE", "User Created"), ("USER_DEACTIVATE", "User Deactivated"),
                    ("USER_ACTIVATE", "User Activated"), ("INVITE_SENT", "Invitation Sent"),
                    ("INVITE_ACCEPTED", "Invitation Accepted"),
                ], max_length=30)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("performed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="activity_actions_performed", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="activity_logs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="UserInvitation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("email", models.EmailField(max_length=254)),
                ("username", models.CharField(max_length=150)),
                ("role", models.CharField(choices=[
                    ("SUPER_ADMIN", "Super Admin"), ("GENERAL_OVERSEER", "General Overseer"),
                    ("DISTRICT_PASTOR", "District Pastor"), ("LOCAL_PASTOR", "Local Pastor"),
                    ("SECRETARY", "Secretary"), ("TREASURY", "Treasury"), ("MEMBER", "Member"),
                ], max_length=30)),
                ("token", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("is_accepted", models.BooleanField(default=False)),
                ("accepted_at", models.DateTimeField(blank=True, null=True)),
                ("expires_at", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("church", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="invitations", to="organization.church")),
                ("invited_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="invitations_sent", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["user", "action"], name="accounts_us_user_id_7c3f1d_idx"),
        ),
        migrations.AddIndex(
            model_name="useractivitylog",
            index=models.Index(fields=["-created_at"], name="accounts_us_created_2a8e4b_idx"),
        ),
    ]
