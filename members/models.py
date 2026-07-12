import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from organization.models import Church


# ==============================
# CHOICES
# ==============================

class Gender(models.TextChoices):
    MALE = "Male", "Male"
    FEMALE = "Female", "Female"


class MaritalStatus(models.TextChoices):
    SINGLE = "Single", "Single"
    MARRIED = "Married", "Married"
    WIDOWED = "Widowed", "Widowed"
    DIVORCED = "Divorced", "Divorced"


class MembershipStatus(models.TextChoices):
    ACTIVE = "Active", "Active"
    INACTIVE = "Inactive", "Inactive"
    TRANSFERRED = "Transferred", "Transferred"
    DECEASED = "Deceased", "Deceased"


class RecordType(models.TextChoices):
    BAPTISM = "Baptism", "Baptism"
    MARRIAGE = "Marriage", "Marriage"
    FUNERAL = "Funeral", "Funeral"
    MEETING = "Meeting", "Meeting"
    TRANSFER = "Transfer", "Transfer"
    OTHER = "Other", "Other"


class RecordStatus(models.TextChoices):
    ACTIVE = "Active", "Active"
    ARCHIVED = "Archived", "Archived"


class TransferStatus(models.TextChoices):
    PENDING = "Pending", "Pending"
    COMPLETED = "Completed", "Completed"
    REJECTED = "Rejected", "Rejected"


AGE_GROUP_CHOICES = [
    ("CHILD", "Child (0–12)"),
    ("TEEN", "Teen (13–17)"),
    ("YOUTH", "Youth (18–35)"),
    ("ADULT", "Adult (36–59)"),
    ("SENIOR", "Senior (60+)"),
]


def age_group_for_age(age):
    if age is None:
        return ""
    if age <= 12:
        return "CHILD"
    if age <= 17:
        return "TEEN"
    if age <= 35:
        return "YOUTH"
    if age <= 59:
        return "ADULT"
    return "SENIOR"


# ==============================
# DEPARTMENT
# ==============================

class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="departments")
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==============================
# FAMILY
# ==============================

class Family(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="families")
    name = models.CharField(max_length=200)
    head = models.ForeignKey(
        "Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="families_as_head",
    )
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "families"
        unique_together = ("church", "name")
        ordering = ["name"]

    def clean(self):
        if self.head_id and self.church_id and self.head.church_id != self.church_id:
            raise ValidationError({"head": "Family head must belong to the same church."})

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.members.count()


# ==============================
# OCCUPATION
# ==============================

class Occupation(models.Model):
    name = models.CharField(max_length=150)
    church = models.ForeignKey(Church, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("church", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


# ==============================
# MEMBER
# ==============================

class Member(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE)
    occupation = models.ForeignKey(
        Occupation, on_delete=models.SET_NULL, null=True, blank=True
    )
    department = models.ForeignKey(
        "Department", on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )
    family = models.ForeignKey(
        "Family", on_delete=models.SET_NULL, null=True, blank=True, related_name="members"
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices)
    marital_status = models.CharField(
        max_length=20,
        choices=MaritalStatus.choices,
        blank=True,
        default="",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    date_joined = models.DateField(null=True, blank=True)
    membership_status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
    )
    is_active = models.BooleanField(default=True)
    membership_number = models.CharField(max_length=40, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    baptism_date = models.DateField(null=True, blank=True)
    baptism_place = models.CharField(max_length=200, blank=True, default="")
    baptism_certificate_number = models.CharField(max_length=60, blank=True, default="")
    profile_picture = models.ImageField(
        upload_to="members/profile_pictures/",
        null=True,
        blank=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="members_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["church", "is_active"]),
            models.Index(fields=["church", "membership_status"]),
            models.Index(fields=["church", "last_name", "first_name"]),
            models.Index(fields=["church", "phone"]),
            models.Index(fields=["last_name", "first_name"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "phone"],
                condition=~Q(phone=""),
                name="uniq_member_phone_per_church",
            ),
            models.UniqueConstraint(
                fields=["church", "membership_number"],
                condition=~Q(membership_number=""),
                name="uniq_member_number_per_church",
            ),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        if not self.date_of_birth:
            return None
        from datetime import date

        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return years

    @property
    def age_group(self):
        return age_group_for_age(self.age)

    def clean(self):
        errors = {}
        if self.membership_status == MembershipStatus.DECEASED and self.is_active:
            self.is_active = False
        if self.membership_status == MembershipStatus.TRANSFERRED and self.is_active:
            self.is_active = False
        if self.membership_status == MembershipStatus.INACTIVE and self.is_active:
            self.is_active = False
        if self.department_id and self.church_id and self.department.church_id != self.church_id:
            errors["department"] = "Department must belong to the member's church."
        if self.family_id and self.church_id and self.family.church_id != self.church_id:
            errors["family"] = "Family must belong to the member's church."
        if self.occupation_id and self.church_id and self.occupation.church_id != self.church_id:
            errors["occupation"] = "Occupation must belong to the member's church."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        current_user = getattr(self, "_current_user", None)
        if not self.pk and current_user:
            if not self.church_id and getattr(current_user, "church_id", None):
                self.church = current_user.church
            if not self.created_by_id:
                self.created_by = current_user
        if self.membership_status in (
            MembershipStatus.DECEASED,
            MembershipStatus.TRANSFERRED,
            MembershipStatus.INACTIVE,
        ):
            self.is_active = False
        elif self.membership_status == MembershipStatus.ACTIVE:
            self.is_active = True
        super().save(*args, **kwargs)


# ==============================
# MEMBER TRANSFER
# ==============================

class MemberTransfer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="transfers")
    from_church = models.ForeignKey(
        Church, on_delete=models.CASCADE, related_name="transfers_out"
    )
    to_church = models.ForeignKey(
        Church, on_delete=models.CASCADE, related_name="transfers_in"
    )
    status = models.CharField(
        max_length=20,
        choices=TransferStatus.choices,
        default=TransferStatus.PENDING,
    )
    transfer_date = models.DateField()
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="transfers_requested",
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transfers_processed",
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["from_church", "status"]),
            models.Index(fields=["to_church", "status"]),
        ]

    def __str__(self):
        return f"{self.member} → {self.to_church.name} ({self.status})"


# ==============================
# RECORD IMAGE
# ==============================

class RecordImage(models.Model):
    image = models.ImageField(upload_to="records/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Record Image {self.id}"


# ==============================
# RECORD
# ==============================

class Record(models.Model):
    church = models.ForeignKey(Church, on_delete=models.CASCADE)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="records",
    )
    record_type = models.CharField(max_length=50, choices=RecordType.choices)
    status = models.CharField(
        max_length=20,
        choices=RecordStatus.choices,
        default=RecordStatus.ACTIVE,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    place = models.CharField(max_length=200, blank=True, default="")
    officiant = models.CharField(max_length=150, blank=True, default="")
    certificate_number = models.CharField(max_length=60, blank=True, default="")
    images = models.ManyToManyField(RecordImage, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="records_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["church", "record_type", "event_date"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        current_user = getattr(self, "_current_user", None)
        if not self.pk and current_user:
            if not self.church_id and getattr(current_user, "church_id", None):
                self.church = current_user.church
            if not self.created_by_id:
                self.created_by = current_user
        super().save(*args, **kwargs)


# ==============================
# HISTORY IMAGE
# ==============================

class HistoryImage(models.Model):
    image = models.ImageField(upload_to="history/")
    uploaded_at = models.DateTimeField(auto_now_add=True)


# ==============================
# HISTORY
# ==============================

class History(models.Model):
    church = models.ForeignKey(Church, on_delete=models.CASCADE)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="history",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    date = models.DateField()
    images = models.ManyToManyField(HistoryImage, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        editable=False,
        related_name="history_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        current_user = getattr(self, "_current_user", None)
        if not self.pk and current_user:
            if not self.church_id and getattr(current_user, "church_id", None):
                self.church = current_user.church
            if not self.created_by_id:
                self.created_by = current_user
        super().save(*args, **kwargs)


# ==============================
# SPIRITUAL GIFTS
# ==============================

class SpiritualGift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="spiritual_gifts")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    class Meta:
        unique_together = ("church", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class MemberSpiritualGift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="spiritual_gift_assignments")
    gift = models.ForeignKey(SpiritualGift, on_delete=models.CASCADE, related_name="member_assignments")
    noted_at = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = ("member", "gift")

    def clean(self):
        if self.member_id and self.gift_id and self.member.church_id != self.gift.church_id:
            raise ValidationError("Gift must belong to the member's church.")

    def __str__(self):
        return f"{self.member} — {self.gift.name}"


# ==============================
# LEADERSHIP ROLES
# ==============================

class LeadershipRole(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="leadership_roles")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="leadership_roles")
    department = models.ForeignKey(
        Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="leadership_roles"
    )
    title = models.CharField(max_length=150)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_active", "title"]

    def clean(self):
        if self.member_id and self.church_id and self.member.church_id != self.church_id:
            raise ValidationError({"member": "Member must belong to the same church as the role."})
        if self.department_id and self.church_id and self.department.church_id != self.church_id:
            raise ValidationError({"department": "Department must belong to the same church."})

    def __str__(self):
        return f"{self.title} — {self.member.full_name}"


# ==============================
# MEMBER AUDIT LOG
# ==============================

class MemberAuditLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("STATUS", "Status Change"),
        ("TRANSFER_REQUEST", "Transfer Request"),
        ("TRANSFER_COMPLETE", "Transfer Complete"),
        ("TRANSFER_REJECT", "Transfer Reject"),
        ("EXPORT", "Export"),
        ("DEACTIVATE", "Deactivate"),
        ("ACTIVATE", "Activate"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        Church,
        on_delete=models.CASCADE,
        related_name="member_audit_logs",
    )
    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_audit_actions",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "created_at"]),
            models.Index(fields=["member", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.created_at:%Y-%m-%d %H:%M}"
