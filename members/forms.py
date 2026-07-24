from django import forms

from organization.models import Church

from .models import (
    AGE_GROUP_CHOICES,
    Department,
    Family,
    FamilyRelationship,
    Member,
    MemberTransfer,
    MembershipStatus,
    Occupation,
    Record,
    Visitor,
    VisitorFollowUpStatus,
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
        exclude = (
            "church",
            "created_by",
            "created_at",
            "updated_at",
            "is_active",
            "is_deleted",
            "deleted_at",
            "deleted_by",
            "deletion_reason",
        )
        widgets = {
            "first_name": forms.TextInput(attrs=_text()),
            "middle_name": forms.TextInput(attrs=_text()),
            "last_name": forms.TextInput(attrs=_text()),
            "preferred_name": forms.TextInput(attrs=_text()),
            "gender": forms.Select(attrs=_select()),
            "marital_status": forms.Select(attrs=_select()),
            "date_of_birth": forms.DateInput(attrs={**_text(), "type": "date"}),
            "date_joined": forms.DateInput(attrs={**_text(), "type": "date"}),
            "membership_status": forms.Select(attrs=_select()),
            "membership_number": forms.TextInput(attrs=_text()),
            "phone": forms.TextInput(attrs=_text()),
            "email": forms.EmailInput(attrs=_text()),
            "address": forms.Textarea(attrs={**_text(), "rows": 2}),
            "emergency_contact_name": forms.TextInput(attrs=_text()),
            "emergency_contact_phone": forms.TextInput(attrs=_text()),
            "emergency_contact_relation": forms.TextInput(attrs=_text()),
            "baptism_date": forms.DateInput(attrs={**_text(), "type": "date"}),
            "baptism_place": forms.TextInput(attrs=_text()),
            "baptism_certificate_number": forms.TextInput(attrs=_text()),
            "occupation": forms.Select(attrs=_select()),
            "department": forms.Select(attrs=_select()),
            "family": forms.Select(attrs=_select()),
            "family_relationship": forms.Select(attrs=_select()),
            "profile_picture": forms.ClearableFileInput(attrs=input_attrs()),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        self.duplicate_warnings = []
        from .lookups import (
            LookupCategory,
            apply_lookup_choices,
            apply_static_choices,
            ensure_member_form_catalogs,
        )

        ensure_member_form_catalogs(church)
        apply_lookup_choices(self.fields["gender"], LookupCategory.GENDER)
        apply_lookup_choices(
            self.fields["marital_status"], LookupCategory.MARITAL_STATUS, blank=True
        )
        apply_lookup_choices(
            self.fields["membership_status"], LookupCategory.MEMBERSHIP_STATUS
        )
        apply_static_choices(
            self.fields["family_relationship"],
            FamilyRelationship.choices,
            blank=True,
        )
        if church:
            self.fields["occupation"].queryset = Occupation.objects.filter(
                church=church
            ).order_by("name")
            self.fields["department"].queryset = Department.objects.filter(
                church=church
            ).order_by("name")
            self.fields["family"].queryset = Family.objects.filter(church=church).order_by(
                "name"
            )
        self.fields["occupation"].empty_label = "—"
        self.fields["occupation"].required = False
        self.fields["department"].empty_label = "—"
        self.fields["department"].required = False
        self.fields["family"].empty_label = "—"
        self.fields["family"].required = False
        self.fields["family_relationship"].required = False

    def clean_profile_picture(self):
        from church_system.uploads import validate_upload

        picture = self.cleaned_data.get("profile_picture")
        if picture:
            validate_upload(picture, kind="image")
        return picture

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

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            return ""
        qs = Member.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(
                "This email is already used by another member. "
                "Portal sign-in requires a unique email."
            )
        return email

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
        email = (cleaned.get("email") or "").strip()
        dob = cleaned.get("date_of_birth")
        if email and not dob:
            self.add_error(
                "date_of_birth",
                "Date of birth is required when an email is set "
                "(needed for member portal first sign-in).",
            )
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
        from .lookups import LookupCategory, apply_lookup_choices

        apply_lookup_choices(self.fields["record_type"], LookupCategory.RECORD_TYPE)
        apply_lookup_choices(self.fields["status"], LookupCategory.RECORD_STATUS)
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
        choices=[("", "All statuses")],
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
        choices=[("", "All genders")],
        widget=forms.Select(attrs=_select()),
    )
    age_group = forms.ChoiceField(
        required=False,
        choices=[("", "All age groups")] + list(AGE_GROUP_CHOICES),
        widget=forms.Select(attrs=_select()),
    )

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .lookups import LookupCategory, lookup_choice_tuples

        self.fields["status"].choices = lookup_choice_tuples(
            LookupCategory.MEMBERSHIP_STATUS, include_blank="", blank_label="All statuses"
        )
        self.fields["gender"].choices = lookup_choice_tuples(
            LookupCategory.GENDER, include_blank="", blank_label="All genders"
        )
        if church:
            self.fields["department"].queryset = Department.objects.filter(church=church)


class BaptismRegisterFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs=search_attrs(placeholder="Member, place, certificate…")),
    )
    date_from = forms.DateField(
        required=False,
        label="From date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "All statuses")],
        widget=forms.Select(attrs=_select()),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .lookups import LookupCategory, lookup_choice_tuples

        self.fields["status"].choices = lookup_choice_tuples(
            LookupCategory.RECORD_STATUS, include_blank="", blank_label="All statuses"
        )


class RecordFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(attrs=search_attrs(placeholder="Member, title, place…")),
    )
    type = forms.ChoiceField(
        required=False,
        label="Type",
        choices=[("", "All types")],
        widget=forms.Select(attrs=_select()),
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=[("", "All statuses")],
        widget=forms.Select(attrs=_select()),
    )
    date_from = forms.DateField(
        required=False,
        label="From date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .lookups import LookupCategory, lookup_choice_tuples

        self.fields["type"].choices = lookup_choice_tuples(
            LookupCategory.RECORD_TYPE, include_blank="", blank_label="All types"
        )
        self.fields["status"].choices = lookup_choice_tuples(
            LookupCategory.RECORD_STATUS, include_blank="", blank_label="All statuses"
        )


class OccupationForm(forms.ModelForm):
    class Meta:
        model = Occupation
        fields = ("name",)
        widgets = {"name": forms.TextInput(attrs=_text())}

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        if self.church:
            qs = Occupation.objects.filter(church=self.church, name__iexact=name)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("An occupation with this name already exists for this church.")
        return name


class MemberLookupOptionForm(forms.ModelForm):
    class Meta:
        from members.models import MemberLookupOption

        model = MemberLookupOption
        fields = ("category", "code", "label", "is_active", "sort_order")
        widgets = {
            "category": forms.Select(attrs=_select()),
            "code": forms.TextInput(attrs=_text()),
            "label": forms.TextInput(attrs=_text()),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs=_text()),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.is_system:
            self.fields["category"].disabled = True
            self.fields["code"].disabled = True

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            raise forms.ValidationError("Code is required.")
        return code


class VisitorForm(forms.ModelForm):
    class Meta:
        model = Visitor
        fields = (
            "first_name",
            "last_name",
            "phone",
            "email",
            "address",
            "visit_date",
            "invited_by",
            "interests",
            "follow_up_status",
            "assigned_elder",
            "notes",
        )
        widgets = {
            "first_name": forms.TextInput(attrs=_text()),
            "last_name": forms.TextInput(attrs=_text()),
            "phone": forms.TextInput(attrs=_text()),
            "email": forms.EmailInput(attrs=_text()),
            "address": forms.Textarea(attrs={**_text(), "rows": 2}),
            "visit_date": forms.DateInput(attrs={**_text(), "type": "date"}),
            "invited_by": forms.HiddenInput(),
            "interests": forms.TextInput(attrs=_text()),
            "follow_up_status": forms.Select(attrs=_select()),
            "assigned_elder": forms.HiddenInput(),
            "notes": forms.Textarea(attrs={**_text(), "rows": 3}),
        }

    def __init__(self, *args, church=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.church = church
        members = Member.objects.none()
        if church:
            members = Member.objects.filter(church=church, is_active=True).order_by(
                "last_name", "first_name"
            )
        self.fields["invited_by"].queryset = members
        self.fields["assigned_elder"].queryset = members
        self.fields["invited_by"].required = False
        self.fields["assigned_elder"].required = False

    def clean_invited_by(self):
        member = self.cleaned_data.get("invited_by")
        if member and self.church and member.church_id != self.church.pk:
            raise forms.ValidationError("Invited-by member must belong to this church.")
        return member

    def clean_assigned_elder(self):
        member = self.cleaned_data.get("assigned_elder")
        if member and self.church and member.church_id != self.church.pk:
            raise forms.ValidationError("Assigned elder must belong to this church.")
        return member


class VisitorFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs=search_attrs(placeholder="Search name, phone, email…")),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + list(VisitorFollowUpStatus.choices),
        widget=forms.Select(attrs=_select()),
    )
    date_from = forms.DateField(
        required=False,
        label="From date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="To date",
        widget=forms.DateInput(attrs={**_text(), "type": "date"}),
    )


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
