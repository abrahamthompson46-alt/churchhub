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


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_institution_branding_activity_action"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(choices=ROLE_CHOICES, default="MEMBER", max_length=30),
        ),
        migrations.AlterField(
            model_name="userinvitation",
            name="role",
            field=models.CharField(choices=ROLE_CHOICES, max_length=30),
        ),
    ]
