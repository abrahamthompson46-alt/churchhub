from django.db import migrations, models


ROLE_CHOICES = [
    ("SUPER_ADMIN", "Super Admin"),
    ("GENERAL_OVERSEER", "General Overseer"),
    ("UNION_ADMIN", "Union Administrator"),
    ("CONFERENCE_ADMIN", "Conference Administrator"),
    ("ZONE_DIRECTOR", "Zone Director"),
    ("DISTRICT_PASTOR", "District Administrator"),
    ("DISTRICT_TREASURY", "District Treasurer"),
    ("LOCAL_PASTOR", "Local Pastor"),
    ("SECRETARY", "Secretary"),
    ("TREASURY", "Treasury"),
    ("BOARD_MEMBER", "Board Member"),
    ("MEMBER", "Member"),
]


def sync_district_finance_defaults(apps, schema_editor):
    from permissions.registry import PERMISSION_REGISTRY
    from permissions.roles import UserRole

    Permission = apps.get_model("permissions", "Permission")
    RolePermission = apps.get_model("permissions", "RolePermission")
    roles = (UserRole.DISTRICT_PASTOR, UserRole.DISTRICT_TREASURY)
    for codename, meta in PERMISSION_REGISTRY.items():
        perm = Permission.objects.filter(codename=codename).first()
        if not perm:
            continue
        defaults = set(meta.get("default_roles", set()))
        for role in roles:
            RolePermission.objects.update_or_create(
                role=role,
                permission=perm,
                defaults={"granted": role in defaults},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("permissions", "0003_merge_rc1_and_alter_role"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rolepermission",
            name="role",
            field=models.CharField(choices=ROLE_CHOICES, db_index=True, max_length=30),
        ),
        migrations.RunPython(sync_district_finance_defaults, migrations.RunPython.noop),
    ]
