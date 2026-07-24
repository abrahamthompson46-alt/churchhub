"""Tests for shared upload validation."""

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from church_system.uploads import (
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    validate_upload,
)


class UploadValidationTests(SimpleTestCase):
    def test_accepts_jpeg_image(self):
        f = SimpleUploadedFile("photo.jpg", b"fake-jpeg", content_type="image/jpeg")
        validate_upload(f, kind="image")

    def test_rejects_oversized_image(self):
        f = SimpleUploadedFile(
            "big.jpg",
            b"x" * (MAX_IMAGE_BYTES + 1),
            content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError) as ctx:
            validate_upload(f, kind="image")
        self.assertIn("or smaller", str(ctx.exception))

    def test_rejects_blocked_extension(self):
        f = SimpleUploadedFile("payload.exe", b"MZ", content_type="application/octet-stream")
        with self.assertRaises(ValidationError):
            validate_upload(f, kind="document")

    def test_rejects_svg_even_as_image_claim(self):
        f = SimpleUploadedFile(
            "icon.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'></svg>",
            content_type="image/svg+xml",
        )
        with self.assertRaises(ValidationError):
            validate_upload(f, kind="image")

    def test_accepts_pdf_document(self):
        f = SimpleUploadedFile("agenda.pdf", b"%PDF-1.4", content_type="application/pdf")
        validate_upload(f, kind="document")

    def test_rejects_oversized_document(self):
        f = SimpleUploadedFile(
            "huge.pdf",
            b"x" * (MAX_DOCUMENT_BYTES + 1),
            content_type="application/pdf",
        )
        with self.assertRaises(ValidationError):
            validate_upload(f, kind="document")

    def test_rejects_disallowed_document_extension(self):
        f = SimpleUploadedFile("notes.rtf", b"rtf", content_type="application/rtf")
        with self.assertRaises(ValidationError):
            validate_upload(f, kind="document")

    @override_settings()
    def test_branding_uses_stricter_size(self):
        from church_system.uploads import MAX_BRANDING_BYTES

        f = SimpleUploadedFile(
            "logo.png",
            b"x" * (MAX_BRANDING_BYTES + 1),
            content_type="image/png",
        )
        with self.assertRaises(ValidationError):
            validate_upload(f, kind="branding")
