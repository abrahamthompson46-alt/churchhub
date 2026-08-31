"""Platform sidebar navigation with capability filtering."""

from sitecontrol.rbac import CAP_VIEW, NAV_ITEM_CAPABILITIES, operator_has_capability

PLATFORM_NAV = [
    {
        "id": "overview",
        "label": "Overview",
        "icon": "bi-speedometer2",
        "items": [
            {"label": "Control Room", "url_name": "sitecontrol:dashboard", "icon": "bi-grid-1x2-fill"},
            {"label": "Setup Guide", "url_name": "sitecontrol:setup", "icon": "bi-list-check"},
            {"label": "Tenant Health", "url_name": "sitecontrol:health", "icon": "bi-heart-pulse"},
            {"label": "Operations", "url_name": "sitecontrol:ops_health", "icon": "bi-activity"},
            {"label": "Audit Log", "url_name": "sitecontrol:audit_log", "icon": "bi-journal-check"},
        ],
    },
    {
        "id": "tenants",
        "label": "Tenants",
        "icon": "bi-buildings",
        "items": [
            {"label": "Denominations", "url_name": "sitecontrol:denomination_list", "icon": "bi-layers"},
            {"label": "Billing Roll-ups", "url_name": "sitecontrol:denomination_billing_rollups", "icon": "bi-cash-stack"},
            {"label": "Applications", "url_name": "sitecontrol:application_list", "icon": "bi-inbox"},
            {"label": "Activation requests", "url_name": "sitecontrol:activation_request_list", "icon": "bi-patch-check"},
            {"label": "Provision Tenant", "url_name": "sitecontrol:tenant_provision", "icon": "bi-magic"},
            {"label": "All Churches", "url_name": "sitecontrol:tenant_list", "icon": "bi-building"},
            {"label": "Subscriptions", "url_name": "sitecontrol:subscription_list", "icon": "bi-credit-card"},
            {"label": "Plans", "url_name": "sitecontrol:plan_list", "icon": "bi-box-seam"},
            {"label": "Payment Methods", "url_name": "sitecontrol:payment_method_list", "icon": "bi-wallet2"},
            {"label": "Organization Tree", "url_name": "sitecontrol:hierarchy", "icon": "bi-diagram-3"},
            {"label": "Data Import", "url_name": "sitecontrol:import_hub", "icon": "bi-file-earmark-spreadsheet"},
        ],
    },
    {
        "id": "operators",
        "label": "Access",
        "icon": "bi-shield-lock",
        "items": [
            {"label": "Registration Controls", "url_name": "sitecontrol:registration_settings", "icon": "bi-door-open"},
            {"label": "Platform Operators", "url_name": "sitecontrol:operator_list", "icon": "bi-person-badge"},
            {"label": "Announcements", "url_name": "sitecontrol:announcement_list", "icon": "bi-megaphone"},
        ],
    },
    {
        "id": "growth",
        "label": "Growth",
        "icon": "bi-graph-up-arrow",
        "items": [
            {
                "label": "Marketing Hub",
                "url_name": "sitecontrol:marketing_hub",
                "icon": "bi-megaphone-fill",
            },
        ],
    },
    {
        "id": "config",
        "label": "Configuration",
        "icon": "bi-sliders2-vertical",
        "items": [
            {"label": "General", "url_name": "sitecontrol:settings", "icon": "bi-gear"},
            {"label": "Branding", "url_name": "sitecontrol:branding", "icon": "bi-palette"},
            {"label": "Email", "url_name": "sitecontrol:email_settings", "icon": "bi-envelope-at"},
            {"label": "Security", "url_name": "sitecontrol:security_settings", "icon": "bi-lock"},
            {"label": "Feature Registry", "url_name": "sitecontrol:features", "icon": "bi-toggles"},
            {"label": "Member Dropdowns", "url_name": "sitecontrol:member_lookup_list", "icon": "bi-list-ul"},
            {"label": "Billing", "url_name": "sitecontrol:billing_settings", "icon": "bi-currency-exchange"},
        ],
    },
]


def get_platform_navigation(user=None):
    if user is None:
        return PLATFORM_NAV
    filtered = []
    for section in PLATFORM_NAV:
        items = []
        for item in section["items"]:
            cap = NAV_ITEM_CAPABILITIES.get(item["url_name"], CAP_VIEW)
            if operator_has_capability(user, cap):
                items.append(item)
        if items:
            filtered.append({**section, "items": items})
    return filtered
