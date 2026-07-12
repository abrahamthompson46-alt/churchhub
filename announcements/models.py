"""Church announcements — models with approval lifecycle and audit."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from organization.models import Church

MAX_PINNED_PER_CHURCH = 3
MAX_ANNOUNCEMENT_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_CONTENT_TYPES = frozenset({
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
})


class Announcement(models.Model):
    VISIBILITY_CHOICES = (
        ("general", "General"),
        ("church", "Church Only"),
    )
    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_ARCHIVED = "ARCHIVED"
    STATUS_CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_ARCHIVED, "Archived"),
    )

    title = models.CharField(max_length=255)
    content = models.TextField()

    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcements",
    )

    visibility = models.CharField(
        max_length=10,
        choices=VISIBILITY_CHOICES,
        default="church",
    )

    event_date = models.DateTimeField(null=True, blank=True)
    publish_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, announcement is hidden from the public list until this time.",
    )
    auto_expire = models.BooleanField(default=True)

    is_pinned = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    is_rejected = models.BooleanField(default=False)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcements_created",
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_rejected",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default="")

    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements_archived",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"
        indexes = [
            models.Index(
                fields=["church", "status", "is_archived"],
                name="ann_church_status_idx",
            ),
            models.Index(fields=["is_approved", "is_archived", "event_date"], name="ann_visible_idx"),
            models.Index(fields=["created_at"], name="ann_created_idx"),
            models.Index(fields=["publish_at"], name="ann_publish_at_idx"),
        ]

    def is_expired(self):
        if self.auto_expire and self.event_date:
            return timezone.now() > self.event_date
        return False

    def is_scheduled_future(self):
        if self.publish_at and self.publish_at > timezone.now():
            return True
        return False

    def sync_status_flags(self):
        """Keep status and boolean flags consistent."""
        if self.is_archived:
            self.status = self.STATUS_ARCHIVED
        elif self.is_rejected:
            self.status = self.STATUS_REJECTED
            self.is_approved = False
        elif self.is_approved:
            self.status = self.STATUS_APPROVED
            self.is_rejected = False
        else:
            self.status = self.STATUS_PENDING

    def clean(self):
        super().clean()
        if self.visibility == "church" and not self.church_id:
            raise ValidationError({"church": "Church is required for church-scoped announcements."})
        if self.visibility == "general":
            self.church = None

    def save(self, *args, **kwargs):
        if self.visibility == "general":
            self.church = None
        if self.is_approved and not self.approved_at:
            self.approved_at = timezone.now()
        self.sync_status_flags()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class AnnouncementImage(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to="announcements/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if not self.image:
            return
        f = self.image
        size = getattr(f, "size", None)
        if size is not None and size > MAX_ANNOUNCEMENT_IMAGE_BYTES:
            raise ValidationError(
                {"image": f"Image must be {MAX_ANNOUNCEMENT_IMAGE_BYTES // (1024 * 1024)} MB or smaller."}
            )
        content_type = getattr(getattr(f, "file", None), "content_type", None) or getattr(
            f, "content_type", None
        )
        if content_type and content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise ValidationError(
                {"image": "Only JPEG, PNG, GIF, or WebP images are allowed."}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Image for {self.announcement.title}"


class AnnouncementView(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="announcement_views",
    )
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("announcement", "user")
        verbose_name = "Announcement View"
        verbose_name_plural = "Announcement Views"
        indexes = [
            models.Index(fields=["announcement", "viewed_at"], name="ann_view_ann_idx"),
        ]

    def __str__(self):
        return f"{self.user} viewed {self.announcement.title}"


class AnnouncementAuditLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("APPROVE", "Approve"),
        ("REJECT", "Reject"),
        ("ARCHIVE", "Archive"),
        ("PIN", "Pin"),
        ("UNPIN", "Unpin"),
        ("EXPORT", "Export"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="announcement_audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcement_audit_actions",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "created_at"], name="ann_audit_church_idx"),
            models.Index(fields=["announcement", "created_at"], name="ann_audit_ann_idx"),
        ]

    def __str__(self):
        return f"{self.action} — {self.announcement_id}"
