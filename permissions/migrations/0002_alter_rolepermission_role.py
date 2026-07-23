# Generated manually to reconcile PythonAnywhere leaf with 0002_rc1_consistency.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("permissions", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="rolepermission",
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
                db_index=True,
                max_length=30,
            ),
        ),
    ]
