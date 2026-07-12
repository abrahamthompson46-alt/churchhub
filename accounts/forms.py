from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

from church_system.widgets import input_attrs, select_attrs
from organization.models import Church
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
    role = forms.ChoiceField(choices=[], widget=forms.Select(attrs=select_attrs()))
    church = forms.ModelChoiceField(
        queryset=Church.objects.none(),
        widget=forms.Select(attrs=select_attrs()),
    )

    def __init__(self, *args, manager=None, **kwargs):
        self.manager = manager
        super().__init__(*args, **kwargs)
        if manager:
            self.fields["role"].choices = UserRole.assignable_role_choices(manager)
            churches = get_manageable_churches(manager)
            self.fields["church"].queryset = churches
            if churches.count() == 1:
                self.fields["church"].initial = churches.first().pk

    def clean_role(self):
        role = self.cleaned_data["role"]
        if self.manager and not UserRole.can_assign_role(
            self.manager.role,
            role,
            actor_is_superuser=self.manager.is_superuser,
        ):
            raise ValidationError("You are not allowed to assign this role.")
        return role


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

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "role", "church", "member")
        widgets = {
            "first_name": forms.TextInput(attrs=input_attrs()),
            "last_name": forms.TextInput(attrs=input_attrs()),
            "email": forms.EmailInput(attrs=input_attrs()),
            "phone": forms.TextInput(attrs=input_attrs()),
            "role": forms.Select(attrs=select_attrs()),
            "church": forms.Select(attrs=select_attrs()),
        }

    def __init__(self, *args, manager=None, **kwargs):
        self.manager = manager
        from members.models import Member

        # Avoid evaluating Member at import/class-body time.
        self.base_fields["member"].queryset = Member.objects.none()
        super().__init__(*args, **kwargs)
        if manager:
            self.fields["church"].queryset = get_manageable_churches(manager)
            self.fields["role"].choices = UserRole.assignable_role_choices(manager)
            # Keep current role visible even if manager could not newly assign it
            current_role = getattr(self.instance, "role", None)
            choice_values = {c[0] for c in self.fields["role"].choices}
            if current_role and current_role not in choice_values:
                label = UserRole.label(current_role)
                self.fields["role"].choices = list(self.fields["role"].choices) + [
                    (current_role, label)
                ]

        church = None
        if self.is_bound:
            church_id = self.data.get("church") or getattr(self.instance, "church_id", None)
            if church_id:
                church = Church.objects.filter(pk=church_id).first()
        else:
            church = getattr(self.instance, "church", None)

        member_qs = Member.objects.none()
        if church:
            member_qs = Member.objects.filter(church=church).filter(
                Q(user_account__isnull=True) | Q(pk=getattr(self.instance, "member_id", None))
            ).order_by("last_name", "first_name")
        self.fields["member"].queryset = member_qs

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
