from django import forms

from church_system.widgets import input_attrs, select_attrs
from permissions.checks import can_view_all_churches

from .registry import PERIOD_CHOICES


class ReportFilterForm(forms.Form):
    period = forms.ChoiceField(
        choices=PERIOD_CHOICES,
        initial="monthly",
        widget=forms.Select(attrs=select_attrs()),
    )
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )

    def __init__(self, *args, user=None, hierarchy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self._hierarchy_enabled = False
        # Non-overseers must not receive HiddenInput UUID fields (ID forgery vector).
        if hierarchy and can_view_all_churches(user):
            self._hierarchy_enabled = True
            self.fields["conference"] = forms.ModelChoiceField(
                queryset=hierarchy["conferences"],
                required=False,
                empty_label="All conferences",
                widget=forms.Select(attrs={**select_attrs(), "data-hierarchy": "conference"}),
            )
            self.fields["zone"] = forms.ModelChoiceField(
                queryset=hierarchy["zones"],
                required=False,
                empty_label="All zones",
                widget=forms.Select(attrs={**select_attrs(), "data-hierarchy": "zone"}),
            )
            self.fields["district"] = forms.ModelChoiceField(
                queryset=hierarchy["districts"],
                required=False,
                empty_label="All districts",
                widget=forms.Select(attrs={**select_attrs(), "data-hierarchy": "district"}),
            )
            self.fields["church"] = forms.ModelChoiceField(
                queryset=hierarchy["churches"],
                required=False,
                empty_label="All churches",
                widget=forms.Select(attrs={**select_attrs(), "data-hierarchy": "church"}),
            )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after start date.")
        return cleaned

    @property
    def show_hierarchy_filters(self):
        return self._hierarchy_enabled


class WelfareStatementForm(forms.Form):
    member = forms.CharField(required=False, widget=forms.HiddenInput())
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church

    def clean(self):
        cleaned = super().clean()
        member_id = (cleaned.get("member") or "").strip()
        if not member_id:
            raise forms.ValidationError({"member": "Select a member."})
        if not self.church:
            raise forms.ValidationError({"member": "Church context is required."})
        from members.models import Member

        try:
            cleaned["member_obj"] = Member.objects.get(
                pk=member_id,
                church=self.church,
                is_active=True,
            )
        except (Member.DoesNotExist, ValueError):
            raise forms.ValidationError({"member": "Select a valid active member."})
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after start date.")
        return cleaned
