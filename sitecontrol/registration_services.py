"""Tenant registration application workflow."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from accounts.models import User
from accounts.services import create_invitation
from organization.models import Church, District
from organization.services import create_church, onboard_full_hierarchy
from permissions.roles import UserRole

from .models import TenantApplication
from .services import (
    assign_subscription,
    get_default_plan,
    get_site_settings,
    log_platform_action,
)


def public_registration_allowed():
    if not get_site_settings().allow_church_self_registration:
        return False
    from sitecontrol.models import Denomination

    return Denomination.objects.filter(is_active=True, allow_public_registration=True).exists()


def institution_invites_allowed():
    return get_site_settings().allow_institution_user_invites


def institution_onboarding_allowed():
    return get_site_settings().allow_institution_church_onboarding


def pending_application_count():
    return TenantApplication.objects.filter(status="PENDING").count()


def _validate_role(role):
    valid = {c[0] for c in UserRole.CHOICES}
    if role not in valid:
        return UserRole.LOCAL_PASTOR
    return role


@transaction.atomic
def submit_tenant_application(data, ip_address=None):
    if not public_registration_allowed():
        raise ValueError("Church registration is not currently open.")

    email = data["contact_email"].lower().strip()
    username = data["applicant_username"].strip()

    if TenantApplication.objects.filter(status="PENDING", contact_email=email).exists():
        raise ValueError("An application with this email is already pending review.")

    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("This username is already taken.")

    if User.objects.filter(email__iexact=email).exists():
        raise ValueError("An account with this email already exists.")

    app_type = data.get("application_type", "EXISTING_DISTRICT")
    denomination = data.get("denomination")
    if not denomination:
        raise ValueError("Please select your denomination.")
    if not denomination.allow_public_registration:
        raise ValueError("Registration is not open for the selected denomination.")

    if app_type == "EXISTING_DISTRICT":
        district = data.get("district")
        if not district:
            raise ValueError("Please select a district.")
        if district.zone.conference.denomination_id != denomination.pk:
            raise ValueError("The selected district does not belong to your denomination.")
        if Church.objects.filter(district=district, code=data["church_code"]).exists():
            raise ValueError("A church with this code already exists in the selected district.")
    else:
        if Church.objects.filter(code=data["church_code"]).exists():
            raise ValueError("A church with this code already exists.")

    application = TenantApplication.objects.create(
        application_type=app_type,
        denomination=denomination,
        church_name=data["church_name"].strip(),
        church_code=data["church_code"].strip().upper(),
        address=data.get("address", "").strip(),
        district=data.get("district") if app_type == "EXISTING_DISTRICT" else None,
        conference_name=data.get("conference_name", "").strip(),
        conference_code=data.get("conference_code", "").strip().upper(),
        zone_name=data.get("zone_name", "").strip(),
        zone_code=data.get("zone_code", "").strip().upper(),
        district_name=data.get("district_name", "").strip(),
        district_code=data.get("district_code", "").strip().upper(),
        contact_name=data["contact_name"].strip(),
        contact_email=email,
        contact_phone=data.get("contact_phone", "").strip(),
        applicant_username=username,
        applicant_notes=data.get("applicant_notes", "").strip(),
        ip_address=ip_address,
    )
    return application


@transaction.atomic
def approve_tenant_application(
    application,
    reviewer,
    review_notes="",
    plan=None,
    status="ACTIVE",
    billing_interval="MONTHLY",
    payment_method=None,
    payment_reference="",
    trial_days=None,
    role=None,
):
    if not application.is_pending:
        raise ValueError("Only pending applications can be approved.")

    settings_obj = get_site_settings()
    denomination = application.denomination
    plan = (
        plan
        or (denomination.default_plan if denomination else None)
        or settings_obj.application_default_plan
        or get_default_plan()
    )
    if not plan:
        raise ValueError("No subscription plan available. Create a plan first.")

    role = _validate_role(
        role
        or (denomination.default_role if denomination else None)
        or settings_obj.application_default_role
    )

    if application.application_type == "NEW_HIERARCHY":
        church, _ = onboard_full_hierarchy(
            conference_name=application.conference_name,
            conference_code=application.conference_code,
            zone_name=application.zone_name,
            zone_code=application.zone_code,
            district_name=application.district_name,
            district_code=application.district_code,
            church_name=application.church_name,
            church_code=application.church_code,
            address=application.address,
            setup_financials=True,
            denomination=denomination,
            performed_by=reviewer,
        )
    else:
        if not application.district_id:
            raise ValueError("Application is missing a district.")
        church, _ = create_church(
            district=application.district,
            name=application.church_name,
            code=application.church_code,
            address=application.address,
            setup_financials=True,
            performed_by=reviewer,
        )

    started_at = timezone.now().date()
    expires_at = None
    if status == "TRIAL":
        days = trial_days if trial_days is not None else plan.trial_days
        expires_at = started_at + timedelta(days=days)

    from sitecontrol.provisioning_services import _compute_next_billing

    assign_subscription(
        church,
        plan,
        status=status,
        user=reviewer,
        expires_at=expires_at,
        billing_interval=billing_interval,
        payment_method=payment_method,
        payment_reference=payment_reference,
        started_at=started_at,
        next_billing_at=(
            _compute_next_billing(started_at, billing_interval)
            if status in ("ACTIVE", "TRIAL")
            else None
        ),
    )

    invitation = create_invitation(
        email=application.contact_email,
        username=application.applicant_username,
        role=role,
        church=church,
        invited_by=reviewer,
        days_valid=14,
    )

    application.status = "APPROVED"
    application.review_notes = review_notes
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.created_church = church
    application.invitation = invitation
    application.save()

    return application, church, invitation


@transaction.atomic
def reject_tenant_application(application, reviewer, review_notes=""):
    if not application.is_pending:
        raise ValueError("Only pending applications can be rejected.")

    application.status = "REJECTED"
    application.review_notes = review_notes
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.save()
    return application
