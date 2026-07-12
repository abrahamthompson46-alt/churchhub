from django.db.models.signals import post_save
from django.dispatch import receiver

from organization.models import Church

from ledger.services import seed_ledger


@receiver(post_save, sender=Church)
def seed_ledger_on_church_create(sender, instance, created, **kwargs):
    if created:
        seed_ledger(instance)
