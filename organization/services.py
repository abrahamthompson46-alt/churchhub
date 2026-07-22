"""Organization hierarchy services."""

from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction

from organization import repositories as repo
from organization import selectors
from transactions.services import create_default_accounts, create_default_offering_categories


def get_client_ip(request):
    if not request:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_org_audit(action, entity, performed_by=None, ip_address=None, details=None):
    return repo.create_org_audit(
        action=action,
        entity_type=entity.__class__.__name__,
        entity_id=entity.pk,
        entity_label=str(entity),
        performed_by=performed_by,
        ip_address=ip_address,
        details=details or {},
    )


def get_church_financial_chain(church):
    """Return org units from church up to general conference."""
    district = church.district
    zone = district.zone
    conference = zone.conference
    union = conference.union if conference.union_id else None
    general_conference = union.general_conference if union else None
    return {
        "church": church,
        "district": district,
        "zone": zone,
        "conference": conference,
        "union": union,
        "general_conference": general_conference,
    }


def setup_church_financials(church):
    """Seed default accounts, offerings, and module defaults for a church."""
    denomination = church.denomination
    if denomination:
        from sitecontrol.denomination_services import apply_seed_config_to_church

        apply_seed_config_to_church(church, denomination)
    else:
        create_default_accounts(church)
        create_default_offering_categories(church)
        from remittance.services import ensure_default_policies_for_church
        from payroll.services import ensure_payroll_defaults_for_church

        ensure_default_policies_for_church(church)
        ensure_payroll_defaults_for_church(church)
        from assets.services import ensure_asset_defaults_for_church

        ensure_asset_defaults_for_church(church)
        from ledger.services import seed_ledger

        seed_ledger(church)


def provision_church(church, force=False):
    """Single orchestrator for church financial seeding."""
    if church.financials_provisioned and not force:
        return church
    setup_church_financials(church)
    church.financials_provisioned = True
    repo.save_church(church, update_fields=["financials_provisioned", "updated_at"])
    return church


@db_transaction.atomic
def create_church(
    district,
    name,
    code,
    address="",
    setup_financials=True,
    performed_by=None,
    ip_address=None,
):
    """Create a church under an existing district."""
    from sitecontrol.services import can_add_branch_to_district, ensure_church_subscription

    allowed, message = can_add_branch_to_district(district)
    if not allowed:
        raise ValueError(message)

    church, created = repo.get_or_create_church(
        district=district,
        code=code,
        defaults={"name": name, "address": address, "is_active": True},
    )
    if not created:
        church.name = name
        church.address = address
        church.is_active = True
        repo.save_church(
            church, update_fields=["name", "address", "is_active", "updated_at"]
        )

    if setup_financials:
        provision_church(church, force=True)
    ensure_church_subscription(church)
    log_org_audit(
        "CREATE" if created else "UPDATE",
        church,
        performed_by=performed_by,
        ip_address=ip_address,
        details={"district_id": str(district.pk), "code": code},
    )
    return church, created


def _resolve_or_create_conference(
    conference_name,
    conference_code,
    union=None,
    denomination=None,
):
    """Create conference or reuse only when denomination matches."""
    if denomination is None:
        from sitecontrol.models import Denomination

        denomination = Denomination.get_default()

    existing = selectors.conference_by_code(conference_code)
    if existing:
        if denomination and existing.denomination_id and existing.denomination_id != denomination.pk:
            raise ValueError(
                f"Conference code {conference_code} is already used by another denomination."
            )
        conference = existing
        created = False
        updates = []
        if conference.name != conference_name:
            conference.name = conference_name
            updates.append("name")
        if union and conference.union_id != union.pk:
            conference.union = union
            updates.append("union")
        if denomination and conference.denomination_id != denomination.pk:
            conference.denomination = denomination
            updates.append("denomination")
        if updates:
            updates.append("updated_at")
            repo.save_conference(conference, update_fields=updates)
        return conference, created

    conference = repo.create_conference(
        code=conference_code,
        name=conference_name,
        union=union,
        denomination=denomination,
    )
    return conference, True


@db_transaction.atomic
def onboard_full_hierarchy(
    conference_name,
    conference_code,
    zone_name,
    zone_code,
    district_name,
    district_code,
    church_name,
    church_code,
    address="",
    setup_financials=True,
    union=None,
    denomination=None,
    performed_by=None,
    ip_address=None,
):
    """Create or reuse conference, zone, district, then create the church."""
    conference, conf_created = _resolve_or_create_conference(
        conference_name,
        conference_code,
        union=union,
        denomination=denomination,
    )
    zone, _ = repo.get_or_create_zone(
        conference=conference,
        code=zone_code,
        defaults={"name": zone_name},
    )
    if zone.name != zone_name:
        zone.name = zone_name
        repo.save_zone(zone, update_fields=["name", "updated_at"])

    district, _ = repo.get_or_create_district(
        zone=zone,
        code=district_code,
        defaults={"name": district_name},
    )
    if district.name != district_name:
        district.name = district_name
        repo.save_district(district, update_fields=["name", "updated_at"])

    church, created = create_church(
        district=district,
        name=church_name,
        code=church_code,
        address=address,
        setup_financials=setup_financials,
        performed_by=performed_by,
        ip_address=ip_address,
    )
    if conf_created:
        log_org_audit(
            "CREATE",
            conference,
            performed_by=performed_by,
            ip_address=ip_address,
            details={"via": "onboard_full_hierarchy"},
        )
    return church, created


@db_transaction.atomic
def update_church(church, performed_by=None, ip_address=None, **fields):
    if "district" in fields:
        raise ValueError("District changes must use transfer_church().")
    serializable = {}
    for key, value in fields.items():
        setattr(church, key, value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            serializable[key] = value
        else:
            serializable[key] = str(value)
    church.full_clean()
    repo.save_church(church)
    log_org_audit(
        "UPDATE", church, performed_by=performed_by, ip_address=ip_address, details=serializable
    )
    return church


@db_transaction.atomic
def transfer_church(church, new_district, performed_by=None, ip_address=None, reason=""):
    """Move a church to another district within the same denomination."""
    old_district = church.district
    old_denom = church.conference.denomination_id if church.conference else None
    new_denom = new_district.zone.conference.denomination_id if new_district.zone.conference else None
    if old_denom and new_denom and old_denom != new_denom:
        raise ValidationError("Cannot transfer a church across denominations.")

    if selectors.church_code_exists_in_district(
        new_district, church.code, exclude_pk=church.pk
    ):
        raise ValidationError("A church with this code already exists in the target district.")

    church.district = new_district
    church.full_clean()
    repo.save_church(church, update_fields=["district", "updated_at"])
    log_org_audit(
        "TRANSFER",
        church,
        performed_by=performed_by,
        ip_address=ip_address,
        details={
            "from_district_id": str(old_district.pk),
            "to_district_id": str(new_district.pk),
            "reason": reason,
        },
    )
    return church


@db_transaction.atomic
def set_church_active(church, active, performed_by=None, ip_address=None):
    church.is_active = active
    repo.save_church(church, update_fields=["is_active", "updated_at"])
    log_org_audit(
        "ACTIVATE" if active else "DEACTIVATE",
        church,
        performed_by=performed_by,
        ip_address=ip_address,
    )
    return church


def export_hierarchy_rows(request):
    """Flat rows for CSV/Excel export of churches in scope."""
    rows = []
    churches = selectors.churches_for_export(request)
    for church in churches:
        conf = church.conference
        rows.append([
            conf.denomination.name if conf and conf.denomination_id else "",
            conf.name if conf else "",
            church.district.zone.name,
            church.district.name,
            church.name,
            church.code,
            "Active" if church.is_active else "Inactive",
            church.address,
        ])
    headers = [
        "Denomination",
        "Conference",
        "Zone",
        "District",
        "Church",
        "Code",
        "Status",
        "Address",
    ]
    return headers, rows


def reconcile_organization(denomination=None):
    """Return issues: churches without subscription, unprovisioned financials, orphan conferences."""
    issues = []
    churches = selectors.churches_for_reconcile(denomination)

    for church in churches.filter(is_active=True):
        if not church.financials_provisioned:
            issues.append({
                "kind": "unprovisioned_financials",
                "church": church.name,
                "church_id": str(church.pk),
            })
        if not selectors.church_has_subscription(church):
            issues.append({
                "kind": "missing_subscription",
                "church": church.name,
                "church_id": str(church.pk),
            })

    for conf in selectors.orphan_conferences_qs()[:50]:
        issues.append({
            "kind": "orphan_conference",
            "conference": conf.name,
            "conference_id": str(conf.pk),
        })
    return issues
