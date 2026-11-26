"""Convert legacy naive Meeting.scheduled_at values to timezone-aware datetimes."""

from django.db import migrations
from django.utils import timezone


def _aware_scheduled_times(apps, schema_editor):
    Meeting = apps.get_model("meetings", "Meeting")
    tz = timezone.get_current_timezone()
    for meeting in Meeting.objects.all().iterator():
        when = meeting.scheduled_at
        if when is None or timezone.is_aware(when):
            continue
        meeting.scheduled_at = timezone.make_aware(when, tz)
        meeting.save(update_fields=["scheduled_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("meetings", "0003_meeting_zoom_portal"),
    ]

    operations = [
        migrations.RunPython(_aware_scheduled_times, migrations.RunPython.noop),
    ]