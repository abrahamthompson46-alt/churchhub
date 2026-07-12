"""Tests for flash message helpers and template tags."""

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from church_system.flash import (
    TITLE_SEP,
    flash_denied,
    flash_success,
    flash_validation_errors,
)
from church_system.templatetags.churchhub_tags import message_body, message_title

User = get_user_model()


class FlashHelperTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user(username="flash_user", password="pass12345")
        self.request = self.factory.get("/")
        self.request.user = self.user
        self.request.session = {}
        setattr(self.request, "_messages", FallbackStorage(self.request))

    def test_flash_success_structures_title_and_body(self):
        flash_success(self.request, "Profile saved.", title="Profile updated")
        stored = list(get_messages(self.request))[0]
        self.assertIn(TITLE_SEP, str(stored))
        self.assertIn("Profile updated", str(stored))
        self.assertIn("Profile saved.", str(stored))

    def test_flash_denied_uses_warning_tag(self):
        flash_denied(self.request)
        stored = list(get_messages(self.request))[0]
        self.assertEqual(stored.level_tag, "warning")

    def test_flash_validation_errors_surfaces_field_errors(self):
        from django import forms

        class SampleForm(forms.Form):
            name = forms.CharField(required=True)

        form = SampleForm({})
        self.assertFalse(form.is_valid())
        flash_validation_errors(self.request, form)
        stored = list(get_messages(self.request))[0]
        self.assertEqual(stored.level_tag, "error")
        self.assertIn("Name", str(stored))


class FlashTemplateTagTests(TestCase):
    def test_message_title_and_body_from_structured_flash(self):
        text = f"Saved{TITLE_SEP}Your changes were stored."
        self.assertEqual(message_title(text, "success"), "Saved")
        self.assertEqual(message_body(text), "Your changes were stored.")

    def test_plain_message_uses_tag_label_as_title(self):
        self.assertEqual(message_title("Budget line added.", "success"), "Success")
        self.assertEqual(message_body("Budget line added."), "Budget line added.")
