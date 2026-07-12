"""Seed GRA-aligned platform asset category templates."""

from django.db import migrations


def seed_templates(apps, schema_editor):
    from assets.services import seed_platform_category_templates

    seed_platform_category_templates()


class Migration(migrations.Migration):

    dependencies = [
        ("assets", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_templates, migrations.RunPython.noop),
    ]
