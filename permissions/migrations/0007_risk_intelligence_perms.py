from django.db import migrations


NEW_CODENAMES = (
    "view_risk_alerts",
    "review_risk_alerts",
    "manage_risk_policy",
)


def seed_risk_permissions(apps, schema_editor):
    from permissions.registry import PERMISSION_REGISTRY
    from permissions.roles import UserRole

    Permission = apps.get_model("permissions", "Permission")
    RolePermission = apps.get_model("permissions", "RolePermission")
    sort = 920
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
        ("permissions", "0006_maker_checker_perms"),
    ]

    operations = [
        migrations.RunPython(seed_risk_permissions, migrations.RunPython.noop),
    ]
