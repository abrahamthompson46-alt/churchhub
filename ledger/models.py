"""Ledger configuration — categories map to standard debit/credit accounts."""

import uuid

from django.core.exceptions import ValidationError
from django.db import models


class LedgerCategory(models.Model):
    """Posting template: one category defines default DR/CR accounts for a transaction type."""

    TRANSACTION_TYPES = [
        ("RECEIPT", "Receipt"),
        ("EXPENSE", "Expense"),
        ("TRANSFER", "Transfer"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    church = models.ForeignKey(
        "organization.Church",
        on_delete=models.CASCADE,
        related_name="ledger_categories",
    )
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    default_debit_account = models.ForeignKey(
        "transactions.Account",
        on_delete=models.PROTECT,
        related_name="ledger_debit_categories",
    )
    default_credit_account = models.ForeignKey(
        "transactions.Account",
        on_delete=models.PROTECT,
        related_name="ledger_credit_categories",
    )
    default_narration = models.CharField(
        max_length=200,
        blank=True,
        help_text="Suggested narration when this category is selected.",
    )
    requires_member = models.BooleanField(
        default=False,
        help_text="Member must be linked for member-specific receipts (e.g. tithe).",
    )
    remit_to_district = models.BooleanField(
        default=False,
        help_text=(
            "When set on a receipt category, posting uses remittance policy splits "
            "(retain + remit payables) instead of a flat credit to the template account."
        ),
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["transaction_type", "sort_order", "name"]
        unique_together = ("church", "code")
        verbose_name_plural = "Ledger categories"
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(default_debit_account=models.F("default_credit_account")),
                name="ledger_category_debit_ne_credit",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.default_debit_account_id
            and self.default_credit_account_id
            and self.default_debit_account_id == self.default_credit_account_id
        ):
            raise ValidationError("Debit and credit accounts must be different.")
        if self.default_debit_account_id and self.church_id:
            if self.default_debit_account.church_id != self.church_id:
                raise ValidationError(
                    {"default_debit_account": "Debit account must belong to this church."}
                )
        if self.default_credit_account_id and self.church_id:
            if self.default_credit_account.church_id != self.church_id:
                raise ValidationError(
                    {"default_credit_account": "Credit account must belong to this church."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_transaction_type_display()})"
