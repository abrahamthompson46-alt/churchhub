from django.db import migrations


NEW_CODENAMES = (
    "view_enterprise_controls",
    "view_enterprise_audit",
    "export_enterprise_audit",
)


def seed_enterprise_audit_permissions(apps, schema_editor):
    from permissions.registry import PERMISSION_REGISTRY
    from permissions.roles import UserRole

    Permission = apps.get_model("permissions", "Permission")
    RolePermission = apps.get_model("permissions", "RolePermission")
    sort = 900
    for codename in NEW_CODENAMES:
        meta = PERMISSION_REGISTRY[codename]
        sort += 1
        perm, _ = Permission.objects.update_or_create(
            codename=codename,
            defaults={
                "name": meta["name"],
                "category": meta.get("category", "Controls"),
                "description": meta.get("description", ""),
                "sort_order": sort,
                "is_active": True,
            },
        )
        defaults = set(meta.get("default_roles", set()))
        for role, _label in UserRole.CHOICES:
            RolePermission.objects.update_or_create(
                role=role,
                permission=perm,
                defaults={"granted": role in defaults},
            )


class Migration(migrations.Migration):

    dependencies = [
        ("permissions", "0004_district_treasury_role"),
    ]

    operations = [
        migrations.RunPython(seed_enterprise_audit_permissions, migrations.RunPython.noop),
    ]
