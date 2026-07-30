"""Excel import for campaign contributions."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from church_system.spreadsheet_io import parse_decimal_amount, parse_excel_date, read_xlsx_rows
from contributions.services import record_member_contribution
from members.models import Member

IMPORT_CANONICAL = {"membership_number", "member_email", "amount", "date", "notes", "payment_method"}
IMPORT_ALIASES = {
    "email": "member_email",
    "member_number": "membership_number",
    "membership_no": "membership_number",
    "contribution_date": "date",
    "receipt_date": "date",
    "memo": "notes",
    "payment_account": "payment_method",
    "payment_type": "payment_method",
}
VALID_PAYMENT = {"CASH", "BANK"}


@dataclass
class ImportRowResult:
    row_number: int
    ok: bool
    message: str
    label: str = ""


@dataclass
class ImportBatchResult:
    dry_run: bool
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    rows: list[ImportRowResult] = field(default_factory=list)


def _map_row(raw, aliases, canonical):
    mapped = {}
    for key, value in raw.items():
        if key == "_row_number":
            continue
        canon = aliases.get(key, key)
        if canon in canonical:
            mapped[canon] = value
    return mapped


def _text(value):
    if value is None:
        return ""
    return str(value).strip()


def _resolve_member(church, email, membership_number):
    email = (email or "").strip().lower()
    membership_number = (membership_number or "").strip()
    if email:
        member = Member.objects.filter(church=church, email__iexact=email, is_deleted=False).first()
        if member:
            return member
        raise ValidationError(f"No member with email {email}.")
    if membership_number:
        member = Member.objects.filter(
            church=church,
            membership_number=membership_number,
            is_deleted=False,
        ).first()
        if member:
            return member
        raise ValidationError(f"No member with number {membership_number}.")
    raise ValidationError("Membership number or member email is required.")


def _validate_row(campaign, data):
    email = _text(data.get("member_email"))
    number = _text(data.get("membership_number"))
    member = _resolve_member(campaign.church, email, number)
    amount = parse_decimal_amount(data.get("amount"), field_label="Amount")
    if amount <= 0:
        raise ValidationError("Amount must be greater than zero.")
    txn_date = parse_excel_date(data.get("date")) if data.get("date") else timezone.localdate()
    payment = _text(data.get("payment_method")).upper() or "CASH"
    if payment not in VALID_PAYMENT:
        raise ValidationError("Payment method must be CASH or BANK.")
    return member, amount, txn_date, payment, _text(data.get("notes"))


def preview_campaign_import(campaign, uploaded) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=True, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, IMPORT_ALIASES, IMPORT_CANONICAL)
            member, amount, _, _, _ = _validate_row(campaign, data)
            result.rows.append(
                ImportRowResult(row_number, True, "Ready to import.", label=member.full_name)
            )
            result.succeeded += 1
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
    return result


@transaction.atomic
def commit_campaign_import(campaign, performed_by, uploaded) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=False, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, IMPORT_ALIASES, IMPORT_CANONICAL)
            member, amount, txn_date, payment, notes = _validate_row(campaign, data)
            record_member_contribution(
                campaign,
                member=member,
                amount=amount,
                performed_by=performed_by,
                contribution_date=txn_date,
                notes=notes,
                payment_account_type=payment,
            )
            result.rows.append(
                ImportRowResult(row_number, True, "Contribution recorded.", label=member.full_name)
            )
            result.succeeded += 1
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
        except Exception as exc:
            result.rows.append(ImportRowResult(row_number, False, str(exc)))
            result.failed += 1
    if result.failed:
        transaction.set_rollback(True)
    return result
