from decimal import Decimal

from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from ledger.models import LedgerCategory
from members.models import Member
from transactions.models import Account, OfferingCategory, TreasuryApprovalPolicy
from transactions.services import resolve_transaction_date

_MONEY = lambda **extra: input_attrs(step="0.01", placeholder="0.00", **extra)


class ReceiptForm(forms.Form):
    """Category-driven teller receipt: one category, one amount, description preserved."""

    idempotency_key = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )
    category = forms.ModelChoiceField(
        label="Category",
        queryset=LedgerCategory.objects.none(),
        widget=forms.Select(
            attrs={
                **select_attrs(),
                "id": "id_category",
                "class": select_attrs()["class"] + " js-category-picker",
            }
        ),
        help_text="Debit and credit accounts fill automatically from the category.",
    )
    amount = forms.DecimalField(
        label="Amount",
        min_value=Decimal("0.01"),
        decimal_places=2,
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.TextInput(
            attrs={
                **input_attrs(placeholder="e.g. Sabbath morning offering"),
                "id": "id_description",
            }
        ),
    )
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        required=False,
        label="Member",
        widget=forms.HiddenInput(attrs={"id": "id_member"}),
    )
    date = forms.DateField(
        required=False,
        label="Receipt Date",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            from ledger import selectors as ledger_selectors
            from ledger.services import seed_ledger

            if not ledger_selectors.categories_for_type_qs(church, "RECEIPT").exists():
                seed_ledger(church)
            if "date" not in self.initial and not self.data:
                self.fields["date"].initial = resolve_transaction_date(church)
            self.fields["category"].queryset = ledger_selectors.categories_for_type_qs(
                church, "RECEIPT"
            )
            self.fields["member"].queryset = Member.objects.filter(
                church=church, is_active=True
            )

    def clean(self):
        cleaned = super().clean()
        if self.church and not cleaned.get("date"):
            cleaned["date"] = resolve_transaction_date(self.church)
        category = cleaned.get("category")
        member = cleaned.get("member")
        if category and self.church and category.church_id != self.church.pk:
            raise forms.ValidationError("Invalid category for this church.")
        if category and category.transaction_type != "RECEIPT":
            raise forms.ValidationError("Only receipt categories can be used here.")
        if category and not category.is_active:
            raise forms.ValidationError("This category is inactive.")
        if category and category.requires_member and not member:
            self.add_error("member", "This category requires a member.")
        if category:
            debit = category.default_debit_account
            credit = category.default_credit_account
            if debit.church_id != category.church_id or credit.church_id != category.church_id:
                raise forms.ValidationError(
                    "Category accounts are misconfigured for this church. "
                    "Contact an administrator."
                )
        description = (cleaned.get("description") or "").strip()
        if not description and category:
            description = (category.default_narration or category.name or "").strip()
        cleaned["description"] = description
        return cleaned


class ClassicReceiptForm(forms.Form):
    """Legacy multi-amount receipt (escape hatch via ?classic=1)."""

    idempotency_key = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )
    tithe_amount = forms.DecimalField(
        min_value=0, decimal_places=2, initial=0,
        label="Tithe",
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    combined_amount = forms.DecimalField(
        min_value=0, decimal_places=2, initial=0,
        label="Combined Offering",
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    income_amount = forms.DecimalField(
        min_value=0, decimal_places=2, initial=0,
        label="General Income",
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    payment_account_type = forms.ChoiceField(
        label="Payment Method",
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        widget=forms.Select(attrs=select_attrs()),
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.TextInput(attrs=input_attrs(placeholder="e.g. Sunday service offering")),
    )
    member = forms.ModelChoiceField(
        queryset=Member.objects.none(),
        required=False,
        label="Member (optional)",
        widget=forms.HiddenInput(attrs={"id": "id_member"}),
    )
    date = forms.DateField(
        required=False,
        label="Receipt Date",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            self.fields["member"].queryset = Member.objects.filter(church=church, is_active=True)
            special = OfferingCategory.objects.filter(
                church=church, is_active=True
            ).exclude(code__in=["TITHE", "COMBINED"]).order_by("name")
            for cat in special:
                self.fields[f"offering_{cat.code}"] = forms.DecimalField(
                    min_value=0, decimal_places=2, initial=0, required=False,
                    label=cat.name,
                    widget=forms.NumberInput(attrs=_MONEY()),
                )

    def get_special_offerings(self):
        """Return {code: amount} dict for non-zero special offering fields."""
        offerings = {}
        if not self.church:
            return offerings
        for cat in OfferingCategory.objects.filter(
            church=self.church, is_active=True
        ).exclude(code__in=["TITHE", "COMBINED"]):
            val = self.cleaned_data.get(f"offering_{cat.code}", Decimal("0"))
            if val and val > 0:
                offerings[cat.code] = val
        return offerings

    def clean(self):
        cleaned = super().clean()
        total = (
            cleaned.get("tithe_amount", Decimal("0"))
            + cleaned.get("combined_amount", Decimal("0"))
            + cleaned.get("income_amount", Decimal("0"))
        )
        if self.church:
            for cat in OfferingCategory.objects.filter(
                church=self.church, is_active=True
            ).exclude(code__in=["TITHE", "COMBINED"]):
                total += cleaned.get(f"offering_{cat.code}", Decimal("0")) or Decimal("0")
        if total <= 0:
            raise forms.ValidationError("At least one amount must be greater than zero.")
        return cleaned


class ExpenseForm(forms.Form):
    idempotency_key = forms.CharField(
        widget=forms.HiddenInput(),
        required=True,
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"), decimal_places=2,
        label="Amount",
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    expense_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        label="Expense Category",
        widget=forms.Select(attrs=select_attrs()),
    )
    payment_account_type = forms.ChoiceField(
        label="Payment Method",
        choices=[("CASH", "Cash"), ("BANK", "Bank")],
        widget=forms.Select(attrs=select_attrs()),
    )
    description = forms.CharField(
        required=False,
        label="Description",
        widget=forms.TextInput(attrs=input_attrs(placeholder="e.g. Utility bill")),
    )
    date = forms.DateField(
        required=False,
        label="Expense Date",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            expense_qs = Account.objects.filter(
                church=church, account_type="EXPENSE"
            ).order_by("name")
            self.fields["expense_account"].queryset = expense_qs
            self.fields["expense_account"].label_from_instance = lambda obj: obj.name
            default = expense_qs.filter(name="General Expense").first() or expense_qs.first()
            if default and not self.is_bound:
                self.fields["expense_account"].initial = default.pk


class PeriodLockForm(forms.Form):
    year = forms.IntegerField(min_value=2000, max_value=2100, widget=forms.NumberInput(attrs=input_attrs()))
    month = forms.IntegerField(min_value=1, max_value=12, widget=forms.NumberInput(attrs=input_attrs()))
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs=input_attrs(placeholder="Optional note")),
    )


class TreasuryApprovalPolicyForm(forms.ModelForm):
    class Meta:
        model = TreasuryApprovalPolicy
        fields = (
            "receipt_auto_approve_enabled",
            "default_receipt_auto_approve_limit",
        )
        widgets = {
            "receipt_auto_approve_enabled": forms.CheckboxInput(
                attrs={"class": "form-check-input"}
            ),
            "default_receipt_auto_approve_limit": forms.NumberInput(
                attrs=input_attrs(step="0.01", placeholder="Blank = unlimited")
            ),
        }
        labels = {
            "receipt_auto_approve_enabled": "Auto-approve income receipts",
            "default_receipt_auto_approve_limit": "Default max amount for auto-approve",
        }
        help_texts = {
            "default_receipt_auto_approve_limit": (
                "Receipts up to this amount are auto-approved. "
                "Leave blank for unlimited. Set 0 to require second approval for every receipt. "
                "Per-user overrides are set on the user profile."
            ),
        }


class WorkingDayOpenForm(forms.Form):
    date = forms.DateField(
        label="Business date",
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    notes = forms.CharField(
        required=False,
        label="Notes",
        widget=forms.TextInput(attrs=input_attrs(placeholder="Optional note")),
    )


class WorkingDayCloseForm(forms.Form):
    notes = forms.CharField(
        required=False,
        label="Closing notes",
        widget=forms.TextInput(attrs=input_attrs(placeholder="Optional note")),
    )


class VoidTransactionForm(forms.Form):
    reason = forms.CharField(
        required=False,
        label="Reason for void",
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
    )


class BankReconciliationForm(forms.Form):
    bank_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    statement_date = forms.DateField(
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    statement_balance = forms.DecimalField(
        decimal_places=2,
        label="Statement Ending Balance",
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["bank_account"].queryset = Account.objects.filter(
                church=church, account_type="BANK"
            )
