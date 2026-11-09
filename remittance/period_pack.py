"""Read-only settlement period pack: posted batches, linked journals, remittances."""

from datetime import date, datetime
from decimal import Decimal

from django.db.models import Prefetch, Q

from remittance import selectors
from remittance.models import SettlementBatch, SettlementLine
from remittance.services import resolve_unit_label

PACK_ROW_LIMIT = 500

PACK_HEADERS = [
    "Section",
    "Date",
    "Period",
    "From",
    "To",
    "Offering",
    "Church",
    "Journal",
    "Status",
    "Gross",
    "Retention",
    "Payable / amount",
]


def parse_pack_date(value, fallback):
    if not value:
        return fallback
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return fallback


def _quantize(value):
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _empty_pack(start, end):
    return {
        "title": "Settlement Register",
        "headers": PACK_HEADERS,
        "rows": [],
        "summary": {
            "posted_batches": 0,
            "linked_journals": 0,
            "remittance_payments": 0,
            "gross": Decimal("0.00"),
            "retention": Decimal("0.00"),
            "payable": Decimal("0.00"),
            "payments": Decimal("0.00"),
        },
        "settlement_pack": {
            "batches": [],
            "journals": [],
            "payments": [],
        },
        "notes": [],
        "truncated": False,
        "start_date": start,
        "end_date": end,
    }


def _unit_ids_from_churches(churches):
    church_ids = [c.pk for c in churches]
    district_ids = set()
    conference_ids = set()
    union_ids = set()
    gc_ids = set()
    for church in churches:
        district = getattr(church, "district", None)
        if not district:
            continue
        district_ids.add(district.pk)
        zone = getattr(district, "zone", None)
        conference = getattr(zone, "conference", None) if zone else None
        if not conference:
            continue
        conference_ids.add(conference.pk)
        union = getattr(conference, "union", None)
        if not union:
            continue
        union_ids.add(union.pk)
        gc = getattr(union, "general_conference", None)
        if gc:
            gc_ids.add(gc.pk)
    return church_ids, district_ids, conference_ids, union_ids, gc_ids


def posted_settlements_for_pack(
    *,
    churches,
    start,
    end,
    offering_type=None,
    desk=None,
    limit=PACK_ROW_LIMIT,
):
    church_ids, district_ids, conference_ids, union_ids, gc_ids = _unit_ids_from_churches(
        churches
    )
    if desk is not None:
        qs = selectors.settlement_desk_batches(
            desk_type=desk.unit_type,
            desk_id=desk.unit_id,
            church_ids=church_ids,
            tab="all",
            status="POSTED",
            offering_type=offering_type,
            limit=None,
        )
    else:
        if not church_ids:
            return SettlementBatch.objects.none()
        scope = Q(from_unit_type="CHURCH", from_unit_id__in=church_ids) | Q(
            to_unit_type="CHURCH", to_unit_id__in=church_ids
        )
        if district_ids:
            scope |= Q(from_unit_type="DISTRICT", from_unit_id__in=district_ids)
            scope |= Q(to_unit_type="DISTRICT", to_unit_id__in=district_ids)
        if conference_ids:
            scope |= Q(from_unit_type="CONFERENCE", from_unit_id__in=conference_ids)
            scope |= Q(to_unit_type="CONFERENCE", to_unit_id__in=conference_ids)
        if union_ids:
            scope |= Q(from_unit_type="UNION", from_unit_id__in=union_ids)
            scope |= Q(to_unit_type="UNION", to_unit_id__in=union_ids)
        if gc_ids:
            scope |= Q(
                from_unit_type="GENERAL_CONFERENCE", from_unit_id__in=gc_ids
            )
            scope |= Q(to_unit_type="GENERAL_CONFERENCE", to_unit_id__in=gc_ids)
        qs = SettlementBatch.objects.filter(scope)
        if offering_type:
            qs = qs.filter(offering_type=offering_type)
        qs = qs.filter(status="POSTED")
    qs = (
        qs.filter(posted_at__date__gte=start, posted_at__date__lte=end)
        .prefetch_related(
            Prefetch(
                "lines",
                queryset=SettlementLine.objects.select_related(
                    "source_transaction", "source_transaction__church"
                ),
            )
        )
        .order_by("posted_at", "period_end")
        .distinct()
    )
    if limit:
        return qs[:limit]
    return qs


def remittance_payment_journals(church_ids, start, end, limit=PACK_ROW_LIMIT):
    from transactions.models import FinancialAuditLog, TransactionLine

    if not church_ids:
        return FinancialAuditLog.objects.none()
    return (
        FinancialAuditLog.objects.filter(
            action="REMIT",
            church_id__in=list(church_ids),
            transaction__isnull=False,
            transaction__date__gte=start,
            transaction__date__lte=end,
        )
        .exclude(transaction__is_voided=True)
        .select_related("transaction", "church")
        .prefetch_related(
            Prefetch(
                "transaction__lines",
                queryset=TransactionLine.objects.select_related("account"),
            )
        )
        .order_by("transaction__date", "created_at")[:limit]
    )


def _txn_debit_total(txn):
    if txn is None:
        return Decimal("0.00")
    total = Decimal("0.00")
    for line in txn.lines.all():
        if line.amount > 0:
            total += line.amount
    return _quantize(total)


def _journal_status(txn):
    if txn is None:
        return ""
    if txn.is_voided:
        return "Voided"
    return txn.get_approval_status_display()


def build_settlement_period_pack(
    *,
    start,
    end,
    churches,
    offering_type=None,
    desk=None,
):
    """Flatten posted settlements, SettlementLine journals, and REMIT payments."""
    pack = _empty_pack(start, end)
    church_list = list(churches)
    if not church_list and desk is None:
        pack["notes"].append("No churches are in scope for this period pack.")
        return pack

    batches = list(
        posted_settlements_for_pack(
            churches=church_list,
            start=start,
            end=end,
            offering_type=offering_type,
            desk=desk,
            limit=PACK_ROW_LIMIT + 1,
        )
    )
    truncated = len(batches) > PACK_ROW_LIMIT
    batches = batches[:PACK_ROW_LIMIT]

    church_ids = [c.pk for c in church_list]
    payments = list(remittance_payment_journals(church_ids, start, end))

    batch_rows = []
    journal_rows = []
    payment_rows = []
    rows = []
    gross = Decimal("0.00")
    retention = Decimal("0.00")
    payable = Decimal("0.00")
    payment_total = Decimal("0.00")

    for batch in batches:
        from_label = resolve_unit_label(batch.from_unit_type, batch.from_unit_id)
        to_label = resolve_unit_label(batch.to_unit_type, batch.to_unit_id)
        posted = batch.posted_at.date() if batch.posted_at else ""
        offering = batch.get_offering_type_display()
        period = f"{batch.period_start} – {batch.period_end}"
        church_name = from_label if batch.from_unit_type == "CHURCH" else ""
        gross += _quantize(batch.gross_received)
        retention += _quantize(batch.retain_amount)
        payable += _quantize(batch.remit_amount)
        batch_row = {
            "posted": posted,
            "period": period,
            "from_label": from_label,
            "to_label": to_label,
            "offering": offering,
            "church": church_name,
            "status": batch.get_status_display(),
            "gross": _quantize(batch.gross_received),
            "retention": _quantize(batch.retain_amount),
            "payable": _quantize(batch.remit_amount),
        }
        batch_rows.append(batch_row)
        rows.append(
            [
                "Posted batch",
                posted,
                period,
                from_label,
                to_label,
                offering,
                church_name,
                "",
                batch.get_status_display(),
                _quantize(batch.gross_received),
                _quantize(batch.retain_amount),
                _quantize(batch.remit_amount),
            ]
        )
        for line in batch.lines.all():
            txn = line.source_transaction
            amount = _quantize(line.amount)
            journal = {
                "date": txn.date if txn else posted,
                "church": txn.church.name if txn and txn.church_id else church_name,
                "reference": (txn.reference or "") if txn else "",
                "narration": (txn.description or "") if txn else (line.notes or ""),
                "status": _journal_status(txn),
                "amount": amount,
            }
            journal_rows.append(journal)
            rows.append(
                [
                    "Linked journal",
                    journal["date"],
                    period,
                    from_label,
                    to_label,
                    offering,
                    journal["church"],
                    journal["reference"],
                    journal["status"],
                    "",
                    "",
                    amount,
                ]
            )

    for log in payments:
        txn = log.transaction
        amount = _txn_debit_total(txn)
        payment_total += amount
        payment = {
            "date": txn.date if txn else log.created_at.date(),
            "church": log.church.name if log.church_id else "",
            "reference": (txn.reference or "") if txn else "",
            "narration": (txn.description or "District remittance") if txn else "District remittance",
            "status": _journal_status(txn),
            "amount": amount,
        }
        payment_rows.append(payment)
        rows.append(
            [
                "Remittance payment",
                payment["date"],
                "",
                payment["church"],
                "",
                "",
                payment["church"],
                payment["reference"],
                payment["status"],
                "",
                "",
                amount,
            ]
        )

    if truncated:
        rows.append(
            [
                "",
                "… truncated",
                "",
                f"Showing first {PACK_ROW_LIMIT} posted batches",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )

    notes = [
        "Posted batches are included by posted date in this window.",
        "Linked journals are SettlementLine source transactions (church and district TRANSFER postings).",
        "Remittance payments are cash/bank journals logged as district remittance (FinancialAuditLog REMIT).",
        "Union and General Conference drafts stay review-only and do not appear until posted.",
    ]
    pack.update(
        {
            "rows": rows,
            "truncated": truncated,
            "notes": notes,
            "summary": {
                "posted_batches": len(batch_rows),
                "linked_journals": len(journal_rows),
                "remittance_payments": len(payment_rows),
                "gross": gross,
                "retention": retention,
                "payable": payable,
                "payments": payment_total,
            },
            "settlement_pack": {
                "batches": batch_rows,
                "journals": journal_rows,
                "payments": payment_rows,
            },
        }
    )
    return pack
