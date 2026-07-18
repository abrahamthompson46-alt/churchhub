from django import forms

from organization.models import Church

from .models import (
    AGE_GROUP_CHOICES,
    Department,
    Family,
    Member,
    MemberTransfer,
    MembershipStatus,
    Record,
)
from .services import find_duplicate_members

from church_system.widgets import input_attrs, search_attrs, select_attrs


def _text(attrs=None):
    return input_attrs(**(attrs or {}))


def _select(attrs=None):
    return select_attrs(**(attrs or {}))


class MemberForm(forms.ModelForm):
    class Meta:
        model = Member
        exclude = ("church", "created_by", "created_at", "updated_at")
        widgets = {
            "first_name": forms.TextInput(attrs=_text()),
            "last_name": forms.TextInput(attrs=_text()),
            "gender": forms.Select(attrs=_select()),
            "marital_status": forms.Select(attrs=_select()),
            "date_of_birth": forms.DateInput(attrs={**_text(), "type": "date"}),
            "date_joined": forms.DateInput(attrs={**_text(), "type": "date"}),
            "membership_status": forms.Select(attrs=_select()),
            "membership_number": forms.TextInput(attrs=_text()),
            "phone": forms.TextInput(attrs=_text()),
            "address": forms.Textarea(attrs={**_text(), "rows": 2}),
            "baptism_date": forms.DateInput(attrs={**_text(), "type": "date"}),
            "baptism_place": forms.TextInput(attrs=_text()),
            "baptism_certificate_number": forms.TextInput(attrs=_text()),
            "occupation": forms.Select(attrs=_select()),
            "department": forms.Select(attrs=_select()),
            "family": forms.Select(attrs=_select()),
            "profile_picture": forms.ClearableFileInput(attrs=input_attrs()),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.duplicate_warnings = []
        if church:
            from .models import Occupation

            self.fields["occupation"].queryset = Occupation.objects.filter(church=church)
            self.fields["department"].queryset = Department.objects.filter(church=church)
            self.fields["family"].queryset = Family.objects.filter(church=church)

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not phone or not self.church:
            return phone
        qs = Member.objects.filter(church=self.church, phone=phone)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "A member with this phone number already exists in this church."
            )
        return phone

    def clean_membership_number(self):
        number = (self.cleaned_data.get("membership_number") or "").strip()
        if not number or not self.church:
            return number
        qs = Member.objects.filter(church=self.church, membership_number=number)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "This membership number is already assigned in this church."
            )
        return number

    def clean(self):
        cleaned = super().clean()
        if not self.church:
            return cleaned
        duplicates = find_duplicate_members(
            self.church,
            cleaned.get("first_name", ""),
            cleaned.get("last_name", ""),
            date_of_birth=cleaned.get("date_of_birth"),
            phone=cleaned.get("phone", ""),
            exclude_pk=self.instance.pk if self.instance else None,
        )
        # Soft warning for name+DOB matches that aren't hard phone conflicts
        name_dob_matches = [
            m for m in duplicates
            if m.date_of_birth and m.date_of_birth == cleaned.get("date_of_birth")
        ]
        if name_dob_matches and cleaned.get("date_of_birth"):
            names = ", ".join(m.full_name for m in name_dob_matches[:3])
            self.duplicate_warnings.append(
                f"Possible duplicate(s) with same name and date of birth: {names}."
            )
        return cleaned


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "description")
        widgets = {
            "name": forms.TextInput(attrs=_text()),
            "description": forms.Textarea(attrs={**_text(), "rows": 2}),
        }


class FamilyForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ("name", "head", "address", "phone")
        widgets = {
            "name": forms.TextInput(attrs=_text()),
            "head": forms.HiddenInput(),
            "address": forms.Textarea(attrs={**_text(), "rows": 2}),
            "phone": forms.TextInput(attrs=_text()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            self.fields["head"].queryset = Member.objects.filter(church=church).order_by(
                "last_name", "first_name"
            )
        self.fields["head"].required = False

    def clean_head(self):
        head = self.cleaned_data.get("head")
        if head and self.church and head.church_id != self.church.pk:
            raise forms.ValidationError("Family head must belong to this church.")
        return head


class RecordForm(forms.ModelForm):
    class Meta:
        model = Record
        fields = (
            "member",
            "record_type",
            "title",
            "description",
            "event_date",
            "place",
            "officiant",
            "certificate_number",
            "status",
        )
        widgets = {
            "member": forms.HiddenInput(),
            "record_type": forms.Select(attrs=_select()),
            "title": forms.TextInput(attrs=_text()),
            "description": forms.Textarea(attrs={**_text(), "rows": 3}),
            "event_date": forms.DateInput(attrs={**_text(), "type": "date"}),
            "place": forms.TextInput(attrs=_text()),
            "officiant": forms.TextInput(attrs=_text()),
            "certificate_number": forms.TextInput(attrs=_text()),
            "status": forms.Select(attrs=_select()),
        }

    def __init__(self, *args, church=None, member=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["member"].queryset = Member.objects.filter(church=church).order_by(
                "last_name", "first_name"
            )
        if member:
            self.fields["member"].initial = member.pk
            self.fields["member"].queryset = Member.objects.filter(pk=member.pk)


class MemberTransferForm(forms.ModelForm):
    class Meta:
        model = MemberTransfer
        fields = ("member", "to_church", "transfer_date", "reason")
        widgets = {
            "member": forms.HiddenInput(),
            "to_church": forms.Select(attrs=_select()),
            "transfer_date": forms.DateInput(attrs={**_text(), "type": "date"}),
            "reason": forms.Textarea(attrs={**_text(), "rows": 3}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["member"].queryset = Member.objects.filter(
                church=church, is_active=True,
            ).exclude(membership_status=MembershipStatus.TRANSFERRED).order_by(
                "last_name", "first_name"
            )
            # Same denomination wall; allow cross-conference destinations.
            dest = Church.objects.filter(is_active=True).exclude(pk=church.pk)
            denom = church.denomination
            if denom:
                dest = dest.filter(district__zone__conference__denomination=denom)
            elif church.district_id:
                dest = dest.filter(
                    district__zone__conference_id=church.district.zone.conference_id,
                )
            self.fields["to_church"].queryset = dest.select_related(
                "district__zone__conference"
            ).order_by("name")


class MemberFilterForm(forms.Form):
    q = forms.CharField(required=False, widget=forms.TextInput(attrs=search_attrs(
        placeholder="Search name, phone, or membership #…",
    )))
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + list(MembershipStatus.choices),
        widget=forms.Select(attrs=_select()),
    )
    department = forms.ModelChoiceField(
        required=False,
        queryset=Department.objects.none(),
        empty_label="All departments",
        widget=forms.Select(attrs=_select()),
    )
    gender = forms.ChoiceField(
        required=False,
        choices=[("", "All genders"), ("Male", "Male"), ("Female", "Female")],
        widget=forms.Select(attrs=_select()),
    )
    age_group = forms.ChoiceField(
        required=False,
        choices=[("", "All age groups")] + list(AGE_GROUP_CHOICES),
        widget=forms.Select(attrs=_select()),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church:
            self.fields["department"].queryset = Department.objects.filter(church=church)


class SpiritualGiftForm(forms.ModelForm):
    class Meta:
        from .models import SpiritualGift
        model = SpiritualGift
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(attrs=_text()),
            "description": forms.Textarea(attrs={**_text(), "rows": 2}),
        }


class MemberGiftForm(forms.Form):
    gift = forms.ModelChoiceField(queryset=None, widget=forms.Select(attrs=_select()))
    noted_at = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    notes = forms.CharField(required=False, widget=forms.TextInput(attrs=_text()))

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import SpiritualGift
        if church:
            self.fields["gift"].queryset = SpiritualGift.objects.filter(church=church)


class LeadershipRoleForm(forms.ModelForm):
    class Meta:
        from .models import LeadershipRole
        model = LeadershipRole
        fields = ["member", "department", "title", "start_date", "end_date", "is_active"]
        widgets = {
            "member": forms.HiddenInput(),
            "department": forms.Select(attrs=_select()),
            "title": forms.TextInput(attrs=_text()),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        if church:
            self.fields["member"].queryset = Member.objects.filter(church=church, is_active=True)
            self.fields["department"].queryset = Department.objects.filter(church=church)

    def clean(self):
        cleaned = super().clean()
        member = cleaned.get("member")
        department = cleaned.get("department")
        if self.church and member and member.church_id != self.church.pk:
            raise forms.ValidationError("Member must belong to this church.")
        if self.church and department and department.church_id != self.church.pk:
            raise forms.ValidationError("Department must belong to this church.")
        return cleaned
