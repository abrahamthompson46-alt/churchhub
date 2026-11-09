"""Fixed asset register — business logic."""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from transactions.services import (
    PeriodLockedError,
    UnbalancedTransactionError,
    WorkingDayClosedError,
    _commit_journal_approval,
    _get_account,
    _log_audit,
    _post_line,
    _quantize_currency,
    approve_module_journal,
    assert_period_open,
    assert_working_day_allows_posting,
    resolve_authorized_journal_checker,
    validate_transaction_balance,
)
from transactions import repositories as txn_repo

from . import repositories as repo
from . import selectors


class AssetError(ValueError):
    pass


PLATFORM_CATEGORY_TEMPLATES = [
    {
        "code": "buildings",
        "name": "Buildings & Structures",
        "description": "Church buildings, halls, parsonages, and permanent structures.",
        "gra_asset_class": "1",
        "default_useful_life_months": 240,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("10.00"),
        "sort_order": 1,
    },
    {
        "code": "vehicles",
        "name": "Vehicles & Transport",
        "description": "Cars, vans, motorcycles, and transport equipment.",
        "gra_asset_class": "2",
        "default_useful_life_months": 60,
        "default_depreciation_method": "DECLINING_BALANCE",
        "default_salvage_percent": Decimal("5.00"),
        "sort_order": 2,
    },
    {
        "code": "plant-equipment",
        "name": "Plant & Heavy Equipment",
        "description": "Generators, HVAC, kitchen plant, and heavy machinery.",
        "gra_asset_class": "2",
        "default_useful_life_months": 84,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("5.00"),
        "sort_order": 3,
    },
    {
        "code": "furniture-fixtures",
        "name": "Furniture & Fixtures",
        "description": "Pews, chairs, pulpits, cabinets, and fixed furnishings.",
        "gra_asset_class": "3",
        "default_useful_life_months": 60,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("5.00"),
        "sort_order": 4,
    },
    {
        "code": "computer-it",
        "name": "Computers & IT Equipment",
        "description": "Computers, servers, networking, and software hardware.",
        "gra_asset_class": "3",
        "default_useful_life_months": 36,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("0.00"),
        "sort_order": 5,
    },
    {
        "code": "audio-visual",
        "name": "Audio-Visual & Media",
        "description": "Sound systems, projectors, cameras, and broadcast equipment.",
        "gra_asset_class": "3",
        "default_useful_life_months": 48,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("5.00"),
        "sort_order": 6,
    },
    {
        "code": "office-equipment",
        "name": "Office Equipment",
        "description": "Printers, copiers, safes, and general office machines.",
        "gra_asset_class": "3",
        "default_useful_life_months": 48,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("5.00"),
        "sort_order": 7,
    },
    {
        "code": "low-value",
        "name": "Low-Value Assets",
        "description": "Items below capitalization threshold or short useful life.",
        "gra_asset_class": "4",
        "default_useful_life_months": 12,
        "default_depreciation_method": "STRAIGHT_LINE",
        "default_salvage_percent": Decimal("0.00"),
        "sort_order": 8,
    },
]


def _quantize(amount):
    return _quantize_currency(amount)


def _asset_log(asset, action, user, notes=""):
    repo.create_asset_audit(asset=asset, action=action, user=user, notes=notes)


def log_policy_change(church, action, user, *, target_label="", notes="", details=None):
    return repo.create_policy_audit(
        church=church,
        action=action,
        user=user,
        target_label=target_label,
        notes=notes,
        details=details,
    )


def seed_platform_category_templates():
    """Seed or refresh platform-wide asset category templates."""
    for row in PLATFORM_CATEGORY_TEMPLATES:
        repo.update_or_create_template(code=row["code"], defaults=row)


def ensure_depreciation_policy(church):
    policy, _ = repo.get_or_create_depreciation_policy(church)
    return policy


def seed_church_categories(church):
    """Copy platform templates into church-specific categories."""
    ensure_depreciation_policy(church)
    templates = selectors.active_templates()
    for template in templates:
        repo.update_or_create_category(
            church=church,
            code=template.code,
            defaults={
                "template": template,
                "name": template.name,
                "gra_asset_class": template.gra_asset_class,
                "useful_life_months": template.default_useful_life_months,
                "depreciation_method": template.default_depreciation_method,
                "salvage_percent": template.default_salvage_percent,
                "is_active": True,
                "is_custom": False,
            },
        )


def ensure_asset_defaults_for_church(church):
    seed_platform_category_templates()
    seed_church_categories(church)


@db_transaction.atomic
def generate_asset_code(church):
    prefix = church.code.upper()[:6] if church.code else "AST"
    pattern = f"{prefix}-FA-"
    last_code = selectors.last_asset_code_for_prefix(church, pattern)
    if last_code:
        try:
            seq = int(last_code.rsplit("-", 1)[-1]) + 1
        except (ValueError, IndexError):
            seq = selectors.asset_count_for_church(church) + 1
    else:
        seq = 1
    return f"{pattern}{seq:04d}"


def compute_salvage_value(acquisition_cost, salvage_percent):
    pct = Decimal(str(salvage_percent))
    return _quantize(acquisition_cost * pct / Decimal("100"))


def apply_category_defaults(asset, category=None):
    category = category or asset.category
    asset.gra_asset_class = category.gra_asset_class
    asset.useful_life_months = category.useful_life_months
    asset.depreciation_method = category.depreciation_method
    if not asset.salvage_value and asset.acquisition_cost:
        asset.salvage_value = compute_salvage_value(asset.acquisition_cost, category.salvage_percent)


def allowed_methods_for_church(church):
    policy = ensure_depreciation_policy(church)
    methods = []
    if policy.allow_straight_line:
        methods.append("STRAIGHT_LINE")
    if policy.allow_declining_balance:
        methods.append("DECLINING_BALANCE")
    return methods or ["STRAIGHT_LINE"]


def validate_depreciation_method(church, method):
    if method not in allowed_methods_for_church(church):
        raise AssetError("Selected depreciation method is not enabled in church policy.")


def validate_depreciation_period(period_year, period_month):
    """Depreciation cannot be posted for future months."""
    today = timezone.now().date()
    if (period_year, period_month) > (today.year, today.month):
        raise AssetError("Depreciation cannot be posted for a future period.")


def assert_segregation_of_duties(asset, user):
    if asset.submitted_by_id and asset.submitted_by_id == user.pk:
        raise AssetError(
            "Segregation of duties: you cannot approve an asset you submitted."
        )
    if asset.created_by_id and asset.created_by_id == user.pk:
        raise AssetError(
            "Segregation of duties: you cannot approve an asset you created."
        )


def months_since_acquisition(asset, period_year, period_month):
    start = asset.purchase_date.replace(day=1)
    end = date(period_year, period_month, 1)
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def calculate_monthly_depreciation(asset, period_year, period_month):
    """Return depreciation amount for a given month (0 if fully depreciated)."""
    if asset.status != "ACTIVE":
        return Decimal("0.00")
    if asset.net_book_value <= asset.salvage_value:
        return Decimal("0.00")

    month_index = months_since_acquisition(asset, period_year, period_month)
    if month_index < 1 or month_index > asset.useful_life_months:
        return Decimal("0.00")

    base = asset.depreciable_base
    if base <= 0:
        return Decimal("0.00")

    if asset.depreciation_method == "STRAIGHT_LINE":
        return _quantize(base / asset.useful_life_months)

    # 150% declining balance — monthly rate from useful life in years
    years = max(Decimal(str(asset.useful_life_months)) / Decimal("12"), Decimal("1"))
    annual_rate = Decimal("1.5") / Decimal(str(years))
    monthly_rate = annual_rate / Decimal("12")
    nbv = asset.net_book_value
    amount = _quantize(nbv * monthly_rate)
    remaining = nbv - asset.salvage_value
    if amount > remaining:
        amount = _quantize(remaining)
    return max(amount, Decimal("0.00"))


@db_transaction.atomic
def post_acquisition_to_ledger(asset, user):
    """DR Property & Equipment, CR Cash/Bank on asset approval."""
    policy = ensure_depreciation_policy(asset.church)
    if not policy.capitalize_on_approval:
        return None

    if asset.acquisition_transaction_id:
        return asset.acquisition_transaction

    assert_period_open(asset.church, asset.purchase_date)
    assert_working_day_allows_posting(asset.church, asset.purchase_date)
    payment_type = policy.default_payment_account_type

    trx = txn_repo.create_transaction(
        transaction_type="CAPITAL",
        church=asset.church,
        created_by=asset.submitted_by or asset.created_by or user,
        description=f"Capitalize asset {asset.asset_code} — {asset.name}",
        date=asset.purchase_date,
    )

    ppe = _get_account(asset.church, "FIXED_ASSET")
    payment = _get_account(asset.church, payment_type)
    amount = _quantize(asset.acquisition_cost)

    _post_line(trx, ppe, amount)
    _post_line(trx, payment, -amount)
    validate_transaction_balance(trx)
    asset.acquisition_transaction = trx
    repo.save_asset(asset, update_fields=["acquisition_transaction", "updated_at"])
    trx = approve_module_journal(trx, user)
    if trx.approval_status != "APPROVED":
        raise AssetError(
            "Asset capitalization journal requires an authorized checker other "
            "than the submitter (approve_transactions or a valid in-scope "
            "delegation). Asset posting permission is not general-ledger "
            "approval authority."
        )
    _log_audit(
        asset.church,
        "CREATE",
        user,
        transaction=trx,
        details={"type": "ASSET_ACQUISITION", "asset_id": str(asset.pk), "amount": str(amount)},
    )
    return trx


@db_transaction.atomic
def submit_asset_for_approval(asset, user):
    if asset.status not in ("DRAFT", "REJECTED"):
        raise AssetError("Only draft or rejected assets can be submitted.")
    apply_category_defaults(asset)
    validate_depreciation_method(asset.church, asset.depreciation_method)
    asset.status = "PENDING_APPROVAL"
    asset.submitted_by = user
    asset.submitted_at = timezone.now()
    asset.rejected_by = None
    asset.rejected_at = None
    asset.rejection_reason = ""
    repo.save_asset(asset)
    _asset_log(asset, "SUBMIT", user)
    return asset


@db_transaction.atomic
def approve_asset(asset, user):
    if asset.status != "PENDING_APPROVAL":
        raise AssetError("Asset is not pending approval.")
    assert_segregation_of_duties(asset, user)
    asset.status = "ACTIVE"
    asset.approved_by = user
    asset.approved_at = timezone.now()
    repo.save_asset(asset)
    post_acquisition_to_ledger(asset, user)
    _asset_log(asset, "APPROVE", user)
    return asset


@db_transaction.atomic
def reject_asset(asset, user, reason=""):
    if asset.status != "PENDING_APPROVAL":
        raise AssetError("Asset is not pending approval.")
    asset.status = "REJECTED"
    asset.rejected_by = user
    asset.rejected_at = timezone.now()
    asset.rejection_reason = reason
    repo.save_asset(asset)
    _asset_log(asset, "REJECT", user, notes=reason)
    return asset


def _depreciation_journal_description(asset, period_year, period_month):
    return f"Depreciation {asset.asset_code} {period_year}-{period_month:02d}"


def _checker_required_error():
    return AssetError(
        "An authenticated user is required to prepare or approve depreciation. "
        "Depreciation was not posted; no journal or period entry was created."
    )


def _journal_is_approved(trx):
    return bool(
        trx
        and trx.approval_status == "APPROVED"
        and trx.locked
        and not getattr(trx, "is_voided", False)
    )


REGISTER_RECONCILE_REQUIRED = (
    "Depreciation register reconciliation is required before further "
    "depreciation can be posted for this asset. Stored accumulated "
    "depreciation was not changed."
)


def assert_depreciation_register_recompute_safe(asset):
    """Fail closed before any selector-sum rewrite of stored accum.

    APPROVED journals are not proof the amount is in stored NBV. Block when
    contributing totals disagree with stored accum, or when FK-linked recovery/
    voided/reversed rows exist. Null-FK rows are not treated as recovery; they
    only block when their contributing amounts disagree with stored accum.
    """
    if selectors.asset_has_unresolved_register_history(asset):
        raise AssetError(REGISTER_RECONCILE_REQUIRED)
    stored = _quantize(asset.accumulated_depreciation)
    contributing = _quantize(selectors.asset_depreciation_total(asset))
    if stored != contributing:
        raise AssetError(REGISTER_RECONCILE_REQUIRED)


def _finalize_depreciation_register(asset, period_year, period_month, amount, user, trx):
    """Write an applied period row and recompute stored accum from contributing rows.

    Totals exclude PENDING/REJECTED-linked entries (FK). Do not use this to
    backfill historical APPROVED-but-stale NBV; that needs a reconciliation report.
    """
    assert_depreciation_register_recompute_safe(asset)
    entry, _ = repo.update_or_create_depreciation_entry(
        asset=asset,
        period_year=period_year,
        period_month=period_month,
        defaults={
            "amount": amount,
            "method_used": asset.depreciation_method,
            "transaction": trx,
            "posted_by": user,
            "posted_at": timezone.now(),
            "workflow_status": "POSTED",
            "register_applied": True,
        },
    )
    asset.accumulated_depreciation = _quantize(selectors.asset_depreciation_total(asset))
    repo.save_asset(asset, update_fields=["accumulated_depreciation", "updated_at"])
    _asset_log(asset, "DEPRECIATE", user, notes=f"{period_year}-{period_month:02d}: {amount}")
    return entry


def _record_unapplied_depreciation_entry(asset, period_year, period_month, amount, user, trx):
    entry, _ = repo.update_or_create_depreciation_entry(
        asset=asset,
        period_year=period_year,
        period_month=period_month,
        defaults={
            "amount": amount,
            "method_used": asset.depreciation_method,
            "transaction": trx,
            "posted_by": None,
            "posted_at": None,
            "workflow_status": "AWAITING_APPROVAL",
            "register_applied": False,
            "initiated_by": user,
        },
    )
    return entry


def _recover_pending_depreciation(
    asset, pending_trx, user, amount, period_year, period_month, *, allow_approval
):
    entry = selectors.depreciation_entry_for_period(asset, period_year, period_month)
    if not allow_approval:
        return entry
    if user is None:
        return entry
    resolved = resolve_authorized_journal_checker(pending_trx, user)
    if resolved is None:
        if getattr(user, "pk", None) == getattr(pending_trx, "created_by_id", None):
            return entry
        raise AssetError(
            "The authenticated user is not authorized to approve this depreciation "
            "journal. The register was not updated and no duplicate journal was created."
        )
    assert_depreciation_register_recompute_safe(asset)
    trx = _commit_journal_approval(pending_trx, resolved)
    return _finalize_depreciation_register(
        asset, period_year, period_month, amount, user, trx
    )


def _assert_no_unlinked_pending_depreciation_journal(asset, period_year, period_month, linked_pk=None):
    """Fail closed on description-matched PENDING journals that have no register FK.

    Description matching is not identity for approval. It is only used to refuse
    a duplicate prepare when an unlinked historical journal already exists.
    """
    qs = selectors.pending_depreciation_journals(asset, period_year, period_month)
    if linked_pk:
        qs = qs.exclude(pk=linked_pk)
    if qs.exists():
        raise AssetError(
            "An unlinked pending depreciation journal exists for this period. "
            "Reconciliation is required; no duplicate journal was created and "
            "the register was not updated."
        )


@db_transaction.atomic
def post_depreciation_entry(
    asset, period_year, period_month, user, *, force=False, allow_approval=False
):
    """
    Prepare or approve monthly depreciation.

    Ledger path: create a CAPITAL journal, link an unapplied register row, then
    approve only when ``allow_approval`` is True and ``user`` is the authenticated
    eligible checker (not the maker). Background callers must leave the journal
    PENDING. Approval and register finalization share this atomic block.
    """
    asset = (
        type(asset)
        .objects.select_for_update()
        .select_related("church")
        .get(pk=asset.pk)
    )
    if asset.status != "ACTIVE":
        raise AssetError("Depreciation applies only to active assets.")
    validate_depreciation_period(period_year, period_month)

    existing = selectors.depreciation_entry_for_period(asset, period_year, period_month)
    existing_trx = getattr(existing, "transaction", None) if existing else None
    if existing and _journal_is_approved(existing_trx) and not force:
        raise AssetError("Depreciation already posted for this period.")

    pending_trx = None
    if (
        existing_trx
        and existing_trx.approval_status == "PENDING"
        and not existing_trx.is_voided
    ):
        pending_trx = existing_trx
    if existing and not pending_trx and not force:
        raise AssetError("Depreciation already posted for this period.")

    amount = calculate_monthly_depreciation(asset, period_year, period_month)
    if amount <= 0:
        return None

    policy = ensure_depreciation_policy(asset.church)
    period_date = date(period_year, period_month, min(28, monthrange(period_year, period_month)[1]))
    assert_period_open(asset.church, period_date)
    assert_working_day_allows_posting(asset.church, period_date)

    assert_depreciation_register_recompute_safe(asset)

    if not policy.post_depreciation_to_ledger:
        if existing and not force:
            raise AssetError("Depreciation already posted for this period.")
        return _finalize_depreciation_register(
            asset, period_year, period_month, amount, user, None
        )

    linked_pk = getattr(pending_trx, "pk", None)
    _assert_no_unlinked_pending_depreciation_journal(
        asset, period_year, period_month, linked_pk=linked_pk
    )

    if pending_trx is not None:
        return _recover_pending_depreciation(
            asset,
            pending_trx,
            user,
            amount,
            period_year,
            period_month,
            allow_approval=allow_approval,
        )

    if user is None:
        raise _checker_required_error()

    trx = txn_repo.create_transaction(
        transaction_type="CAPITAL",
        church=asset.church,
        created_by=user,
        description=_depreciation_journal_description(asset, period_year, period_month),
        date=period_date,
    )
    dep_expense = _get_account(asset.church, "DEPRECIATION_EXPENSE")
    accum = _get_account(asset.church, "ACCUMULATED_DEPRECIATION")
    _post_line(trx, dep_expense, amount)
    _post_line(trx, accum, -amount)
    validate_transaction_balance(trx)
    _record_unapplied_depreciation_entry(
        asset, period_year, period_month, amount, user, trx
    )
    _log_audit(
        asset.church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "type": "ASSET_DEPRECIATION",
            "asset_id": str(asset.pk),
            "period": f"{period_year}-{period_month:02d}",
            "amount": str(amount),
        },
    )
    if not allow_approval:
        return selectors.depreciation_entry_for_period(asset, period_year, period_month)

    resolved = resolve_authorized_journal_checker(trx, user)
    if resolved is None:
        return selectors.depreciation_entry_for_period(asset, period_year, period_month)

    trx = _commit_journal_approval(trx, resolved)
    return _finalize_depreciation_register(
        asset, period_year, period_month, amount, user, trx
    )


def preview_monthly_depreciation(church, year, month):
    """Estimate depreciation for all active assets before posting."""
    validate_depreciation_period(year, month)
    rows = []
    total = Decimal("0.00")
    for asset in selectors.active_assets_for_church(church, with_category=True):
        amount = calculate_monthly_depreciation(asset, year, month)
        if amount > 0:
            rows.append({
                "asset": asset,
                "code": asset.asset_code,
                "name": asset.name,
                "amount": amount,
            })
            total += amount
    return {
        "rows": rows,
        "total": _quantize(total),
        "asset_count": len(rows),
    }


def run_monthly_depreciation(church, year, month, user, *, allow_approval=False):
    """Prepare (and optionally approve) depreciation for active assets."""
    validate_depreciation_period(year, month)
    posted = 0
    skipped = 0
    pending = 0
    failed = 0
    errors = []
    for asset in selectors.active_assets_for_church(church):
        try:
            result = post_depreciation_entry(
                asset, year, month, user, allow_approval=allow_approval
            )
            if result is None:
                skipped += 1
            elif getattr(result, "register_applied", False):
                posted += 1
            else:
                pending += 1
        except (AssetError, PeriodLockedError, WorkingDayClosedError, UnbalancedTransactionError) as exc:
            text = str(exc).lower()
            if "already posted" in text:
                skipped += 1
                continue
            errors.append(f"{asset.asset_code}: {exc}")
            if "already pending" in text:
                pending += 1
            else:
                failed += 1
    return {
        "posted": posted,
        "skipped": skipped,
        "pending": pending,
        "failed": failed,
        "errors": errors,
    }


def format_depreciation_run_summary(result):
    """User-facing counts. Do not describe pending/failed work as posted."""
    return (
        f"{result.get('posted', 0)} completed, "
        f"{result.get('skipped', 0)} skipped, "
        f"{result.get('pending', 0)} pending, "
        f"{result.get('failed', 0)} failed"
    )


@db_transaction.atomic
def post_disposal_to_ledger(asset, user, disposal_date=None, *, checker=None):
    """Write off remaining book value on disposal — link the asset FK before approve."""
    policy = ensure_depreciation_policy(asset.church)
    if not policy.post_disposal_to_ledger:
        return None

    decision_user = checker if checker is not None else user
    existing = asset.disposal_transaction
    if existing is not None:
        if _journal_is_approved(existing):
            return existing
        return approve_module_journal(existing, decision_user)

    disposal_date = disposal_date or asset.disposed_at or timezone.now().date()
    assert_period_open(asset.church, disposal_date)
    assert_working_day_allows_posting(asset.church, disposal_date)

    accum = _quantize(asset.accumulated_depreciation)
    cost = _quantize(asset.acquisition_cost)
    nbv = _quantize(cost - accum)

    trx = txn_repo.create_transaction(
        transaction_type="CAPITAL",
        church=asset.church,
        created_by=user,
        description=f"Dispose asset {asset.asset_code} — {asset.name}",
        date=disposal_date,
    )

    ppe = _get_account(asset.church, "FIXED_ASSET")
    accum_acct = _get_account(asset.church, "ACCUMULATED_DEPRECIATION")

    if accum > 0:
        _post_line(trx, accum_acct, accum)
    if nbv > 0:
        expense = _get_account(asset.church, "EXPENSE")
        _post_line(trx, expense, nbv)
    _post_line(trx, ppe, -cost)

    validate_transaction_balance(trx)
    _log_audit(
        asset.church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "type": "ASSET_DISPOSAL",
            "asset_id": str(asset.pk),
            "cost": str(cost),
            "accumulated": str(accum),
            "nbv": str(nbv),
        },
    )
    asset.disposal_transaction = trx
    repo.save_asset(asset, update_fields=["disposal_transaction", "updated_at"])
    return approve_module_journal(trx, decision_user)


@db_transaction.atomic
def dispose_asset(asset, user, disposal_date=None, notes="", *, checker=None):
    asset = (
        type(asset)
        .objects.select_for_update()
        .select_related("church")
        .get(pk=asset.pk)
    )
    if asset.status not in ("ACTIVE", "UNDER_REPAIR"):
        raise AssetError("Only active assets can be disposed.")
    disposal_date = disposal_date or timezone.now().date()
    # Journal + SoD first; only then mark DISPOSED (CH-SEC-005).
    policy = ensure_depreciation_policy(asset.church)
    if policy.post_disposal_to_ledger:
        post_disposal_to_ledger(
            asset, user, disposal_date=disposal_date, checker=checker
        )
        asset.refresh_from_db()
        trx = asset.disposal_transaction
        if not _journal_is_approved(trx):
            if notes:
                asset.disposal_notes = notes
                repo.save_asset(asset, update_fields=["disposal_notes", "updated_at"])
            return asset
    asset.status = "DISPOSED"
    asset.disposed_at = disposal_date
    asset.disposal_notes = notes
    repo.save_asset(asset)
    _asset_log(asset, "DISPOSE", user, notes=notes)
    return asset


def asset_register_rows(church, status=None):
    qs = selectors.assets_register_qs(church, status=status)
    rows = []
    for asset in qs:
        rows.append({
            "code": asset.asset_code,
            "name": asset.name,
            "category": asset.category.name,
            "status": asset.get_status_display(),
            "purchase_date": asset.purchase_date,
            "cost": asset.acquisition_cost,
            "accumulated": asset.accumulated_depreciation,
            "nbv": asset.net_book_value,
            "location": asset.location,
            "gra_class": asset.get_gra_asset_class_display(),
        })
    return rows


def asset_register_csv(church):
    import csv
    from io import StringIO

    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "Code", "Name", "Category", "Status", "Purchase Date",
        "Cost (GHS)", "Accumulated Dep (GHS)", "NBV (GHS)", "Location", "GRA Class",
    ])
    for row in asset_register_rows(church):
        writer.writerow([
            row["code"], row["name"], row["category"], row["status"],
            row["purchase_date"], row["cost"], row["accumulated"], row["nbv"],
            row["location"], row["gra_class"],
        ])
    return buffer.getvalue()


def depreciation_schedule_rows(asset):
    rows = []
    for entry in asset.depreciation_entries.filter(
        selectors.register_contributing_q()
    ).order_by("period_year", "period_month"):
        rows.append({
            "period": f"{entry.period_year}-{entry.period_month:02d}",
            "amount": entry.amount,
            "method": entry.get_method_used_display() if hasattr(entry, "get_method_used_display") else entry.method_used,
            "posted_at": entry.posted_at,
        })
    return rows


def hierarchy_asset_rollup(user, conference_id=None, zone_id=None, district_id=None):
    """Roll up asset counts and NBV by church — scoped to manageable churches."""
    from .rbac import churches_in_asset_scope

    churches = churches_in_asset_scope(
        user,
        conference_id=conference_id,
        zone_id=zone_id,
        district_id=district_id,
    )

    agg = selectors.active_assets_rollup_agg(churches)
    rows = []
    for row in agg:
        cost = row["total_cost"] or Decimal("0")
        accum = row["total_accum"] or Decimal("0")
        rows.append({
            "church": row["church__name"],
            "district": row["church__district__name"],
            "count": row["asset_count"],
            "cost": cost,
            "accumulated": accum,
            "nbv": _quantize(cost - accum),
        })
    return rows


def church_activity_logs(church, *, action="", limit=500):
    """Combined asset and policy audit entries for a church."""
    asset_logs = selectors.asset_audit_logs_for_church(church, action=action)
    policy_logs = selectors.policy_audit_logs_for_church(church, action=action)

    entries = []
    for log in asset_logs[:limit]:
        entries.append({
            "when": log.created_at,
            "action": log.action,
            "label": log.asset.asset_code,
            "user": log.user,
            "notes": log.notes,
            "kind": "asset",
        })
    for log in policy_logs[:limit]:
        entries.append({
            "when": log.created_at,
            "action": log.get_action_display(),
            "label": log.target_label,
            "user": log.user,
            "notes": log.notes,
            "kind": "policy",
        })
    entries.sort(key=lambda row: row["when"], reverse=True)
    return entries[:limit]


def register_dashboard_kpis(church):
    """Summary metrics for the asset dashboard."""
    assets = selectors.church_assets_qs(church)
    active = assets.filter(status="ACTIVE")
    agg = active.aggregate(
        total_cost=Sum("acquisition_cost"),
        total_accum=Sum("accumulated_depreciation"),
    )
    cost = agg["total_cost"] or Decimal("0.00")
    accum = agg["total_accum"] or Decimal("0.00")
    return {
        "pending_count": assets.filter(status="PENDING_APPROVAL").count(),
        "active_count": active.count(),
        "total_count": assets.count(),
        "total_cost": cost,
        "total_accumulated": accum,
        "total_nbv": _quantize(cost - accum),
    }


def insurance_warranty_alerts(church, days=60):
    """Assets with insurance or warranty expiring within N days."""
    today = timezone.now().date()
    horizon = today + timedelta(days=days)
    qs = selectors.active_assets_for_church(church, with_category=True)
    alerts = []
    for asset in qs:
        if asset.insurance_expiry and today <= asset.insurance_expiry <= horizon:
            alerts.append({
                "asset": asset,
                "type": "Insurance",
                "expiry": asset.insurance_expiry,
                "days_left": (asset.insurance_expiry - today).days,
                "severity": "danger" if (asset.insurance_expiry - today).days <= 14 else "warning",
            })
        if asset.warranty_expiry and today <= asset.warranty_expiry <= horizon:
            alerts.append({
                "asset": asset,
                "type": "Warranty",
                "expiry": asset.warranty_expiry,
                "days_left": (asset.warranty_expiry - today).days,
                "severity": "danger" if (asset.warranty_expiry - today).days <= 14 else "warning",
            })
    alerts.sort(key=lambda x: x["expiry"])
    return alerts


def report_asset_register(request, start, end, **hierarchy):
    from reports.services import _churches_in_scope

    churches = _churches_in_scope(request, **hierarchy)
    headers = [
        "Church", "Code", "Name", "Category", "Status",
        "Cost (GHS)", "Accumulated (GHS)", "NBV (GHS)", "GRA Class",
    ]
    rows = []
    qs = selectors.assets_for_churches(churches)
    for asset in qs.order_by("church__name", "asset_code"):
        rows.append([
            asset.church.name,
            asset.asset_code,
            asset.name,
            asset.category.name,
            asset.get_status_display(),
            asset.acquisition_cost,
            asset.accumulated_depreciation,
            asset.net_book_value,
            asset.get_gra_asset_class_display(),
        ])
    return {"title": "Fixed Asset Register", "headers": headers, "rows": rows}


def report_depreciation_schedule(request, start, end, **hierarchy):
    from reports.services import _churches_in_scope

    churches = _churches_in_scope(request, **hierarchy)
    headers = ["Church", "Asset", "Period", "Amount (GHS)", "Method"]
    rows = []
    entries = selectors.depreciation_entries_for_churches(
        churches, register_applied=True
    )
    if start:
        entries = entries.filter(
            period_year__gte=start.year,
        )
    if end:
        entries = entries.filter(
            period_year__lte=end.year,
        )
    for entry in entries.order_by("-period_year", "-period_month", "asset__asset_code"):
        rows.append([
            entry.asset.church.name,
            f"{entry.asset.asset_code} — {entry.asset.name}",
            f"{entry.period_year}-{entry.period_month:02d}",
            entry.amount,
            entry.method_used,
        ])
    return {"title": "Depreciation Schedule", "headers": headers, "rows": rows}


def report_asset_hierarchy_rollup(request, start, end, **hierarchy):
    rows_data = hierarchy_asset_rollup(
        request.user,
        conference_id=hierarchy.get("conference_id"),
        zone_id=hierarchy.get("zone_id"),
        district_id=hierarchy.get("district_id"),
    )
    headers = ["Church", "District", "Active Assets", "Cost (GHS)", "Accumulated (GHS)", "NBV (GHS)"]
    rows = [
        [r["church"], r["district"], r["count"], r["cost"], r["accumulated"], r["nbv"]]
        for r in rows_data
    ]
    return {"title": "Asset Hierarchy Roll-up", "headers": headers, "rows": rows}
