"""Phase 3 CH-SEC-L3: one active settlement per obligation period key.

Business key: (from_unit_type, from_unit_id, offering_type, period_start, period_end)
for status in DRAFT|POSTED. Historical duplicates are quarantined to VOID (never deleted).
"""

from django.db import migrations, models


def quarantine_duplicate_settlements(apps, schema_editor):
    SettlementBatch = apps.get_model("remittance", "SettlementBatch")

    active = SettlementBatch.objects.filter(status__in=["DRAFT", "POSTED"]).order_by(
        "from_unit_type",
        "from_unit_id",
        "offering_type",
        "period_start",
        "period_end",
        "created_at",
        "id",
    )
    seen = {}
    for batch in active.iterator():
        key = (
            batch.from_unit_type,
            str(batch.from_unit_id),
            batch.offering_type,
            batch.period_start.isoformat(),
            batch.period_end.isoformat(),
        )
        if key not in seen:
            # Prefer keeping POSTED over DRAFT when both exist.
            seen[key] = batch
            continue
        kept = seen[key]
        if kept.status == "DRAFT" and batch.status == "POSTED":
            # Swap: quarantine the draft, keep the posted.
            kept.status = "VOID"
            kept.save(update_fields=["status"])
            seen[key] = batch
            continue
        batch.status = "VOID"
        batch.save(update_fields=["status"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("remittance", "0004_rc1_consistency"),
    ]

    operations = [
        migrations.RunPython(quarantine_duplicate_settlements, noop_reverse),
        migrations.AddConstraint(
            model_name="settlementbatch",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=["DRAFT", "POSTED"]),
                fields=(
                    "from_unit_type",
                    "from_unit_id",
                    "offering_type",
                    "period_start",
                    "period_end",
                ),
                name="uniq_settlement_active_period_obligation",
            ),
        ),
    ]
