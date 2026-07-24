from decimal import Decimal

from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from members.models import Member
from transactions.models import Account, OfferingCategory, TreasuryApprovalPolicy

_MONEY = lambda **extra: input_attrs(step="0.01", placeholder="0.00", **extra)


class ReceiptForm(forms.Form):
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
        for cat in OfferingCategory.objects.filter(church=self.church, is_active=True).exclude(code__in=["TITHE", "COMBINED"]):
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
            for cat in OfferingCategory.objects.filter(church=self.church, is_active=True).exclude(code__in=["TITHE", "COMBINED"]):
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
