from django.apps import AppConfig


class PayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payroll"
    verbose_name = "Payroll"

    def ready(self):
        from django.db.models.signals import post_save

        from organization.models import Church
        from payroll.services import ensure_payroll_defaults_for_church

        def _seed_payroll(sender, instance, created, **kwargs):
            if created:
                ensure_payroll_defaults_for_church(instance)

        post_save.connect(_seed_payroll, sender=Church, dispatch_uid="payroll_seed_defaults")
