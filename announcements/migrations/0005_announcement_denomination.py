"""Add Announcement.denomination with deterministic church-based backfill.

CH-SEC-002 / INV-ANN-01:

- Stage 1: nullable FK + indexes + visibility/church CheckConstraint.
- Stage 2: backfill denomination ONLY from church → conference.denomination.
- GENERAL rows with no church: leave denomination NULL (quarantine). Do NOT
  guess from creator — that is not authoritative under the security contract.
- denomination remains nullable so quarantined rows can exist; selectors and
  services FAIL CLOSED when denomination is NULL.
"""

import django.db.models.deletion
from django.db import migrations, models


def backfill_announcement_denomination(apps, schema_editor):
    Announcement = apps.get_model("announcements", "Announcement")
    Church = apps.get_model("organization", "Church")

    church_denom_cache = {}
    filled = 0
    quarantined = []

    def church_denomination_id(church_id):
        if church_id in church_denom_cache:
            return church_denom_cache[church_id]
        denom_id = (
            Church.objects.filter(pk=church_id)
            .values_list("district__zone__conference__denomination_id", flat=True)
            .first()
        )
        church_denom_cache[church_id] = denom_id
        return denom_id

    for ann in Announcement.objects.all().iterator():
        if ann.denomination_id:
            continue
        if ann.church_id:
            denom_id = church_denomination_id(ann.church_id)
            if denom_id:
                Announcement.objects.filter(pk=ann.pk).update(denomination_id=denom_id)
                filled += 1
                continue
        # No authoritative source (general without church, or church without denom).
        quarantined.append(ann.pk)

    if quarantined:
        # Explicit report for operators; do not silently invent a tenant.
        print(
            "CH-SEC-002 backfill quarantined announcement PKs "
            f"(denomination left NULL, fail-closed): {quarantined}"
        )
    print(
        f"CH-SEC-002 backfill complete: filled={filled}, quarantined={len(quarantined)}"
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("announcements", "0004_enterprise_comms_phase12"),
        ("sitecontrol", "0005_denomination_saas"),
        ("organization", "0003_conference_denomination"),
    ]

    operations = [
        migrations.AddField(
            model_name="announcement",
            name="denomination",
            field=models.ForeignKey(
                blank=True,
                help_text=(
                    "Authoritative tenant owner. Required for live church and "
                    "general announcements."
                ),
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="announcements",
                to="sitecontrol.denomination",
            ),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(
                fields=["denomination", "visibility", "status", "is_archived"],
                name="ann_denom_vis_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="announcement",
            index=models.Index(
                fields=["denomination", "is_approved", "publish_at"],
                name="ann_denom_approved_pub_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="announcement",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(visibility="general", church__isnull=True)
                    | models.Q(visibility="church", church__isnull=False)
                ),
                name="ann_visibility_church_consistency",
            ),
        ),
        migrations.RunPython(backfill_announcement_denomination, noop_reverse),
    ]
