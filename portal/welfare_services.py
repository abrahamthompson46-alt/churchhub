"""Member portal welfare — self-service filters and safe case presentation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied

from remittance.models import WelfareAssistanceCase, WelfareMemberLedger
from remittance.welfare_services import (
    build_member_welfare_statement,
    can_view_member_welfare,
    member_welfare_cases,
    member_welfare_contributions,
    member_welfare_summary,
    welfare_module_enabled,
    welfare_year_choices,
)


@dataclass(frozen=True)
class PortalWelfareFilters:
    year: int | None
    start_date: date | None
    end_date: date | None
    entry_type: str
    direction: str
    case_status: str
    assistance_type: str
    view: str  # all | ledger | contributions | cases

    def has_date_range(self) -> bool:
        return bool(self.start_date or self.end_date)

    def has_ledger_filters(self) -> bool:
        return bool(self.entry_type or self.direction)

    def query_dict(self, *, exclude: frozenset[str] | None = None) -> dict[str, str]:
        exclude = exclude or frozenset()
        data: dict[str, str] = {}
        if self.year and "year" not in exclude:
            data["year"] = str(self.year)
        if self.start_date and "start_date" not in exclude:
            data["start_date"] = self.start_date.isoformat()
        if self.end_date and "end_date" not in exclude:
            data["end_date"] = self.end_date.isoformat()
        if self.entry_type and "entry_type" not in exclude:
            data["entry_type"] = self.entry_type
        if self.direction and "direction" not in exclude:
            data["direction"] = self.direction
        if self.case_status and "case_status" not in exclude:
            data["case_status"] = self.case_status
        if self.assistance_type and "assistance_type" not in exclude:
            data["assistance_type"] = self.assistance_type
        if self.view and self.view != "all" and "view" not in exclude:
            data["view"] = self.view
        return data

    def export_query(self, export_fmt: str) -> str:
        params = self.query_dict()
        params["export"] = export_fmt
        return urlencode(params)


def parse_portal_welfare_filters(get_params) -> PortalWelfareFilters:
    start_date = end_date = None
    start_raw = (get_params.get("start_date") or "").strip()
    end_raw = (get_params.get("end_date") or "").strip()
    try:
        if start_raw:
            start_date = datetime.strptime(start_raw, "%Y-%m-%d").date()
        if end_raw:
            end_date = datetime.strptime(end_raw, "%Y-%m-%d").date()
    except ValueError:
        start_date = end_date = None

    year = None
    year_raw = (get_params.get("year") or "").strip()
    if year_raw and not start_date and not end_date:
        try:
            year = int(year_raw)
        except ValueError:
            year = None

    entry_type = (get_params.get("entry_type") or "").strip().upper()
    if entry_type not in dict(WelfareMemberLedger.ENTRY_TYPES):
        entry_type = ""

    direction = (get_params.get("direction") or "").strip().upper()
    if direction not in dict(WelfareMemberLedger.DIRECTIONS):
        direction = ""

    case_status = (get_params.get("case_status") or "").strip().upper()
    if case_status not in dict(WelfareAssistanceCase.STATUS_CHOICES):
        case_status = ""

    assistance_type = (get_params.get("assistance_type") or "").strip().upper()
    if assistance_type not in dict(WelfareAssistanceCase.ASSISTANCE_TYPES):
        assistance_type = ""

    view = (get_params.get("view") or "all").strip().lower()
    if view not in {"all", "ledger", "contributions", "cases"}:
        view = "all"

    return PortalWelfareFilters(
        year=year,
        start_date=start_date,
        end_date=end_date,
        entry_type=entry_type,
        direction=direction,
        case_status=case_status,
        assistance_type=assistance_type,
        view=view,
    )


def require_portal_welfare_access(user, member) -> None:
    if not member:
        raise PermissionDenied("Link your account to a member profile to view welfare.")
    if not welfare_module_enabled(member.church, user):
        raise PermissionDenied("Welfare is not enabled for your church.")
    if not can_view_member_welfare(user, member):
        raise PermissionDenied("You may only view your own welfare record.")


def portal_welfare_case_for_member(member, case_id):
    return (
        WelfareAssistanceCase.objects.filter(member=member, pk=case_id)
        .select_related("church")
        .first()
    )


def member_safe_case_detail(case: WelfareAssistanceCase) -> dict[str, Any]:
    """Fields safe to show a member about their own assistance case."""
    member_message = ""
    if case.status == "REJECTED" and case.rejection_reason:
        member_message = case.rejection_reason.strip()
    elif case.status == "APPROVED" and case.amount_approved:
        member_message = f"Approved for disbursement: ₵{case.amount_approved:.2f}."
    elif case.status == "DISBURSED" and case.amount_approved:
        member_message = f"Assistance disbursed: ₵{case.amount_approved:.2f}."
    return {
        "case": case,
        "member_message": member_message,
        "show_reason": True,
    }


def build_portal_welfare_page(member, filters: PortalWelfareFilters) -> dict[str, Any]:
    year = filters.year
    start = filters.start_date
    end = filters.end_date

    summary = member_welfare_summary(
        member, year=year, start_date=start, end_date=end
    )
    statement = build_member_welfare_statement(
        member,
        start_date=start,
        end_date=end,
        entry_type=filters.entry_type or None,
        direction=filters.direction or None,
    )
    cases = list(
        member_welfare_cases(
            member,
            limit=100,
            status=filters.case_status or None,
            assistance_type=filters.assistance_type or None,
        )
    )
    contributions = list(
        member_welfare_contributions(
            member,
            year=year if not filters.has_date_range() else None,
            limit=100,
        )
    )
    if start or end:
        contributions = [
            c
            for c in contributions
            if (not start or c.contribution_date >= start)
            and (not end or c.contribution_date <= end)
        ]

    return {
        "filters": filters,
        "summary": summary,
        "statement": statement,
        "cases": cases,
        "contributions": contributions,
        "year_choices": welfare_year_choices(),
        "entry_type_choices": WelfareMemberLedger.ENTRY_TYPES,
        "direction_choices": WelfareMemberLedger.DIRECTIONS,
        "case_status_choices": WelfareAssistanceCase.STATUS_CHOICES,
        "assistance_type_choices": WelfareAssistanceCase.ASSISTANCE_TYPES,
        "filtered_balance_note": filters.has_ledger_filters(),
    }


def welfare_statement_export_rows(statement: dict) -> tuple[list[str], list[list]]:
    headers = ["Date", "Type", "Reference", "Description", "In", "Out", "Balance"]
    rows: list[list] = []
    if statement.get("opening_balance"):
        rows.append(
            ["", "Opening", "", "Balance brought forward", "", "", statement["opening_balance"]]
        )
    for row in statement.get("rows", []):
        rows.append(
            [
                row["date"],
                row["type"],
                row["reference"],
                row["description"],
                row["in_amount"] or "",
                row["out_amount"] or "",
                row["balance"],
            ]
        )
    return headers, rows
