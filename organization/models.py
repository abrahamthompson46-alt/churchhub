import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

class GeneralConference(models.Model):
    """Top-level church administration body."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "general conferences"

    def __str__(self):
        return self.name


class Union(models.Model):
    """Regional union between General Conference and local conferences."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    general_conference = models.ForeignKey(
        GeneralConference,
        on_delete=models.CASCADE,
        related_name="unions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "general_conference")
        verbose_name_plural = "unions"

    def __str__(self):
        return f"{self.name} ({self.general_conference.name})"


class Conference(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, unique=True)
    code = models.CharField(max_length=20, unique=True)
    denomination = models.ForeignKey(
        "sitecontrol.Denomination",
        on_delete=models.PROTECT,
        related_name="conferences",
        null=True,
        blank=True,
    )
    union = models.ForeignKey(
        Union,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conferences",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class Zone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    conference = models.ForeignKey(
        Conference,
        on_delete=models.CASCADE,
        related_name="zones"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "conference")
        constraints = [
            models.UniqueConstraint(
                fields=["conference", "code"],
                name="uniq_zone_code_per_conference",
            ),
        ]
        indexes = [
            models.Index(fields=["conference", "code"], name="org_zone_conf_code_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.conference.name})"


class District(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    zone = models.ForeignKey(
        Zone,
        on_delete=models.CASCADE,
        related_name="districts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "zone")
        constraints = [
            models.UniqueConstraint(
                fields=["zone", "code"],
                name="uniq_district_code_per_zone",
            ),
        ]
        indexes = [
            models.Index(fields=["zone", "code"], name="org_dist_zone_code_idx"),
        ]

    def __str__(self):
        return f"{self.name} ({self.zone.name})"


class Church(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=20)
    address = models.TextField(blank=True)
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive churches are hidden from operations and user assignment.",
    )
    financials_provisioned = models.BooleanField(
        default=False,
        help_text="True after denomination/default financial seeds have been applied.",
    )
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name="churches",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("name", "district")
        constraints = [
            models.UniqueConstraint(
                fields=["district", "code"],
                name="uniq_church_code_per_district",
            ),
        ]
        indexes = [
            models.Index(fields=["district", "code"], name="org_church_dist_code_idx"),
        ]

    def clean(self):
        if self.district_id and self.pk:
            previous = Church.objects.filter(pk=self.pk).select_related(
                "district__zone__conference"
            ).first()
            if previous and previous.district_id != self.district_id:
                old_denom = previous.conference.denomination_id if previous.conference else None
                new_denom = self.conference.denomination_id if self.conference else None
                if old_denom != new_denom:
                    raise ValidationError(
                        "Cannot transfer a church to a district in another denomination. "
                        "Use the church transfer workflow."
                    )

    def __str__(self):
        return f"{self.name} ({self.district.name})"

    @property
    def zone(self):
        return self.district.zone

    @property
    def conference(self):
        return self.district.zone.conference

    @property
    def union(self):
        conf = self.conference
        return conf.union if conf and conf.union_id else None

    @property
    def general_conference(self):
        union = self.union
        return union.general_conference if union else None

    @property
    def denomination(self):
        return self.conference.denomination if self.conference else None


class ChurchHistoryEntry(models.Model):
    """Institutional chronicle entry for a local church (Church Life history panel)."""

    class Category(models.TextChoices):
        FOUNDING = "FOUNDING", "Founding"
        BUILDING = "BUILDING", "Building / Facility"
        PASTORATE = "PASTORATE", "Pastorate"
        LEADERSHIP = "LEADERSHIP", "Leadership"
        MILESTONE = "MILESTONE", "Milestone"
        EVENT = "EVENT", "Special Event"
        OTHER = "OTHER", "Other"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    title = models.CharField(max_length=200)
    body = models.TextField(
        help_text="Narrative details preserved for future reference.",
    )
    event_date = models.DateField(
        help_text="When this history event occurred (or best known date).",
    )
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.MILESTONE,
        db_index=True,
    )
    location = models.CharField(max_length=200, blank=True)
    tags = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional keywords for search (comma-separated).",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="church_history_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="church_history_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-event_date", "-created_at"]
        verbose_name = "church history entry"
        verbose_name_plural = "church history entries"
        indexes = [
            models.Index(fields=["church", "-event_date"], name="org_chhist_church_date_idx"),
            models.Index(fields=["category", "-event_date"], name="org_chhist_cat_date_idx"),
        ]

    def __str__(self):
        return f"{self.event_date:%Y-%m-%d} — {self.title}"


class OrganizationAuditLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("DEACTIVATE", "Deactivate"),
        ("ACTIVATE", "Activate"),
        ("TRANSFER", "Transfer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    entity_type = models.CharField(max_length=30)
    entity_id = models.UUIDField()
    entity_label = models.CharField(max_length=255, blank=True)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="organization_audit_actions",
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} {self.entity_type} — {self.created_at:%Y-%m-%d %H:%M}"
