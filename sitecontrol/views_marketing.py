"""Platform Owner Marketing Hub views."""

import csv

from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from church_system.flash import flash_error, flash_success
from church_system.client_ip import get_client_ip
from sitecontrol import marketing_selectors
from sitecontrol.checks import platform_required, require_platform_capability
from sitecontrol.marketing_forms import (
    MarketingAssetForm,
    MarketingCampaignForm,
    MarketingLeadUpdateForm,
    MarketingSettingsForm,
    PublicMarketingInquiryForm,
)
from sitecontrol.marketing_services import (
    archive_asset,
    archive_campaign,
    anonymize_expired_leads,
    anonymize_lead,
    build_campaign_inquiry_url,
    build_inquiry_url,
    build_registration_url,
    create_public_lead,
    get_marketing_settings,
    inquiry_rate_limits_allow,
    marketing_inquiry_is_ready,
    save_asset,
    save_campaign,
    save_marketing_settings,
    update_lead,
)
from sitecontrol.rbac import CAP_EXPORT_MARKETING, CAP_MANAGE_MARKETING
from sitecontrol.services import get_site_settings, log_platform_action


def _breadcrumbs(*crumbs):
    return [{"label": c[0], **({"url": c[1]} if len(c) > 1 else {})} for c in crumbs]


def _marketing_breadcrumbs(*crumbs):
    return _breadcrumbs(
        ("Platform", "/platform/"),
        ("Marketing Hub", "/platform/marketing/"),
        *crumbs,
    )


def marketing_inquiry(request):
    settings_obj = get_marketing_settings()
    if not marketing_inquiry_is_ready(settings_obj):
        return HttpResponseForbidden(
            "Marketing inquiries are currently closed. Please contact the platform owner."
        )

    initial = {
        "campaign_slug": request.GET.get("campaign", "")[:80],
        "utm_source": request.GET.get("utm_source", "")[:80],
        "utm_medium": request.GET.get("utm_medium", "")[:80],
        "utm_campaign": request.GET.get("utm_campaign", "")[:100],
    }
    form = PublicMarketingInquiryForm(
        request.POST or None,
        initial=initial,
        marketing_settings=settings_obj,
    )
    if request.method == "POST":
        if form.is_valid():
            ip_address = get_client_ip(request)
            if not inquiry_rate_limits_allow(
                ip_address,
                form.cleaned_data["contact_email"],
                form.cleaned_data.get("campaign_slug", ""),
            ):
                return HttpResponse(
                    "Too many inquiries have been submitted. Please try again later.",
                    status=429,
                )
            try:
                create_public_lead(form.cleaned_data, ip_address=ip_address)
                return redirect("marketing_inquiry_success")
            except ValueError as exc:
                form.add_error(None, str(exc))

    return render(request, "registration/marketing_inquiry.html", {
        "form": form,
        "marketing_settings": settings_obj,
        "site_name": get_site_settings().site_name,
    })


def marketing_inquiry_success(request):
    return render(request, "registration/marketing_inquiry_success.html", {
        "marketing_settings": get_marketing_settings(),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_hub(request):
    settings_obj = get_marketing_settings()
    counts = marketing_selectors.dashboard_counts()
    conversion_rate = (
        round((counts["converted_leads"] / counts["total_leads"]) * 100, 1)
        if counts["total_leads"]
        else 0
    )
    inquiry_url = build_inquiry_url(request)
    registration_url = build_registration_url(request)
    return render(request, "sitecontrol/marketing/hub.html", {
        "marketing_settings": settings_obj,
        "counts": counts,
        "conversion_rate": conversion_rate,
        "recent_leads": marketing_selectors.lead_list()[:8],
        "campaigns": [
            {"campaign": campaign, "url": build_campaign_inquiry_url(campaign, request)}
            for campaign in marketing_selectors.campaign_list()[:8]
        ],
        "assets": marketing_selectors.asset_list(include_archived=False)[:8],
        "inquiry_url": inquiry_url,
        "registration_url": registration_url,
        "demo_button_html": (
            f'<a href="{inquiry_url}" class="churchhub-cta">Request a ChurchHub demo</a>'
        ),
        "registration_button_html": (
            f'<a href="{registration_url}" class="churchhub-cta">Register your church</a>'
        ),
        "breadcrumbs": _marketing_breadcrumbs(),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_settings(request):
    settings_obj = get_marketing_settings()
    form = MarketingSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and form.is_valid():
        save_marketing_settings(form)
        log_platform_action(
            request,
            "MARKETING_SETTINGS",
            "Marketing settings updated",
            target_model="MarketingSettings",
            target_id=1,
            details={"changed_fields": sorted(form.changed_data)},
        )
        flash_success(request, "Marketing settings saved.")
        return redirect("sitecontrol:marketing_settings")
    return render(request, "sitecontrol/marketing/settings.html", {
        "form": form,
        "breadcrumbs": _marketing_breadcrumbs(("Settings",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_campaigns(request):
    return render(request, "sitecontrol/marketing/campaign_list.html", {
        "campaigns": [
            {"campaign": campaign, "url": build_campaign_inquiry_url(campaign, request)}
            for campaign in marketing_selectors.campaign_list()
        ],
        "breadcrumbs": _marketing_breadcrumbs(("Campaigns",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_campaign_edit(request, pk=None):
    campaign = marketing_selectors.get_campaign_or_404(pk) if pk else None
    form = MarketingCampaignForm(request.POST or None, instance=campaign)
    if request.method == "POST" and form.is_valid():
        created = campaign is None
        campaign = save_campaign(form, actor=request.user)
        log_platform_action(
            request,
            "MARKETING_CAMPAIGN_CREATE" if created else "MARKETING_CAMPAIGN_UPDATE",
            "Marketing campaign created" if created else "Marketing campaign updated",
            target_model="MarketingCampaign",
            target_id=campaign.pk,
            details={
                "status": campaign.status,
                "changed_fields": sorted(form.changed_data),
            },
        )
        flash_success(request, "Campaign saved.")
        return redirect("sitecontrol:marketing_campaigns")
    return render(request, "sitecontrol/marketing/campaign_form.html", {
        "form": form,
        "campaign": campaign,
        "breadcrumbs": _marketing_breadcrumbs(
            ("Campaigns", "/platform/marketing/campaigns/"),
            ("Edit" if campaign else "Add",),
        ),
    })


@require_POST
@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_campaign_archive(request, pk):
    campaign = marketing_selectors.get_campaign_or_404(pk)
    archive_campaign(campaign)
    log_platform_action(
        request,
        "MARKETING_CAMPAIGN_ARCHIVE",
        "Marketing campaign archived",
        target_model="MarketingCampaign",
        target_id=campaign.pk,
    )
    flash_success(request, "Campaign archived.")
    return redirect("sitecontrol:marketing_campaigns")


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_leads(request):
    leads = marketing_selectors.lead_list()
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    allowed_statuses = {value for value, _ in leads.model.STATUS_CHOICES}
    if status in allowed_statuses:
        leads = leads.filter(status=status)
    else:
        status = ""
    if query:
        leads = leads.filter(
            Q(contact_name__icontains=query)
            | Q(contact_email__icontains=query)
            | Q(organization_name__icontains=query)
        )
    page_obj = Paginator(leads, 25).get_page(request.GET.get("page"))
    return render(request, "sitecontrol/marketing/lead_list.html", {
        "page_obj": page_obj,
        "status_filter": status,
        "query": query,
        "status_choices": leads.model.STATUS_CHOICES,
        "breadcrumbs": _marketing_breadcrumbs(("Leads",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_lead_detail(request, pk):
    lead = marketing_selectors.get_lead_or_404(pk)
    old_status = lead.status
    old_assignee = str(lead.assigned_to_id or "")
    old_notes = lead.internal_notes
    form = MarketingLeadUpdateForm(request.POST or None, instance=lead)
    if request.method == "POST" and form.is_valid():
        lead = update_lead(form)
        log_platform_action(
            request,
            "MARKETING_LEAD_UPDATE",
            "Marketing lead workflow updated",
            target_model="MarketingLead",
            target_id=lead.pk,
            denomination=lead.denomination,
            details={
                "old_status": old_status,
                "new_status": lead.status,
                "old_assignee_id": old_assignee,
                "new_assignee_id": str(lead.assigned_to_id or ""),
                "notes_changed": old_notes != lead.internal_notes,
            },
        )
        flash_success(request, "Lead updated.")
        return redirect("sitecontrol:marketing_lead_detail", pk=lead.pk)
    return render(request, "sitecontrol/marketing/lead_detail.html", {
        "lead": lead,
        "form": form,
        "breadcrumbs": _marketing_breadcrumbs(
            ("Leads", "/platform/marketing/leads/"),
            ("Inquiry",),
        ),
    })


def _csv_safe(value):
    text = str(value or "")
    return f"'{text}" if text.startswith(("=", "+", "-", "@")) else text


@require_POST
@platform_required
@require_platform_capability(CAP_EXPORT_MARKETING)
def marketing_lead_export(request):
    leads = marketing_selectors.lead_list()
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="churchhub-marketing-leads.csv"'
    writer = csv.writer(response)
    writer.writerow([
        "Received",
        "Status",
        "Contact",
        "Email",
        "Phone",
        "Organization",
        "Denomination",
        "Campaign",
        "Source",
        "Medium",
        "Consent date",
        "Notification",
    ])
    count = 0
    for lead in leads.iterator():
        writer.writerow([
            lead.created_at.isoformat(),
            lead.get_status_display(),
            _csv_safe(lead.contact_name),
            _csv_safe(lead.contact_email),
            _csv_safe(lead.contact_phone),
            _csv_safe(lead.organization_name),
            _csv_safe(lead.denomination),
            _csv_safe(lead.campaign),
            _csv_safe(lead.utm_source),
            _csv_safe(lead.utm_medium),
            lead.consented_at.isoformat(),
            lead.get_notification_status_display(),
        ])
        count += 1
    log_platform_action(
        request,
        "MARKETING_LEAD_EXPORT",
        "Marketing leads exported",
        target_model="MarketingLead",
        details={"record_count": count},
    )
    return response


@require_POST
@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_lead_anonymize(request, pk):
    lead = marketing_selectors.get_lead_or_404(pk)
    old_status = lead.status
    try:
        anonymize_lead(lead, actor=request.user)
    except ValueError as exc:
        flash_error(request, str(exc), title="Lead not anonymized")
    else:
        log_platform_action(
            request,
            "MARKETING_LEAD_ANONYMIZE",
            "Marketing lead anonymized",
            target_model="MarketingLead",
            target_id=lead.pk,
            denomination=lead.denomination,
            details={"previous_status": old_status},
        )
        flash_success(request, "Lead personal data anonymized.")
    return redirect("sitecontrol:marketing_lead_detail", pk=lead.pk)


@require_POST
@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_retention_run(request):
    count = anonymize_expired_leads(actor=request.user)
    log_platform_action(
        request,
        "MARKETING_LEAD_ANONYMIZE",
        "Marketing lead retention run completed",
        target_model="MarketingLead",
        details={"record_count": count},
    )
    flash_success(request, f"Retention completed: {count} closed lead(s) anonymized.")
    return redirect("sitecontrol:marketing_leads")


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_assets(request):
    return render(request, "sitecontrol/marketing/asset_list.html", {
        "assets": marketing_selectors.asset_list(),
        "breadcrumbs": _marketing_breadcrumbs(("Assets",)),
    })


@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_asset_edit(request, pk=None):
    asset = marketing_selectors.get_asset_or_404(pk) if pk else None
    form = MarketingAssetForm(request.POST or None, instance=asset)
    if request.method == "POST" and form.is_valid():
        created = asset is None
        asset = save_asset(form, actor=request.user)
        log_platform_action(
            request,
            "MARKETING_ASSET_CREATE" if created else "MARKETING_ASSET_UPDATE",
            "Marketing asset created" if created else "Marketing asset updated",
            target_model="MarketingAsset",
            target_id=asset.pk,
            details={
                "status": asset.status,
                "asset_type": asset.asset_type,
                "changed_fields": sorted(form.changed_data),
            },
        )
        flash_success(request, "Marketing asset saved.")
        return redirect("sitecontrol:marketing_assets")
    return render(request, "sitecontrol/marketing/asset_form.html", {
        "form": form,
        "asset": asset,
        "breadcrumbs": _marketing_breadcrumbs(
            ("Assets", "/platform/marketing/assets/"),
            ("Edit" if asset else "Add",),
        ),
    })


@require_POST
@platform_required
@require_platform_capability(CAP_MANAGE_MARKETING)
def marketing_asset_archive(request, pk):
    asset = marketing_selectors.get_asset_or_404(pk)
    archive_asset(asset)
    log_platform_action(
        request,
        "MARKETING_ASSET_ARCHIVE",
        "Marketing asset archived",
        target_model="MarketingAsset",
        target_id=asset.pk,
    )
    flash_success(request, "Marketing asset archived.")
    return redirect("sitecontrol:marketing_assets")
