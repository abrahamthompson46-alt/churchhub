from django.db.models.signals import post_save
from django.dispatch import receiver
from organization.models import Church
from .services import create_default_accounts, create_default_offering_categories


@receiver(post_save, sender=Church)
def auto_create_accounts(sender, instance, created, **kwargs):
    if created and not instance.financials_provisioned:
        create_default_accounts(instance)
        create_default_offering_categories(instance)
