"""Tenant registration application workflow."""

import re
from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.utils import timezone

from accounts import repositories as accounts_repo
from accounts.models import User
from accounts.services import create_invitation, log_activity
from organization.services import create_church, onboard_full_hierarchy
from permissions.org_scope import OrgScopeLevel, apply_org_scope
from permissions.roles import UserRole
from permissions.services import sync_role_groups

from sitecontrol import repositories as repo
from sitecontrol import selectors
from .services import (
    assign_subscription,
    get_default_plan,
    get_site_settings,
)

# Public demos never exceed this, including if SiteSettings is tampered in the DB.
PUBLIC_DEMO_TRIAL_DAYS_CAP = 30
PUBLIC_DEMO_ROLE = UserRole.LOCAL_PASTOR
DEMO_IDENTITY_ERROR = (
    "This email, username, or phone has already used a ChurchHub demo. "
    "A second trial is not available."
)


def public_registration_allowed():
    if not get_site_settings().allow_church_self_registration:
        return False
    return selectors.public_registration_denomination_exists()


def institution_invites_allowed():
    return get_site_settings().allow_institution_user_invites


def institution_onboarding_allowed():
    return get_site_settings().allow_institution_church_onboarding


def pending_application_count():
    return selectors.pending_application_count()


def public_demo_auto_provision_enabled():
    return bool(get_site_settings().auto_provision_public_trials)


def public_demo_trial_days():
    raw = getattr(get_site_settings(), "public_demo_trial_days", None) or PUBLIC_DEMO_TRIAL_DAYS_CAP
    return min(max(int(raw), 1), PUBLIC_DEMO_TRIAL_DAYS_CAP)


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def _validate_role(role):
    valid = {c[0] for c in UserRole.CHOICES}
    if role not in valid:
        return UserRole.LOCAL_PASTOR
    return role


def _split_contact_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split(None, 1)
    first = parts[0][:150] if parts else ""
    last = parts[1][:150] if len(parts) > 1 else ""
    return first, last


def _assert_demo_identity_available(email: str, username: str, phone: str = ""):
    if selectors.approved_application_for_email(email):
        raise ValueError(DEMO_IDENTITY_ERROR)
    if selectors.approved_application_for_username(username):
        raise ValueError(DEMO_IDENTITY_ERROR)
    normalized = normalize_phone(phone)
    if len(normalized) >= 8 and selectors.approved_application_for_normalized_phone(normalized):
        raise ValueError(DEMO_IDENTITY_ERROR)


def _create_church_from_application(
    application,
    reviewer,
    *,
    skip_branch_limit=False,
    ensure_subscription=True,
):
    denomination = application.denomination
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
            skip_branch_limit=skip_branch_limit,
            ensure_subscription=ensure_subscription,
        )
        return church

    if not application.district_id:
        raise ValueError("Application is missing a district.")
    church, _ = create_church(
        district=application.district,
        name=application.church_name,
        code=application.church_code,
        address=application.address,
        setup_financials=True,
        performed_by=reviewer,
        skip_branch_limit=skip_branch_limit,
        ensure_subscription=ensure_subscription,
    )
    return church


def _assign_trial_subscription(church, plan, reviewer, *, trial_days, status="TRIAL"):
    started_at = timezone.now().date()
    expires_at = None
    if status == "TRIAL":
        days = trial_days if trial_days is not None else plan.trial_days
        expires_at = started_at + timedelta(days=int(days))

    from sitecontrol.provisioning_services import _compute_next_billing

    return assign_subscription(
        church,
        plan,
        status=status,
        user=reviewer,
        expires_at=expires_at,
        billing_interval="MONTHLY",
        started_at=started_at,
        next_billing_at=(
            _compute_next_billing(started_at, "MONTHLY")
            if status in ("ACTIVE", "TRIAL")
            else None
        ),
    )


def _create_demo_admin(application, church, password: str):
    from sitecontrol.services import can_add_user_to_church

    allowed, message = can_add_user_to_church(church)
    if not allowed:
        raise ValueError(message)

    first_name, last_name = _split_contact_name(application.contact_name)
    validate_password(
        password,
        user=User(username=application.applicant_username, email=application.contact_email),
    )
    role = PUBLIC_DEMO_ROLE
    scope_level = OrgScopeLevel.default_for_role(role)
    denom = application.denomination or getattr(church, "denomination", None)
    user = accounts_repo.create_user(
        username=application.applicant_username,
        email=application.contact_email,
        password=password,
        role=role,
        church=church,
        first_name=first_name,
        last_name=last_name,
        is_staff=False,
        denomination=denom,
        scope_level=scope_level,
    )
    apply_org_scope(
        user,
        role=role,
        scope_level=scope_level,
        church=church,
        denomination=denom,
    )
    accounts_repo.save_user(user)
    sync_role_groups(user)
    log_activity(
        user,
        "USER_CREATE",
        details={"source": "public_demo_auto_provision", "church_id": str(church.pk)},
    )
    return user


@transaction.atomic
def auto_provision_public_demo(application, password: str):
    """Provision church + TRIAL (capped) + first user. No operator, no invitation."""
    if not application.is_pending:
        raise ValueError("Only pending applications can be auto-provisioned.")
    if not password:
        raise ValueError("A password is required to start the demo.")

    settings_obj = get_site_settings()
    denomination = application.denomination
    plan = (
        (denomination.default_plan if denomination else None)
        or settings_obj.application_default_plan
        or get_default_plan()
    )
    if not plan:
        raise ValueError("No subscription plan available. Create a plan first.")

    church = _create_church_from_application(
        application,
        reviewer=None,
        skip_branch_limit=True,
        ensure_subscription=False,
    )
    trial_days = public_demo_trial_days()
    sub = _assign_trial_subscription(
        church,
        plan,
        reviewer=None,
        trial_days=trial_days,
        status="TRIAL",
    )
    if not sub.expires_at:
        raise ValueError("Demo subscription is missing an expiry date.")
    if (sub.expires_at - sub.started_at).days > PUBLIC_DEMO_TRIAL_DAYS_CAP:
        raise ValueError("Demo window exceeds the allowed 30 days.")

    user = _create_demo_admin(application, church, password)

    application.status = "APPROVED"
    application.review_notes = "Auto-provisioned public 30-day demo."
    application.reviewed_by = None
    application.reviewed_at = timezone.now()
    application.created_church = church
    application.invitation = None
    repo.save_application(application)
    return application, church, user, sub


@transaction.atomic
def submit_tenant_application(data, ip_address=None):
    if not public_registration_allowed():
        raise ValueError("Church registration is not currently open.")

    email = data["contact_email"].lower().strip()
    username = data["applicant_username"].strip()
    phone = (data.get("contact_phone") or "").strip()
    password = data.get("password") or ""

    if selectors.pending_application_for_email(email):
        raise ValueError("An application with this email is already pending review.")

    _assert_demo_identity_available(email, username, phone)

    if selectors.username_exists_iexact(username):
        raise ValueError("This username is already taken.")

    if selectors.email_exists_iexact(email):
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
        if selectors.church_code_exists_in_district(district, data["church_code"]):
            raise ValueError("A church with this code already exists in the selected district.")
    else:
        if selectors.church_code_exists(data["church_code"]):
            raise ValueError("A church with this code already exists.")

    if public_demo_auto_provision_enabled() and not password:
        raise ValueError("A password is required to start the demo.")

    application = repo.create_tenant_application(
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
        contact_phone=phone,
        contact_phone_normalized=normalize_phone(phone),
        applicant_username=username,
        applicant_notes=data.get("applicant_notes", "").strip(),
        ip_address=ip_address,
    )

    if public_demo_auto_provision_enabled():
        application, _church, _user, _sub = auto_provision_public_demo(application, password)
        return application
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

    church = _create_church_from_application(application, reviewer)

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
    )

    application.status = "APPROVED"
    application.review_notes = review_notes
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    application.created_church = church
    application.invitation = invitation
    repo.save_application(application)

    return application, church, invitation


@transaction.atomic
def reject_tenant_application(application, reviewer, review_notes=""):
    if not application.is_pending:
        raise ValueError("Only pending applications can be rejected.")

    application.status = "REJECTED"
    application.review_notes = review_notes
    application.reviewed_by = reviewer
    application.reviewed_at = timezone.now()
    repo.save_application(application)
    return application
