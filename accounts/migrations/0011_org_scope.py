# Generated manually for organization subtree scoping

import django.db.models.deletion
from django.db import migrations, models


def backfill_org_scope(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Invitation = apps.get_model("accounts", "UserInvitation")

    role_level = {
        "SUPER_ADMIN": "DENOMINATION",
        "GENERAL_OVERSEER": "DENOMINATION",
        "UNION_ADMIN": "UNION",
        "CONFERENCE_ADMIN": "CONFERENCE",
        "ZONE_DIRECTOR": "ZONE",
        "DISTRICT_PASTOR": "DISTRICT",
        "LOCAL_PASTOR": "CHURCH",
        "SECRETARY": "CHURCH",
        "TREASURY": "CHURCH",
        "BOARD_MEMBER": "CHURCH",
        "MEMBER": "CHURCH",
    }

    for user in User.objects.select_related(
        "church__district__zone__conference"
    ).iterator():
        if user.is_platform_user:
            user.scope_level = "DENOMINATION"
            user.save(update_fields=["scope_level"])
            continue

        level = role_level.get(user.role, "CHURCH")
        user.scope_level = level
        update = ["scope_level"]

        church = user.church
        if level == "DISTRICT" and church_id_safe(church):
            user.scope_district_id = church.district_id
            update.append("scope_district")
            if not user.denomination_id and church.district_id:
                conf = getattr(getattr(church.district, "zone", None), "conference", None)
                if conf and conf.denomination_id:
                    user.denomination_id = conf.denomination_id
                    update.append("denomination")
        elif level == "DENOMINATION":
            if not user.denomination_id and church_id_safe(church):
                conf = church.district.zone.conference
                if conf.denomination_id:
                    user.denomination_id = conf.denomination_id
                    update.append("denomination")
        user.save(update_fields=update)

    for inv in Invitation.objects.select_related("church__district").iterator():
        level = role_level.get(inv.role, "CHURCH")
        inv.scope_level = level
        update = ["scope_level"]
        if level == "DISTRICT" and inv.church_id:
            inv.scope_district_id = inv.church.district_id
            update.append("scope_district")
        inv.save(update_fields=update)


def church_id_safe(church):
    return bool(church and getattr(church, "district_id", None))


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_accounts_enterprise"),
        ("organization", "0005_backfill_financials_provisioned"),
        ("sitecontrol", "0010_login_highlights"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="scope_level",
            field=models.CharField(
                choices=[
                    ("CHURCH", "Local Church"),
                    ("DISTRICT", "District"),
                    ("ZONE", "Zone"),
                    ("CONFERENCE", "Conference"),
                    ("UNION", "Union"),
                    ("GENERAL_CONFERENCE", "General Conference"),
                    ("DENOMINATION", "Denomination"),
                ],
                db_index=True,
                default="CHURCH",
                help_text="Organization tree level this user may administer (subtree access).",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="scope_district",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scoped_users",
                to="organization.district",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="scope_zone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scoped_users",
                to="organization.zone",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="scope_conference",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scoped_users",
                to="organization.conference",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="scope_union",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scoped_users",
                to="organization.union",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="scope_general_conference",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="scoped_users",
                to="organization.generalconference",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="church",
            field=models.ForeignKey(
                blank=True,
                help_text="Home church. Required for local roles; optional anchor for hierarchy admins.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="users",
                to="organization.church",
            ),
        ),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPER_ADMIN", "Super Admin"),
                    ("GENERAL_OVERSEER", "General Overseer"),
                    ("UNION_ADMIN", "Union Administrator"),
                    ("CONFERENCE_ADMIN", "Conference Administrator"),
                    ("ZONE_DIRECTOR", "Zone Director"),
                    ("DISTRICT_PASTOR", "District Administrator"),
                    ("LOCAL_PASTOR", "Local Pastor"),
                    ("SECRETARY", "Secretary"),
                    ("TREASURY", "Treasury"),
                    ("BOARD_MEMBER", "Board Member"),
                    ("MEMBER", "Member"),
                ],
                default="MEMBER",
                max_length=30,
            ),
        ),
        migrations.AddIndex(
            model_name="user",
            index=models.Index(fields=["scope_level", "is_active"], name="accounts_us_scope_l_7c2e1a_idx"),
        ),
        # Invitation scope fields
        migrations.AddField(
            model_name="userinvitation",
            name="scope_level",
            field=models.CharField(
                choices=[
                    ("CHURCH", "Local Church"),
                    ("DISTRICT", "District"),
                    ("ZONE", "Zone"),
                    ("CONFERENCE", "Conference"),
                    ("UNION", "Union"),
                    ("GENERAL_CONFERENCE", "General Conference"),
                    ("DENOMINATION", "Denomination"),
                ],
                default="CHURCH",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="scope_district",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.district",
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="scope_zone",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.zone",
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="scope_conference",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.conference",
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="scope_union",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.union",
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="scope_general_conference",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.generalconference",
            ),
        ),
        migrations.AddField(
            model_name="userinvitation",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.AlterField(
            model_name="userinvitation",
            name="church",
            field=models.ForeignKey(
                blank=True,
                help_text="Home church (required for local roles).",
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="invitations",
                to="organization.church",
            ),
        ),
        migrations.AlterField(
            model_name="userinvitation",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPER_ADMIN", "Super Admin"),
                    ("GENERAL_OVERSEER", "General Overseer"),
                    ("UNION_ADMIN", "Union Administrator"),
                    ("CONFERENCE_ADMIN", "Conference Administrator"),
                    ("ZONE_DIRECTOR", "Zone Director"),
                    ("DISTRICT_PASTOR", "District Administrator"),
                    ("LOCAL_PASTOR", "Local Pastor"),
                    ("SECRETARY", "Secretary"),
                    ("TREASURY", "Treasury"),
                    ("BOARD_MEMBER", "Board Member"),
                    ("MEMBER", "Member"),
                ],
                max_length=30,
            ),
        ),
        migrations.RunPython(backfill_org_scope, noop_reverse),
    ]
