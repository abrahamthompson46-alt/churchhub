from decimal import Decimal

from django import forms
from django.forms import formset_factory

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from transactions.adjustment_services import adjustment_account_queryset
from transactions.models import Account
from transactions.services import resolve_transaction_date


class AdjustmentLineForm(forms.Form):
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
        required=False,
    )
    side = forms.ChoiceField(
        choices=[("", "—"), ("DEBIT", "Debit"), ("CREDIT", "Credit")],
        widget=forms.Select(attrs=select_attrs()),
        required=False,
    )
    amount = forms.DecimalField(
        min_value=Decimal("0.01"),
        decimal_places=2,
        required=False,
        widget=forms.NumberInput(attrs=input_attrs(step="0.01", placeholder="0.00")),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["account"].queryset = adjustment_account_queryset(church)
            self.fields["account"].label_from_instance = lambda obj: obj.name

    def clean(self):
        cleaned = super().clean()
        account = cleaned.get("account")
        side = cleaned.get("side")
        amount = cleaned.get("amount")
        if not account and not side and not amount:
            cleaned["empty"] = True
            return cleaned
        if not account or not side or not amount:
            raise forms.ValidationError(
                "Complete account, debit/credit, and amount for each line."
            )
        cleaned["empty"] = False
        return cleaned


class AdjustmentJournalForm(forms.Form):
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
        if church and not self.data and "date" not in self.initial:
            self.fields["date"].initial = resolve_transaction_date(church)


AdjustmentLineFormSet = formset_factory(
    AdjustmentLineForm,
    extra=3,
    min_num=2,
    validate_min=True,
    max_num=20,
)