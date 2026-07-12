# Generated manually for Union / General Conference hierarchy layer

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organization", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="GeneralConference",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=200, unique=True)),
                ("code", models.CharField(max_length=20, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name_plural": "general conferences",
            },
        ),
        migrations.CreateModel(
            name="Union",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("code", models.CharField(max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "general_conference",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="unions",
                        to="organization.generalconference",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "unions",
                "unique_together": {("name", "general_conference")},
            },
        ),
        migrations.AddField(
            model_name="conference",
            name="union",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="conferences",
                to="organization.union",
            ),
        ),
    ]
