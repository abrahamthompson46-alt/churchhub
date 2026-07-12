"""Shared compact form base classes for ChurchHub."""

from django import forms

from church_system.widgets import checkbox_attrs, input_attrs, select_attrs, textarea_attrs


class CompactFormMixin:
    """Apply compact Bootstrap widgets to any form that does not set attrs explicitly."""

    compact_text_widget = forms.TextInput
    compact_select_widget = forms.Select
    compact_textarea_widget = forms.Textarea
    compact_number_widget = forms.NumberInput
    compact_email_widget = forms.EmailInput
    compact_date_widget = forms.DateInput
    compact_checkbox_widget = forms.CheckboxInput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault("class", checkbox_attrs()["class"])
            elif isinstance(widget, forms.CheckboxSelectMultiple):
                widget.attrs.setdefault("class", "form-check-input")
            elif isinstance(widget, forms.RadioSelect):
                continue
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault("class", select_attrs()["class"])
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("class", textarea_attrs()["class"])
                widget.attrs.setdefault("rows", textarea_attrs()["rows"])
            elif isinstance(widget, forms.DateInput):
                widget.attrs.setdefault("class", input_attrs()["class"])
                widget.attrs.setdefault("type", "date")
            elif isinstance(widget, forms.NumberInput):
                widget.attrs.setdefault("class", input_attrs()["class"])
            elif isinstance(widget, forms.EmailInput):
                widget.attrs.setdefault("class", input_attrs()["class"])
            elif isinstance(widget, forms.FileInput):
                widget.attrs.setdefault("class", input_attrs()["class"])
            elif isinstance(widget, forms.TextInput):
                widget.attrs.setdefault("class", input_attrs()["class"])


class ChurchHubForm(CompactFormMixin, forms.Form):
    """Compact non-model form."""


class ChurchHubModelForm(CompactFormMixin, forms.ModelForm):
    """Compact model form."""
