import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from payroll.constants import UNIT_TYPES


class PayComponentType(models.Model):
    """Configurable earning types (basic, housing, transport, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="pay_components",
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    is_taxable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("host_church", "code")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class DeductionType(models.Model):
    """Configurable deduction types (PAYE, SSNIT, loans, etc.)."""

    CALCULATION_METHODS = [
        ("FIXED", "Fixed Amount"),
        ("PERCENT_GROSS", "Percent of Gross"),
        ("PERCENT_BASIC", "Percent of Basic"),
        ("COMPUTED", "Computed (Statutory)"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="deduction_types",
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    is_statutory = models.BooleanField(default=False)
    calculation_method = models.CharField(max_length=20, choices=CALCULATION_METHODS, default="FIXED")
    default_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = ("host_church", "code")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class PayrollTaxTable(models.Model):
    """Versioned PAYE tax band table — rates are never hardcoded in calculation logic."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="paye_tax_tables",
    )
    name = models.CharField(max_length=100, default="Standard PAYE")
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.name} (from {self.effective_from})"


class PayrollTaxBand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tax_table = models.ForeignKey(PayrollTaxTable, on_delete=models.CASCADE, related_name="bands")
    lower_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    upper_limit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    rate_percent = models.DecimalField(max_digits=5, decimal_places=2)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "lower_limit"]

    def __str__(self):
        upper = self.upper_limit if self.upper_limit is not None else "∞"
        return f"{self.lower_limit} – {upper} @ {self.rate_percent}%"


class StatutoryContributionRule(models.Model):
    """SSNIT, pension, and other statutory contribution rules."""

    APPLIES_TO = [
        ("BASIC", "Basic Salary"),
        ("GROSS", "Gross Taxable"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="statutory_rules",
    )
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    employee_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    employer_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    applies_to = models.CharField(max_length=10, choices=APPLIES_TO, default="BASIC")
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("host_church", "code", "effective_from")
        ordering = ["code", "-effective_from"]

    def __str__(self):
        return self.name


class Employee(models.Model):
    EMPLOYMENT_TYPES = [
        ("FULL_TIME", "Full Time"),
        ("PART_TIME", "Part Time"),
        ("CONTRACT", "Contract"),
        ("STIPEND", "Stipend"),
        ("VOLUNTEER_ALLOWANCE", "Volunteer Allowance"),
    ]

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("SUSPENDED", "Suspended"),
        ("TERMINATED", "Terminated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="employees",
    )
    paying_unit_type = models.CharField(max_length=30, choices=UNIT_TYPES, default="CHURCH")
    paying_unit_id = models.UUIDField(db_index=True)

    member = models.ForeignKey(
        "members.Member",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employment_records",
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_profile",
    )

    employee_number = models.CharField(max_length=30)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)

    employment_type = models.CharField(max_length=30, choices=EMPLOYMENT_TYPES, default="FULL_TIME")
    department = models.ForeignKey(
        "members.Department",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees",
    )
    job_title = models.CharField(max_length=150, blank=True)

    tin_encrypted = models.TextField(blank=True)
    ssnit_number_encrypted = models.TextField(blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    bank_branch = models.CharField(max_length=100, blank=True)
    bank_account_encrypted = models.TextField(blank=True)

    date_joined = models.DateField()
    date_terminated = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employees_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("host_church", "employee_number")
        ordering = ["last_name", "first_name"]
        indexes = [
            models.Index(fields=["host_church", "status"]),
            models.Index(fields=["paying_unit_type", "paying_unit_id"]),
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return f"{self.employee_number} — {self.full_name}"


class EmployeeCompensation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="compensations")
    effective_from = models.DateField(default=timezone.now)
    effective_to = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from"]

    def __str__(self):
        return f"{self.employee} from {self.effective_from}"


class EmployeeCompensationLine(models.Model):
    LINE_TYPES = [
        ("EARNING", "Earning"),
        ("DEDUCTION", "Deduction"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    compensation = models.ForeignKey(
        EmployeeCompensation,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    line_type = models.CharField(max_length=10, choices=LINE_TYPES)
    pay_component = models.ForeignKey(
        PayComponentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="compensation_lines",
    )
    deduction_type = models.ForeignKey(
        DeductionType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="compensation_lines",
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    rate_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["line_type", "pay_component__sort_order", "deduction_type__sort_order"]

    def clean(self):
        if self.line_type == "EARNING" and not self.pay_component_id:
            raise ValidationError("Earning lines require a pay component.")
        if self.line_type == "DEDUCTION" and not self.deduction_type_id:
            raise ValidationError("Deduction lines require a deduction type.")
        if self.pay_component_id and self.deduction_type_id:
            raise ValidationError("Line cannot be both earning and deduction.")


class EmployeeLoan(models.Model):
    """Salary advance / loan recovery (Phase 2)."""

    STATUS_CHOICES = [
        ("ACTIVE", "Active"),
        ("PAID", "Paid Off"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="loans")
    principal = models.DecimalField(max_digits=12, decimal_places=2)
    balance = models.DecimalField(max_digits=12, decimal_places=2)
    monthly_recovery = models.DecimalField(max_digits=12, decimal_places=2)
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    description = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Loan {self.employee} — ₵{self.balance}"


class PayrollRun(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("CALCULATED", "Calculated"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
        ("POSTED", "Posted"),
        ("PAID", "Paid"),
        ("VOID", "Void"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reference = models.CharField(max_length=30, unique=True, editable=False)
    host_church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="payroll_runs",
    )
    paying_unit_type = models.CharField(max_length=30, choices=UNIT_TYPES, default="CHURCH")
    paying_unit_id = models.UUIDField(db_index=True)

    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    pay_date = models.DateField()
    description = models.CharField(max_length=200, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_employer_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs",
    )
    payment_transaction = models.ForeignKey(
        "transactions.Transaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_payments",
    )

    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payroll_runs_prepared",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    treasury_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payroll_runs_treasury_approved",
    )
    treasury_approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    budget_warning = models.JSONField(default=dict, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("host_church", "paying_unit_type", "paying_unit_id", "year", "month")
        ordering = ["-year", "-month", "-created_at"]

    def __str__(self):
        return f"{self.reference} ({self.year}-{self.month:02d})"

    @property
    def period_label(self):
        return f"{self.year}-{self.month:02d}"


class PayrollLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, related_name="payroll_lines")

    gross_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    employer_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    days_in_period = models.PositiveSmallIntegerField(default=30)
    days_worked = models.PositiveSmallIntegerField(default=30)
    is_pro_rata = models.BooleanField(default=False)

    payslip_number = models.CharField(max_length=40, blank=True)

    class Meta:
        unique_together = ("payroll_run", "employee")
        ordering = ["employee__last_name", "employee__first_name"]

    def __str__(self):
        return f"{self.employee.full_name} — ₵{self.net_pay}"


class PayrollLineItem(models.Model):
    ITEM_TYPES = [
        ("EARNING", "Earning"),
        ("DEDUCTION", "Deduction"),
        ("EMPLOYER", "Employer Contribution"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_line = models.ForeignKey(PayrollLine, on_delete=models.CASCADE, related_name="items")
    item_type = models.CharField(max_length=10, choices=ITEM_TYPES)
    code = models.CharField(max_length=30)
    label = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    source_ref = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Optional source id (e.g. loan UUID) for recovery posting.",
    )

    class Meta:
        ordering = ["item_type", "code"]

    def __str__(self):
        return f"{self.label}: ₵{self.amount}"


class PayrollRunAuditLog(models.Model):
    ACTIONS = [
        ("CREATE", "Created"),
        ("CALCULATE", "Calculated"),
        ("APPROVE", "Approved"),
        ("REJECT", "Rejected"),
        ("POST", "Posted"),
        ("PAY", "Paid"),
        ("VOID", "Voided"),
        ("REOPEN", "Reopened"),
        ("REVERSE", "Reversed"),
        ("EXPORT", "Exported"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payroll_run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="audit_logs")
    action = models.CharField(max_length=20, choices=ACTIONS)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
