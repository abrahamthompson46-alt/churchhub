from decimal import Decimal

from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from ledger import selectors
from ledger.models import LedgerCategory
from members.models import Member
from transactions.models import Account
from transactions.services import resolve_transaction_date

_MONEY = lambda **extra: input_attrs(step="0.01", placeholder="0.00", **extra)


def _account_label(obj):
    """Short account label for selects (name only)."""
    return obj.name if obj else ""


class LedgerEntryForm(forms.Form):
    """Simplified JV entry: type → category cascade, one amount, one narration."""

    transaction_type = forms.ChoiceField(
        label="Transaction Type",
        choices=LedgerCategory.TRANSACTION_TYPES,
        widget=forms.Select(attrs={**select_attrs(), "id": "id_transaction_type"}),
    )
    category = forms.ModelChoiceField(
        label="Category",
        queryset=LedgerCategory.objects.none(),
        widget=forms.Select(attrs={**select_attrs(), "id": "id_category"}),
        help_text="Accounts for debit/credit are filled automatically from the category.",
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
        required=False,
        widget=forms.HiddenInput(),
    )
    member = forms.ModelChoiceField(
        label="Member",
        required=False,
        queryset=Member.objects.none(),
        widget=forms.HiddenInput(attrs={"id": "id_member"}),
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
            if "date" not in self.initial and not self.data:
                self.fields["date"].initial = resolve_transaction_date(church)
            self.fields["category"].queryset = selectors.categories_for_type_qs(
                church, txn_type
            )
            self.fields["member"].queryset = selectors.active_members_for_church_qs(church)

    def clean(self):
        cleaned = super().clean()
        if self.church and not cleaned.get("date"):
            cleaned["date"] = resolve_transaction_date(self.church)
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
            accounts = selectors.active_accounts_for_church_qs(church)
            self.fields["default_debit_account"].queryset = accounts
            self.fields["default_credit_account"].queryset = accounts
            self.fields["default_debit_account"].label_from_instance = _account_label
            self.fields["default_credit_account"].label_from_instance = _account_label
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


class LedgerCategoryCreateForm(forms.Form):
    code = forms.CharField(
        max_length=40,
        widget=forms.TextInput(attrs=input_attrs(placeholder="e.g. REC_CUSTOM_CASH")),
        help_text="Unique code for this church (letters, numbers, underscores).",
    )
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs=input_attrs()))
    transaction_type = forms.ChoiceField(
        choices=LedgerCategory.TRANSACTION_TYPES,
        widget=forms.Select(attrs=select_attrs()),
    )
    default_debit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    default_credit_account = forms.ModelChoiceField(
        queryset=Account.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    default_narration = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs=input_attrs()),
    )
    requires_member = forms.BooleanField(required=False)
    remit_to_district = forms.BooleanField(
        required=False,
        label="Apply remittance split (receipts)",
        help_text="For receipt categories: split credit into retain + remit payable.",
    )
    sort_order = forms.IntegerField(
        min_value=0,
        initial=100,
        widget=forms.NumberInput(attrs=input_attrs()),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            accounts = selectors.active_accounts_for_church_qs(church)
            self.fields["default_debit_account"].queryset = accounts
            self.fields["default_credit_account"].queryset = accounts
            self.fields["default_debit_account"].label_from_instance = _account_label
            self.fields["default_credit_account"].label_from_instance = _account_label

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper().replace(" ", "_")
        if not code:
            raise forms.ValidationError("Code is required.")
        if self.church and selectors.category_code_exists(self.church, code):
            raise forms.ValidationError("This code already exists for your church.")
        return code

    def clean(self):
        cleaned = super().clean()
        debit = cleaned.get("default_debit_account")
        credit = cleaned.get("default_credit_account")
        if debit and credit and debit.pk == credit.pk:
            raise forms.ValidationError("Debit and credit accounts must be different.")
        return cleaned


class AccountForm(forms.Form):
    name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=input_attrs()))
    code = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs=input_attrs(placeholder="e.g. UTILITIES")),
        help_text="Stable code for reports and remittance (auto-filled from name if blank).",
    )
    account_type = forms.ChoiceField(
        choices=Account.ACCOUNT_TYPES,
        widget=forms.Select(attrs=select_attrs()),
    )
    is_active = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, church=None, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.instance = instance
        if instance and not self.data:
            self.fields["name"].initial = instance.name
            self.fields["code"].initial = instance.code
            self.fields["account_type"].initial = instance.account_type
            self.fields["is_active"].initial = instance.is_active
            if selectors.account_has_journal_lines(instance):
                self.fields["code"].disabled = True
                self.fields["code"].help_text = "Code is locked because this account has journal lines."

    def clean_code(self):
        if self.instance and selectors.account_has_journal_lines(self.instance):
            return self.instance.code
        return (self.cleaned_data.get("code") or "").strip().upper().replace(" ", "_")

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        exclude_pk = self.instance.pk if self.instance else None
        if self.church and selectors.account_name_exists(
            self.church, name, exclude_pk=exclude_pk
        ):
            raise forms.ValidationError("An account with this name already exists.")
        return name
