# church_system/urls.py
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from church_system.auth import ChurchHubLoginView
from church_system.media_views import protected_media
from church_system.views import health_check, live_check, metrics_check, public_home, ready_check
from sitecontrol.views_registration import (
    church_apply,
    church_apply_success,
    subscription_expired,
    subscription_subscribe,
)
from sitecontrol.views_marketing import marketing_inquiry, marketing_inquiry_success

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("health/live/", live_check, name="health_live"),
    path("health/ready/", ready_check, name="health_ready"),
    path("metrics/", metrics_check, name="metrics"),
    path("apply/", church_apply, name="church_apply"),
    path("apply/success/", church_apply_success, name="church_apply_success"),
    path(
        "accounts/subscription-expired/",
        subscription_expired,
        name="subscription_expired",
    ),
    path(
        "accounts/subscription-subscribe/",
        subscription_subscribe,
        name="subscription_subscribe",
    ),
    path("contact/", marketing_inquiry, name="marketing_inquiry"),
    path(
        "contact/success/",
        marketing_inquiry_success,
        name="marketing_inquiry_success",
    ),
    path("", public_home, name="public_home"),
    path(
        "accounts/login/",
        ChurchHubLoginView.as_view(),
        name="login",
    ),
    path("admin/", admin.site.urls),
    path("dashboard/", include(("dashboard.urls", "dashboard"), namespace="dashboard")),
    path("members/", include(("members.urls", "members"), namespace="members")),
    path("organization/", include(("organization.urls", "organization"), namespace="organization")),
    path("transactions/", include(("transactions.urls", "transactions"), namespace="transactions")),
    path("accounts/", include(("accounts.urls", "accounts"), namespace="accounts")),
    path("permissions/", include(("permissions.urls", "permissions"), namespace="permissions")),
    path("accounts/", include("church_system.auth_urls")),
    path("announcements/", include(("announcements.urls", "announcements"), namespace="announcements")),
    path("reports/", include(("reports.urls", "reports"), namespace="reports")),
    path("meetings/", include(("meetings.urls", "meetings"), namespace="meetings")),
    path("budgets/", include(("budgets.urls", "budgets"), namespace="budgets")),
    path("giving/", include(("giving.urls", "giving"), namespace="giving")),
    path("contributions/", include(("contributions.urls", "contributions"), namespace="contributions")),
    path("ledger/", include(("ledger.urls", "ledger"), namespace="ledger")),
    path("remittance/", include(("remittance.urls", "remittance"), namespace="remittance")),
    path("payroll/", include(("payroll.urls", "payroll"), namespace="payroll")),
    path("assets/", include(("assets.urls", "assets"), namespace="assets")),
    path("portal/", include(("portal.urls", "portal"), namespace="portal")),
    path("platform/", include(("sitecontrol.urls", "sitecontrol"), namespace="sitecontrol")),
    # Always auth-gate private media (DEBUG and production). Public branding is
    # allowlisted in media_access / served directly by Nginx in production.
    path("media/<path:path>", protected_media, name="protected_media"),
]

handler403 = "church_system.views.permission_denied"

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
