"""Platform bulk import of members and receipts from Excel."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from church_system.spreadsheet_io import parse_decimal_amount, parse_excel_date, read_xlsx_rows
from members.models import Gender, Member, MembershipStatus
from members.services import create_member
from organization.models import Church
from transactions.services import record_receipt

MEMBER_CANONICAL = {
    "first_name",
    "last_name",
    "middle_name",
    "preferred_name",
    "email",
    "phone",
    "gender",
    "date_of_birth",
    "membership_number",
    "membership_status",
    "date_joined",
    "marital_status",
    "address",
}

MEMBER_ALIASES = {
    "firstname": "first_name",
    "first": "first_name",
    "given_name": "first_name",
    "lastname": "last_name",
    "last": "last_name",
    "surname": "last_name",
    "family_name": "last_name",
    "middlename": "middle_name",
    "middle": "middle_name",
    "preferredname": "preferred_name",
    "nickname": "preferred_name",
    "dob": "date_of_birth",
    "birth_date": "date_of_birth",
    "birthdate": "date_of_birth",
    "member_number": "membership_number",
    "membership_no": "membership_number",
    "membership_id": "membership_number",
    "status": "membership_status",
    "joined": "date_joined",
    "join_date": "date_joined",
    "membership_date": "date_joined",
}

TRANSACTION_CANONICAL = {
    "date",
    "member_email",
    "membership_number",
    "tithe",
    "combined",
    "income",
    "description",
    "reference",
    "payment_method",
}

TRANSACTION_ALIASES = {
    "receipt_date": "date",
    "transaction_date": "date",
    "posting_date": "date",
    "email": "member_email",
    "member_number": "membership_number",
    "tithe_amount": "tithe",
    "combined_offering": "combined",
    "combined_amount": "combined",
    "offering": "combined",
    "income_amount": "income",
    "notes": "description",
    "memo": "description",
    "payment_account": "payment_method",
    "payment_type": "payment_method",
}

VALID_PAYMENT_METHODS = {"CASH", "BANK"}


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

    @property
    def can_commit(self) -> bool:
        return self.total > 0 and self.failed == 0


def _map_row(raw: dict[str, Any], aliases: dict[str, str], canonical: set[str]) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "_row_number":
            continue
        canon = aliases.get(key, key)
        if canon in canonical:
            mapped[canon] = value
    return mapped


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _validate_gender(value: str) -> str:
    if not value:
        raise ValidationError("Gender is required (Male or Female).")
    normalized = value.strip().title()
    if normalized not in Gender.values:
        raise ValidationError(f"Gender must be one of: {', '.join(Gender.values)}.")
    return normalized


def _validate_membership_status(value: str) -> str:
    if not value:
        return MembershipStatus.ACTIVE
    for choice_value, choice_label in MembershipStatus.choices:
        if value.strip().lower() in (choice_value.lower(), choice_label.lower()):
            return choice_value
    allowed = ", ".join(c[0] for c in MembershipStatus.choices)
    raise ValidationError(f"Membership status must be one of: {allowed}.")


def preview_member_import(uploaded) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=True, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, MEMBER_ALIASES, MEMBER_CANONICAL)
            first = _text(data.get("first_name"))
            last = _text(data.get("last_name"))
            if not first or not last:
                raise ValidationError("First name and last name are required.")
            gender = _validate_gender(_text(data.get("gender")))
            email = _text(data.get("email")).lower()
            dob = parse_excel_date(data.get("date_of_birth")) if data.get("date_of_birth") else None
            if email and not dob:
                raise ValidationError("Date of birth is required when email is set.")
            _validate_membership_status(_text(data.get("membership_status")))
            label = f"{first} {last}".strip()
            result.rows.append(
                ImportRowResult(row_number, True, "Ready to import.", label=label or gender)
            )
            result.succeeded += 1
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
    return result


@transaction.atomic
def commit_member_import(
    church: Church,
    performed_by,
    uploaded,
) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=False, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, MEMBER_ALIASES, MEMBER_CANONICAL)
            first = _text(data.get("first_name"))
            last = _text(data.get("last_name"))
            if not first or not last:
                raise ValidationError("First name and last name are required.")
            fields = {
                "first_name": first,
                "last_name": last,
                "middle_name": _text(data.get("middle_name")),
                "preferred_name": _text(data.get("preferred_name")),
                "email": _text(data.get("email")).lower(),
                "phone": _text(data.get("phone")),
                "gender": _validate_gender(_text(data.get("gender"))),
                "marital_status": _text(data.get("marital_status")),
                "address": _text(data.get("address")),
                "membership_number": _text(data.get("membership_number")),
                "membership_status": _validate_membership_status(
                    _text(data.get("membership_status"))
                ),
            }
            if data.get("date_of_birth"):
                fields["date_of_birth"] = parse_excel_date(data.get("date_of_birth"))
            if data.get("date_joined"):
                fields["date_joined"] = parse_excel_date(data.get("date_joined"))
            member = create_member(church, performed_by=performed_by, **fields)
            result.rows.append(
                ImportRowResult(
                    row_number,
                    True,
                    "Member created.",
                    label=member.full_name,
                )
            )
            result.succeeded += 1
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                parts = []
                for key, msgs in exc.message_dict.items():
                    parts.extend(f"{key}: {m}" for m in msgs)
                msg = "; ".join(parts) or str(exc)
            elif getattr(exc, "messages", None):
                msg = exc.messages[0]
            else:
                msg = str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
    if result.failed:
        transaction.set_rollback(True)
    return result


def _resolve_member(church: Church, email: str, membership_number: str) -> Member | None:
    email = (email or "").strip().lower()
    membership_number = (membership_number or "").strip()
    if email:
        member = Member.objects.filter(church=church, email__iexact=email, is_deleted=False).first()
        if member:
            return member
        if membership_number:
            raise ValidationError(f"No member with email {email} in this church.")
    if membership_number:
        member = Member.objects.filter(
            church=church,
            membership_number=membership_number,
            is_deleted=False,
        ).first()
        if member:
            return member
        raise ValidationError(f"No member with membership number {membership_number} in this church.")
    return None


def preview_transaction_import(church: Church, uploaded) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=True, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, TRANSACTION_ALIASES, TRANSACTION_CANONICAL)
            txn_date = parse_excel_date(data.get("date"))
            if not txn_date:
                raise ValidationError("Date is required.")
            tithe = parse_decimal_amount(data.get("tithe"), field_label="Tithe")
            combined = parse_decimal_amount(data.get("combined"), field_label="Combined")
            income = parse_decimal_amount(data.get("income"), field_label="Income")
            if tithe + combined + income <= 0:
                raise ValidationError("At least one of tithe, combined, or income must be greater than zero.")
            email = _text(data.get("member_email"))
            number = _text(data.get("membership_number"))
            if email or number:
                member = _resolve_member(church, email, number)
                label = member.full_name if member else ""
            else:
                label = _text(data.get("description")) or "Receipt"
            payment = _text(data.get("payment_method")).upper() or "CASH"
            if payment not in VALID_PAYMENT_METHODS:
                raise ValidationError("Payment method must be CASH or BANK.")
            result.rows.append(
                ImportRowResult(row_number, True, "Ready to import.", label=label)
            )
            result.succeeded += 1
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
    return result


@transaction.atomic
def commit_transaction_import(
    church: Church,
    performed_by,
    uploaded,
) -> ImportBatchResult:
    _, rows = read_xlsx_rows(uploaded)
    result = ImportBatchResult(dry_run=False, total=len(rows))
    for raw in rows:
        row_number = int(raw["_row_number"])
        try:
            data = _map_row(raw, TRANSACTION_ALIASES, TRANSACTION_CANONICAL)
            txn_date = parse_excel_date(data.get("date"))
            if not txn_date:
                raise ValidationError("Date is required.")
            tithe = parse_decimal_amount(data.get("tithe"), field_label="Tithe")
            combined = parse_decimal_amount(data.get("combined"), field_label="Combined")
            income = parse_decimal_amount(data.get("income"), field_label="Income")
            if tithe + combined + income <= 0:
                raise ValidationError("At least one of tithe, combined, or income must be greater than zero.")
            email = _text(data.get("member_email"))
            number = _text(data.get("membership_number"))
            member = _resolve_member(church, email, number) if (email or number) else None
            payment = _text(data.get("payment_method")).upper() or "CASH"
            if payment not in VALID_PAYMENT_METHODS:
                raise ValidationError("Payment method must be CASH or BANK.")
            description = _text(data.get("description"))
            reference = _text(data.get("reference"))
            if reference and not description:
                description = f"Import ref {reference}"
            elif reference:
                description = f"{description} (ref {reference})"
            trx = record_receipt(
                church,
                performed_by,
                tithe_amount=tithe,
                combined_amount=combined,
                income_amount=income,
                payment_account_type=payment,
                description=description or "Imported receipt",
                member=member,
                date=txn_date,
            )
            result.rows.append(
                ImportRowResult(
                    row_number,
                    True,
                    f"Receipt recorded ({trx.approval_status}).",
                    label=str(trx.reference or trx.pk),
                )
            )
            result.succeeded += 1
        except ValidationError as exc:
            msg = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
            result.rows.append(ImportRowResult(row_number, False, msg))
            result.failed += 1
        except ValueError as exc:
            result.rows.append(ImportRowResult(row_number, False, str(exc)))
            result.failed += 1
    if result.failed:
        transaction.set_rollback(True)
    return result
