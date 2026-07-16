"""Organization hierarchy views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.shortcuts import redirect, render

from church_system.church_scope import get_active_church
from church_system.flash import flash_error, flash_exception, flash_success, flash_warning
from members.models import Member
from organization.access import (
    assert_can_manage_church,
    assert_global_structure_manage,
    get_scoped_church,
    get_scoped_conference,
    get_scoped_district,
    get_scoped_general_conference,
    get_scoped_union,
    get_scoped_zone,
    is_district_scoped_user,
    is_global_org_admin,
    require_org_manage,
    require_org_read,
    scoped_churches,
    scoped_conferences,
    scoped_districts,
    scoped_general_conferences,
    scoped_unions,
    scoped_zones,
    user_district,
)
from organization.forms import (
    ChurchForm,
    ChurchOnboardingForm,
    ChurchTransferForm,
    ConferenceForm,
    DistrictForm,
    FullChurchOnboardingForm,
    GeneralConferenceForm,
    UnionForm,
    ZoneForm,
)
from organization.models import Church, Conference, District, GeneralConference, Union, Zone
from organization.services import (
    create_church,
    export_hierarchy_rows,
    get_client_ip,
    log_org_audit,
    onboard_full_hierarchy,
    provision_church,
    set_church_active,
    transfer_church,
    update_church,
)
from permissions.checks import can_manage_organization


@login_required
def hierarchy_overview(request):
    """Read-only organization tree for hierarchy-level users."""
    require_org_read(request)

    if is_district_scoped_user(request.user):
        district = user_district(request.user)
        if district:
            return redirect("organization:district_detail", pk=district.pk)

    from church_system.denomination_scope import (
        churches_for_denomination,
        get_active_denomination,
    )
    from sitecontrol.denomination_services import (
        get_level_label,
        hierarchy_chain_description,
        level_enabled,
    )

    denomination = get_active_denomination(request)
    active_church = get_active_church(request)
    search_q = request.GET.get("q", "").strip()

    conf_base = scoped_conferences(request)
    if search_q:
        matching_church_confs = scoped_churches(request).filter(
            Q(name__icontains=search_q) | Q(code__icontains=search_q)
        ).values_list("district__zone__conference_id", flat=True)
        conf_base = conf_base.filter(
            Q(name__icontains=search_q)
            | Q(code__icontains=search_q)
            | Q(pk__in=matching_church_confs)
        )

    conf_prefetch = conf_base.prefetch_related("zones__districts__churches")

    general_conferences = GeneralConference.objects.none()
    if not denomination or level_enabled(denomination, "general_conference"):
        unions = Union.objects.filter(conferences__in=conf_base).distinct().prefetch_related(
            Prefetch("conferences", queryset=conf_prefetch)
        )
        general_conferences = (
            scoped_general_conferences(request)
            .filter(unions__in=unions)
            .distinct()
            .prefetch_related(Prefetch("unions", queryset=unions))
            .order_by("name")
        )

    orphan_conferences = conf_base.filter(union__isnull=True).prefetch_related(
        "zones__districts__churches"
    ).order_by("name")

    stats = {}
    church_qs = scoped_churches(request)
    level_stat_map = [
        ("general_conference", GeneralConference.objects.filter(unions__conferences__in=conf_base).distinct()),
        ("union", Union.objects.filter(conferences__in=conf_base).distinct()),
        ("conference", conf_base),
        ("zone", Zone.objects.filter(conference__in=conf_base)),
        ("district", District.objects.filter(zone__conference__in=conf_base)),
        ("church", church_qs),
    ]
    for key, qs in level_stat_map:
        if level_enabled(denomination, key):
            label = get_level_label(denomination, key, plural=True)
            if label:
                stats[label] = qs.count()

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        from reports.exporters import export_table_csv, export_table_excel

        headers, rows = export_hierarchy_rows(request)
        slug = "organization-hierarchy"
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        return export_table_excel(headers, rows, f"{slug}.xlsx", "Organization Hierarchy")

    return render(request, "organization/hierarchy.html", {
        "general_conferences": general_conferences,
        "orphan_conferences": orphan_conferences,
        "active_church": active_church,
        "stats": stats,
        "hierarchy_chain": hierarchy_chain_description(denomination),
        "can_manage": can_manage_organization(request.user),
        "search_q": search_q,
        "is_global_admin": is_global_org_admin(request.user),
    })


@login_required
def unit_directory(request):
    """Tabbed list of all hierarchy units in scope (GC, unions, conferences, zones, districts, churches)."""
    require_org_read(request)
    from sitecontrol.denomination_services import get_level_label, level_enabled
    from church_system.denomination_scope import get_active_denomination

    denomination = get_active_denomination(request)
    level = (request.GET.get("level") or "church").strip().lower()
    q = request.GET.get("q", "").strip()

    tabs = []
    level_map = [
        ("general_conference", "general_conference"),
        ("union", "union"),
        ("conference", "conference"),
        ("zone", "zone"),
        ("district", "district"),
        ("church", "church"),
    ]
    for key, slug in level_map:
        if level_enabled(denomination, key):
            tabs.append({
                "slug": slug,
                "label": get_level_label(denomination, key, plural=True) or slug.title(),
            })
    if not tabs:
        tabs = [{"slug": "church", "label": "Churches"}]
    valid_slugs = {t["slug"] for t in tabs}
    if level not in valid_slugs:
        level = tabs[0]["slug"]

    rows = []
    if level == "general_conference":
        qs = scoped_general_conferences(request).annotate(
            union_count=Count("unions", distinct=True)
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": f"{obj.union_count} unions",
                "url_name": "organization:general_conference_detail",
                "pk": obj.pk,
            })
    elif level == "union":
        qs = scoped_unions(request).select_related("general_conference").annotate(
            conference_count=Count("conferences", distinct=True)
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.general_conference.name if obj.general_conference_id else "—",
                "extra": f"{obj.conference_count} conferences",
                "url_name": "organization:union_detail",
                "pk": obj.pk,
            })
    elif level == "conference":
        qs = scoped_conferences(request).select_related("union").annotate(
            zone_count=Count("zones", distinct=True)
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.union.name if obj.union_id else "—",
                "extra": f"{obj.zone_count} zones",
                "url_name": "organization:conference_detail",
                "pk": obj.pk,
            })
    elif level == "zone":
        qs = scoped_zones(request).select_related("conference").annotate(
            district_count=Count("districts", distinct=True)
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.conference.name,
                "extra": f"{obj.district_count} districts",
                "url_name": "organization:zone_detail",
                "pk": obj.pk,
            })
    elif level == "district":
        qs = scoped_districts(request).select_related("zone__conference").annotate(
            church_count=Count("churches", distinct=True)
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": f"{obj.zone.name} · {obj.zone.conference.name}",
                "extra": f"{obj.church_count} churches",
                "url_name": "organization:district_detail",
                "pk": obj.pk,
            })
    else:
        qs = scoped_churches(request).select_related(
            "district__zone__conference"
        ).order_by("name")
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
        for obj in qs[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": f"{obj.district.name} · {obj.district.zone.conference.name}",
                "extra": "Active" if obj.is_active else "Inactive",
                "url_name": "organization:church_detail",
                "pk": obj.pk,
                "badge": "success" if obj.is_active else "secondary",
            })

    return render(request, "organization/directory.html", {
        "tabs": tabs,
        "level": level,
        "rows": rows,
        "search_q": q,
        "can_manage": can_manage_organization(request.user),
        "active_level_label": next((t["label"] for t in tabs if t["slug"] == level), level.title()),
    })


@login_required
def conference_detail(request, pk):
    require_org_read(request)
    conference = get_scoped_conference(request, pk)
    conference = Conference.objects.annotate(zone_count=Count("zones")).get(pk=conference.pk)
    zones = conference.zones.annotate(district_count=Count("districts")).order_by("name")
    return render(request, "organization/conference_detail.html", {
        "conference": conference,
        "zones": zones,
        "can_manage": can_manage_organization(request.user) and is_global_org_admin(request.user),
    })


@login_required
def conference_create(request):
    assert_global_structure_manage(request)
    form = ConferenceForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        conference = form.save()
        log_org_audit(
            "CREATE",
            conference,
            performed_by=request.user,
            ip_address=get_client_ip(request),
        )
        flash_success(request, f"Conference “{conference.name}” created.")
        return redirect("organization:conference_detail", pk=conference.pk)
    return render(request, "organization/conference_form.html", {
        "form": form,
        "title": "Add Conference",
    })


@login_required
def conference_edit(request, pk):
    assert_global_structure_manage(request)
    conference = get_scoped_conference(request, pk)
    form = ConferenceForm(request.POST or None, instance=conference, request=request)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_org_audit("UPDATE", conference, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "Conference updated.")
        return redirect("organization:conference_detail", pk=pk)
    return render(request, "organization/conference_form.html", {
        "form": form,
        "title": "Edit Conference",
        "object": conference,
    })


@login_required
def zone_detail(request, pk):
    require_org_read(request)
    zone = get_scoped_zone(request, pk)
    zone = Zone.objects.select_related("conference").annotate(district_count=Count("districts")).get(pk=zone.pk)
    districts = zone.districts.annotate(church_count=Count("churches")).order_by("name")
    return render(request, "organization/zone_detail.html", {
        "zone": zone,
        "districts": districts,
        "can_manage": can_manage_organization(request.user) and is_global_org_admin(request.user),
    })


@login_required
def zone_create(request):
    assert_global_structure_manage(request)
    conference = None
    conf_pk = request.GET.get("conference")
    if conf_pk:
        conference = get_scoped_conference(request, conf_pk)
    form = ZoneForm(request.POST or None, conference=conference, request=request)
    if request.method == "POST" and form.is_valid():
        zone = form.save()
        log_org_audit("CREATE", zone, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, f"Zone “{zone.name}” created.")
        return redirect("organization:zone_detail", pk=zone.pk)
    return render(request, "organization/zone_form.html", {
        "form": form,
        "title": "Add Zone",
        "conference": conference,
    })


@login_required
def zone_edit(request, pk):
    assert_global_structure_manage(request)
    zone = get_scoped_zone(request, pk)
    form = ZoneForm(request.POST or None, instance=zone, request=request)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_org_audit("UPDATE", zone, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "Zone updated.")
        return redirect("organization:zone_detail", pk=pk)
    return render(request, "organization/zone_form.html", {
        "form": form,
        "title": "Edit Zone",
        "object": zone,
    })


@login_required
def district_detail(request, pk):
    require_org_read(request)
    district = get_scoped_district(request, pk)
    district = District.objects.select_related("zone__conference").annotate(
        church_count=Count("churches")
    ).get(pk=district.pk)
    churches_qs = district.churches.order_by("name")
    paginator = Paginator(churches_qs, 25)
    churches_page = paginator.get_page(request.GET.get("page"))
    return render(request, "organization/district_detail.html", {
        "district": district,
        "churches": churches_page,
        "can_manage": can_manage_organization(request.user),
    })


@login_required
def district_create(request):
    assert_global_structure_manage(request)
    zone = None
    zone_pk = request.GET.get("zone")
    if zone_pk:
        zone = get_scoped_zone(request, zone_pk)
    form = DistrictForm(request.POST or None, zone=zone, request=request)
    if request.method == "POST" and form.is_valid():
        district = form.save()
        log_org_audit("CREATE", district, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, f"District “{district.name}” created.")
        return redirect("organization:district_detail", pk=district.pk)
    return render(request, "organization/district_form.html", {
        "form": form,
        "title": "Add District",
        "zone": zone,
    })


@login_required
def district_edit(request, pk):
    assert_global_structure_manage(request)
    district = get_scoped_district(request, pk)
    form = DistrictForm(request.POST or None, instance=district, request=request)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_org_audit("UPDATE", district, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "District updated.")
        return redirect("organization:district_detail", pk=pk)
    return render(request, "organization/district_form.html", {
        "form": form,
        "title": "Edit District",
        "object": district,
    })


@login_required
def church_detail(request, pk):
    require_org_read(request)
    church = get_scoped_church(request, pk)
    member_count = Member.objects.filter(church=church, is_active=True).count()
    return render(request, "organization/church_detail.html", {
        "church": church,
        "member_count": member_count,
        "account_count": church.accounts.count(),
        "txn_count": church.transactions.count(),
        "can_manage": can_manage_organization(request.user),
        "is_global_admin": is_global_org_admin(request.user),
    })


@login_required
def church_create(request):
    require_org_manage(request)
    district = None
    district_pk = request.GET.get("district")
    if district_pk:
        district = get_scoped_district(request, district_pk)
        if is_district_scoped_user(request.user) and district.pk != request.user.church.district_id:
            raise PermissionDenied
    form = ChurchForm(request.POST or None, district=district, request=request)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        target_district = data["district"]
        if is_district_scoped_user(request.user) and target_district.pk != request.user.church.district_id:
            raise PermissionDenied
        try:
            church, created = create_church(
                district=target_district,
                name=data["name"],
                code=data["code"],
                address=data.get("address", ""),
                setup_financials=True,
                performed_by=request.user,
                ip_address=get_client_ip(request),
            )
        except ValueError as exc:
            flash_error(request, str(exc))
            return render(request, "organization/church_form.html", {
                "form": form,
                "title": "Add Church",
                "district": district,
            })
        flash_success(request, f"Church “{church.name}” created.")
        return redirect("organization:church_detail", pk=church.pk)
    return render(request, "organization/church_form.html", {
        "form": form,
        "title": "Add Church",
        "district": district,
    })


@login_required
def church_edit(request, pk):
    require_org_manage(request)
    church = get_scoped_church(request, pk)
    assert_can_manage_church(request, church)
    form = ChurchForm(
        request.POST or None,
        instance=church,
        request=request,
        show_status=is_global_org_admin(request.user),
    )
    if request.method == "POST" and form.is_valid():
        try:
            data = form.cleaned_data
            update_church(
                church,
                performed_by=request.user,
                ip_address=get_client_ip(request),
                name=data["name"],
                code=data["code"],
                address=data.get("address", ""),
                **({"is_active": data["is_active"]} if "is_active" in data else {}),
            )
        except ValidationError as exc:
            flash_exception(request, exc)
            return render(request, "organization/church_form.html", {
                "form": form,
                "title": "Edit Church",
                "object": church,
            })
        flash_success(request, "Church updated.")
        return redirect("organization:church_detail", pk=pk)
    return render(request, "organization/church_form.html", {
        "form": form,
        "title": "Edit Church",
        "object": church,
    })


@login_required
def church_transfer(request, pk):
    require_org_manage(request)
    church = get_scoped_church(request, pk)
    assert_can_manage_church(request, church)
    if not is_global_org_admin(request.user):
        raise PermissionDenied("Church transfers require conference-level administration.")
    form = ChurchTransferForm(request.POST or None, church=church, request=request)
    if request.method == "POST" and form.is_valid():
        try:
            transfer_church(
                church,
                form.cleaned_data["district"],
                performed_by=request.user,
                ip_address=get_client_ip(request),
                reason=form.cleaned_data.get("reason", ""),
            )
        except ValidationError as exc:
            flash_exception(request, exc)
            return render(request, "organization/church_transfer.html", {"form": form, "church": church})
        flash_success(request, f"Church “{church.name}” transferred to {church.district.name}.")
        return redirect("organization:church_detail", pk=pk)
    return render(request, "organization/church_transfer.html", {"form": form, "church": church})


@login_required
def church_toggle_active(request, pk):
    require_org_manage(request)
    church = get_scoped_church(request, pk)
    assert_can_manage_church(request, church)
    if request.method != "POST":
        return redirect("organization:church_detail", pk=pk)
    active = not church.is_active
    set_church_active(
        church,
        active,
        performed_by=request.user,
        ip_address=get_client_ip(request),
    )
    flash_success(request, f"Church “{church.name}” marked as {'active' if active else 'inactive'}.")
    return redirect("organization:church_detail", pk=pk)


@login_required
def church_onboard(request):
    """Wizard: add church to existing district or create full hierarchy."""
    require_org_manage(request)
    from sitecontrol.registration_services import institution_onboarding_allowed

    if not institution_onboarding_allowed():
        flash_error(
            request,
            "Church onboarding is disabled by the platform administrator.",
            title="Onboarding disabled",
        )
        return redirect("organization:hierarchy")

    mode = request.GET.get("mode", "existing")
    if request.method == "POST":
        mode = request.POST.get("mode", mode)

    ip = get_client_ip(request)

    if mode == "full":
        if is_district_scoped_user(request.user):
            raise PermissionDenied("District pastors cannot create full hierarchy paths.")
        form = FullChurchOnboardingForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            from church_system.denomination_scope import get_active_denomination

            try:
                church, created = onboard_full_hierarchy(
                    conference_name=data["conference_name"],
                    conference_code=data["conference_code"],
                    zone_name=data["zone_name"],
                    zone_code=data["zone_code"],
                    district_name=data["district_name"],
                    district_code=data["district_code"],
                    church_name=data["church_name"],
                    church_code=data["church_code"],
                    address=data.get("address", ""),
                    setup_financials=data.get("setup_financials", True),
                    denomination=get_active_denomination(request),
                    performed_by=request.user,
                    ip_address=ip,
                )
            except ValueError as exc:
                flash_error(request, str(exc))
                return render(request, "organization/church_onboard.html", {"form": form, "mode": mode})
            if created:
                flash_success(request, f"Church “{church.name}” onboarded with full hierarchy.")
            else:
                flash_warning(request, f"Church with code {church.code} already exists — details updated.")
            return redirect("organization:church_detail", pk=church.pk)
    else:
        form = ChurchOnboardingForm(request.POST or None, request=request)
        if request.method == "POST" and form.is_valid():
            data = form.cleaned_data
            try:
                church, created = create_church(
                    district=data["district"],
                    name=data["name"],
                    code=data["code"],
                    address=data.get("address", ""),
                    setup_financials=data.get("setup_financials", True),
                    performed_by=request.user,
                    ip_address=ip,
                )
            except ValueError as exc:
                flash_error(request, str(exc))
                return render(request, "organization/church_onboard.html", {"form": form, "mode": mode})
            if created:
                flash_success(request, f"Church “{church.name}” onboarded.")
            else:
                flash_warning(request, f"Church with code {church.code} already exists — details updated.")
            return redirect("organization:church_detail", pk=church.pk)

    return render(request, "organization/church_onboard.html", {
        "form": form,
        "mode": mode,
        "allow_full_mode": is_global_org_admin(request.user),
    })


@login_required
def general_conference_detail(request, pk):
    require_org_read(request)
    gc = get_scoped_general_conference(request, pk)
    gc = GeneralConference.objects.annotate(union_count=Count("unions")).get(pk=gc.pk)
    unions = gc.unions.annotate(conference_count=Count("conferences")).order_by("name")
    return render(request, "organization/general_conference_detail.html", {
        "general_conference": gc,
        "unions": unions,
        "can_manage": can_manage_organization(request.user) and is_global_org_admin(request.user),
    })


@login_required
def general_conference_create(request):
    assert_global_structure_manage(request)
    form = GeneralConferenceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        gc = form.save()
        log_org_audit("CREATE", gc, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, f"General Conference “{gc.name}” created.")
        return redirect("organization:general_conference_detail", pk=gc.pk)
    return render(request, "organization/general_conference_form.html", {
        "form": form,
        "title": "Add General Conference",
    })


@login_required
def general_conference_edit(request, pk):
    assert_global_structure_manage(request)
    gc = get_scoped_general_conference(request, pk)
    form = GeneralConferenceForm(request.POST or None, instance=gc)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_org_audit("UPDATE", gc, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "General Conference updated.")
        return redirect("organization:general_conference_detail", pk=pk)
    return render(request, "organization/general_conference_form.html", {
        "form": form,
        "title": "Edit General Conference",
        "object": gc,
    })


@login_required
def union_detail(request, pk):
    require_org_read(request)
    union = get_scoped_union(request, pk)
    union = Union.objects.select_related("general_conference").annotate(
        conference_count=Count("conferences")
    ).get(pk=union.pk)
    conferences = union.conferences.annotate(zone_count=Count("zones")).order_by("name")
    return render(request, "organization/union_detail.html", {
        "union": union,
        "conferences": conferences,
        "can_manage": can_manage_organization(request.user) and is_global_org_admin(request.user),
    })


@login_required
def union_create(request):
    assert_global_structure_manage(request)
    general_conference = None
    gc_pk = request.GET.get("general_conference")
    if gc_pk:
        general_conference = get_scoped_general_conference(request, gc_pk)
    form = UnionForm(request.POST or None, general_conference=general_conference, request=request)
    if request.method == "POST" and form.is_valid():
        union = form.save()
        log_org_audit("CREATE", union, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, f"Union “{union.name}” created.")
        return redirect("organization:union_detail", pk=union.pk)
    return render(request, "organization/union_form.html", {
        "form": form,
        "title": "Add Union",
        "general_conference": general_conference,
    })


@login_required
def union_edit(request, pk):
    assert_global_structure_manage(request)
    union = get_scoped_union(request, pk)
    form = UnionForm(request.POST or None, instance=union, request=request)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_org_audit("UPDATE", union, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "Union updated.")
        return redirect("organization:union_detail", pk=pk)
    return render(request, "organization/union_form.html", {
        "form": form,
        "title": "Edit Union",
        "object": union,
    })
