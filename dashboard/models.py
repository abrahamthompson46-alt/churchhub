from django.db import models
from django.conf import settings


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ("INFO", "Info"),
        ("FINANCE", "Finance"),
        ("MEMBER", "Member"),
        ("MEETING", "Meeting"),
        ("SYSTEM", "System"),
    ]
    SEVERITY_CHOICES = [
        ("INFO", "Info"),
        ("SUCCESS", "Success"),
        ("WARNING", "Warning"),
        ("CRITICAL", "Critical"),
    ]
    VALID_CATEGORIES = frozenset(c[0] for c in CATEGORY_CHOICES)
    VALID_SEVERITIES = frozenset(c[0] for c in SEVERITY_CHOICES)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200, default="Notification")
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="INFO")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="INFO")
    event_key = models.CharField(
        max_length=120,
        blank=True,
        db_index=True,
        help_text="Stable key so unread duplicates of the same event are coalesced.",
    )
    occurrence_count = models.PositiveIntegerField(default=1)
    action_url = models.CharField(max_length=500, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_event_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-last_event_at", "-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "-last_event_at"], name="dash_n_user_lstev_idx"),
            models.Index(fields=["user", "read"]),
            models.Index(fields=["user", "category", "read"]),
            models.Index(fields=["user", "event_key", "read"], name="dash_n_user_evtrd_idx"),
        ]

    def __str__(self):
        return f"{self.user}: {self.title}"

    def mark_read(self):
        if not self.read:
            self.read = True
            self.save(update_fields=["read"])
