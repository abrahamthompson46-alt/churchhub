"""
Read/query helpers for the organization hierarchy domain.

Views and services call selectors for scoped and annotated querysets.
Authorization gates stay in access.py; persistence writes stay in repositories.
"""

from __future__ import annotations

from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404

from church_system.denomination_scope import conferences_for_denomination, get_active_denomination
from members.models import Member

from .models import Church, Conference, District, GeneralConference, Union, Zone


# ---------------------------------------------------------------------------
# Request-scoped querysets (denomination + org_scope)
# ---------------------------------------------------------------------------


def scoped_conferences(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    denomination = get_active_denomination(request)
    qs = conferences_for_denomination(denomination) if denomination else Conference.objects.all()
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.CONFERENCE:
        conf_id = request.user.scope_conference_id or (
            request.user.church.district.zone.conference_id if request.user.church_id else None
        )
        if conf_id:
            qs = qs.filter(pk=conf_id)
    elif level in {OrgScopeLevel.ZONE, OrgScopeLevel.DISTRICT, OrgScopeLevel.CHURCH}:
        ids = get_manageable_churches(request.user).values_list(
            "district__zone__conference_id", flat=True
        )
        qs = qs.filter(pk__in=ids)
    elif level == OrgScopeLevel.UNION and request.user.scope_union_id:
        qs = qs.filter(union_id=request.user.scope_union_id)
    elif level == OrgScopeLevel.GENERAL_CONFERENCE and request.user.scope_general_conference_id:
        qs = qs.filter(union__general_conference_id=request.user.scope_general_conference_id)
    return qs


def scoped_zones(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    qs = Zone.objects.filter(conference__in=scoped_conferences(request))
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.ZONE:
        zone_id = request.user.scope_zone_id or (
            request.user.church.district.zone_id if request.user.church_id else None
        )
        if zone_id:
            qs = qs.filter(pk=zone_id)
    elif level in {OrgScopeLevel.DISTRICT, OrgScopeLevel.CHURCH}:
        ids = get_manageable_churches(request.user).values_list("district__zone_id", flat=True)
        qs = qs.filter(pk__in=ids)
    return qs


def scoped_districts(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level
    from permissions.scoping import get_manageable_churches

    qs = District.objects.filter(zone__in=scoped_zones(request))
    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.DISTRICT:
        user = request.user
        district = None
        if getattr(user, "scope_district_id", None):
            district = user.scope_district
        elif user.church_id:
            district = user.church.district
        if district:
            qs = qs.filter(pk=district.pk)
    elif level == OrgScopeLevel.CHURCH:
        ids = get_manageable_churches(request.user).values_list("district_id", flat=True)
        qs = qs.filter(pk__in=ids)
    return qs


def scoped_churches(request, active_only=False):
    from permissions.scoping import get_manageable_churches

    qs = get_manageable_churches(request.user)
    if not active_only:
        from permissions.org_scope import church_q_for_scope

        qs = Church.objects.filter(church_q_for_scope(request.user)).select_related(
            "district__zone__conference__denomination"
        )
    return qs.order_by("name")


def scoped_unions(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.GENERAL_CONFERENCE and request.user.scope_general_conference_id:
        return Union.objects.filter(
            general_conference_id=request.user.scope_general_conference_id
        )
    if level == OrgScopeLevel.UNION and request.user.scope_union_id:
        return Union.objects.filter(pk=request.user.scope_union_id)
    return Union.objects.filter(conferences__in=scoped_conferences(request)).distinct()


def scoped_general_conferences(request):
    from permissions.org_scope import OrgScopeLevel, infer_scope_level

    level = infer_scope_level(request.user)
    if level == OrgScopeLevel.GENERAL_CONFERENCE and request.user.scope_general_conference_id:
        return GeneralConference.objects.filter(pk=request.user.scope_general_conference_id)
    if level == OrgScopeLevel.UNION and request.user.scope_union_id:
        return GeneralConference.objects.filter(
            unions__pk=request.user.scope_union_id
        ).distinct()
    return GeneralConference.objects.filter(
        unions__conferences__in=scoped_conferences(request)
    ).distinct()


# ---------------------------------------------------------------------------
# Hierarchy overview
# ---------------------------------------------------------------------------


def empty_general_conferences():
    return GeneralConference.objects.none()


def hierarchy_conf_base(request, search_q=""):
    """Conferences in scope, optionally narrowed by hierarchy search."""
    conf_base = scoped_conferences(request)
    if not search_q:
        return conf_base
    matching_church_confs = scoped_churches(request).filter(
        Q(name__icontains=search_q) | Q(code__icontains=search_q)
    ).values_list("district__zone__conference_id", flat=True)
    return conf_base.filter(
        Q(name__icontains=search_q)
        | Q(code__icontains=search_q)
        | Q(pk__in=matching_church_confs)
    )


def hierarchy_tree_prefetch(conf_base):
    return conf_base.prefetch_related("zones__districts__churches")


def hierarchy_general_conferences(request, conf_base):
    unions = Union.objects.filter(conferences__in=conf_base).distinct().prefetch_related(
        Prefetch("conferences", queryset=hierarchy_tree_prefetch(conf_base))
    )
    return (
        scoped_general_conferences(request)
        .filter(unions__in=unions)
        .distinct()
        .prefetch_related(Prefetch("unions", queryset=unions))
        .order_by("name")
    )


def hierarchy_orphan_conferences(conf_base):
    return (
        conf_base.filter(union__isnull=True)
        .prefetch_related("zones__districts__churches")
        .order_by("name")
    )


def hierarchy_level_stat_qs(request, conf_base):
    """Map of hierarchy level key → queryset for counts."""
    church_qs = scoped_churches(request)
    return {
        "general_conference": GeneralConference.objects.filter(
            unions__conferences__in=conf_base
        ).distinct(),
        "union": Union.objects.filter(conferences__in=conf_base).distinct(),
        "conference": conf_base,
        "zone": Zone.objects.filter(conference__in=conf_base),
        "district": District.objects.filter(zone__conference__in=conf_base),
        "church": church_qs,
    }


# ---------------------------------------------------------------------------
# Directory
# ---------------------------------------------------------------------------


def _filter_name_code(qs, q):
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs


def directory_general_conferences(request, q=""):
    qs = scoped_general_conferences(request).annotate(
        union_count=Count("unions", distinct=True)
    ).order_by("name")
    return _filter_name_code(qs, q)


def directory_unions(request, q=""):
    qs = scoped_unions(request).select_related("general_conference").annotate(
        conference_count=Count("conferences", distinct=True)
    ).order_by("name")
    return _filter_name_code(qs, q)


def directory_conferences(request, q=""):
    qs = scoped_conferences(request).select_related("union").annotate(
        zone_count=Count("zones", distinct=True)
    ).order_by("name")
    return _filter_name_code(qs, q)


def directory_zones(request, q=""):
    qs = scoped_zones(request).select_related("conference").annotate(
        district_count=Count("districts", distinct=True)
    ).order_by("name")
    return _filter_name_code(qs, q)


def directory_districts(request, q=""):
    qs = scoped_districts(request).select_related("zone__conference").annotate(
        church_count=Count("churches", distinct=True)
    ).order_by("name")
    return _filter_name_code(qs, q)


def directory_churches(request, q=""):
    qs = scoped_churches(request).select_related(
        "district__zone__conference"
    ).order_by("name")
    return _filter_name_code(qs, q)


# ---------------------------------------------------------------------------
# Detail annotations
# ---------------------------------------------------------------------------


def conference_for_detail(pk):
    return Conference.objects.annotate(zone_count=Count("zones")).get(pk=pk)


def zones_for_conference(conference):
    return conference.zones.annotate(district_count=Count("districts")).order_by("name")


def zone_for_detail(pk):
    return (
        Zone.objects.select_related("conference")
        .annotate(district_count=Count("districts"))
        .get(pk=pk)
    )


def districts_for_zone(zone):
    return zone.districts.annotate(church_count=Count("churches")).order_by("name")


def district_for_detail(pk):
    return (
        District.objects.select_related("zone__conference")
        .annotate(church_count=Count("churches"))
        .get(pk=pk)
    )


def churches_for_district(district):
    return district.churches.order_by("name")


def general_conference_for_detail(pk):
    return GeneralConference.objects.annotate(union_count=Count("unions")).get(pk=pk)


def unions_for_general_conference(gc):
    return gc.unions.annotate(conference_count=Count("conferences")).order_by("name")


def union_for_detail(pk):
    return (
        Union.objects.select_related("general_conference")
        .annotate(conference_count=Count("conferences"))
        .get(pk=pk)
    )


def conferences_for_union(union):
    return union.conferences.annotate(zone_count=Count("zones")).order_by("name")


def active_member_count(church):
    return Member.objects.filter(church=church, is_active=True).count()


def church_account_count(church):
    return church.accounts.count()


def church_transaction_count(church):
    return church.transactions.count()


# ---------------------------------------------------------------------------
# Export / reconcile / lookup
# ---------------------------------------------------------------------------


def churches_for_export(request):
    return (
        scoped_churches(request)
        .select_related("district__zone__conference__denomination")
        .order_by(
            "district__zone__conference__name",
            "district__zone__name",
            "district__name",
            "name",
        )
    )


def churches_for_reconcile(denomination=None):
    qs = Church.objects.select_related("district__zone__conference")
    if denomination:
        qs = qs.filter(district__zone__conference__denomination=denomination)
    return qs


def orphan_conferences_qs():
    return Conference.objects.filter(denomination__isnull=True)


def conference_by_code(code):
    return Conference.objects.filter(code=code).first()


def church_code_exists_in_district(district, code, *, exclude_pk=None):
    qs = Church.objects.filter(district=district, code=code)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return qs.exists()


def church_has_subscription(church):
    from sitecontrol.models import TenantSubscription

    return TenantSubscription.objects.filter(church=church).exists()


# ---------------------------------------------------------------------------
# Form / dropdown querysets (denomination + parent locks)
# ---------------------------------------------------------------------------


def zones_for_denomination(denomination):
    return Zone.objects.filter(conference__denomination=denomination).select_related(
        "conference"
    )


def districts_for_denomination(denomination):
    return District.objects.filter(
        zone__conference__denomination=denomination
    ).select_related("zone__conference")


def general_conference_by_pk(pk):
    return GeneralConference.objects.filter(pk=pk)


def conference_by_pk(pk):
    return Conference.objects.filter(pk=pk)


def zone_by_pk(pk):
    return Zone.objects.filter(pk=pk).select_related("conference")


def all_districts_with_parents():
    return District.objects.all().select_related("zone__conference")


def empty_districts():
    return District.objects.none()


def transfer_target_districts(request, church):
    from organization.access import scoped_districts

    qs = scoped_districts(request).exclude(pk=church.district_id)
    denom_id = church.conference.denomination_id if church.conference else None
    if denom_id:
        qs = qs.filter(zone__conference__denomination_id=denom_id)
    return qs.select_related("zone__conference")


def get_conference_or_404(qs, pk):
    return get_object_or_404(qs, pk=pk)


def get_zone_or_404(qs, pk):
    return get_object_or_404(qs.select_related("conference"), pk=pk)


def get_district_or_404(qs, pk):
    return get_object_or_404(qs.select_related("zone__conference"), pk=pk)


def get_church_or_404(qs, pk):
    return get_object_or_404(
        qs.select_related("district__zone__conference__union__general_conference"),
        pk=pk,
    )


def get_union_or_404(qs, pk):
    return get_object_or_404(qs.select_related("general_conference"), pk=pk)


def get_general_conference_or_404(qs, pk):
    return get_object_or_404(qs, pk=pk)
