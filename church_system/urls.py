# church_system/urls.py
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

from church_system.auth import ChurchHubLoginView
from church_system.views import health_check
from sitecontrol.views_registration import church_apply, church_apply_success

urlpatterns = [
    path("health/", health_check, name="health_check"),
    path("apply/", church_apply, name="church_apply"),
    path("apply/success/", church_apply_success, name="church_apply_success"),
    path("", RedirectView.as_view(pattern_name="login", permanent=False)),
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
    path("accounts/", include("django.contrib.auth.urls")),
    path("announcements/", include(("announcements.urls", "announcements"), namespace="announcements")),
    path("reports/", include(("reports.urls", "reports"), namespace="reports")),
    path("meetings/", include(("meetings.urls", "meetings"), namespace="meetings")),
    path("budgets/", include(("budgets.urls", "budgets"), namespace="budgets")),
    path("giving/", include(("giving.urls", "giving"), namespace="giving")),
    path("ledger/", include(("ledger.urls", "ledger"), namespace="ledger")),
    path("remittance/", include(("remittance.urls", "remittance"), namespace="remittance")),
    path("payroll/", include(("payroll.urls", "payroll"), namespace="payroll")),
    path("assets/", include(("assets.urls", "assets"), namespace="assets")),
    path("platform/", include(("sitecontrol.urls", "sitecontrol"), namespace="sitecontrol")),
]

handler403 = "church_system.views.permission_denied"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += staticfiles_urlpatterns()
