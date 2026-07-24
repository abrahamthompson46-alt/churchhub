from django.contrib.auth.decorators import login_required

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.generic import ListView

from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_exception, flash_success, flash_warning
from members.access import (
    require_add_members,
    require_baptism_register,
    require_edit_members,
    require_export_members,
    require_manage_configuration,
    require_manage_departments,
    require_manage_families,
    require_manage_gifts,
    require_manage_leadership,
    require_manage_member_lookups,
    require_manage_occupations,
    require_manage_records,
    require_manage_visitors,
    require_process_transfers,
    require_transfer_members,
    require_view_members,
    require_view_records,
    require_view_visitors,
)
from permissions.checks import (
    can_add_members,
    can_edit_members,
    can_manage_member_configuration,
    can_manage_member_lookups,
    can_manage_members,
    can_manage_occupations,
    can_view_members,
)
from permissions.scoping import get_manageable_churches

from . import repositories as repo
from . import selectors
from .forms import (
    BaptismRegisterFilterForm,
    DepartmentForm,
    FamilyForm,
    LeadershipRoleForm,
    MemberFilterForm,
    MemberForm,
    MemberGiftForm,
    MemberLookupOptionForm,
    MemberTransferForm,
    OccupationForm,
    RecordFilterForm,
    RecordForm,
    SpiritualGiftForm,
    VisitorFilterForm,
    VisitorForm,
)
from .models import Member, RecordType
from .services import (
    MemberServiceError,
    assign_leadership_role,
    assign_spiritual_gift,
    can_process_transfer,
    capped_queryset,
    complete_transfer,
    convert_visitor_to_member,
    create_member,
    create_spiritual_gift_catalog,
    create_visitor,
    delete_department,
    delete_occupation_record,
    end_leadership_role,
    export_directory_rows,
    get_member_directory_stats,
    log_member_audit,
    reject_transfer,
    request_transfer,
    save_department,
    save_family,
    save_member_lookup_option,
    save_occupation,
    save_record,
    unassign_spiritual_gift,
    update_member,
    update_visitor,
    user_can_view_transfer,
)


def _filter_querystring(request, exclude_page=True):
    params = request.GET.copy()
    if exclude_page:
        params.pop("page", None)
    return params.urlencode()


class MemberListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Member
    template_name = "members/list.html"
    context_object_name = "members"
    paginate_by = 25

    def test_func(self):
        return can_view_members(self.request.user) or can_manage_members(self.request.user)

    def get_queryset(self):
        return selectors.member_directory_qs(
            self.request,
            q=self.request.GET.get("q", "").strip(),
            status=self.request.GET.get("status", ""),
            department=self.request.GET.get("department", ""),
            gender=self.request.GET.get("gender", ""),
            age_group=self.request.GET.get("age_group", ""),
        )

    def get(self, request, *args, **kwargs):
        export = request.GET.get("export", "")
        if export in ("csv", "excel"):
            require_export_members(request)
            qs = self.get_queryset()
            headers, rows, truncated, total = export_directory_rows(qs)
            church = get_active_church(request)
            if truncated:
                flash_warning(
                    request,
                    f"Export limited to {len(rows)} of {total} members.",
                )
            if church:
                log_member_audit(
                    church,
                    "EXPORT",
                    performed_by=request.user,
                    details={
                        "format": export,
                        "count": len(rows),
                        "truncated": truncated,
                        "total": total,
                    },
                )
            from reports.exporters import export_table_csv, export_table_excel
            from reports.services import audit_export

            audit_export(
                user=request.user,
                report_key="member_directory",
                export_format=export,
                row_count=len(rows),
                church=church,
                params={"count": len(rows), "truncated": truncated, "total": total},
            )
            if export == "csv":
                return export_table_csv(headers, rows, "member-directory.csv")
            return export_table_excel(headers, rows, "member-directory.xlsx", "Members")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        church = get_active_church(self.request)
        base_qs = selectors.members_base_qs(self.request)
        context["stats"] = get_member_directory_stats(base_qs, church=church)
        context["filter_form"] = MemberFilterForm(self.request.GET, church=church)
        context["church"] = church
        context["can_manage"] = can_manage_members(self.request.user)
        context["filter_qs"] = _filter_querystring(self.request)
        manageable_count = get_manageable_churches(self.request.user).count()
        context["show_multi_church_banner"] = church is None and manageable_count > 1
        context["manageable_church_count"] = manageable_count
        return context


@login_required
def member_detail(request, member_id):
    require_view_members(request)
    member = selectors.member_for_request(request, member_id, detail=True)
    records = selectors.member_recent_records(member)
    transfers = selectors.member_recent_transfers(member)
    gifts = selectors.member_gift_assignments(member)
    roles = selectors.member_active_leadership_roles(member)
    attendance_count = selectors.member_attendance_present_count(member)
    welfare_summary = None
    show_welfare = False
    try:
        from remittance.welfare_services import can_view_member_welfare, member_welfare_summary, welfare_module_enabled

        show_welfare = welfare_module_enabled(member.church, request.user) and can_view_member_welfare(
            request.user, member
        )
        if show_welfare:
            welfare_summary = member_welfare_summary(member)
    except ImportError:
        pass
    return render(request, "members/detail.html", {
        "member": member,
        "records": records,
        "transfers": transfers,
        "gifts": gifts,
        "roles": roles,
        "attendance_count": attendance_count,
        "welfare_summary": welfare_summary,
        "show_welfare": show_welfare,
        "can_manage": can_manage_members(request.user),
        "breadcrumbs": [
            {"label": "Members", "url": "/members/"},
            {"label": member.full_name},
        ],
    })


@login_required
def member_search(request):
    """JSON member search for searchable pickers across members/finance forms."""
    from permissions.checks import (
        can_manage_families,
        can_manage_finances,
        can_manage_leadership,
        can_manage_ledger_entries,
        can_manage_member_records,
        can_manage_receipts,
        can_manage_spiritual_gifts,
        can_manage_welfare_cases,
        can_transfer_members,
    )

    if not (
        can_view_members(request.user)
        or can_manage_members(request.user)
        or can_manage_finances(request.user)
        or can_manage_member_records(request.user)
        or can_manage_leadership(request.user)
        or can_manage_families(request.user)
        or can_transfer_members(request.user)
        or can_manage_spiritual_gifts(request.user)
        or can_manage_receipts(request.user)
        or can_manage_ledger_entries(request.user)
        or can_manage_welfare_cases(request.user)
    ):
        raise PermissionDenied

    member_id = request.GET.get("id", "").strip()
    q = request.GET.get("q", "").strip()
    if not member_id and not q:
        return JsonResponse({"results": []})

    qs = selectors.member_search_results_qs(request, member_id=member_id, q=q)
    include_detail = (
        request.GET.get("detail") == "1" and can_view_members(request.user)
    )

    results = []
    for member in qs:
        subtitle_parts = []
        if member.membership_number:
            subtitle_parts.append(f"#{member.membership_number}")
        if member.phone:
            subtitle_parts.append(member.phone)
        if member.department:
            subtitle_parts.append(member.department.name)
        elif member.membership_status:
            subtitle_parts.append(member.membership_status)
        row = {
            "id": str(member.pk),
            "name": member.full_name,
            "subtitle": " · ".join(subtitle_parts),
            "photo_url": member.profile_picture.url if member.profile_picture else "",
            "initials": f"{(member.first_name or '?')[:1]}{(member.last_name or '?')[:1]}".upper(),
        }
        if include_detail:
            dob = member.date_of_birth.isoformat() if member.date_of_birth else ""
            row.update({
                "membership_number": member.membership_number or "",
                "membership_status": member.membership_status or "",
                "gender": member.gender or "",
                "phone": member.phone or "",
                "department": member.department.name if member.department else "",
                "date_of_birth": dob,
                "address": (member.address or "")[:120],
                "church": member.church.name if member.church_id else "",
            })
        results.append(row)
    return JsonResponse({"results": results})


@login_required
def add(request):
    require_add_members(request)
    church = require_church(request)
    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, church=church)
        if form.is_valid():
            try:
                data = form.cleaned_data.copy()
                data.pop("profile_picture", None)
                member = create_member(church, performed_by=request.user, **data)
                picture = form.cleaned_data.get("profile_picture")
                if picture:
                    member.profile_picture = picture
                    repo.save_member(
                        member, update_fields=["profile_picture", "updated_at"]
                    )
                for warning in form.duplicate_warnings:
                    flash_warning(request, warning)
                flash_success(request, f"{member} added successfully.")
                return redirect("members:detail", member_id=member.pk)
            except ValidationError as exc:
                flash_exception(request, exc)
    else:
        form = MemberForm(church=church)
    return render(request, "members/add.html", {
        "form": form,
        "breadcrumbs": [{"label": "Members", "url": "/members/"}, {"label": "Add"}],
    })


@login_required
def edit(request, member_id):
    require_edit_members(request)
    member = selectors.member_for_request(request, member_id)
    church = member.church
    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, instance=member, church=church)
        if form.is_valid():
            try:
                data = form.cleaned_data.copy()
                picture = data.pop("profile_picture", None)
                update_member(member, performed_by=request.user, **data)
                if picture is not None:
                    member.profile_picture = picture
                    repo.save_member(
                        member, update_fields=["profile_picture", "updated_at"]
                    )
                for warning in form.duplicate_warnings:
                    flash_warning(request, warning)
                flash_success(request, f"{member} updated successfully.")
                return redirect("members:detail", member_id=member.pk)
            except ValidationError as exc:
                flash_exception(request, exc)
    else:
        form = MemberForm(instance=member, church=church)
    return render(
        request,
        "members/edit.html",
        {
            "form": form,
            "member": member,
            "breadcrumbs": [
                {"label": "Members", "url": "/members/"},
                {"label": member.full_name, "url": f"/members/{member.pk}/"},
                {"label": "Edit"},
            ],
        },
    )


@login_required
def member_timeline(request, member_id):
    require_view_members(request)
    member = selectors.member_for_request(request, member_id)
    timeline = list(member.records.all().order_by("-event_date", "-created_at"))
    return render(request, "members/timeline.html", {
        "member": member,
        "timeline": timeline,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def member_export(request, member_id):
    """Subject-access JSON export for a single member."""
    require_export_members(request)
    member = selectors.member_for_request(request, member_id, with_church=True)
    from members.export import export_member_json

    payload = export_member_json(member)
    log_member_audit(
        member.church,
        "EXPORT",
        performed_by=request.user,
        member=member,
        details={"format": "json"},
    )
    response = HttpResponse(payload, content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="member-{member.pk}.json"'
    return response


@login_required
def record_list(request):
    require_view_records(request)
    filter_form = RecordFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    records_qs = selectors.records_qs(
        request,
        record_type=filters.get("type") or "",
        status=filters.get("status") or "",
        q=filters.get("q") or "",
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
    )
    paginator = Paginator(records_qs, 50)
    records = paginator.get_page(request.GET.get("page"))
    return render(request, "members/record_list.html", {
        "records": records,
        "page_obj": records,
        "filter_form": filter_form,
        "record_type": filters.get("type") or "",
        "can_manage": can_manage_members(request.user),
        "filter_qs": _filter_querystring(request),
    })


@login_required
def record_add(request):
    require_manage_records(request)
    church = require_church(request)
    member_id = request.GET.get("member")
    member = None
    if member_id:
        member = selectors.member_pk_for_request(request, member_id)
    form = RecordForm(request.POST or None, church=church, member=member)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.church = church
        record.created_by = request.user
        save_record(record=record, user=request.user, is_new=True)
        if record.record_type == RecordType.BAPTISM and record.member_id:
            updates = {}
            if record.event_date and not record.member.baptism_date:
                updates["baptism_date"] = record.event_date
            if record.place and not record.member.baptism_place:
                updates["baptism_place"] = record.place
            if record.certificate_number and not record.member.baptism_certificate_number:
                updates["baptism_certificate_number"] = record.certificate_number
            if updates:
                update_member(record.member, performed_by=request.user, **updates)
        flash_success(request, "Record saved.")
        return redirect("members:record_detail", pk=record.pk)
    return render(request, "members/record_form.html", {
        "form": form,
        "title": "Add Record",
        "member": member,
    })


@login_required
def record_edit(request, pk):
    require_manage_records(request)
    record = selectors.record_for_request(request, pk)
    form = RecordForm(request.POST or None, instance=record, church=record.church)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        save_record(record=record, user=request.user, is_new=False)
        flash_success(request, "Record updated.")
        return redirect("members:record_detail", pk=pk)
    return render(request, "members/record_form.html", {
        "form": form,
        "title": "Edit Record",
        "record": record,
        "member": record.member,
    })


@login_required
def record_detail(request, pk):
    require_view_records(request)
    record = selectors.record_for_request(request, pk, with_member=True)
    return render(request, "members/record_detail.html", {
        "record": record,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def department_list(request):
    require_view_members(request)
    departments = selectors.departments_qs(request)
    return render(request, "members/department_list.html", {
        "departments": departments,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def department_add(request):
    require_manage_departments(request)
    church = require_church(request)
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dept = form.save(commit=False)
        dept.church = church
        save_department(department=dept, user=request.user, is_new=True)
        flash_success(request, f"Department “{dept.name}” created.")
        return redirect("members:department_list")
    return render(request, "members/department_form.html", {"form": form, "title": "Add Department"})


@login_required
def department_edit(request, pk):
    require_manage_departments(request)
    dept = selectors.department_for_request(request, pk)
    form = DepartmentForm(request.POST or None, instance=dept)
    if request.method == "POST" and form.is_valid():
        dept = form.save(commit=False)
        save_department(department=dept, user=request.user, is_new=False)
        flash_success(request, f"Department “{dept.name}” updated.")
        return redirect("members:department_list")
    return render(request, "members/department_form.html", {
        "form": form,
        "title": "Edit Department",
        "department": dept,
    })


@login_required
def department_delete(request, pk):
    require_manage_departments(request)
    dept = selectors.department_for_request(request, pk)
    if request.method == "POST":
        name = dept.name
        try:
            delete_department(dept, request.user)
        except MemberServiceError as exc:
            flash_exception(request, exc)
            return redirect("members:department_list")
        flash_success(request, f"Department “{name}” removed.")
        return redirect("members:department_list")
    return render(request, "members/confirm_delete.html", {
        "object": dept,
        "object_label": dept.name,
        "title": "Remove Department",
        "cancel_href": reverse("members:department_list"),
    })


@login_required
def family_list(request):
    require_view_members(request)
    families = selectors.families_qs(request)
    return render(request, "members/family_list.html", {
        "families": families,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def family_add(request):
    require_manage_families(request)
    church = require_church(request)
    form = FamilyForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        family = form.save(commit=False)
        family.church = church
        save_family(family=family, user=request.user, is_new=True)
        flash_success(request, f"Family “{family.name}” created.")
        return redirect("members:family_detail", pk=family.pk)
    return render(request, "members/family_form.html", {"form": form, "title": "Add Family"})


@login_required
def family_edit(request, pk):
    require_manage_families(request)
    family = selectors.family_for_request(request, pk)
    form = FamilyForm(request.POST or None, instance=family, church=family.church)
    if request.method == "POST" and form.is_valid():
        family = form.save(commit=False)
        save_family(family=family, user=request.user, is_new=False)
        flash_success(request, f"Family “{family.name}” updated.")
        return redirect("members:family_detail", pk=family.pk)
    return render(request, "members/family_form.html", {
        "form": form,
        "title": "Edit Family",
        "family": family,
    })


@login_required
def family_detail(request, pk):
    require_view_members(request)
    family = selectors.family_for_request(request, pk)
    members = selectors.family_members(family)
    return render(request, "members/family_detail.html", {
        "family": family,
        "members": members,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def transfer_list(request):
    require_view_members(request)
    church = get_active_church(request)
    status = request.GET.get("status", "")
    transfers = selectors.transfers_for_user_qs(request.user, status=status)
    paginator = Paginator(transfers, 50)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "members/transfer_list.html", {
        "transfers": page,
        "page_obj": page,
        "status_filter": status,
        "church": church,
        "can_manage": can_manage_members(request.user),
        "filter_qs": _filter_querystring(request),
    })


@login_required
def transfer_create(request):
    require_transfer_members(request)
    church = require_church(request)
    member_id = request.GET.get("member") or (request.POST.get("member") if request.method == "POST" else "")
    form = MemberTransferForm(request.POST or None, church=church)
    if member_id and not form.data.get("member"):
        form.fields["member"].initial = member_id

    selected_member = None
    mid = None
    if form.is_bound and form.data.get("member"):
        mid = form.data.get("member")
    elif member_id:
        mid = member_id
        form.fields["member"].initial = member_id
    if mid:
        selected_member = (
            Member.objects.select_related("department", "church")
            .filter(pk=mid, church=church)
            .first()
        )
    if selected_member:
        form.fields["member"].initial = selected_member

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            transfer = request_transfer(
                member=data["member"],
                to_church=data["to_church"],
                transfer_date=data["transfer_date"],
                requested_by=request.user,
                reason=data.get("reason", ""),
            )
            flash_success(request, "Transfer request submitted.")
            return redirect("members:transfer_detail", pk=transfer.pk)
        except ValueError as exc:
            flash_exception(request, str(exc))

    return render(request, "members/transfer_form.html", {
        "form": form,
        "title": "Request Transfer",
        "selected_member": selected_member,
    })


@login_required
def transfer_detail(request, pk):
    require_view_members(request)
    transfer = selectors.transfer_for_user(request.user, pk)
    if not user_can_view_transfer(request.user, transfer):
        raise PermissionDenied

    can_process = can_process_transfer(request.user, transfer)

    if request.method == "POST":
        require_process_transfers(request)
        if not can_process:
            raise PermissionDenied
        action = request.POST.get("action")
        notes = request.POST.get("notes", "")
        try:
            if action == "complete":
                complete_transfer(transfer, request.user, notes=notes)
                flash_success(request, "Transfer completed.")
                return redirect("members:transfer_detail", pk=pk)
            if action == "reject":
                reject_transfer(transfer, request.user, notes=notes)
                flash_warning(request, "Transfer rejected.")
                return redirect("members:transfer_detail", pk=pk)
        except (ValueError, PermissionDenied) as exc:
            flash_exception(request, str(exc))

    return render(request, "members/transfer_detail.html", {
        "transfer": transfer,
        "can_process": can_process,
    })


@login_required
def baptism_register(request):
    require_baptism_register(request)
    filter_form = BaptismRegisterFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    records_qs = selectors.baptism_records_qs(
        request,
        q=filters.get("q") or "",
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
        status=filters.get("status") or "",
    )
    export = request.GET.get("export", "")
    if export in ("csv", "excel"):
        require_export_members(request)
        capped, truncated, total = capped_queryset(records_qs)
        headers = ["Member", "Date", "Place", "Officiant", "Certificate", "Title"]
        rows = [
            [
                r.member.full_name,
                r.event_date.isoformat() if r.event_date else "",
                r.place,
                r.officiant,
                r.certificate_number,
                r.title,
            ]
            for r in capped
        ]
        church = get_active_church(request)
        if truncated:
            flash_warning(
                request,
                f"Export limited to {len(rows)} of {total} baptism records.",
            )
        if church:
            log_member_audit(
                church,
                "EXPORT",
                performed_by=request.user,
                details={
                    "format": export,
                    "report": "baptism_register",
                    "count": len(rows),
                    "truncated": truncated,
                    "total": total,
                },
            )
        from reports.exporters import export_table_csv, export_table_excel
        from reports.services import audit_export

        audit_export(
            user=request.user,
            report_key="baptism_register",
            export_format=export,
            row_count=len(rows),
            church=church,
            params={"count": len(rows), "truncated": truncated, "total": total},
        )
        if export == "csv":
            return export_table_csv(headers, rows, "baptism-register.csv")
        return export_table_excel(headers, rows, "baptism-register.xlsx", "Baptisms")

    paginator = Paginator(records_qs, 50)
    records = paginator.get_page(request.GET.get("page"))
    return render(request, "members/baptism_register.html", {
        "records": records,
        "page_obj": records,
        "filter_form": filter_form,
        "filter_qs": _filter_querystring(request),
        "can_manage": can_manage_members(request.user),
    })


@login_required
def leadership_list(request):
    require_view_members(request)
    roles_qs = selectors.leadership_roles_qs(request)
    paginator = Paginator(roles_qs, 50)
    roles = paginator.get_page(request.GET.get("page"))
    return render(request, "members/leadership_list.html", {
        "roles": roles,
        "page_obj": roles,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def leadership_add(request):
    require_manage_leadership(request)
    church = require_church(request)
    if request.method == "POST":
        form = LeadershipRoleForm(request.POST, church=church)
        if form.is_valid():
            role = form.save(commit=False)
            role.church = church
            assign_leadership_role(role=role, user=request.user)
            flash_success(request, "Leadership role assigned.")
            return redirect("members:leadership_list")
    else:
        form = LeadershipRoleForm(church=church)
    return render(request, "members/leadership_form.html", {"form": form})


@login_required
def leadership_end(request, pk):
    require_manage_leadership(request)
    role = selectors.leadership_role_for_request(request, pk)
    if request.method == "POST":
        end_leadership_role(role=role, user=request.user)
        flash_success(request, f"Ended role “{role.title}” for {role.member.full_name}.")
        return redirect("members:leadership_list")
    return render(request, "members/confirm_delete.html", {
        "object": role,
        "object_label": f"{role.title} — {role.member.full_name}",
        "title": "End Leadership Role",
        "confirm_label": "End role",
        "cancel_href": reverse("members:leadership_list"),
    })


@login_required
def spiritual_gift_list(request):
    require_view_members(request)
    gifts = selectors.spiritual_gifts_qs(request)
    return render(request, "members/spiritual_gifts.html", {
        "gifts": gifts,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def spiritual_gift_add(request):
    require_manage_gifts(request)
    church = require_church(request)
    if request.method == "POST":
        form = SpiritualGiftForm(request.POST)
        if form.is_valid():
            create_spiritual_gift_catalog(
                church=church, user=request.user, **form.cleaned_data
            )
            flash_success(request, "Spiritual gift added.")
            return redirect("members:spiritual_gift_list")
    else:
        form = SpiritualGiftForm()
    return render(request, "members/spiritual_gift_form.html", {"form": form})


@login_required
def member_assign_gift(request, member_id):
    require_manage_gifts(request)
    member = selectors.member_pk_for_request(request, member_id)
    if request.method == "POST":
        form = MemberGiftForm(request.POST, church=member.church)
        if form.is_valid():
            try:
                assign_spiritual_gift(
                    member=member,
                    gift=form.cleaned_data["gift"],
                    user=request.user,
                    noted_at=form.cleaned_data.get("noted_at"),
                    notes=form.cleaned_data.get("notes", ""),
                )
                flash_success(request, "Gift assigned.")
                return redirect("members:detail", member_id=member.pk)
            except MemberServiceError as exc:
                flash_exception(request, exc)
    else:
        form = MemberGiftForm(church=member.church)
    return render(request, "members/assign_gift.html", {"form": form, "member": member})


@login_required
def member_unassign_gift(request, member_id, assignment_id):
    require_manage_gifts(request)
    member = selectors.member_pk_for_request(request, member_id)
    assignment = selectors.gift_assignment_for_member(member, assignment_id)
    if request.method == "POST":
        label = assignment.gift.name
        unassign_spiritual_gift(assignment, request.user)
        flash_success(request, f"Removed gift “{label}”.")
        return redirect("members:detail", member_id=member.pk)
    return render(request, "members/confirm_delete.html", {
        "object": assignment,
        "object_label": assignment.gift.name,
        "title": "Remove Spiritual Gift",
        "cancel_href": reverse("members:detail", kwargs={"member_id": member.pk}),
    })


@login_required
def visitor_list(request):
    require_view_visitors(request)
    filter_form = VisitorFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    visitors_qs = selectors.visitors_qs(
        request,
        q=filters.get("q") or "",
        status=filters.get("status") or "",
        date_from=filters.get("date_from"),
        date_to=filters.get("date_to"),
    )
    paginator = Paginator(visitors_qs, 50)
    visitors = paginator.get_page(request.GET.get("page"))
    return render(request, "members/visitor_list.html", {
        "visitors": visitors,
        "page_obj": visitors,
        "filter_form": filter_form,
        "filter_qs": _filter_querystring(request),
        "can_manage": (
            can_manage_members(request.user)
            or can_add_members(request.user)
            or can_edit_members(request.user)
        ),
    })


@login_required
def visitor_add(request):
    require_manage_visitors(request)
    church = require_church(request)
    form = VisitorForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        try:
            visitor = create_visitor(church, request.user, **form.cleaned_data)
            flash_success(request, f"Visitor “{visitor.full_name}” recorded.")
            return redirect("members:visitor_list")
        except ValidationError as exc:
            flash_exception(request, exc)
    return render(request, "members/visitor_form.html", {
        "form": form,
        "title": "Add Visitor",
    })


@login_required
def visitor_edit(request, pk):
    require_manage_visitors(request)
    visitor = selectors.visitor_for_request(request, pk)
    form = VisitorForm(request.POST or None, instance=visitor, church=visitor.church)
    if request.method == "POST" and form.is_valid():
        try:
            update_visitor(visitor, request.user, **form.cleaned_data)
            flash_success(request, f"Visitor “{visitor.full_name}” updated.")
            return redirect("members:visitor_list")
        except ValidationError as exc:
            flash_exception(request, exc)
    return render(request, "members/visitor_form.html", {
        "form": form,
        "title": "Edit Visitor",
        "visitor": visitor,
    })


@login_required
def visitor_convert(request, pk):
    require_manage_visitors(request)
    visitor = selectors.visitor_for_request(request, pk)
    if visitor.converted_member_id:
        flash_warning(request, "This visitor was already converted to a member.")
        return redirect("members:detail", member_id=visitor.converted_member_id)
    if request.method == "POST":
        try:
            member = convert_visitor_to_member(visitor, request.user)
            flash_success(
                request,
                f"Converted {visitor.full_name} to member {member.full_name}.",
            )
            return redirect("members:detail", member_id=member.pk)
        except (MemberServiceError, ValidationError) as exc:
            flash_exception(request, exc)
            return redirect("members:visitor_convert", pk=pk)
    return render(request, "members/visitor_convert.html", {
        "visitor": visitor,
        "title": "Convert Visitor to Member",
    })


# ── Administration → Configuration ────────────────────────────────


@login_required
def configuration_hub(request):
    require_manage_configuration(request)
    church = get_active_church(request)
    return render(request, "members/configuration_hub.html", {
        "church": church,
        "can_occupations": can_manage_occupations(request.user) or can_manage_members(request.user),
        "can_lookups": can_manage_member_lookups(request.user) or can_manage_members(request.user),
        "can_hub": can_manage_member_configuration(request.user) or can_manage_members(request.user),
    })


@login_required
def occupation_list(request):
    require_manage_occupations(request)
    church = require_church(request)
    occupations = selectors.occupations_qs(request)
    return render(request, "members/occupation_list.html", {
        "occupations": occupations,
        "church": church,
        "can_manage": True,
    })


@login_required
def occupation_add(request):
    require_manage_occupations(request)
    church = require_church(request)
    form = OccupationForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        occupation = form.save(commit=False)
        occupation.church = church
        save_occupation(occupation=occupation, user=request.user, is_new=True)
        flash_success(request, f"Occupation “{occupation.name}” created.")
        return redirect("members:occupation_list")
    return render(request, "members/occupation_form.html", {
        "form": form,
        "title": "Add Occupation",
    })


@login_required
def occupation_edit(request, pk):
    require_manage_occupations(request)
    occupation = selectors.occupation_for_request(request, pk)
    form = OccupationForm(request.POST or None, instance=occupation, church=occupation.church)
    if request.method == "POST" and form.is_valid():
        occupation = form.save(commit=False)
        save_occupation(occupation=occupation, user=request.user, is_new=False)
        flash_success(request, f"Occupation “{occupation.name}” updated.")
        return redirect("members:occupation_list")
    return render(request, "members/occupation_form.html", {
        "form": form,
        "title": "Edit Occupation",
        "occupation": occupation,
    })


@login_required
def occupation_delete(request, pk):
    require_manage_occupations(request)
    occupation = selectors.occupation_for_request(request, pk)
    if request.method == "POST":
        name = occupation.name
        delete_occupation_record(occupation, request.user)
        flash_success(request, f"Occupation “{name}” removed.")
        return redirect("members:occupation_list")
    return render(request, "members/confirm_delete.html", {
        "title": "Delete Occupation",
        "object": occupation,
        "object_label": occupation.name,
        "cancel_href": reverse("members:occupation_list"),
        "confirm_label": "Delete",
    })


@login_required
def member_lookup_list(request):
    require_manage_member_lookups(request)
    from members.lookups import ensure_default_member_lookups
    from members.models import LookupCategory, MemberLookupOption

    church = require_church(request)
    ensure_default_member_lookups()
    category = request.GET.get("category", "")
    qs = MemberLookupOption.objects.all().order_by("category", "sort_order", "label")
    if category:
        qs = qs.filter(category=category)
    return render(request, "members/member_lookup_list.html", {
        "options": qs,
        "categories": LookupCategory.choices,
        "active_category": category,
        "church": church,
    })


@login_required
def member_lookup_edit(request, pk=None):
    require_manage_member_lookups(request)
    from members.lookups import ensure_default_member_lookups
    from members.models import MemberLookupOption
    from django.shortcuts import get_object_or_404

    church = require_church(request)
    ensure_default_member_lookups()
    option = get_object_or_404(MemberLookupOption, pk=pk) if pk else None
    form = MemberLookupOptionForm(request.POST or None, instance=option)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        is_new = option is None
        if option and option.is_system:
            obj.category = option.category
            obj.code = option.code
            obj.is_system = True
        elif is_new:
            obj.is_system = False
        save_member_lookup_option(
            option=obj, user=request.user, church=church, is_new=is_new
        )
        flash_success(request, f"Saved “{obj.label}”.")
        return redirect("members:member_lookup_list")
    return render(request, "members/member_lookup_form.html", {
        "form": form,
        "option": option,
        "title": "Edit List Option" if option else "Add List Option",
    })
