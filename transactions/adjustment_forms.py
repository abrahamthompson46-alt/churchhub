from decimal import Decimal

from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from transactions.adjustment_services import adjustment_account_queryset
from transactions.models import Account
from transactions.services import resolve_transaction_date


class AdjustmentJournalForm(forms.Form):
    debit_account = forms.ModelChoiceField(
        label="Debit account",
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    credit_account = forms.ModelChoiceField(
        label="Credit account",
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    amount = forms.DecimalField(
        label="Amount",
        min_value=Decimal("0.01"),
        decimal_places=2,
        widget=forms.NumberInput(attrs=input_attrs(step="0.01", placeholder="0.00")),
    )
    narration = forms.CharField(
        label="Reason for adjustment",
        min_length=10,
        max_length=200,
        widget=forms.Textarea(
            attrs=textarea_attrs(
                rows=2,
                placeholder="Explain why this correction is needed (auditors will see this).",
            )
        ),
    )
    date = forms.DateField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            qs = adjustment_account_queryset(church)
            for field in ("debit_account", "credit_account"):
                self.fields[field].queryset = qs
                self.fields[field].label_from_instance = lambda obj: obj.name
            if not self.data and "date" not in self.initial:
                self.fields["date"].initial = resolve_transaction_date(church)

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("debit_account")
        credit = cleaned.get("credit_account")
        if debit and credit and debit.pk == credit.pk:
            raise forms.ValidationError("Debit and credit accounts must be different.")
        return cleaned