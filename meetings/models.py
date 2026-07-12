import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from members.models import Department, Member
from organization.models import Church


class MeetingStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    HELD = "HELD", "Held"
    CANCELLED = "CANCELLED", "Cancelled"


class MeetingType(models.TextChoices):
    BOARD = "BOARD", "Board Meeting"
    CHURCH_BOARD = "CHURCH_BOARD", "Church Board"
    DEACONS = "DEACONS", "Deacons Council"
    DEPARTMENT = "DEPARTMENT", "Department Meeting"
    GENERAL = "GENERAL", "General Meeting"
    OTHER = "OTHER", "Other"


class MinutesStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class Meeting(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="meetings")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="meetings"
    )
    meeting_type = models.CharField(
        max_length=20,
        choices=MeetingType.choices,
        default=MeetingType.GENERAL,
    )
    title = models.CharField(max_length=255)
    agenda = models.TextField(blank=True)
    location = models.CharField(max_length=255, blank=True)
    chair_person = models.CharField(max_length=150, blank=True)
    secretary_name = models.CharField(max_length=150, blank=True)
    scheduled_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=MeetingStatus.choices, default=MeetingStatus.SCHEDULED)
    minutes_status = models.CharField(
        max_length=20,
        choices=MinutesStatus.choices,
        default=MinutesStatus.DRAFT,
    )
    minutes_locked = models.BooleanField(default=False)
    minutes_opening = models.TextField(blank=True, help_text="Call to order, opening prayer, quorum.")
    minutes_previous = models.TextField(blank=True, help_text="Approval of previous minutes.")
    minutes_deliberations = models.TextField(blank=True, help_text="Discussion and reports.")
    minutes_motions = models.TextField(blank=True, help_text="Motions raised.")
    minutes_votes = models.TextField(blank=True, help_text="Votes and outcomes.")
    minutes_adjournment = models.TextField(blank=True, help_text="Closing and adjournment.")
    minutes = models.TextField(blank=True, help_text="Supplementary notes.")
    minutes_submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_minutes_submitted",
    )
    minutes_submitted_at = models.DateTimeField(null=True, blank=True)
    minutes_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meetings_minutes_approved",
    )
    minutes_approved_at = models.DateTimeField(null=True, blank=True)
    minutes_rejection_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="meetings_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-scheduled_at"]
        indexes = [
            models.Index(fields=["church", "scheduled_at"]),
            models.Index(fields=["church", "minutes_status"]),
            models.Index(fields=["church", "meeting_type"]),
        ]

    def __str__(self):
        return self.title

    @property
    def minutes_editable(self):
        return not self.minutes_locked and self.minutes_status != MinutesStatus.APPROVED


class MeetingAttendance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attendees")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="meeting_attendance")
    is_present = models.BooleanField(default=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("meeting", "member")

    def __str__(self):
        return f"{self.member} @ {self.meeting.title}"


class MeetingAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="meetings/attachments/")
    label = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_attachments_uploaded",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.label or self.file.name


class ActionItemStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    IN_PROGRESS = "IN_PROGRESS", "In Progress"
    DONE = "DONE", "Done"


class MeetingActionItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="action_items")
    description = models.TextField()
    assigned_to = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_items"
    )
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ActionItemStatus.choices, default=ActionItemStatus.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_date", "created_at"]

    def __str__(self):
        return self.description[:50]


class MeetingDecision(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name="decisions")
    decision_text = models.TextField()
    motion_text = models.CharField(max_length=255, blank=True)
    vote_result = models.CharField(max_length=100, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.decision_text[:50]


class EventType(models.TextChoices):
    WORSHIP = "WORSHIP", "Worship Service"
    SABBATH_SCHOOL = "SABBATH_SCHOOL", "Sabbath School"
    PRAYER = "PRAYER", "Prayer Meeting"
    DEPARTMENT = "DEPARTMENT", "Department Event"
    OTHER = "OTHER", "Other"


class AttendanceEvent(models.Model):
    """Worship and event attendance (may link to a formal meeting)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="attendance_events")
    meeting = models.ForeignKey(
        Meeting, on_delete=models.SET_NULL, null=True, blank=True, related_name="attendance_events"
    )
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="attendance_events"
    )
    title = models.CharField(max_length=255)
    event_type = models.CharField(max_length=20, choices=EventType.choices, default=EventType.WORSHIP)
    event_date = models.DateField()
    headcount = models.PositiveIntegerField(default=0, help_text="Visitors/guests not in member roll")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="attendance_events_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-event_date"]

    def __str__(self):
        return f"{self.title} ({self.event_date})"

    @property
    def present_count(self):
        return self.records.filter(is_present=True).count()


class AttendanceRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(AttendanceEvent, on_delete=models.CASCADE, related_name="records")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="attendance_records")
    is_present = models.BooleanField(default=True)

    class Meta:
        unique_together = ("event", "member")

    def __str__(self):
        status = "Present" if self.is_present else "Absent"
        return f"{self.member} — {status}"
