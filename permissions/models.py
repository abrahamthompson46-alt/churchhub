import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from permissions.roles import UserRole


class Permission(models.Model):
    """System permission definition (codename is the stable API key)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    codename = models.CharField(max_length=64, unique=True, db_index=True)
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=64, db_index=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "sort_order", "name"]

    def __str__(self):
        return self.name


class RolePermission(models.Model):
    """Role × permission matrix cell."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=30, choices=UserRole.CHOICES, db_index=True)
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_grants",
    )
    granted = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_permission_updates",
    )

    class Meta:
        unique_together = [("role", "permission")]
        ordering = ["role", "permission__category", "permission__sort_order"]
        indexes = [
            models.Index(fields=["role", "permission"]),
        ]

    def __str__(self):
        state = "granted" if self.granted else "denied"
        return f"{UserRole.label(self.role)} — {self.permission.codename} ({state})"


class PermissionOverride(models.Model):
    """Per-user grant or deny override (takes precedence over the role matrix)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="permission_overrides",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="user_overrides",
    )
    granted = models.BooleanField(
        help_text="True = grant permission; False = explicitly deny.",
    )
    reason = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="overrides_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "permission", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        state = "grant" if self.granted else "deny"
        return f"{self.user.username} — {self.permission.codename} ({state})"

    @property
    def is_expired(self):
        return self.expires_at and timezone.now() > self.expires_at

    @property
    def is_effective(self):
        return self.is_active and not self.is_expired


class PermissionAuditLog(models.Model):
    """Audit trail for matrix and override changes."""

    ACTION_CHOICES = [
        ("MATRIX_UPDATE", "Matrix Update"),
        ("MATRIX_RESET", "Matrix Reset"),
        ("OVERRIDE_CREATE", "Override Created"),
        ("OVERRIDE_UPDATE", "Override Updated"),
        ("OVERRIDE_DELETE", "Override Removed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_audit_actions",
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_audit_targets",
    )
    details = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.created_at:%Y-%m-%d %H:%M}"
