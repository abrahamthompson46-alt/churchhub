"""Organization hierarchy forms."""

from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs
from organization import selectors
from organization.models import Church, Conference, District, GeneralConference, Union, Zone, ChurchHistoryEntry


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
            self.fields["zone"].queryset = selectors.zones_for_denomination(denomination)
        if "district" in self.fields:
            self.fields["district"].queryset = selectors.districts_for_denomination(
                denomination
            )


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
            self.fields["general_conference"].queryset = selectors.general_conference_by_pk(
                general_conference.pk
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
            self.fields["conference"].queryset = selectors.conference_by_pk(conference.pk)
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
            self.fields["zone"].queryset = selectors.zone_by_pk(zone.pk)
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
        self.preselected_district = district
        if not show_status:
            self.fields.pop("is_active", None)

        if self.instance and self.instance.pk:
            # District changes go through the transfer flow, not edit.
            self.fields.pop("district", None)
            return

        if request:
            self.apply_denomination_scope(request)
            from organization.access import scoped_districts

            scoped = scoped_districts(request).select_related("zone__conference")
        else:
            scoped = selectors.all_districts_with_parents()

        if district:
            # Lock to the district from ?district= so create-from-district-detail always works.
            self.fields["district"].queryset = scoped.filter(pk=district.pk)
            self.fields["district"].initial = district.pk
            self.fields["district"].widget = forms.HiddenInput()
        else:
            self.fields["district"].queryset = scoped.order_by(
                "zone__conference__name", "zone__name", "name"
            )


class ChurchOnboardingForm(forms.Form):
    """Add a church under an existing district."""

    district = forms.ModelChoiceField(
        queryset=selectors.empty_districts(),
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
        queryset=selectors.empty_districts(),
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
            self.fields["district"].queryset = selectors.transfer_target_districts(
                request, church
            )

    def clean(self):
        cleaned = super().clean()
        district = cleaned.get("district")
        if not district:
            return cleaned
        return cleaned


class ChurchHistoryEntryForm(forms.ModelForm):
    class Meta:
        model = ChurchHistoryEntry
        fields = (
            "church",
            "title",
            "event_date",
            "category",
            "location",
            "tags",
            "body",
        )
        widgets = {
            "church": forms.Select(attrs=select_attrs()),
            "title": forms.TextInput(attrs=input_attrs()),
            "event_date": forms.DateInput(attrs={**input_attrs(), "type": "date"}),
            "category": forms.Select(attrs=select_attrs()),
            "location": forms.TextInput(attrs=input_attrs()),
            "tags": forms.TextInput(
                attrs={
                    **input_attrs(),
                    "placeholder": "e.g. dedication, anniversary, building",
                }
            ),
            "body": forms.Textarea(attrs=textarea_attrs(rows=6)),
        }

    def __init__(self, *args, churches=None, default_church=None, **kwargs):
        super().__init__(*args, **kwargs)
        church_qs = churches if churches is not None else Church.objects.none()
        self.fields["church"].queryset = church_qs.order_by("name")
        self.fields["church"].empty_label = None
        if default_church and not self.instance.pk:
            self.fields["church"].initial = default_church.pk
        if church_qs.count() == 1:
            only = church_qs.first()
            self.fields["church"].initial = only.pk
            self.fields["church"].widget = forms.HiddenInput()
        self.fields["title"].help_text = "Short headline shown in the chronicle list."
        self.fields["body"].label = "History details"
        self.fields["tags"].help_text = "Optional keywords for search (comma-separated)."


class ChurchHistorySearchForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                **input_attrs(),
                "type": "search",
                "placeholder": "Search title, details, tags, church…",
                "autocomplete": "off",
            }
        ),
    )
    category = forms.ChoiceField(
        required=False,
        label="Category",
        choices=[("", "All categories")],
        widget=forms.Select(attrs=select_attrs()),
    )
    church = forms.ModelChoiceField(
        required=False,
        label="Church",
        queryset=Church.objects.none(),
        empty_label="All churches in scope",
        widget=forms.Select(attrs=select_attrs()),
    )
    conference = forms.ModelChoiceField(
        required=False,
        label="Conference",
        queryset=Conference.objects.none(),
        empty_label="All conferences in scope",
        widget=forms.Select(attrs=select_attrs()),
    )
    date_from = forms.DateField(
        required=False,
        label="From",
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To",
        widget=forms.DateInput(attrs={**input_attrs(), "type": "date"}),
    )

    def __init__(self, *args, churches=None, conferences=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].choices = [("", "All categories")] + list(
            ChurchHistoryEntry.Category.choices
        )
        if churches is not None:
            self.fields["church"].queryset = churches.order_by("name")
        if conferences is not None:
            self.fields["conference"].queryset = conferences.order_by("name")
        # Hide conference/church filters when only one church is in scope (local users).
        if churches is not None and churches.count() <= 1:
            self.fields["conference"].widget = forms.HiddenInput()
            self.fields["church"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", "End date must be on or after the start date.")
        return cleaned