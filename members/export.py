"""Member personal data export for GDPR-style subject access requests."""

import json
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def build_member_export_payload(member):
    """Assemble exportable member data scoped to the member's church."""
    from members.models import LeadershipRole, MemberSpiritualGift, Record
    from transactions.models import Transaction

    payload = {
        "member": {
            "id": str(member.pk),
            "full_name": member.full_name,
            "church": member.church.name,
            "gender": member.gender,
            "date_of_birth": member.date_of_birth,
            "date_joined": member.date_joined,
            "membership_status": member.membership_status,
            "phone": member.phone,
            "address": member.address,
            "department": member.department.name if member.department_id else "",
            "family": member.family.name if member.family_id else "",
        },
        "spiritual_gifts": [
            {
                "gift": a.gift.name,
                "noted_at": a.noted_at,
                "notes": a.notes,
            }
            for a in MemberSpiritualGift.objects.filter(member=member).select_related("gift")
        ],
        "leadership_roles": [
            {
                "title": r.title,
                "start_date": r.start_date,
                "end_date": r.end_date,
                "is_active": r.is_active,
            }
            for r in LeadershipRole.objects.filter(member=member)
        ],
        "records": [
            {
                "type": r.record_type,
                "title": r.title,
                "event_date": r.event_date,
                "status": r.status,
            }
            for r in Record.objects.filter(member=member)
        ],
        "financial_transactions": [
            {
                "reference": t.reference,
                "type": t.transaction_type,
                "date": t.date,
                "description": t.description,
                "approval_status": t.approval_status,
            }
            for t in Transaction.objects.filter(member=member).order_by("-date")[:500]
        ],
        "exported_at": datetime.now().isoformat(),
    }
    return payload


def export_member_json(member):
    return json.dumps(build_member_export_payload(member), indent=2, default=_json_default)
