from django.db import migrations


def clear_birthday_photo_consent(apps, schema_editor):
    Member = apps.get_model("members", "Member")
    Member.objects.filter(allow_birthday_photo=True).update(allow_birthday_photo=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("members", "0011_birthday_photo_consent_default"),
    ]

    operations = [
        migrations.RunPython(clear_birthday_photo_consent, noop),
    ]
