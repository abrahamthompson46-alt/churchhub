import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from organization.models import Church


# ==============================
# SOFT DELETE
# ==============================

class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(is_deleted=False)

    def deleted(self):
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_deletions",
    )
    deletion_reason = models.CharField(max_length=255, blank=True, default="")

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def soft_delete(self, *, user=None, reason=""):
        from django.utils import timezone

        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.deletion_reason = (reason or "")[:255]
        update_fields = ["is_deleted", "deleted_at", "deleted_by", "deletion_reason"]
        if any(f.name == "updated_at" for f in self._meta.local_fields):
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.deletion_reason = ""
        update_fields = ["is_deleted", "deleted_at", "deleted_by", "deletion_reason"]
        if any(f.name == "updated_at" for f in self._meta.local_fields):
            update_fields.append("updated_at")
        self.save(update_fields=update_fields)


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
    MISSING = "Missing", "Missing"
    SUSPENDED = "Suspended", "Suspended"
    FORMER = "Former Member", "Former Member"


class FamilyRelationship(models.TextChoices):
    HEAD = "Head", "Head of household"
    SPOUSE = "Spouse", "Spouse"
    CHILD = "Child", "Child"
    DEPENDENT = "Dependent", "Dependent"
    OTHER = "Other", "Other"


ACTIVE_MEMBERSHIP_STATUSES = frozenset({
    MembershipStatus.ACTIVE,
})

INACTIVE_MEMBERSHIP_STATUSES = frozenset({
    MembershipStatus.INACTIVE,
    MembershipStatus.TRANSFERRED,
    MembershipStatus.DECEASED,
    MembershipStatus.MISSING,
    MembershipStatus.SUSPENDED,
    MembershipStatus.FORMER,
})


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


class LookupCategory(models.TextChoices):
    RECORD_TYPE = "record_type", "Record type"
    RECORD_STATUS = "record_status", "Record status"
    MEMBERSHIP_STATUS = "membership_status", "Membership status"
    GENDER = "gender", "Gender"
    MARITAL_STATUS = "marital_status", "Marital status"


class MemberLookupOption(models.Model):
    """
    Platform-managed dropdown values for member forms.

    System options are seeded from legacy TextChoices and cannot be deleted.
    Site owners can rename labels, reorder, deactivate, and add new options
    (especially record types) without deploying code.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=40, choices=LookupCategory.choices)
    code = models.CharField(
        max_length=50,
        help_text="Stored value on member/record rows. Prefer stable codes.",
    )
    label = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(
        default=False,
        help_text="Seeded option — code cannot be deleted.",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "sort_order", "label"]
        unique_together = ("category", "code")
        verbose_name = "Member lookup option"
        verbose_name_plural = "Member lookup options"

    def __str__(self):
        return f"{self.get_category_display()}: {self.label}"


# ==============================
# DEPARTMENT
# ==============================

class Department(SoftDeleteModel):
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

class Family(SoftDeleteModel):
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
        return self.members.filter(is_deleted=False).count()


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

class Member(SoftDeleteModel):
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
    family_relationship = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Role within the household when a family is assigned.",
    )
    first_name = models.CharField(max_length=150)
    middle_name = models.CharField(max_length=150, blank=True, default="")
    last_name = models.CharField(max_length=150)
    preferred_name = models.CharField(max_length=150, blank=True, default="")
    gender = models.CharField(max_length=50)
    marital_status = models.CharField(
        max_length=50,
        blank=True,
        default="",
    )
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        help_text="Required when an email is set (used for member portal first sign-in).",
    )
    date_joined = models.DateField(null=True, blank=True)
    membership_status = models.CharField(
        max_length=50,
        default=MembershipStatus.ACTIVE,
    )
    is_active = models.BooleanField(default=True)
    membership_number = models.CharField(max_length=40, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(
        blank=True,
        default="",
        help_text="Must be unique when set. Used as the member portal username.",
    )
    address = models.TextField(blank=True)
    emergency_contact_name = models.CharField(max_length=150, blank=True, default="")
    emergency_contact_phone = models.CharField(max_length=20, blank=True, default="")
    emergency_contact_relation = models.CharField(max_length=80, blank=True, default="")
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
            models.Index(fields=["church", "is_deleted"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "phone"],
                condition=~Q(phone="") & Q(is_deleted=False),
                name="uniq_member_phone_per_church",
            ),
            models.UniqueConstraint(
                fields=["church", "membership_number"],
                condition=~Q(membership_number="") & Q(is_deleted=False),
                name="uniq_member_number_per_church",
            ),
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email="") & Q(is_deleted=False),
                name="uniq_member_email_active_ci",
            ),
        ]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        preferred = (self.preferred_name or "").strip()
        if preferred:
            return preferred
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p).strip()

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
        email = (self.email or "").strip().lower()
        self.email = email
        if email and not self.date_of_birth:
            errors["date_of_birth"] = (
                "Date of birth is required when an email is set "
                "(needed for member portal first sign-in)."
            )
        if email:
            qs = Member.objects.filter(email__iexact=email)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                errors["email"] = (
                    "This email is already used by another member. "
                    "Portal sign-in requires a unique email."
                )
        if self.membership_status in INACTIVE_MEMBERSHIP_STATUSES:
            self.is_active = False
        elif self.membership_status in ACTIVE_MEMBERSHIP_STATUSES:
            self.is_active = True
        if self.department_id and self.church_id and self.department.church_id != self.church_id:
            errors["department"] = "Department must belong to the member's church."
        if self.family_id and self.church_id and self.family.church_id != self.church_id:
            errors["family"] = "Family must belong to the member's church."
        if self.occupation_id and self.church_id and self.occupation.church_id != self.church_id:
            errors["occupation"] = "Occupation must belong to the member's church."
        if self.family_id and self.family_relationship == FamilyRelationship.HEAD:
            # Prefer head FK on Family when relationship is Head
            pass
        if self.profile_picture:
            from church_system.uploads import validate_upload

            try:
                validate_upload(self.profile_picture, kind="image")
            except ValidationError as exc:
                errors["profile_picture"] = exc.messages
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        current_user = getattr(self, "_current_user", None)
        if self.email:
            self.email = self.email.strip().lower()
        if not self.pk and current_user:
            if not self.church_id and getattr(current_user, "church_id", None):
                self.church = current_user.church
            if not self.created_by_id:
                self.created_by = current_user
        if self.membership_status in INACTIVE_MEMBERSHIP_STATUSES:
            self.is_active = False
        elif self.membership_status in ACTIVE_MEMBERSHIP_STATUSES:
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

    def clean(self):
        from church_system.uploads import validate_upload

        super().clean()
        if self.image:
            try:
                validate_upload(self.image, kind="image")
            except ValidationError as exc:
                raise ValidationError({"image": exc.messages}) from exc

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"Record Image {self.id}"


# ==============================
# RECORD
# ==============================

class Record(SoftDeleteModel):
    church = models.ForeignKey(Church, on_delete=models.CASCADE)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="records",
    )
    record_type = models.CharField(max_length=50)
    status = models.CharField(
        max_length=50,
        default=RecordStatus.ACTIVE,
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    event_date = models.DateField()
    place = models.CharField(max_length=200, blank=True, default="")
    officiant = models.CharField(max_length=150, blank=True, default="")
    certificate_number = models.CharField(max_length=60, blank=True, default="")
    images = models.ManyToManyField(RecordImage, blank=True)
    migrated_from_history_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Set when converted from legacy History rows.",
    )
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
            models.Index(fields=["church", "is_deleted"]),
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

    def clean(self):
        from church_system.uploads import validate_upload

        super().clean()
        if self.image:
            try:
                validate_upload(self.image, kind="image")
            except ValidationError as exc:
                raise ValidationError({"image": exc.messages}) from exc

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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

class SpiritualGift(SoftDeleteModel):
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

class LeadershipRole(SoftDeleteModel):
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
# VISITORS
# ==============================

class VisitorFollowUpStatus(models.TextChoices):
    NEW = "New", "New"
    CONTACTED = "Contacted", "Contacted"
    IN_PROGRESS = "In Progress", "In Progress"
    CONVERTED = "Converted", "Converted"
    CLOSED = "Closed", "Closed"


class Visitor(SoftDeleteModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(Church, on_delete=models.CASCADE, related_name="visitors")
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    visit_date = models.DateField()
    invited_by = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors_invited",
    )
    interests = models.CharField(max_length=255, blank=True, default="")
    follow_up_status = models.CharField(
        max_length=20,
        choices=VisitorFollowUpStatus.choices,
        default=VisitorFollowUpStatus.NEW,
    )
    assigned_elder = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors_assigned",
    )
    notes = models.TextField(blank=True, default="")
    converted_member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="converted_from_visitor",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="visitors_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-visit_date", "-created_at"]
        indexes = [
            models.Index(fields=["church", "visit_date"]),
            models.Index(fields=["church", "follow_up_status"]),
            models.Index(fields=["church", "is_deleted"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()


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
        ("SOFT_DELETE", "Soft Delete"),
        ("RESTORE", "Restore"),
        ("DEPARTMENT_CREATE", "Department Created"),
        ("DEPARTMENT_UPDATE", "Department Updated"),
        ("DEPARTMENT_DELETE", "Department Deleted"),
        ("FAMILY_CREATE", "Family Created"),
        ("FAMILY_UPDATE", "Family Updated"),
        ("RECORD_CREATE", "Record Created"),
        ("RECORD_UPDATE", "Record Updated"),
        ("LEADERSHIP_ASSIGN", "Leadership Assigned"),
        ("LEADERSHIP_END", "Leadership Ended"),
        ("GIFT_ASSIGN", "Spiritual Gift Assigned"),
        ("GIFT_UNASSIGN", "Spiritual Gift Unassigned"),
        ("GIFT_CATALOG_CREATE", "Spiritual Gift Catalog Created"),
        ("VISITOR_CREATE", "Visitor Created"),
        ("VISITOR_UPDATE", "Visitor Updated"),
        ("VISITOR_CONVERT", "Visitor Converted"),
        ("OCCUPATION_CREATE", "Occupation Created"),
        ("OCCUPATION_UPDATE", "Occupation Updated"),
        ("OCCUPATION_DELETE", "Occupation Deleted"),
        ("LOOKUP_CREATE", "Lookup Option Created"),
        ("LOOKUP_UPDATE", "Lookup Option Updated"),
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
