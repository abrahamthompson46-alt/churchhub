# Data migration: assign platform_role for existing platform operators.

from django.db import migrations


def assign_platform_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    for user in User.objects.filter(is_platform_user=True):
        if user.is_superuser:
            user.platform_role = "OWNER"
        elif not user.platform_role:
            user.platform_role = "SUPPORT"
        user.save(update_fields=["platform_role"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_control_tower_enterprise"),
    ]

    operations = [
        migrations.RunPython(assign_platform_roles, migrations.RunPython.noop),
    ]
