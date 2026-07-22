from django.db import models
from django.conf import settings


class Notification(models.Model):
    CATEGORY_CHOICES = [
        ("INFO", "Info"),
        ("FINANCE", "Finance"),
        ("MEMBER", "Member"),
        ("SYSTEM", "System"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    title = models.CharField(max_length=200, default="Notification")
    message = models.TextField()
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="INFO")
    action_url = models.CharField(max_length=500, blank=True)
    read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "read"]),
        ]

    def __str__(self):
        return f"{self.user}: {self.title}"

    def mark_read(self):
        if not self.read:
            self.read = True
            self.save(update_fields=["read"])
