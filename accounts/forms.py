from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from church_system.widgets import input_attrs, select_attrs
from accounts import repositories as repo
from accounts import selectors
from permissions.org_scope import (
    OrgScopeLevel,
    apply_org_scope,
    manageable_scope_units,
)
from permissions.roles import UserRole
from permissions.scoping import get_manageable_churches

from .models import User


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")
        widgets = {
            "first_name": forms.TextInput(attrs=input_attrs()),
            "last_name": forms.TextInput(attrs=input_attrs()),
            "email": forms.EmailInput(attrs=input_attrs()),
            "phone": forms.TextInput(attrs=input_attrs()),
        }

    def changed_profile_data(self):
        """Return cleaned_data subset for fields that actually changed."""
        if not self.is_valid():
            return {}
        changed = {}
        for name in self.Meta.fields:
            if name in self.changed_data:
                changed[name] = self.cleaned_data[name]
        return changed


class UserInviteForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs=input_attrs()))
    username = forms.CharField(max_length=150, widget=forms.TextInput(attrs=input_attrs()))
    role = forms.ChoiceField(choices=[], widget=forms.Select(attrs=select_attrs(**{"class": "scope-role-select"})))
    scope_level = forms.ChoiceField(
        choices=OrgScopeLevel.CHOICES,
        widget=forms.Select(attrs=select_attrs(**{"class": "scope-level-select"})),
        help_text="How wide this person’s authority is in the organization tree.",
    )
    scope_unit = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs=select_attrs(**{"class": "scope-unit-select"})),
        label="Organization unit",
        help_text="The node they belong to. They can only manage inside this subtree.",
    )
    church = forms.ModelChoiceField(
        queryset=selectors.empty_churches(),
        required=False,
        widget=forms.Select(attrs=select_attrs()),
        label="Home church",
        help_text="Required for local roles. Optional anchor for district/conference admins.",
    )

    def __init__(self, *args, manager=None, **kwargs):
        self.manager = manager
        super().__init__(*args, **kwargs)
        if not manager:
            return

        self.fields["role"].choices = UserRole.assignable_role_choices(manager)
        role = self.data.get("role") if self.is_bound else self.initial.get("role")
        if not role and self.fields["role"].choices:
            role = self.fields["role"].choices[0][0]
        if role and not self.is_bound:
            self.fields["role"].initial = role

        default_level = OrgScopeLevel.default_for_role(role or UserRole.MEMBER)
        allowed_levels = OrgScopeLevel.allowed_for_role(role or UserRole.MEMBER)
        self.fields["scope_level"].choices = [
            c for c in OrgScopeLevel.CHOICES if c[0] in allowed_levels
        ]
        level = self.data.get("scope_level") if self.is_bound else self.initial.get("scope_level")
        if not level or level not in allowed_levels:
            level = default_level
        if not self.is_bound:
            self.fields["scope_level"].initial = level

        units = manageable_scope_units(manager, level)
        self.fields["scope_unit"].choices = [("", "— Select —")] + [
            (str(obj.pk), str(obj)) for obj in units
        ]

        churches = get_manageable_churches(manager)
        # Narrow home church options to selected unit when possible
        unit_id = self.data.get("scope_unit") if self.is_bound else None
        if unit_id and level == OrgScopeLevel.DISTRICT:
            churches = churches.filter(district_id=unit_id)
        elif unit_id and level == OrgScopeLevel.ZONE:
            churches = churches.filter(district__zone_id=unit_id)
        elif unit_id and level == OrgScopeLevel.CONFERENCE:
            churches = churches.filter(district__zone__conference_id=unit_id)
        elif unit_id and level == OrgScopeLevel.UNION:
            churches = churches.filter(district__zone__conference__union_id=unit_id)
        elif unit_id and level == OrgScopeLevel.CHURCH:
            churches = churches.filter(pk=unit_id)

        self.fields["church"].queryset = churches
        if churches.count() == 1:
            self.fields["church"].initial = churches.first().pk

        if UserRole.requires_church(role or UserRole.MEMBER):
            self.fields["church"].required = True
            self.fields["scope_unit"].required = level == OrgScopeLevel.CHURCH
        else:
            self.fields["scope_unit"].required = level != OrgScopeLevel.DENOMINATION

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.manager and not UserRole.can_assign_role(
            self.manager.role,
            role,
            actor_is_superuser=self.manager.is_superuser,
        ):
            raise ValidationError("You are not allowed to assign this role.")
        return role

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        level = cleaned.get("scope_level") or OrgScopeLevel.default_for_role(role or UserRole.MEMBER)
        unit_id = cleaned.get("scope_unit")
        church = cleaned.get("church")

        if role and level not in OrgScopeLevel.allowed_for_role(role):
            self.add_error("scope_level", "This scope level is not valid for the selected role.")

        if UserRole.requires_church(role) and not church:
            self.add_error("church", "Local roles require a home church.")

        # Resolve unit object
        cleaned["scope_district"] = None
        cleaned["scope_zone"] = None
        cleaned["scope_conference"] = None
        cleaned["scope_union"] = None
        cleaned["scope_general_conference"] = None
        cleaned["denomination"] = None

        if level == OrgScopeLevel.CHURCH:
            if church:
                cleaned["scope_unit_obj"] = church
            elif unit_id:
                cleaned["scope_unit_obj"] = selectors.church_by_pk(unit_id)
                cleaned["church"] = cleaned["scope_unit_obj"]
            else:
                self.add_error("scope_unit", "Select the local church.")
        elif level == OrgScopeLevel.DISTRICT:
            district = selectors.district_by_pk(unit_id) if unit_id else None
            if not district and church:
                district = church.district
            if not district:
                self.add_error("scope_unit", "Select the district.")
            cleaned["scope_district"] = district
        elif level == OrgScopeLevel.ZONE:
            zone = selectors.zone_by_pk(unit_id) if unit_id else None
            if not zone and church:
                zone = church.district.zone
            if not zone:
                self.add_error("scope_unit", "Select the zone.")
            cleaned["scope_zone"] = zone
        elif level == OrgScopeLevel.CONFERENCE:
            conference = selectors.conference_by_pk(unit_id) if unit_id else None
            if not conference and church:
                conference = church.district.zone.conference
            if not conference:
                self.add_error("scope_unit", "Select the conference.")
            cleaned["scope_conference"] = conference
        elif level == OrgScopeLevel.UNION:
            union = selectors.union_by_pk(unit_id) if unit_id else None
            if not union:
                self.add_error("scope_unit", "Select the union.")
            cleaned["scope_union"] = union
        elif level == OrgScopeLevel.GENERAL_CONFERENCE:
            gc = selectors.general_conference_by_pk(unit_id) if unit_id else None
            if not gc:
                self.add_error("scope_unit", "Select the general conference.")
            cleaned["scope_general_conference"] = gc
        elif level == OrgScopeLevel.DENOMINATION:
            denom = selectors.denomination_by_pk(unit_id) if unit_id else None
            if not denom and self.manager:
                from church_system.denomination_scope import get_user_denomination

                denom = get_user_denomination(self.manager)
            if not denom and church:
                denom = church.denomination
            cleaned["denomination"] = denom

        # Ensure chosen church is inside unit
        church = cleaned.get("church")
        if church and level == OrgScopeLevel.DISTRICT and cleaned.get("scope_district"):
            if church.district_id != cleaned["scope_district"].pk:
                self.add_error("church", "Home church must be inside the selected district.")
        if church and level == OrgScopeLevel.ZONE and cleaned.get("scope_zone"):
            if church.district.zone_id != cleaned["scope_zone"].pk:
                self.add_error("church", "Home church must be inside the selected zone.")
        if church and level == OrgScopeLevel.CONFERENCE and cleaned.get("scope_conference"):
            if church.district.zone.conference_id != cleaned["scope_conference"].pk:
                self.add_error("church", "Home church must be inside the selected conference.")

        cleaned["scope_level"] = level
        return cleaned


class AcceptInvitationForm(forms.Form):
    first_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=input_attrs()))
    last_name = forms.CharField(max_length=150, widget=forms.TextInput(attrs=input_attrs()))
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs=input_attrs()))
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput(attrs=input_attrs()))

    def __init__(self, *args, invitation=None, **kwargs):
        self.invitation = invitation
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get("password1")
        password2 = cleaned.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")
        if password1:
            user = None
            if self.invitation:
                user = User(
                    username=self.invitation.username,
                    email=self.invitation.email,
                )
            try:
                validate_password(password1, user=user)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class UserManageForm(forms.ModelForm):
    member = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="— Not linked —",
        widget=forms.Select(attrs=select_attrs()),
        help_text="Optional link to a church member record.",
    )
    scope_unit = forms.ChoiceField(
        choices=[],
        required=False,
        widget=forms.Select(attrs=select_attrs(**{"class": "scope-unit-select"})),
        label="Organization unit",
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "phone",
            "role",
            "scope_level",
            "church",
            "member",
            "max_receipt_auto_approve",
        )
        widgets = {
            "first_name": forms.TextInput(attrs=input_attrs()),
            "last_name": forms.TextInput(attrs=input_attrs()),
            "email": forms.EmailInput(attrs=input_attrs()),
            "phone": forms.TextInput(attrs=input_attrs()),
            "role": forms.Select(attrs=select_attrs(**{"class": "scope-role-select"})),
            "scope_level": forms.Select(attrs=select_attrs(**{"class": "scope-level-select"})),
            "church": forms.Select(attrs=select_attrs()),
            "max_receipt_auto_approve": forms.NumberInput(
                attrs=input_attrs(step="0.01", placeholder="Blank = church default")
            ),
        }

    def __init__(self, *args, manager=None, **kwargs):
        self.manager = manager
        self.base_fields["member"].queryset = selectors.empty_members()
        super().__init__(*args, **kwargs)
        if manager:
            self.fields["church"].queryset = get_manageable_churches(manager)
            self.fields["role"].choices = UserRole.assignable_role_choices(manager)
            current_role = getattr(self.instance, "role", None)
            choice_values = {c[0] for c in self.fields["role"].choices}
            if current_role and current_role not in choice_values:
                self.fields["role"].choices = list(self.fields["role"].choices) + [
                    (current_role, UserRole.label(current_role))
                ]

        role = self.data.get("role") if self.is_bound else self.instance.role
        allowed = OrgScopeLevel.allowed_for_role(role or UserRole.MEMBER)
        self.fields["scope_level"].choices = [
            c for c in OrgScopeLevel.CHOICES if c[0] in allowed
        ]

        level = self.data.get("scope_level") if self.is_bound else self.instance.scope_level
        if level not in allowed:
            level = OrgScopeLevel.default_for_role(role or UserRole.MEMBER)

        if manager:
            units = manageable_scope_units(manager, level)
        else:
            units = manageable_scope_units(self.instance, level) if self.instance.pk else []

        self.fields["scope_unit"].choices = [("", "— Select —")] + [
            (str(obj.pk), str(obj)) for obj in units
        ]
        if not self.is_bound:
            initial_unit = (
                self.instance.church_id
                if level == OrgScopeLevel.CHURCH
                else self.instance.scope_district_id
                if level == OrgScopeLevel.DISTRICT
                else self.instance.scope_zone_id
                if level == OrgScopeLevel.ZONE
                else self.instance.scope_conference_id
                if level == OrgScopeLevel.CONFERENCE
                else self.instance.scope_union_id
                if level == OrgScopeLevel.UNION
                else self.instance.denomination_id
                if level == OrgScopeLevel.DENOMINATION
                else None
            )
            if initial_unit:
                self.fields["scope_unit"].initial = str(initial_unit)

        church = None
        if self.is_bound:
            church_id = self.data.get("church") or getattr(self.instance, "church_id", None)
            if church_id:
                church = selectors.church_by_pk(church_id)
        else:
            church = getattr(self.instance, "church", None)

        self.fields["member"].queryset = selectors.linkable_members_for_church(
            church,
            current_member_id=getattr(self.instance, "member_id", None),
        )

        if UserRole.requires_church(role or UserRole.MEMBER):
            self.fields["church"].required = True

    def clean_role(self):
        role = self.cleaned_data["role"]
        current = getattr(self.instance, "role", None)
        if role == current:
            return role
        if self.manager and not UserRole.can_assign_role(
            self.manager.role,
            role,
            actor_is_superuser=self.manager.is_superuser,
        ):
            raise ValidationError("You are not allowed to assign this role.")
        return role

    def clean_member(self):
        member = self.cleaned_data.get("member")
        church = self.cleaned_data.get("church") or getattr(self.instance, "church", None)
        if member and church and member.church_id != church.pk:
            raise ValidationError("Member must belong to the selected church.")
        return member

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role") or self.instance.role
        level = cleaned.get("scope_level") or OrgScopeLevel.default_for_role(role)
        unit_id = cleaned.get("scope_unit")
        church = cleaned.get("church")

        kwargs = {
            "role": role,
            "scope_level": level,
            "church": church,
            "district": None,
            "zone": None,
            "conference": None,
            "union": None,
            "general_conference": None,
            "denomination": cleaned.get("denomination"),
        }
        if level == OrgScopeLevel.DISTRICT and unit_id:
            kwargs["district"] = selectors.district_by_pk(unit_id)
        elif level == OrgScopeLevel.ZONE and unit_id:
            kwargs["zone"] = selectors.zone_by_pk(unit_id)
        elif level == OrgScopeLevel.CONFERENCE and unit_id:
            kwargs["conference"] = selectors.conference_by_pk(unit_id)
        elif level == OrgScopeLevel.UNION and unit_id:
            kwargs["union"] = selectors.union_by_pk(unit_id)
        elif level == OrgScopeLevel.GENERAL_CONFERENCE and unit_id:
            kwargs["general_conference"] = selectors.general_conference_by_pk(unit_id)
        elif level == OrgScopeLevel.DENOMINATION and unit_id:
            kwargs["denomination"] = selectors.denomination_by_pk(unit_id)
        elif level == OrgScopeLevel.CHURCH and church:
            pass

        # Stash for save()
        self._scope_apply_kwargs = kwargs
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        kwargs = getattr(self, "_scope_apply_kwargs", None)
        if kwargs:
            apply_org_scope(user, **kwargs)
        if commit:
            repo.save_user(user)
            self.save_m2m()
        return user
