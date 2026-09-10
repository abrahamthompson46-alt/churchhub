from django import forms

from intelligence.models import RiskPolicy


class RiskPolicyForm(forms.ModelForm):
    class Meta:
        model = RiskPolicy
        fields = [
            "is_active",
            "block_auto_approve_on_high",
            "large_absolute",
            "large_multiplier",
            "expense_absolute",
            "near_duplicate_minutes",
            "near_duplicate_min_amount",
            "repeat_count",
            "velocity_count",
            "step_change_ratio",
            "bunching_share",
            "baseline_z",
        ]
        help_texts = {
            "block_auto_approve_on_high": (
                "Stored only. Receipt auto-approve always follows TreasuryApprovalPolicy; "
                "this flag never blocks posting."
            ),
        }


class AlertNoteForm(forms.Form):
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )
