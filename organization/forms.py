"""Organization hierarchy forms."""

from django import forms
from django.core.exceptions import ValidationError

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from organization.models import Church, Conference, District, GeneralConference, Union, Zone


class DenominationScopedFormMixin:
    """Limit parent FK querysets to the active denomination."""

    def apply_denomination_scope(self, request):
        from church_system.denomination_scope import conferences_for_denomination, get_active_denomination

        denomination = get_active_denomination(request)
        if not denomination:
            return
        if "conference" in self.fields:
            self.fields["conference"].queryset = conferences_for_denomination(denomination)
        if "zone" in self.fields:
            self.fields["zone"].queryset = Zone.objects.filter(
                conference__denomination=denomination
            ).select_related("conference")
        if "district" in self.fields:
            self.fields["district"].queryset = District.objects.filter(
                zone__conference__denomination=denomination
            ).select_related("zone__conference")


class ConferenceForm(DenominationScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Conference
        fields = ("denomination", "union", "name", "code")
        widgets = {
            "denomination": forms.Select(attrs=select_attrs()),
            "union": forms.Select(attrs=select_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
        }

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if request:
            self.apply_denomination_scope(request)
            from church_system.denomination_scope import get_active_denomination

            denomination = get_active_denomination(request)
            if denomination and not self.instance.pk:
                self.fields["denomination"].initial = denomination.pk
                self.fields["denomination"].queryset = self.fields["denomination"].queryset.filter(
                    pk=denomination.pk
                )


class GeneralConferenceForm(forms.ModelForm):
    class Meta:
        model = GeneralConference
        fields = ("name", "code")
        widgets = {
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
        }


class UnionForm(forms.ModelForm):
    class Meta:
        model = Union
        fields = ("general_conference", "name", "code")
        widgets = {
            "general_conference": forms.Select(attrs=select_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
        }

    def __init__(self, *args, general_conference=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if general_conference:
            self.fields["general_conference"].queryset = GeneralConference.objects.filter(
                pk=general_conference.pk
            )
            self.fields["general_conference"].initial = general_conference.pk


class ZoneForm(DenominationScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Zone
        fields = ("conference", "name", "code")
        widgets = {
            "conference": forms.Select(attrs=select_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
        }

    def __init__(self, *args, conference=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if conference:
            self.fields["conference"].queryset = Conference.objects.filter(pk=conference.pk)
            self.fields["conference"].initial = conference.pk
        if request:
            self.apply_denomination_scope(request)


class DistrictForm(DenominationScopedFormMixin, forms.ModelForm):
    class Meta:
        model = District
        fields = ("zone", "name", "code")
        widgets = {
            "zone": forms.Select(attrs=select_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
        }

    def __init__(self, *args, zone=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if zone:
            self.fields["zone"].queryset = Zone.objects.filter(pk=zone.pk).select_related("conference")
            self.fields["zone"].initial = zone.pk
        if request:
            self.apply_denomination_scope(request)


class ChurchForm(DenominationScopedFormMixin, forms.ModelForm):
    class Meta:
        model = Church
        fields = ("district", "name", "code", "address", "is_active")
        widgets = {
            "district": forms.Select(attrs=select_attrs()),
            "name": forms.TextInput(attrs=input_attrs()),
            "code": forms.TextInput(attrs=input_attrs()),
            "address": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, district=None, request=None, show_status=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not show_status:
            self.fields.pop("is_active", None)
        if district:
            self.fields["district"].queryset = District.objects.filter(pk=district.pk).select_related(
                "zone__conference"
            )
            self.fields["district"].initial = district.pk
        if request:
            self.apply_denomination_scope(request)
            from organization.access import scoped_districts

            self.fields["district"].queryset = scoped_districts(request).select_related(
                "zone__conference"
            )
        if self.instance and self.instance.pk:
            self.fields.pop("district", None)


class ChurchOnboardingForm(forms.Form):
    """Add a church under an existing district."""

    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )
    name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=3)))
    setup_financials = forms.BooleanField(
        required=False,
        initial=True,
        label="Create default financial accounts and offering categories",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if request:
            from organization.access import scoped_districts

            self.fields["district"].queryset = scoped_districts(request).select_related(
                "zone__conference"
            ).order_by("zone__conference__name", "zone__name", "name")


class FullChurchOnboardingForm(forms.Form):
    """Create a full Conference → Zone → District → Church path in one step."""

    conference_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    conference_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    zone_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    zone_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    district_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    district_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    church_name = forms.CharField(max_length=200, widget=forms.TextInput(attrs=input_attrs()))
    church_code = forms.CharField(max_length=20, widget=forms.TextInput(attrs=input_attrs()))
    address = forms.CharField(required=False, widget=forms.Textarea(attrs=textarea_attrs(rows=3)))
    setup_financials = forms.BooleanField(
        required=False,
        initial=True,
        label="Create default financial accounts and offering categories",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class ChurchTransferForm(forms.Form):
    district = forms.ModelChoiceField(
        queryset=District.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
        label="Target district",
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs=textarea_attrs(rows=2)),
        label="Reason for transfer",
    )

    def __init__(self, *args, church=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        if request and church:
            from organization.access import scoped_districts

            qs = scoped_districts(request).exclude(pk=church.district_id)
            denom_id = church.conference.denomination_id if church.conference else None
            if denom_id:
                qs = qs.filter(zone__conference__denomination_id=denom_id)
            self.fields["district"].queryset = qs.select_related("zone__conference")

    def clean(self):
        cleaned = super().clean()
        district = cleaned.get("district")
        if not district:
            return cleaned
        return cleaned
