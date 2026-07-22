import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "church_system.settings")

app = Celery("churchhub")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    """Connectivity probe for worker monitoring."""
    return {"request_id": self.request.id, "status": "ok"}
