"""Payroll forms."""

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from members.models import Member
from payroll.constants import UNIT_TYPES
from payroll.models import (
    Employee,
    EmployeeLoan,
    PayrollTaxBand,
    StatutoryContributionRule,
)
from payroll.services import get_unit_choices, resolve_paying_unit_id, set_employee_pii

User = get_user_model()


class PayingUnitFormMixin:
    """Dynamic paying unit picker for church-scoped hierarchy units."""

    def _init_paying_unit_fields(self, church):
        unit_type = (
            self.data.get("paying_unit_type")
            or self.initial.get("paying_unit_type")
            or "CHURCH"
        )
        choices = get_unit_choices(unit_type, church=church) or [("", "Select unit")]
        initial_unit = self.data.get("paying_unit_id") or self.initial.get("paying_unit_id", "")
        self.fields["paying_unit_id"] = forms.ChoiceField(
            choices=choices,
            widget=forms.Select(attrs=select_attrs()),
            initial=initial_unit,
            label="Paying unit",
        )


class EmployeeForm(PayingUnitFormMixin, forms.ModelForm):
    tin = forms.CharField(required=False, widget=forms.TextInput(attrs=input_attrs()))
    ssnit_number = forms.CharField(required=False, widget=forms.TextInput(attrs=input_attrs()))
    bank_account = forms.CharField(required=False, widget=forms.TextInput(attrs=input_attrs()))
    portal_user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Link user account (self-service payslips)",
        widget=forms.Select(attrs=select_attrs()),
    )

    class Meta:
        model = Employee
        fields = (
            "member",
            "employee_number",
            "first_name",
            "last_name",
            "email",
            "phone",
            "employment_type",
            "department",
            "job_title",
            "bank_name",
            "bank_branch",
            "paying_unit_type",
            "date_joined",
            "date_terminated",
            "status",
        )
        widgets = {
            "member": forms.Select(attrs=select_attrs()),
            "employee_number": forms.TextInput(attrs=input_attrs()),
            "first_name": forms.TextInput(attrs=input_attrs()),
            "last_name": forms.TextInput(attrs=input_attrs()),
            "email": forms.EmailInput(attrs=input_attrs()),
            "phone": forms.TextInput(attrs=input_attrs()),
            "employment_type": forms.Select(attrs=select_attrs()),
            "department": forms.Select(attrs=select_attrs()),
            "job_title": forms.TextInput(attrs=input_attrs()),
            "bank_name": forms.TextInput(attrs=input_attrs()),
            "bank_branch": forms.TextInput(attrs=input_attrs()),
            "paying_unit_type": forms.Select(attrs=select_attrs()),
            "date_joined": forms.DateInput(attrs=input_attrs(type="date")),
            "date_terminated": forms.DateInput(attrs=input_attrs(type="date")),
            "status": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            self.fields["member"].queryset = Member.objects.filter(
                church=church, is_active=True,
            ).order_by("last_name")
            self.fields["department"].queryset = church.departments.all()
            self.fields["paying_unit_type"].choices = UNIT_TYPES
            self.fields["portal_user"].queryset = User.objects.filter(
                church=church, is_active=True,
            ).order_by("username")
            self._init_paying_unit_fields(church)
            if self.instance.pk and self.instance.user_id:
                self.fields["portal_user"].initial = self.instance.user_id
        if self.instance.pk:
            from payroll.services import get_employee_pii
            pii = get_employee_pii(self.instance)
            self.fields["tin"].initial = pii["tin"]
            self.fields["ssnit_number"].initial = pii["ssnit_number"]
            self.fields["bank_account"].initial = pii["bank_account"]
            if self.instance.paying_unit_id:
                self.fields["paying_unit_id"].initial = str(self.instance.paying_unit_id)

    def save(self, commit=True):
        employee = super().save(commit=False)
        if self.church:
            employee.host_church = self.church
            employee.paying_unit_id = resolve_paying_unit_id(
                self.church,
                self.cleaned_data["paying_unit_type"],
                self.cleaned_data.get("paying_unit_id"),
            )
        portal_user = self.cleaned_data.get("portal_user")
        employee.user = portal_user
        set_employee_pii(
            employee,
            tin=self.cleaned_data.get("tin", ""),
            ssnit_number=self.cleaned_data.get("ssnit_number", ""),
            bank_account=self.cleaned_data.get("bank_account", ""),
        )
        if commit:
            employee.save()
        return employee


class CompensationForm(forms.Form):
    effective_from = forms.DateField(widget=forms.DateInput(attrs=input_attrs(type="date")))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=2)))


class PayrollRunForm(PayingUnitFormMixin, forms.Form):
    year = forms.IntegerField(min_value=2000, max_value=2100, widget=forms.NumberInput(attrs=input_attrs()))
    month = forms.IntegerField(min_value=1, max_value=12, widget=forms.NumberInput(attrs=input_attrs()))
    pay_date = forms.DateField(widget=forms.DateInput(attrs=input_attrs(type="date")))
    paying_unit_type = forms.ChoiceField(choices=UNIT_TYPES, widget=forms.Select(attrs=select_attrs()))
    description = forms.CharField(required=False, widget=forms.TextInput(attrs=input_attrs()))

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, church=church, **kwargs)
        self.church = church
        today = timezone.now().date()
        if not self.initial.get("year"):
            self.initial.setdefault("year", today.year)
            self.initial.setdefault("month", today.month)
            self.initial.setdefault("pay_date", today)
        if church:
            self._init_paying_unit_fields(church)


class RejectPayrollForm(forms.Form):
    reason = forms.CharField(
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
        label="Rejection reason",
    )


class EmployeeLoanForm(forms.ModelForm):
    class Meta:
        model = EmployeeLoan
        fields = ("principal", "monthly_recovery", "start_date", "description")
        widgets = {
            "principal": forms.NumberInput(attrs=input_attrs(step="0.01", min="0.01")),
            "monthly_recovery": forms.NumberInput(attrs=input_attrs(step="0.01", min="0.01")),
            "start_date": forms.DateInput(attrs=input_attrs(type="date")),
            "description": forms.TextInput(attrs=input_attrs()),
        }

    def save(self, commit=True):
        loan = super().save(commit=False)
        if not loan.balance:
            loan.balance = loan.principal
        if commit:
            loan.save()
        return loan


class TaxBandForm(forms.ModelForm):
    class Meta:
        model = PayrollTaxBand
        fields = ("lower_limit", "upper_limit", "rate_percent", "sort_order")
        widgets = {
            "lower_limit": forms.NumberInput(attrs=input_attrs(step="0.01")),
            "upper_limit": forms.NumberInput(attrs=input_attrs(step="0.01")),
            "rate_percent": forms.NumberInput(attrs=input_attrs(step="0.01")),
            "sort_order": forms.NumberInput(attrs=input_attrs()),
        }


class StatutoryRuleForm(forms.ModelForm):
    class Meta:
        model = StatutoryContributionRule
        fields = (
            "code", "name", "employee_rate", "employer_rate",
            "applies_to", "effective_from", "effective_to", "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs=input_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "employee_rate": forms.NumberInput(attrs=input_attrs(step="0.01")),
            "employer_rate": forms.NumberInput(attrs=input_attrs(step="0.01")),
            "applies_to": forms.Select(attrs=select_attrs()),
            "effective_from": forms.DateInput(attrs=input_attrs(type="date")),
            "effective_to": forms.DateInput(attrs=input_attrs(type="date")),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
