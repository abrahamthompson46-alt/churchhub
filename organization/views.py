"""Organization hierarchy views."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect, render

from church_system.church_scope import get_active_church
from church_system.flash import flash_error, flash_exception, flash_success, flash_warning
from organization import repositories as repo
from organization import selectors
from organization.access import (
    assert_can_manage_church,
    assert_can_manage_district,
    assert_global_structure_manage,
    assert_subtree_structure_manage,
    can_manage_subtree_structure,
    can_transfer_churches,
    get_scoped_church,
    get_scoped_conference,
    get_scoped_district,
    get_scoped_general_conference,
    get_scoped_union,
    get_scoped_zone,
    is_district_scoped_user,
    is_global_org_admin,
    org_capability_flags,
    require_org_manage,
    require_org_read,
    user_district,
)
from organization.forms import (
    ChurchForm,
    ChurchHistoryEntryForm,
    ChurchHistorySearchForm,
    ChurchOnboardingForm,
    ChurchTransferForm,
    ConferenceForm,
    DistrictForm,
    FullChurchOnboardingForm,
    GeneralConferenceForm,
    UnionForm,
    ZoneForm,
)
from organization.services import (
    create_church,
    create_church_history_entry,
    export_hierarchy_rows,
    get_client_ip,
    get_scoped_history_entry,
    log_org_audit,
    onboard_full_hierarchy,
    search_church_history_entries,
    set_church_active,
    transfer_church,
    update_church,
    update_church_history_entry,
)
from permissions.checks import (
    any_permission_required,
    can_manage_church_history,
    can_manage_organization,
    can_view_church_history,
    permission_required,
)
from permissions.scoping import get_manageable_churches

@login_required
def hierarchy_overview(request):
    """Read-only organization tree for hierarchy-level users."""
    require_org_read(request)

    if is_district_scoped_user(request.user):
        district = user_district(request.user)
        if district:
            return redirect("organization:district_detail", pk=district.pk)

    from church_system.denomination_scope import get_active_denomination
    from sitecontrol.denomination_services import (
        get_level_label,
        hierarchy_chain_description,
        level_enabled,
    )

    denomination = get_active_denomination(request)
    active_church = get_active_church(request)
    search_q = request.GET.get("q", "").strip()

    conf_base = selectors.hierarchy_conf_base(request, search_q)

    general_conferences = selectors.empty_general_conferences()
    if not denomination or level_enabled(denomination, "general_conference"):
        general_conferences = selectors.hierarchy_general_conferences(request, conf_base)

    orphan_conferences = selectors.hierarchy_orphan_conferences(conf_base)

    stats = {}
    level_stat_map = selectors.hierarchy_level_stat_qs(request, conf_base)
    for key, qs in level_stat_map.items():
        if level_enabled(denomination, key):
            label = get_level_label(denomination, key, plural=True)
            if label:
                stats[label] = qs.count()

    export_fmt = request.GET.get("export", "")
    if export_fmt in ("csv", "excel"):
        from reports.exporters import export_table_csv, export_table_excel
        from reports.services import audit_export

        headers, rows = export_hierarchy_rows(request)
        slug = "organization-hierarchy"
        audit_export(
            user=request.user,
            report_key="organization_hierarchy",
            export_format=export_fmt,
            row_count=len(rows),
            church=active_church,
            params={"search_q": search_q},
        )
        if export_fmt == "csv":
            return export_table_csv(headers, rows, f"{slug}.csv")
        return export_table_excel(headers, rows, f"{slug}.xlsx", "Organization Hierarchy")

    return render(request, "organization/hierarchy.html", {
        "general_conferences": general_conferences,
        "orphan_conferences": orphan_conferences,
        "active_church": active_church,
        "stats": stats,
        "hierarchy_chain": hierarchy_chain_description(denomination),
        "search_q": search_q,
        **org_capability_flags(request.user),
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
        for obj in selectors.directory_general_conferences(request, q)[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": f"{obj.union_count} unions",
                "url_name": "organization:general_conference_detail",
                "pk": obj.pk,
            })
    elif level == "union":
        for obj in selectors.directory_unions(request, q)[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.general_conference.name if obj.general_conference_id else "—",
                "extra": f"{obj.conference_count} conferences",
                "url_name": "organization:union_detail",
                "pk": obj.pk,
            })
    elif level == "conference":
        for obj in selectors.directory_conferences(request, q)[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.union.name if obj.union_id else "—",
                "extra": f"{obj.zone_count} zones",
                "url_name": "organization:conference_detail",
                "pk": obj.pk,
            })
    elif level == "zone":
        for obj in selectors.directory_zones(request, q)[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": obj.conference.name,
                "extra": f"{obj.district_count} districts",
                "url_name": "organization:zone_detail",
                "pk": obj.pk,
            })
    elif level == "district":
        for obj in selectors.directory_districts(request, q)[:500]:
            rows.append({
                "name": obj.name,
                "code": obj.code,
                "meta": f"{obj.zone.name} · {obj.zone.conference.name}",
                "extra": f"{obj.church_count} churches",
                "url_name": "organization:district_detail",
                "pk": obj.pk,
            })
    else:
        for obj in selectors.directory_churches(request, q)[:500]:
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
    conference = selectors.conference_for_detail(conference.pk)
    zones = selectors.zones_for_conference(conference)
    manageable_ids = list(get_manageable_churches(request.user).values_list("pk", flat=True))
    history_count = 0
    if can_view_church_history(request.user):
        history_count = selectors.church_history_count_for_conference(
            conference, church_ids=manageable_ids
        )
    return render(request, "organization/conference_detail.html", {
        "conference": conference,
        "zones": zones,
        "history_count": history_count,
        "can_view_church_history": can_view_church_history(request.user),
        "can_manage_church_history": can_manage_church_history(request.user),
        **org_capability_flags(request.user),
        "can_manage": (
            can_manage_organization(request.user)
            and can_manage_subtree_structure(request.user)
        ),
    })


@login_required
def conference_create(request):
    assert_global_structure_manage(request)
    form = ConferenceForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        conference = form.save(commit=False)
        repo.save_conference(conference)
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
        conference = form.save(commit=False)
        repo.save_conference(conference)
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
    zone = selectors.zone_for_detail(zone.pk)
    districts = selectors.districts_for_zone(zone)
    return render(request, "organization/zone_detail.html", {
        "zone": zone,
        "districts": districts,
        **org_capability_flags(request.user),
        "can_manage": (
            can_manage_organization(request.user)
            and can_manage_subtree_structure(request.user)
        ),
    })


@login_required
def zone_create(request):
    assert_subtree_structure_manage(request)
    conference = None
    conf_pk = request.GET.get("conference")
    if conf_pk:
        conference = get_scoped_conference(request, conf_pk)
    form = ZoneForm(request.POST or None, conference=conference, request=request)
    if request.method == "POST" and form.is_valid():
        zone = form.save(commit=False)
        repo.save_zone(zone)
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
    assert_subtree_structure_manage(request)
    zone = get_scoped_zone(request, pk)
    form = ZoneForm(request.POST or None, instance=zone, request=request)
    if request.method == "POST" and form.is_valid():
        zone = form.save(commit=False)
        repo.save_zone(zone)
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
    district = selectors.district_for_detail(district.pk)
    churches_qs = selectors.churches_for_district(district)
    paginator = Paginator(churches_qs, 25)
    churches_page = paginator.get_page(request.GET.get("page"))
    flags = org_capability_flags(request.user)
    return render(request, "organization/district_detail.html", {
        "district": district,
        "churches": churches_page,
        "can_edit_district": flags["can_manage"],
        **flags,
    })


@login_required
def district_create(request):
    assert_subtree_structure_manage(request)
    zone = None
    zone_pk = request.GET.get("zone")
    if zone_pk:
        zone = get_scoped_zone(request, zone_pk)
    form = DistrictForm(request.POST or None, zone=zone, request=request)
    if request.method == "POST" and form.is_valid():
        district = form.save(commit=False)
        repo.save_district(district)
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
    district = get_scoped_district(request, pk)
    assert_can_manage_district(request, district)
    form = DistrictForm(request.POST or None, instance=district, request=request)
    if request.method == "POST" and form.is_valid():
        district = form.save(commit=False)
        repo.save_district(district)
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
    member_count = selectors.active_member_count(church)
    history_count = 0
    if can_view_church_history(request.user):
        history_count = selectors.church_history_count_for_church(church)
    return render(request, "organization/church_detail.html", {
        "church": church,
        "member_count": member_count,
        "account_count": selectors.church_account_count(church),
        "txn_count": selectors.church_transaction_count(church),
        "history_count": history_count,
        "can_view_church_history": can_view_church_history(request.user),
        "can_manage_church_history": can_manage_church_history(request.user),
        **org_capability_flags(request.user),
    })


@login_required
def church_create(request):
    require_org_manage(request)
    district = None
    district_pk = request.GET.get("district") or request.POST.get("district")
    if district_pk:
        district = get_scoped_district(request, district_pk)
        actor_district = user_district(request.user)
        if is_district_scoped_user(request.user) and (
            actor_district is None or district.pk != actor_district.pk
        ):
            raise PermissionDenied
    form = ChurchForm(request.POST or None, district=district, request=request)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        target_district = data.get("district") or district
        if target_district is None:
            form.add_error("district", "Select a district for this church.")
        else:
            actor_district = user_district(request.user)
            if is_district_scoped_user(request.user) and (
                actor_district is None or target_district.pk != actor_district.pk
            ):
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
    if not can_transfer_churches(request.user):
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
    gc = selectors.general_conference_for_detail(gc.pk)
    unions = selectors.unions_for_general_conference(gc)
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
        gc = form.save(commit=False)
        repo.save_general_conference(gc)
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
        gc = form.save(commit=False)
        repo.save_general_conference(gc)
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
    union = selectors.union_for_detail(union.pk)
    conferences = selectors.conferences_for_union(union)
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
        union = form.save(commit=False)
        repo.save_union(union)
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
        union = form.save(commit=False)
        repo.save_union(union)
        log_org_audit("UPDATE", union, performed_by=request.user, ip_address=get_client_ip(request))
        flash_success(request, "Union updated.")
        return redirect("organization:union_detail", pk=pk)
    return render(request, "organization/union_form.html", {
        "form": form,
        "title": "Edit Union",
        "object": union,
    })


def _history_scope_churches(user):
    return get_manageable_churches(user).select_related(
        "district__zone__conference"
    ).order_by("name")


def _history_scope_conferences(user):
    from organization.models import Conference

    church_ids = get_manageable_churches(user).values_list("pk", flat=True)
    return Conference.objects.filter(
        zones__districts__churches__in=church_ids
    ).distinct().order_by("name")


def _history_search_context(request, *, page_obj, search_form, scope_label, scope_chips):
    return {
        "entries": page_obj,
        "search_form": search_form,
        "result_count": page_obj.paginator.count,
        "scope_label": scope_label,
        "scope_chips": scope_chips,
        "can_manage_church_history": can_manage_church_history(request.user),
        "can_view_church_history": True,
    }


@login_required
@any_permission_required("view_church_history", "manage_church_history")
def church_history_list(request):
    churches = _history_scope_churches(request.user)
    conferences = _history_scope_conferences(request.user)
    search_form = ChurchHistorySearchForm(
        request.GET or None,
        churches=churches,
        conferences=conferences,
    )

    church_id = None
    conference_id = None
    category = ""
    q = ""
    date_from = None
    date_to = None
    if search_form.is_valid():
        cleaned = search_form.cleaned_data
        q = cleaned.get("q") or ""
        category = cleaned.get("category") or ""
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        church_obj = cleaned.get("church")
        conference_obj = cleaned.get("conference")
        if church_obj:
            church_id = church_obj.pk
        if conference_obj:
            conference_id = conference_obj.pk

    # Deep-link query params take precedence when form widgets are hidden.
    if request.GET.get("church") and not church_id:
        church_id = request.GET.get("church")
    if request.GET.get("conference") and not conference_id:
        conference_id = request.GET.get("conference")

    active_church = get_active_church(request)
    entries = search_church_history_entries(
        request.user,
        q=q,
        category=category,
        church_id=church_id,
        conference_id=conference_id,
        date_from=date_from,
        date_to=date_to,
        active_church=None if (church_id or conference_id) else active_church,
    )

    page_obj = Paginator(entries, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)

    scope_chips = []
    scope_label = "Your accessible churches"
    if church_id:
        church = churches.filter(pk=church_id).first()
        if church:
            scope_label = f"Church: {church.name}"
            scope_chips.append({"label": church.name, "kind": "church"})
    elif conference_id:
        conference = conferences.filter(pk=conference_id).first()
        if conference:
            scope_label = f"Conference: {conference.name}"
            scope_chips.append({"label": conference.name, "kind": "conference"})
    elif active_church:
        scope_label = f"Active church: {active_church.name}"
        scope_chips.append({"label": active_church.name, "kind": "church"})

    if category:
        from organization.models import ChurchHistoryEntry

        scope_chips.append({
            "label": dict(ChurchHistoryEntry.Category.choices).get(category, category),
            "kind": "category",
        })
    if q:
        scope_chips.append({"label": f"“{q}”", "kind": "search"})
    if date_from or date_to:
        span = " – ".join(
            filter(None, [
                date_from.isoformat() if date_from else None,
                date_to.isoformat() if date_to else None,
            ])
        )
        scope_chips.append({"label": span, "kind": "dates"})

    return render(request, "organization/church_history_list.html", {
        **_history_search_context(
            request,
            page_obj=page_obj,
            search_form=search_form,
            scope_label=scope_label,
            scope_chips=scope_chips,
        ),
        "page_obj": page_obj,
        "querystring": params.urlencode(),
    })


@login_required
@any_permission_required("view_church_history", "manage_church_history")
def church_history_detail(request, pk):
    entry = get_scoped_history_entry(request.user, pk)
    return render(request, "organization/church_history_detail.html", {
        "entry": entry,
        "can_manage_church_history": can_manage_church_history(request.user),
    })


@login_required
@permission_required("manage_church_history")
def church_history_create(request):
    churches = _history_scope_churches(request.user)
    if not churches.exists():
        raise PermissionDenied("No church is available to record history.")
    default_church = get_active_church(request)
    preset_church = None
    church_param = request.GET.get("church") or request.POST.get("church")
    if church_param:
        preset_church = churches.filter(pk=church_param).first()
    if default_church and default_church.pk not in churches.values_list("pk", flat=True):
        default_church = None
    form = ChurchHistoryEntryForm(
        request.POST or None,
        churches=churches,
        default_church=preset_church or default_church,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        entry = create_church_history_entry(
            church=data["church"],
            title=data["title"],
            body=data["body"],
            event_date=data["event_date"],
            category=data["category"],
            location=data.get("location") or "",
            tags=data.get("tags") or "",
            performed_by=request.user,
            ip_address=get_client_ip(request),
        )
        flash_success(request, "Church history entry saved.")
        return redirect("organization:church_history_detail", pk=entry.pk)
    return render(request, "organization/church_history_form.html", {
        "form": form,
        "title": "Add Church History",
        "cancel_url": "organization:church_history_list",
    })


@login_required
@permission_required("manage_church_history")
def church_history_edit(request, pk):
    entry = get_scoped_history_entry(request.user, pk)
    churches = _history_scope_churches(request.user)
    form = ChurchHistoryEntryForm(
        request.POST or None,
        instance=entry,
        churches=churches,
    )
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        update_church_history_entry(
            entry,
            title=data["title"],
            body=data["body"],
            event_date=data["event_date"],
            category=data["category"],
            location=data.get("location") or "",
            tags=data.get("tags") or "",
            church=data["church"],
            performed_by=request.user,
            ip_address=get_client_ip(request),
        )
        flash_success(request, "Church history entry updated.")
        return redirect("organization:church_history_detail", pk=entry.pk)
    return render(request, "organization/church_history_form.html", {
        "form": form,
        "title": "Edit Church History",
        "object": entry,
        "cancel_url": "organization:church_history_detail",
        "cancel_pk": entry.pk,
    })
