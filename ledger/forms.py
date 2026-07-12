from decimal import Decimal

from django import forms
from django.utils import timezone

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from ledger.models import LedgerCategory
from members.models import Member
from transactions.models import Account

_MONEY = lambda **extra: input_attrs(step="0.01", placeholder="0.00", **extra)


class LedgerEntryForm(forms.Form):
    transaction_type = forms.ChoiceField(
        label="Transaction Type",
        choices=LedgerCategory.TRANSACTION_TYPES,
        widget=forms.Select(attrs={**select_attrs(), "id": "id_transaction_type"}),
    )
    category = forms.ModelChoiceField(
        label="Category",
        queryset=LedgerCategory.objects.none(),
        widget=forms.Select(attrs={**select_attrs(), "id": "id_category"}),
    )
    amount = forms.DecimalField(
        label="Amount",
        min_value=Decimal("0.01"),
        decimal_places=2,
        widget=forms.NumberInput(attrs=_MONEY()),
    )
    narration = forms.CharField(
        label="Narration",
        required=False,
        widget=forms.Textarea(attrs=textarea_attrs(rows=2, placeholder="Transaction description")),
    )
    date = forms.DateField(
        label="Transaction Date",
        initial=timezone.now().date,
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    member = forms.ModelChoiceField(
        label="Member",
        required=False,
        queryset=Member.objects.none(),
        widget=forms.Select(attrs={**select_attrs(), "id": "id_member"}),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        txn_type = (
            self.data.get("transaction_type")
            or self.initial.get("transaction_type")
            or "RECEIPT"
        )
        if church:
            self.fields["category"].queryset = LedgerCategory.objects.filter(
                church=church,
                transaction_type=txn_type,
                is_active=True,
            ).select_related("default_debit_account", "default_credit_account")
            self.fields["member"].queryset = Member.objects.filter(
                church=church, is_active=True
            ).order_by("last_name", "first_name")

    def clean(self):
        cleaned = super().clean()
        category = cleaned.get("category")
        member = cleaned.get("member")
        if category and category.requires_member and not member:
            self.add_error("member", "This category requires a member.")
        if category and self.church and category.church_id != self.church.pk:
            raise forms.ValidationError("Invalid category for this church.")
        if category:
            debit = category.default_debit_account
            credit = category.default_credit_account
            if debit.church_id != category.church_id or credit.church_id != category.church_id:
                raise forms.ValidationError(
                    "Category accounts are misconfigured for this church. Contact an administrator."
                )
        return cleaned


class LedgerCategoryEditForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs=input_attrs()),
    )
    default_narration = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs=input_attrs()),
    )
    default_debit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    default_credit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    requires_member = forms.BooleanField(required=False)
    is_active = forms.BooleanField(required=False)
    sort_order = forms.IntegerField(
        min_value=0,
        widget=forms.NumberInput(attrs=input_attrs()),
    )

    def __init__(self, *args, church=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.instance = instance
        if church:
            accounts = Account.objects.filter(church=church).order_by("name")
            self.fields["default_debit_account"].queryset = accounts
            self.fields["default_credit_account"].queryset = accounts
        if instance and not self.data:
            self.fields["name"].initial = instance.name
            self.fields["default_narration"].initial = instance.default_narration
            self.fields["default_debit_account"].initial = instance.default_debit_account_id
            self.fields["default_credit_account"].initial = instance.default_credit_account_id
            self.fields["requires_member"].initial = instance.requires_member
            self.fields["is_active"].initial = instance.is_active
            self.fields["sort_order"].initial = instance.sort_order

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("default_debit_account")
        credit = cleaned.get("default_credit_account")
        if debit and credit and debit.pk == credit.pk:
            raise forms.ValidationError("Debit and credit accounts must be different.")
        return cleaned
