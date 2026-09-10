from django import forms
from django.contrib.auth import get_user_model

from approvals.models import ApprovalPolicy

User = get_user_model()


class ApprovalPolicyForm(forms.ModelForm):
    class Meta:
        model = ApprovalPolicy
        fields = ["required_steps"]
        widgets = {
            "required_steps": forms.NumberInput(
                attrs={"min": 1, "max": 5, "class": "form-control form-control-sm"}
            ),
        }


class DelegationForm(forms.Form):
    grantee = forms.ModelChoiceField(queryset=User.objects.none())
    valid_from = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"})
    )
    valid_until = forms.DateField(
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"})
    )
    max_amount = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=14)

    def __init__(self, *args, queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["grantee"].queryset = queryset if queryset is not None else User.objects.none()
        self.fields["grantee"].widget.attrs["class"] = "form-select form-select-sm"
        self.fields["max_amount"].widget.attrs["class"] = "form-control form-control-sm"


class CaseNoteForm(forms.Form):
    note = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
    )
