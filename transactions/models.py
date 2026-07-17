from django.db import models, transaction as db_transaction
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.urls import reverse
import uuid

from members.models import Member


# ============================
# ACCOUNT MODEL
# ============================
class Account(models.Model):
    ACCOUNT_TYPES = [
        ("TITHE", "Tithe"),
        ("COMBINED", "Combined Offering"),
        ("INCOME", "Income"),
        ("EXPENSE", "Expense"),
        ("DISTRICT_PAYABLE", "District Payable"),
        ("TITHE_REMIT_PAYABLE", "Tithe Remittance Payable"),
        ("COMBINED_REMIT_PAYABLE", "Combined Remittance Payable"),
        ("COMBINED_RETENTION", "Combined Retention Income"),
        ("WELFARE_FUND", "Welfare Fund"),
        ("REMITTANCE_RECEIVABLE", "Remittance Receivable"),
        ("SALARY_EXPENSE", "Salary Expense"),
        ("EMPLOYER_SSNIT_EXPENSE", "Employer SSNIT Expense"),
        ("SALARIES_PAYABLE", "Salaries Payable"),
        ("PAYE_PAYABLE", "PAYE Payable"),
        ("SSNIT_PAYABLE", "SSNIT Payable"),
        ("PENSION_PAYABLE", "Pension Payable"),
        ("BANK", "Bank"),
        ("CASH", "Cash"),
        ("FIXED_ASSET", "Property, Plant & Equipment"),
        ("ACCUMULATED_DEPRECIATION", "Accumulated Depreciation"),
        ("DEPRECIATION_EXPENSE", "Depreciation Expense"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    code = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Stable account code for lookups (unique per church when set).",
    )
    account_type = models.CharField(max_length=30, choices=ACCOUNT_TYPES)
    is_active = models.BooleanField(default=True)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="accounts"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "name")
        constraints = [
            models.UniqueConstraint(
                fields=["church", "code"],
                condition=~models.Q(code=""),
                name="account_church_code_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["church", "code"]),
            models.Index(fields=["church", "is_active"]),
        ]

    def __str__(self):
        if self.code:
            return f"{self.code} — {self.name}"
        return f"{self.name} ({self.account_type})"


# ============================
# TRANSACTION MODEL
# ============================
class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ("RECEIPT", "Receipt"),
        ("EXPENSE", "Expense"),
        ("TRANSFER", "Transfer"),
        ("PAYROLL", "Payroll"),
        ("CAPITAL", "Capital / Fixed Asset"),
    ]

    APPROVAL_STATUS = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    reference = models.CharField(
        max_length=40,
        editable=False,
        blank=True,
        null=True,
    )

    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    date = models.DateField(default=timezone.now)
    description = models.CharField(max_length=200, blank=True)

    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="transactions"
    )

    member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions"
    )

    approval_status = models.CharField(
        max_length=10,
        choices=APPROVAL_STATUS,
        default="PENDING"
    )

    locked = models.BooleanField(default=False)

    is_voided = models.BooleanField(default=False)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="voided_transactions",
    )
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_transactions"
    )

    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    ledger_category = models.ForeignKey(
        "ledger.LedgerCategory",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    class Meta:
        ordering = ["-date", "-created_at"]
        indexes = [
            models.Index(fields=["church", "approval_status", "date"]),
            models.Index(fields=["church", "transaction_type"]),
            models.Index(fields=["reference"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "reference"],
                name="uniq_txn_reference_per_church",
            ),
        ]

    # ============================
    # SAFE SAVE METHOD
    # ============================
    def save(self, *args, **kwargs):

        # 🔒 Ensure church exists before anything else
        if not self.church_id:
            if self.created_by and hasattr(self.created_by, "church"):
                self.church = self.created_by.church
            else:
                raise ValueError("Transaction cannot be saved without a church.")

        # 🔢 Generate reference safely
        if not self.reference:

            prefix = {
                "RECEIPT": "REC",
                "EXPENSE": "EXP",
                "TRANSFER": "TRF",
                "PAYROLL": "PAY",
                "CAPITAL": "CAP",
            }.get(self.transaction_type, "TXN")

            post_date = self.date or timezone.localdate()
            date_str = post_date.strftime("%Y-%m")

            with db_transaction.atomic():
                last_txn = Transaction.objects.select_for_update().filter(
                    church=self.church,
                    transaction_type=self.transaction_type,
                    date__year=post_date.year,
                    date__month=post_date.month,
                ).order_by("-created_at").first()

                if last_txn and last_txn.reference:
                    try:
                        last_number = int(last_txn.reference.split("-")[-1])
                    except (ValueError, IndexError):
                        last_number = 0
                    new_number = last_number + 1
                else:
                    new_number = 1

                self.reference = f"{prefix}-{self.church.code}-{date_str}-{new_number:03d}"

        super().save(*args, **kwargs)

    # ============================
    # SAFE TOTAL PROPERTY
    # ============================
    @property
    def total_amount(self):
        return sum(line.amount for line in self.lines.all())

    @property
    def receipt_total(self):
        """Positive total received (cash/bank debit side) for display."""
        return sum(
            line.amount for line in self.lines.all()
            if line.account.account_type in ("CASH", "BANK") and line.amount > 0
        ) or abs(
            sum(line.amount for line in self.lines.all() if line.amount < 0)
        )

    def validate_balance(self):
        """Ensure journal lines sum to zero (double-entry integrity)."""
        total = self.lines.aggregate(total=models.Sum("amount"))["total"]
        if total is not None and total != 0:
            raise ValueError(
                f"Transaction {self.reference} is unbalanced: sum={total}"
            )

    def get_receipt_url(self):
        return reverse("transactions:transaction_receipt", args=[self.pk])

    # ============================
    # SAFE STRING METHOD
    # ============================
    def __str__(self):
        ref = self.reference if self.reference else "NEW"
        return f"{ref} - {self.transaction_type}"


# ============================
# TRANSACTION LINE MODEL
# ============================
class TransactionLine(models.Model):
    FUND_CHOICES = [
        ("OPERATIONAL", "Operational"),
        ("TITHE_TRUST", "Tithe Trust"),
        ("COMBINED_TRUST", "Combined Trust"),
        ("COMBINED_RETENTION", "Combined Retention"),
        ("WELFARE", "Welfare"),
    ]

    transaction = models.ForeignKey(
        Transaction,
        related_name="lines",
        on_delete=models.CASCADE
    )

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transaction_lines"
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    fund = models.CharField(max_length=30, choices=FUND_CHOICES, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["account"], name="txn_line_account_idx"),
            models.Index(fields=["transaction", "account"], name="txn_line_txn_acct_idx"),
        ]

    def clean(self):
        if self.account_id and self.transaction_id:
            if self.account.church_id != self.transaction.church_id:
                raise ValidationError(
                    "Journal line account must belong to the same church as the transaction."
                )

    def save(self, *args, **kwargs):
        if self.transaction_id and self.transaction.locked:
            raise ValidationError("Cannot modify lines on a locked transaction.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        account_name = self.account.name if self.account_id else "No Account"
        return f"{account_name} - {self.amount}"


# ============================
# MONTHLY CUTOFF MODEL
# ============================
class MonthlyCutoff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="monthly_cutoffs"
    )

    month = models.DateField(help_text="Use first day of month (e.g. 2026-02-01)")
    total_tithe = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_combined = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    transferred = models.BooleanField(default=False)
    transfer_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "month")
        ordering = ["-month"]

    def __str__(self):
        church_name = self.church.name if self.church_id else "No Church"
        return f"{church_name} - {self.month.strftime('%B %Y')}"

    @property
    def total_payable(self):
        return self.total_tithe + self.total_combined


# ============================
# OFFERING CATEGORY
# ============================
class OfferingCategory(models.Model):
    """Configurable offering types per church (Thanksgiving, Building Fund, etc.)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="offering_categories",
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=30)
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name="offering_categories",
    )
    remit_to_district = models.BooleanField(
        default=False,
        help_text="If true, amounts are included in district remittance.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "code")
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.church.name})"


# ============================
# BUDGET
# ============================
class Budget(models.Model):
    BUDGET_LEVELS = [
        ("CHURCH", "Church"),
        ("DEPARTMENT", "Department"),
        ("DISTRICT", "District"),
        ("CONFERENCE", "Conference"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    level = models.CharField(max_length=20, choices=BUDGET_LEVELS, default="CHURCH")
    year = models.PositiveIntegerField()
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    district = models.ForeignKey(
        "organization.District",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    conference = models.ForeignKey(
        "organization.Conference",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    department = models.ForeignKey(
        "members.Department",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="budget_lines",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "account__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["church", "year", "account"],
                condition=models.Q(level="CHURCH", department__isnull=True),
                name="uniq_budget_church_account_year",
            ),
            models.UniqueConstraint(
                fields=["church", "year", "account", "department"],
                condition=models.Q(level="DEPARTMENT"),
                name="uniq_budget_department_account_year",
            ),
            models.UniqueConstraint(
                fields=["district", "year", "account"],
                condition=models.Q(level="DISTRICT"),
                name="uniq_budget_district_account_year",
            ),
            models.UniqueConstraint(
                fields=["conference", "year", "account"],
                condition=models.Q(level="CONFERENCE"),
                name="uniq_budget_conference_account_year",
            ),
        ]

    def __str__(self):
        return f"{self.year} - {self.account.name} - {self.amount}"


# ============================
# FINANCIAL AUDIT LOG
# ============================
class FinancialAuditLog(models.Model):
    ACTION_CHOICES = [
        ("CREATE", "Create"),
        ("UPDATE", "Update"),
        ("APPROVE", "Approve"),
        ("REJECT", "Reject"),
        ("VOID", "Void"),
        ("REMIT", "District Remittance"),
        ("BUDGET_CREATE", "Budget Create"),
        ("BUDGET_UPDATE", "Budget Update"),
        ("BUDGET_DELETE", "Budget Delete"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="financial_audit_logs",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="financial_audit_actions",
    )
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["church", "created_at"], name="fin_audit_church_dt_idx"),
            models.Index(fields=["church", "action"], name="fin_audit_church_act_idx"),
        ]

    def __str__(self):
        return f"{self.action} - {self.church} - {self.created_at:%Y-%m-%d %H:%M}"


# ============================
# BANK RECONCILIATION
# ============================
class BankReconciliation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="bank_reconciliations",
    )
    bank_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        limit_choices_to={"account_type": "BANK"},
        related_name="reconciliations",
    )
    statement_date = models.DateField()
    statement_balance = models.DecimalField(max_digits=14, decimal_places=2)
    book_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    is_reconciled = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliations_completed",
    )
    reconciled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-statement_date"]

    def __str__(self):
        return f"{self.bank_account.name} - {self.statement_date}"


class BankReconciliationItem(models.Model):
    reconciliation = models.ForeignKey(
        BankReconciliation,
        on_delete=models.CASCADE,
        related_name="items",
    )
    transaction_line = models.ForeignKey(
        TransactionLine,
        on_delete=models.CASCADE,
        related_name="reconciliation_items",
    )
    statement_reference = models.CharField(max_length=100, blank=True)
    is_matched = models.BooleanField(default=False)

    def __str__(self):
        return f"Match {self.transaction_line_id} - {self.is_matched}"


# ============================
# FINANCIAL PERIOD (month locking)
# ============================
class FinancialPeriod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="financial_periods",
    )
    year = models.PositiveIntegerField()
    month = models.PositiveIntegerField()
    is_locked = models.BooleanField(default=False)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="periods_locked",
    )
    notes = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "year", "month")
        ordering = ["-year", "-month"]

    def __str__(self):
        return f"{self.church.name} — {self.year}-{self.month:02d} {'🔒' if self.is_locked else ''}"


class WorkingDay(models.Model):
    """Per-church business day — open/close controls the active posting date."""

    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_CLOSED, "Closed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="working_days",
    )
    date = models.DateField(help_text="Business date for receipts, offerings, and expenses.")
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default=STATUS_OPEN)
    opened_at = models.DateTimeField(auto_now_add=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="working_days_opened",
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="working_days_closed",
    )
    notes = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("church", "date")
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["church", "status"]),
            models.Index(fields=["church", "-date"]),
        ]

    def __str__(self):
        return f"{self.church.name} — {self.date} ({self.get_status_display()})"


class FinancialIdempotencyKey(models.Model):
    """Prevents duplicate financial submissions from double-clicks or retries."""

    ACTION_CHOICES = [
        ("RECEIPT", "Receipt"),
        ("EXPENSE", "Expense"),
        ("REMITTANCE", "Remittance"),
        ("LEDGER", "Ledger Entry"),
        ("PAYROLL_POST", "Payroll Post"),
        ("PAYROLL_PAY", "Payroll Pay"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="financial_idempotency_keys",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="financial_idempotency_keys",
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    idempotency_key = models.CharField(max_length=64)
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idempotency_keys",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("church", "user", "action", "idempotency_key")
        indexes = [
            models.Index(fields=["church", "action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.idempotency_key[:12]}…"
