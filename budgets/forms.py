from django import forms
from django.core.exceptions import ValidationError

from budgets import selectors
from church_system.widgets import input_attrs, select_attrs
from transactions.models import Budget

from .services import apply_budget_scope, available_budget_levels, validate_budget_instance


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ["level", "year", "department", "account", "amount", "notes"]
        widgets = {
            "level": forms.Select(attrs=select_attrs()),
            "year": forms.NumberInput(attrs=input_attrs(min=2020, max=2099)),
            "department": forms.Select(attrs=select_attrs()),
            "account": forms.Select(attrs=select_attrs()),
            "amount": forms.NumberInput(attrs=input_attrs(step="0.01", min="0")),
            "notes": forms.TextInput(attrs=input_attrs()),
        }

    def __init__(self, *args, church=None, district=None, conference=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.district = district
        self.conference = conference
        self.user = user

        if user and church:
            level_choices = available_budget_levels(user, church)
            self.fields["level"].choices = level_choices
        else:
            self.fields["level"].choices = [("CHURCH", "Church")]

        self.fields["account"].queryset = selectors.accounts_for_church_qs(church)
        self.fields["department"].queryset = selectors.departments_for_church_qs(church)

        self.fields["department"].required = False
        self._sync_department_visibility()

    def _sync_department_visibility(self):
        level = self.data.get("level") or self.initial.get("level") or (
            self.instance.level if self.instance.pk else "CHURCH"
        )
        if level != "DEPARTMENT":
            self.fields["department"].widget = forms.HiddenInput()
            self.fields["department"].required = False
        else:
            self.fields["department"].required = True

    def clean(self):
        cleaned = super().clean()
        level = cleaned.get("level") or "CHURCH"
        department = cleaned.get("department")

        if level == "DEPARTMENT" and not department:
            self.add_error("department", "Select a department for department-level budgets.")

        if level == "CHURCH":
            cleaned["department"] = None

        budget = self.instance
        for field, value in cleaned.items():
            setattr(budget, field, value)
        apply_budget_scope(budget, church=self.church, district=self.district, conference=self.conference)

        try:
            validate_budget_instance(budget)
        except ValidationError as exc:
            raise ValidationError(exc.messages) from exc

        return cleaned


class BudgetFilterForm(forms.Form):
    year = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(
            attrs={**input_attrs(placeholder="Year"), "class": "form-control form-control-sm field-w-xs"}
        ),
    )
    level = forms.ChoiceField(
        required=False,
        choices=[
            ("CHURCH", "Church"),
            ("DEPARTMENT", "Department"),
            ("DISTRICT", "District"),
            ("CONFERENCE", "Conference"),
        ],
        widget=forms.Select(attrs={**select_attrs(), "class": "form-select form-select-sm field-w-sm"}),
    )


class BudgetCloneForm(forms.Form):
    source_year = forms.IntegerField(
        min_value=2020,
        max_value=2099,
        widget=forms.NumberInput(attrs=input_attrs(min=2020, max=2099)),
        label="From year",
    )
    target_year = forms.IntegerField(
        min_value=2020,
        max_value=2099,
        widget=forms.NumberInput(attrs=input_attrs(min=2020, max=2099)),
        label="To year",
    )

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source_year")
        target = cleaned.get("target_year")
        if source is not None and target is not None and source == target:
            raise ValidationError("Choose a different target year.")
        return cleaned
