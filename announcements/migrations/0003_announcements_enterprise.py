# Generated manually for announcements enterprise upgrade.

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def backfill_status(apps, schema_editor):
    Announcement = apps.get_model("announcements", "Announcement")
    for ann in Announcement.objects.all().iterator():
        if ann.is_archived:
            ann.status = "ARCHIVED"
        elif getattr(ann, "is_rejected", False):
            ann.status = "REJECTED"
        elif ann.is_approved:
            ann.status = "APPROVED"
        else:
            ann.status = "PENDING"
        ann.save(update_fields=["status"])


class Migration(migrations.Migration):

    dependencies = [
        ("announcements", "0002_announcement_archived_at_announcement_archived_by_and_more"),
        ("organization", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="is_rejected",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="announcement",
            name="rejected_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="announcement",
            name="rejected_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="announcements_rejected",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="rejection_reason",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="announcement",
            name="publish_at",
            field=models.DateTimeField(
                blank=True,
                help_text="If set, announcement is hidden from the public list until this time.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("ARCHIVED", "Archived"),
                ],
                db_index=True,
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="announcement",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(
                fields=["church", "status", "is_archived"],
                name="ann_church_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(
                fields=["is_approved", "is_archived", "event_date"],
                name="ann_visible_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(fields=["created_at"], name="ann_created_idx"),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(fields=["publish_at"], name="ann_publish_at_idx"),
        ),
        migrations.AddIndex(
            model_name="announcementview",
            index=models.Index(
                fields=["announcement", "viewed_at"],
                name="ann_view_ann_idx",
            ),
        ),
        migrations.CreateModel(
            name="AnnouncementAuditLog",
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
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("CREATE", "Create"),
                            ("UPDATE", "Update"),
                            ("APPROVE", "Approve"),
                            ("REJECT", "Reject"),
                            ("ARCHIVE", "Archive"),
                            ("PIN", "Pin"),
                            ("UNPIN", "Unpin"),
                            ("EXPORT", "Export"),
                        ],
                        max_length=20,
                    ),
                ),
                ("details", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "announcement",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="audit_logs",
                        to="announcements.announcement",
                    ),
                ),
                (
                    "church",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="announcement_audit_logs",
                        to="organization.church",
                    ),
                ),
                (
                    "performed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="announcement_audit_actions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="announcementauditlog",
            index=models.Index(
                fields=["church", "created_at"],
                name="ann_audit_church_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="announcementauditlog",
            index=models.Index(
                fields=["announcement", "created_at"],
                name="ann_audit_ann_idx",
            ),
        ),
        migrations.RunPython(backfill_status, migrations.RunPython.noop),
    ]
