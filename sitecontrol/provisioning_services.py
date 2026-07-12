"""Platform tenant provisioning without CLI."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.services import create_invitation
from organization.services import create_church, onboard_full_hierarchy, provision_church
from permissions.roles import UserRole

from .services import assign_subscription, get_default_plan, get_site_settings


def _validate_role(role):
    valid = {c[0] for c in UserRole.CHOICES}
    if role not in valid:
        return UserRole.LOCAL_PASTOR
    return role


def _compute_expires_at(status, plan, trial_days=None):
    if status == "TRIAL":
        days = trial_days if trial_days is not None else plan.trial_days
        return timezone.now().date() + timedelta(days=days)
    return None


def _compute_next_billing(started_at, billing_interval):
    if billing_interval == "YEARLY":
        return started_at + timedelta(days=365)
    return started_at + timedelta(days=30)


@transaction.atomic
def provision_tenant(
    *,
    setup_mode,
    denomination,
    district=None,
    conference_name="",
    conference_code="",
    zone_name="",
    zone_code="",
    district_name="",
    district_code="",
    church_name,
    church_code,
    address="",
    admin_email="",
    admin_username="",
    admin_first_name="",
    plan=None,
    status="ACTIVE",
    billing_interval="MONTHLY",
    payment_method=None,
    payment_reference="",
    trial_days=None,
    admin_role=None,
    send_invite=True,
    reviewer=None,
    ip_address=None,
):
    """Create hierarchy/church, financials, subscription, and optional admin invite."""
    plan = plan or get_default_plan()
    if not plan:
        raise ValueError("No subscription plan available. Create a plan first.")

    role = _validate_role(
        admin_role or get_site_settings().application_default_role
    )

    if setup_mode == "EXISTING_DISTRICT":
        if not district:
            raise ValueError("Select a district for the church.")
        if denomination and district.zone.conference.denomination_id != denomination.pk:
            raise ValueError("District does not belong to the selected denomination.")
        church, _ = create_church(
            district=district,
            name=church_name,
            code=church_code,
            address=address,
            setup_financials=True,
            performed_by=reviewer,
            ip_address=ip_address,
        )
    elif setup_mode == "NEW_HIERARCHY":
        church, _ = onboard_full_hierarchy(
            conference_name=conference_name,
            conference_code=conference_code,
            zone_name=zone_name,
            zone_code=zone_code,
            district_name=district_name,
            district_code=district_code,
            church_name=church_name,
            church_code=church_code,
            address=address,
            setup_financials=True,
            denomination=denomination,
            performed_by=reviewer,
            ip_address=ip_address,
        )
    else:
        raise ValueError("Invalid setup mode.")

    started_at = timezone.now().date()
    expires_at = _compute_expires_at(status, plan, trial_days)
    sub = assign_subscription(
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

    invitation = None
    if send_invite and admin_email and admin_username:
        invitation = create_invitation(
            email=admin_email.strip().lower(),
            username=admin_username.strip(),
            role=role,
            church=church,
            invited_by=reviewer,
            days_valid=14,
        )

    return church, sub, invitation


@transaction.atomic
def reprovision_tenant_financials(church, reviewer=None):
    """Re-run financial seeding for an existing church."""
    provision_church(church, force=True)
    return church
