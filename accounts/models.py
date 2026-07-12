import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from organization.models import Church


from permissions.roles import UserRole


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    role = models.CharField(
        max_length=30,
        choices=UserRole.CHOICES,
        default=UserRole.MEMBER,
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
    )

    phone = models.CharField(max_length=20, blank=True)

    member = models.OneToOneField(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_account",
    )

    is_platform_user = models.BooleanField(
        default=False,
        help_text="Platform operator — access /platform/ only, not the institution dashboard.",
    )

    platform_role = models.CharField(
        max_length=20,
        blank=True,
        default="",
        choices=[
            ("OWNER", "Platform Owner"),
            ("SECURITY", "Security Admin"),
            ("BILLING", "Billing Admin"),
            ("SUPPORT", "Support Operator"),
            ("READONLY", "Read Only"),
        ],
        help_text="Meaningful only when is_platform_user=True. Controls platform capabilities.",
    )

    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="institution_users",
        help_text="Required for hierarchy admins without a church; must match church denomination.",
    )

    managed_denominations = models.ManyToManyField(
        "sitecontrol.Denomination",
        blank=True,
        related_name="platform_operators",
        help_text=(
            "Platform operators: denominations this operator may manage. "
            "Empty no longer means global — only Owner / break-glass superusers have global access."
        ),
    )

    mfa_enabled = models.BooleanField(
        default=False,
        help_text="MFA readiness stub — enforcement not yet implemented.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["church", "is_active"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.role}"

    @property
    def requires_church(self):
        """Local roles must be assigned to a church."""
        if self.is_platform_user:
            return False
        return UserRole.requires_church(self.role)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.is_platform_user:
            if self.church_id:
                raise ValidationError({"church": "Platform users cannot be assigned to a church."})
            if self.is_staff and not self.is_superuser:
                raise ValidationError({"is_staff": "Platform operators use /platform/, not Django admin staff."})

    def save(self, *args, **kwargs):
        if self.is_platform_user:
            self.church = None
            if not self.is_superuser:
                self.is_staff = False
        elif not self.is_superuser:
            self.is_staff = False
        super().save(*args, **kwargs)


class UserActivityLog(models.Model):
    ACTION_CHOICES = [
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
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activity_actions_performed",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "action"]),
            models.Index(fields=["-created_at"]),
        ]

    def __str__(self):
        return f"{self.user.username} — {self.action} — {self.created_at:%Y-%m-%d %H:%M}"


class UserInvitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    username = models.CharField(max_length=150)
    role = models.CharField(max_length=30, choices=UserRole.CHOICES)
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="invitations",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invitations_sent",
    )
    is_accepted = models.BooleanField(default=False)
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invite {self.email} → {self.church.name}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_valid(self):
        return not self.is_accepted and not self.is_expired and not self.is_revoked
