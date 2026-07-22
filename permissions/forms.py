from django import forms

from church_system.widgets import input_attrs, select_attrs, textarea_attrs

from permissions.models import PermissionOverride
from permissions.roles import UserRole


class PermissionMatrixForm(forms.Form):
    """Bulk matrix update — fields generated dynamically in the view."""

    def __init__(self, *args, permissions=None, roles=None, cells=None, **kwargs):
        super().__init__(*args, **kwargs)
        permissions = permissions or []
        roles = roles or UserRole.CHOICES
        cells = cells or {}
        for role, _label in roles:
            for perm in permissions:
                key = f"cell_{role}_{perm.id}"
                initial = cells.get((role, perm.id), False)
                self.fields[key] = forms.BooleanField(
                    required=False,
                    initial=initial,
                    label="",
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input matrix-check"}),
                )


class PermissionOverrideForm(forms.ModelForm):
    class Meta:
        model = PermissionOverride
        fields = ("user", "permission", "granted", "reason", "expires_at", "is_active")
        widgets = {
            "user": forms.Select(attrs=select_attrs()),
            "permission": forms.Select(attrs=select_attrs()),
            "granted": forms.Select(
                choices=[(True, "Grant"), (False, "Deny")],
                attrs=select_attrs(),
            ),
            "reason": forms.Textarea(attrs=textarea_attrs(rows=3)),
            "expires_at": forms.DateTimeInput(
                attrs={**input_attrs(), "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, manager=None, **kwargs):
        super().__init__(*args, **kwargs)
        if manager:
            from permissions.scoping import get_manageable_users
            self.fields["user"].queryset = get_manageable_users(manager).filter(is_active=True)
        from permissions import selectors

        self.fields["permission"].queryset = selectors.active_permissions_ordered()

    def clean_granted(self):
        value = self.cleaned_data.get("granted")
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "grant")
        return bool(value)
