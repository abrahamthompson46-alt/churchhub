from django.apps import AppConfig


class PermissionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "permissions"
    verbose_name = "Permissions & Roles"

    def ready(self):
        from django.db.models.signals import post_migrate

        from permissions.services import ensure_permission_matrix

        def seed_matrix(sender, **kwargs):
            if sender.name == "permissions":
                ensure_permission_matrix()

        post_migrate.connect(seed_matrix, dispatch_uid="permissions_seed_matrix")
