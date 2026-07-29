"""Forms for platform data import."""

from django import forms

from church_system.uploads import document_upload_validator
from organization.models import Church


class PlatformDataImportForm(forms.Form):
    church = forms.ModelChoiceField(
        queryset=Church.objects.none(),
        label="Church",
        help_text="All rows will be imported into this church only.",
    )
    file = forms.FileField(
        label="Excel file (.xlsx)",
        validators=[document_upload_validator],
        help_text="Use the template download on this page. First row must be column headers.",
    )
    commit = forms.BooleanField(
        required=False,
        initial=False,
        label="Import now (skip preview)",
        help_text="Leave unchecked to validate and preview first; check only after a clean preview.",
    )

    def __init__(self, *args, church_queryset=None, **kwargs):
        super().__init__(*args, **kwargs)
        if church_queryset is not None:
            self.fields["church"].queryset = church_queryset
