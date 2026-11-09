"""Read-only depreciation register inventory. Performs no financial writes."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from assets.register_inventory import CATEGORY_KEYS, build_depreciation_register_inventory
from organization.models import Church


def _parse_church_uuid(token):
    try:
        return UUID(str(token).strip())
    except (TypeError, ValueError, AttributeError):
        return None


def resolve_inventory_church(token):
    """Return exactly one Church for a code or UUID. Fail closed if ambiguous."""
    raw = (token or "").strip()
    if not raw:
        raise CommandError("Church code or UUID is required.")

    church_id = _parse_church_uuid(raw)
    if church_id is not None:
        church = Church.objects.filter(pk=church_id).first()
        if church is None:
            raise CommandError(f"Church id {raw!r} was not found.")
        return church

    matches = list(
        Church.objects.filter(code=raw).order_by("district_id", "pk")
    )
    if not matches:
        raise CommandError(f"Church code {raw!r} was not found.")
    if len(matches) > 1:
        details = ", ".join(f"{row.pk}" for row in matches)
        raise CommandError(
            f"Church code {raw!r} matches {len(matches)} churches. "
            "Codes are unique per district, not globally. Pass a church UUID "
            f"with --church. Matching ids: {details}"
        )
    return matches[0]


class Command(BaseCommand):
    help = (
        "Read-only inventory of depreciation register reconciliation categories. "
        "Does not post, approve, void, or update accumulated depreciation. "
        "Does not enforce RBAC. Output contains tenant identifiers and totals. "
        "Requires --church CODE|UUID or explicit --all-churches."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--church",
            type=str,
            help=(
                "Church code or UUID. Codes must match exactly one church; "
                "use the UUID when a code is reused across districts. "
                "Required unless --all-churches is set."
            ),
        )
        parser.add_argument(
            "--all-churches",
            action="store_true",
            help=(
                "Inventory every church. Cross-tenant identifiers and totals "
                "will be printed. This is not an authorization check."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help=(
                "Max identifiers printed per category (default 50). "
                "Does not change category counts. 0 prints counts only."
            ),
        )

    def handle(self, *args, **options):
        token = (options.get("church") or "").strip() or None
        all_churches = bool(options.get("all_churches"))
        if token and all_churches:
            raise CommandError("Use --church or --all-churches, not both.")
        if not token and not all_churches:
            raise CommandError(
                "Refusing unscoped inventory. Pass --church CODE|UUID or "
                "--all-churches (prints every tenant; not an authorization grant)."
            )

        churches = None
        church = None
        if token:
            church = resolve_inventory_church(token)
            churches = [church]

        raw_limit = options.get("limit")
        if raw_limit is None:
            limit = 50
        else:
            try:
                limit = int(raw_limit)
            except (TypeError, ValueError) as exc:
                raise CommandError("--limit must be an integer >= 0.") from exc
            if limit < 0:
                raise CommandError("--limit must be >= 0.")

        inventory = build_depreciation_register_inventory(
            churches, identifier_limit=limit
        )
        self.stdout.write("Depreciation register inventory (read-only)")
        self.stdout.write(
            "Output contains tenant-sensitive identifiers and financial totals. "
            "This command does not enforce RBAC."
        )
        if church is not None:
            self.stdout.write(
                f"Church scope: {church.code} id={church.pk}"
            )
        else:
            self.stdout.write(
                "Church scope: ALL CHURCHES (--all-churches). "
                "Cross-tenant identifiers are included."
            )
        self.stdout.write(
            f"--limit {limit} restricts displayed identifiers only; "
            "category count is the full population."
        )
        for key in CATEGORY_KEYS:
            block = inventory["categories"][key]
            self.stdout.write(
                f"{key}: count={block['count']} shown={block['shown']} "
                f"omitted={block['omitted']} truncated={block['truncated']} "
                f"outcome={block.get('outcome', 'n/a')}"
            )
            self.stdout.write(f"  {block['definition']}")
            if block["ids"]:
                self.stdout.write("  ids: " + ", ".join(block["ids"]))
        overlaps = inventory["overlaps"]
        self.stdout.write("overlaps (full populations, not limited):")
        for name, ids in overlaps.items():
            self.stdout.write(f"  {name}: count={len(ids)}")
        for note in inventory["notes"]:
            self.stdout.write(f"note: {note}")
