from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

from .services import get_client_ip, log_activity, sync_role_groups


@receiver(user_logged_in)
def on_user_login(sender, request, user, **kwargs):
    sync_role_groups(user)
    log_activity(user, "LOGIN", ip_address=get_client_ip(request))


@receiver(user_logged_out)
def on_user_logout(sender, request, user, **kwargs):
    from accounts.mfa import clear_mfa_session

    if request is not None:
        clear_mfa_session(request)
    if user:
        log_activity(user, "LOGOUT", ip_address=get_client_ip(request))
