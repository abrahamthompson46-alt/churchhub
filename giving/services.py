"""Member giving history from approved transactions."""

from decimal import Decimal

from permissions.checks import can_manage_finances, can_manage_members, can_view_giving, can_view_own_giving

from giving import selectors

GIVING_ACCOUNT_TYPES = selectors.GIVING_LINE_ACCOUNT_TYPES


def can_view_member_giving(user, member):
    if can_manage_finances(user) or can_view_giving(user):
        return True
    if can_manage_members(user):
        return True
    linked = getattr(user, "member_id", None)
    if linked is not None and linked == member.pk:
        return can_view_own_giving(user)
    return False


def member_giving_lines(member, year=None):
    return selectors.member_giving_lines_qs(member, year=year)


def member_giving_summary(member, year=None):
    lines = member_giving_lines(member, year)
    raw = selectors.line_totals_by_account_type(lines, GIVING_ACCOUNT_TYPES)
    by_type = {acc: abs(raw.get(acc) or Decimal("0")) for acc in GIVING_ACCOUNT_TYPES}
    by_type["total"] = sum(by_type.values())

    from remittance.welfare_services import member_welfare_summary

    welfare = member_welfare_summary(member, year=year)
    by_type["welfare_contributed"] = welfare["contributed"]
    by_type["welfare_received"] = welfare["received"]
    return by_type


def church_giving_leaders(church, year=None, limit=20):
    """Top contributing members for a church (ORM aggregated)."""
    from church_system.perf_cache import cache_get, cache_set, giving_leaders_key

    cache_key = giving_leaders_key(church.pk, year)
    cached = cache_get(cache_key)
    if cached is not None:
        # Rehydrate member objects for cached id/total pairs
        members = {m.pk: m for m in selectors.members_by_ids([row["member_id"] for row in cached])}
        return [
            {"member": members[row["member_id"]], "total": Decimal(row["total"])}
            for row in cached
            if row["member_id"] in members
        ]

    ranked = selectors.church_giving_leader_totals(church, year=year, limit=limit)
    member_ids = [row["transaction__member_id"] for row in ranked]
    members = {m.pk: m for m in selectors.members_by_ids(member_ids)}
    result = [
        {
            "member": members[row["transaction__member_id"]],
            "total": row["total"] or Decimal("0"),
        }
        for row in ranked
        if row["transaction__member_id"] in members
    ]
    cache_set(
        cache_key,
        [{"member_id": r["member"].pk, "total": str(r["total"])} for r in result],
        timeout=300,
    )
    return result


def export_giving_statement_table(lines):
    """Prepare headers/rows for giving statement export (amounts as abs)."""
    headers = ["Date", "Reference", "Account", "Amount"]
    rows = [
        [
            line.transaction.date,
            line.transaction.reference,
            line.account.name,
            abs(line.amount),
        ]
        for line in lines
    ]
    return {
        "headers": headers,
        "rows": rows,
        "title": "Giving Statement",
    }
