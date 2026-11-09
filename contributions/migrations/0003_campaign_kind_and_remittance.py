import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contributions", "0002_contributioncampaign_default_member_target_and_more"),
        ("transactions", "0023_transaction_reversed_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contributioncampaign",
            name="kind",
            field=models.CharField(
                choices=[
                    ("GENERAL", "Church campaign"),
                    ("DISTRICT_FUNERAL", "District funeral collection"),
                ],
                db_index=True,
                default="GENERAL",
                help_text="District funeral collections are held separately from welfare and remitted to district.",
                max_length=24,
            ),
        ),
        migrations.CreateModel(
            name="CampaignRemittance",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "campaign",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="remittances",
                        to="contributions.contributioncampaign",
                    ),
                ),
                (
                    "remitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="campaign_remittances_recorded",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="campaign_remittances",
                        to="transactions.transaction",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="campaignremittance",
            index=models.Index(
                fields=["campaign", "created_at"], name="contributio_campaig_remit_idx"
            ),
        ),
    ]
