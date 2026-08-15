import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone

from organization.models import Church, Conference, District, GeneralConference, Union, Zone
from permissions.org_scope import OrgScopeLevel, infer_scope_level, scope_display
from permissions.roles import UserRole


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    role = models.CharField(
        max_length=30,
        choices=UserRole.CHOICES,
        default=UserRole.MEMBER,
    )

    scope_level = models.CharField(
        max_length=30,
        choices=OrgScopeLevel.CHOICES,
        default=OrgScopeLevel.CHURCH,
        db_index=True,
        help_text="Organization tree level this user may administer (subtree access).",
    )

    church = models.ForeignKey(
        Church,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Home church. Required for local roles; optional anchor for hierarchy admins.",
    )

    scope_district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoped_users",
    )
    scope_zone = models.ForeignKey(
        Zone,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoped_users",
    )
    scope_conference = models.ForeignKey(
        Conference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoped_users",
    )
    scope_union = models.ForeignKey(
        Union,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoped_users",
    )
    scope_general_conference = models.ForeignKey(
        GeneralConference,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoped_users",
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
        help_text="When True, MFA is enrolled for this user (enforced only if site policy requires it).",
    )
    mfa_secret = models.TextField(
        blank=True,
        default="",
        help_text="Encrypted TOTP shared secret (empty when MFA is not enrolled).",
    )
    mfa_recovery_hashes = models.JSONField(
        default=list,
        blank=True,
        help_text="SHA-256 hashes of unused MFA recovery codes.",
    )

    must_change_password = models.BooleanField(
        default=False,
        help_text="When True, member portal users must set a new password after sign-in.",
    )

    max_receipt_auto_approve = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Per-user override: receipts up to this amount auto-approve. "
            "Blank = use church treasury policy. 0 = always need second approval."
        ),
    )

    class Meta:
        indexes = [
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["church", "is_active"]),
            models.Index(fields=["scope_level", "is_active"]),
        ]

    def __str__(self):
        return f"{self.username} - {self.role}"

    @property
    def requires_church(self):
        """Local roles must be assigned to a church."""
        if self.is_platform_user:
            return False
        return UserRole.requires_church(self.role)

    @property
    def effective_scope_level(self):
        return infer_scope_level(self)

    @property
    def scope_summary(self):
        return scope_display(self)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        if self.is_platform_user:
            if self.church_id:
                raise ValidationError({"church": "Platform users cannot be assigned to a church."})
            if self.is_staff and not self.is_superuser:
                raise ValidationError({"is_staff": "Platform operators use /platform/, not Django admin staff."})
            return

        level = self.scope_level or OrgScopeLevel.default_for_role(self.role)
        if self.requires_church and not self.church_id:
            raise ValidationError({"church": "This role requires a home church."})
        if level == OrgScopeLevel.DISTRICT and not (
            self.scope_district_id or self.church_id
        ):
            raise ValidationError({"scope_district": "District scope requires a district."})
        if level == OrgScopeLevel.ZONE and not (self.scope_zone_id or self.church_id):
            raise ValidationError({"scope_zone": "Zone scope requires a zone."})
        if level == OrgScopeLevel.CONFERENCE and not (
            self.scope_conference_id or self.church_id
        ):
            raise ValidationError({"scope_conference": "Conference scope requires a conference."})
        if level == OrgScopeLevel.UNION and not self.scope_union_id:
            raise ValidationError({"scope_union": "Union scope requires a union."})
        if level == OrgScopeLevel.DENOMINATION and not (
            self.denomination_id or self.church_id
        ):
            raise ValidationError(
                {"denomination": "Denomination scope requires a denomination assignment."}
            )

    def save(self, *args, **kwargs):
        if self.is_platform_user:
            self.church = None
            self.scope_level = OrgScopeLevel.DENOMINATION
            if not self.is_superuser:
                self.is_staff = False
        else:
            role_default = OrgScopeLevel.default_for_role(self.role)
            if not self.scope_level:
                self.scope_level = role_default
            elif (
                self._state.adding
                and self.scope_level == OrgScopeLevel.CHURCH
                and role_default != OrgScopeLevel.CHURCH
                and not self.scope_district_id
                and not self.scope_zone_id
                and not self.scope_conference_id
                and not self.scope_union_id
                and not self.scope_general_conference_id
            ):
                # Model field default is CHURCH; promote to the role default on create
                # when no wider scope unit was explicitly chosen.
                self.scope_level = role_default
            if not self.is_superuser:
                self.is_staff = False
            # Keep denomination aligned with church when church is set.
            if self.church_id and self.church:
                church_denom = getattr(self.church, "denomination", None)
                if church_denom and self.denomination_id != church_denom.pk:
                    self.denomination = church_denom

        # CH-SEC-L1: refuse persisting unanchored denomination-scoped / SUPER_ADMIN
        # institution users. Do not call full_clean() for all roles (would break
        # legacy create_superuser fixtures that are MEMBER+is_superuser without church).
        # Ops should quarantine historical unanchored SUPER_ADMIN rows separately.
        update_fields = kwargs.get("update_fields")
        tenancy_touched = update_fields is None or any(
            f in update_fields
            for f in (
                "role",
                "denomination",
                "church",
                "is_platform_user",
                "scope_level",
            )
        )
        if tenancy_touched and not getattr(self, "is_platform_user", False):
            from django.core.exceptions import ValidationError

            level = self.scope_level or OrgScopeLevel.default_for_role(self.role)
            needs_denom_anchor = (
                level == OrgScopeLevel.DENOMINATION
                or self.role == UserRole.SUPER_ADMIN
            )
            if needs_denom_anchor and not self.denomination_id and not self.church_id:
                raise ValidationError(
                    {
                        "denomination": (
                            "Denomination-scoped users and institution SUPER_ADMIN "
                            "must be assigned a denomination or a church."
                        )
                    }
                )
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
        ("SCOPE_CHANGE", "Organization Scope Changed"),
        ("MFA_ENROLL", "MFA Enrolled"),
        ("MFA_VERIFY", "MFA Verified"),
        ("MFA_RECOVERY", "MFA Recovery Code Used"),
        ("MFA_EMAIL", "MFA Email Code Used"),
        ("MFA_TRUSTED_DEVICE", "MFA Trusted Device Login"),
        ("INSTITUTION_BRANDING_UPDATE", "Institution Branding Updated"),
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
    scope_level = models.CharField(
        max_length=30,
        choices=OrgScopeLevel.CHOICES,
        default=OrgScopeLevel.CHURCH,
    )
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invitations",
        help_text="Home church (required for local roles).",
    )
    scope_district = models.ForeignKey(
        District, on_delete=models.CASCADE, null=True, blank=True, related_name="invitations"
    )
    scope_zone = models.ForeignKey(
        Zone, on_delete=models.CASCADE, null=True, blank=True, related_name="invitations"
    )
    scope_conference = models.ForeignKey(
        Conference, on_delete=models.CASCADE, null=True, blank=True, related_name="invitations"
    )
    scope_union = models.ForeignKey(
        Union, on_delete=models.CASCADE, null=True, blank=True, related_name="invitations"
    )
    scope_general_conference = models.ForeignKey(
        GeneralConference,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invitations",
    )
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
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
        target = self.church.name if self.church_id else self.get_scope_level_display()
        return f"Invite {self.email} → {target}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_revoked(self):
        return self.revoked_at is not None

    @property
    def is_valid(self):
        """Pending invites only: not accepted (single-use), not expired, not revoked."""
        return not self.is_accepted and not self.is_expired and not self.is_revoked


class TrustedDevice(models.Model):
    """Remembered browser/device that may skip MFA for a limited period."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="trusted_devices",
    )
    token_hash = models.CharField(max_length=64, db_index=True)
    label = models.CharField(max_length=200, blank=True, default="")
    user_agent = models.CharField(max_length=300, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-last_used_at"]
        indexes = [
            models.Index(fields=["user", "expires_at"]),
            models.Index(fields=["token_hash", "expires_at"]),
        ]

    def __str__(self):
        return f"TrustedDevice({self.user_id}, expires={self.expires_at:%Y-%m-%d})"

    @property
    def is_valid(self):
        return timezone.now() < self.expires_at
