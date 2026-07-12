from datetime import date

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from permissions.checks import can_manage_members, can_view_members
from church_system.church_scope import filter_by_church, get_active_church, require_church
from church_system.flash import flash_exception, flash_success, flash_warning
from permissions.scoping import get_manageable_churches

from .forms import (
    DepartmentForm,
    FamilyForm,
    LeadershipRoleForm,
    MemberFilterForm,
    MemberForm,
    MemberGiftForm,
    MemberTransferForm,
    RecordForm,
    SpiritualGiftForm,
)
from .models import (
    Department,
    Family,
    LeadershipRole,
    Member,
    MemberSpiritualGift,
    MemberTransfer,
    Record,
    RecordType,
    SpiritualGift,
    age_group_for_age,
)
from .services import (
    can_process_transfer,
    complete_transfer,
    create_member,
    export_directory_rows,
    get_member_directory_stats,
    log_member_audit,
    reject_transfer,
    request_transfer,
    update_member,
    user_can_view_transfer,
)


def _require_view_members(request):
    if not (can_view_members(request.user) or can_manage_members(request.user)):
        raise PermissionDenied


def _require_members(request):
    if not can_manage_members(request.user):
        raise PermissionDenied


def _filter_querystring(request, exclude_page=True):
    params = request.GET.copy()
    if exclude_page:
        params.pop("page", None)
    return params.urlencode()


def _apply_age_group_filter(qs, age_group):
    if not age_group:
        return qs
    today = date.today()
    members = []
    for member in qs.filter(date_of_birth__isnull=False).only("id", "date_of_birth"):
        if age_group_for_age(member.age) == age_group:
            members.append(member.pk)
    return qs.filter(pk__in=members)


class MemberListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = Member
    template_name = "members/list.html"
    context_object_name = "members"
    paginate_by = 25

    def test_func(self):
        return can_view_members(self.request.user) or can_manage_members(self.request.user)

    def get_queryset(self):
        qs = filter_by_church(
            Member.objects.select_related("church", "occupation", "department", "family"),
            self.request,
        )
        q = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        department = self.request.GET.get("department", "")
        gender = self.request.GET.get("gender", "")
        age_group = self.request.GET.get("age_group", "")

        if q:
            qs = qs.filter(
                Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
                | Q(membership_number__icontains=q)
            )
        if status:
            qs = qs.filter(membership_status=status)
        if department:
            qs = qs.filter(department_id=department)
        if gender:
            qs = qs.filter(gender=gender)
        if age_group:
            qs = _apply_age_group_filter(qs, age_group)

        return qs.order_by("last_name", "first_name")

    def get(self, request, *args, **kwargs):
        export = request.GET.get("export", "")
        if export in ("csv", "excel"):
            _require_view_members(request)
            qs = self.get_queryset()
            headers, rows = export_directory_rows(qs)
            church = get_active_church(request)
            if church:
                log_member_audit(
                    church,
                    "EXPORT",
                    performed_by=request.user,
                    details={"format": export, "count": len(rows)},
                )
            from reports.exporters import export_table_csv, export_table_excel

            if export == "csv":
                return export_table_csv(headers, rows, "member-directory.csv")
            return export_table_excel(headers, rows, "member-directory.xlsx", "Members")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        church = get_active_church(self.request)
        base_qs = filter_by_church(Member.objects.all(), self.request)
        context["stats"] = get_member_directory_stats(base_qs, church=church)
        context["filter_form"] = MemberFilterForm(self.request.GET, church=church)
        context["church"] = church
        context["can_manage"] = can_manage_members(self.request.user)
        context["filter_qs"] = _filter_querystring(self.request)
        return context


@login_required
def member_detail(request, member_id):
    _require_view_members(request)
    member = get_object_or_404(
        filter_by_church(
            Member.objects.select_related("church", "occupation", "department", "family"),
            request,
        ),
        id=member_id,
    )
    records = member.records.order_by("-event_date")[:10]
    transfers = member.transfers.select_related("from_church", "to_church").order_by("-created_at")[:5]
    gifts = member.spiritual_gift_assignments.select_related("gift")
    roles = member.leadership_roles.filter(is_active=True).select_related("department")
    attendance_count = 0
    try:
        from meetings.models import MeetingAttendance

        attendance_count = MeetingAttendance.objects.filter(
            member=member, is_present=True
        ).count()
    except Exception:
        pass
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
    """JSON member search for treasury / welfare pickers."""
    from permissions.checks import can_manage_finances

    if not (
        can_manage_finances(request.user)
        or can_manage_members(request.user)
        or can_view_members(request.user)
    ):
        raise PermissionDenied

    qs = filter_by_church(
        Member.objects.filter(is_active=True).select_related(
            "department", "church", "family", "occupation"
        ),
        request,
    )

    member_id = request.GET.get("id", "").strip()
    if member_id:
        qs = qs.filter(pk=member_id)
    else:
        q = request.GET.get("q", "").strip()
        if not q:
            return JsonResponse({"results": []})
        qs = qs.annotate(
            full_name=Concat("first_name", Value(" "), "last_name"),
        ).filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(membership_number__icontains=q)
            | Q(full_name__icontains=q)
            | Q(address__icontains=q)
            | Q(membership_status__icontains=q)
            | Q(gender__icontains=q)
            | Q(department__name__icontains=q)
            | Q(family__name__icontains=q)
            | Q(occupation__name__icontains=q)
        )

    results = []
    for member in qs.order_by("last_name", "first_name")[:20]:
        subtitle_parts = []
        if member.phone:
            subtitle_parts.append(member.phone)
        if member.department:
            subtitle_parts.append(member.department.name)
        elif member.membership_status:
            subtitle_parts.append(member.membership_status)
        results.append({
            "id": str(member.pk),
            "name": member.full_name,
            "subtitle": " · ".join(subtitle_parts),
            "photo_url": member.profile_picture.url if member.profile_picture else "",
            "initials": f"{member.first_name[:1]}{member.last_name[:1]}".upper(),
        })
    return JsonResponse({"results": results})


@login_required
def add(request):
    _require_members(request)
    church = require_church(request)
    if request.method == "POST":
        form = MemberForm(request.POST, request.FILES, church=church)
        if form.is_valid():
            try:
                data = form.cleaned_data.copy()
                data.pop("profile_picture", None)
                member = create_member(church, performed_by=request.user, **data)
                if request.FILES.get("profile_picture"):
                    member.profile_picture = request.FILES["profile_picture"]
                    member.save(update_fields=["profile_picture", "updated_at"])
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
    _require_members(request)
    member = get_object_or_404(
        filter_by_church(Member.objects.all(), request),
        id=member_id,
    )
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
                    member.save(update_fields=["profile_picture", "updated_at"])
                for warning in form.duplicate_warnings:
                    flash_warning(request, warning)
                flash_success(request, f"{member} updated successfully.")
                return redirect("members:detail", member_id=member.pk)
            except ValidationError as exc:
                flash_exception(request, exc)
    else:
        form = MemberForm(instance=member, church=church)
    return render(request, "members/edit.html", {"form": form, "member": member})


@login_required
def member_timeline(request, member_id):
    _require_view_members(request)
    member = get_object_or_404(
        filter_by_church(Member.objects.all(), request),
        id=member_id,
    )
    records = member.records.all()
    history = member.history.all()
    from datetime import date as date_cls

    def _timeline_date(item):
        value = getattr(item, "event_date", None) or getattr(item, "date", None)
        return value or date_cls.min

    timeline = sorted(list(records) + list(history), key=_timeline_date, reverse=True)
    return render(request, "members/timeline.html", {
        "member": member,
        "timeline": timeline,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def member_export(request, member_id):
    """Subject-access JSON export for a single member."""
    _require_members(request)
    member = get_object_or_404(
        filter_by_church(Member.objects.select_related("church"), request),
        id=member_id,
    )
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
    _require_view_members(request)
    records_qs = filter_by_church(
        Record.objects.select_related("member", "church").order_by("-event_date"),
        request,
    )
    record_type = request.GET.get("type", "")
    if record_type:
        records_qs = records_qs.filter(record_type=record_type)
    paginator = Paginator(records_qs, 50)
    records = paginator.get_page(request.GET.get("page"))
    return render(request, "members/record_list.html", {
        "records": records,
        "page_obj": records,
        "record_type": record_type,
        "can_manage": can_manage_members(request.user),
        "filter_qs": _filter_querystring(request),
    })


@login_required
def record_add(request):
    _require_members(request)
    church = require_church(request)
    member_id = request.GET.get("member")
    member = None
    if member_id:
        member = get_object_or_404(
            filter_by_church(Member.objects.all(), request),
            pk=member_id,
        )
    form = RecordForm(request.POST or None, church=church, member=member)
    if request.method == "POST" and form.is_valid():
        record = form.save(commit=False)
        record.church = church
        record.created_by = request.user
        record.save()
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
    _require_members(request)
    record = get_object_or_404(
        filter_by_church(Record.objects.all(), request),
        pk=pk,
    )
    form = RecordForm(request.POST or None, instance=record, church=record.church)
    if request.method == "POST" and form.is_valid():
        form.save()
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
    _require_view_members(request)
    record = get_object_or_404(
        filter_by_church(Record.objects.select_related("member"), request),
        pk=pk,
    )
    return render(request, "members/record_detail.html", {
        "record": record,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def department_list(request):
    _require_view_members(request)
    departments = filter_by_church(
        Department.objects.annotate(member_count=Count("members")).order_by("name"),
        request,
    )
    return render(request, "members/department_list.html", {
        "departments": departments,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def department_add(request):
    _require_members(request)
    church = require_church(request)
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dept = form.save(commit=False)
        dept.church = church
        dept.save()
        flash_success(request, f"Department “{dept.name}” created.")
        return redirect("members:department_list")
    return render(request, "members/department_form.html", {"form": form, "title": "Add Department"})


@login_required
def family_list(request):
    _require_view_members(request)
    families = filter_by_church(
        Family.objects.select_related("head").annotate(
            member_count=Count("members")
        ).order_by("name"),
        request,
    )
    return render(request, "members/family_list.html", {
        "families": families,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def family_add(request):
    _require_members(request)
    church = require_church(request)
    form = FamilyForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        family = form.save(commit=False)
        family.church = church
        family.save()
        flash_success(request, f"Family “{family.name}” created.")
        return redirect("members:family_detail", pk=family.pk)
    return render(request, "members/family_form.html", {"form": form, "title": "Add Family"})


@login_required
def family_detail(request, pk):
    _require_view_members(request)
    family = get_object_or_404(
        filter_by_church(Family.objects.select_related("head"), request),
        pk=pk,
    )
    members = family.members.order_by("last_name", "first_name")
    return render(request, "members/family_detail.html", {
        "family": family,
        "members": members,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def transfer_list(request):
    _require_view_members(request)
    church = get_active_church(request)
    transfers = MemberTransfer.objects.select_related(
        "member", "from_church", "to_church", "requested_by"
    ).order_by("-created_at")

    allowed_churches = get_manageable_churches(request.user)
    transfers = transfers.filter(
        Q(from_church__in=allowed_churches) | Q(to_church__in=allowed_churches)
    )

    status = request.GET.get("status", "")
    if status:
        transfers = transfers.filter(status=status)

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
    _require_members(request)
    church = require_church(request)
    member_id = request.GET.get("member")
    form = MemberTransferForm(request.POST or None, church=church)
    if member_id:
        form.fields["member"].initial = member_id

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

    return render(request, "members/transfer_form.html", {"form": form, "title": "Request Transfer"})


@login_required
def transfer_detail(request, pk):
    _require_view_members(request)
    transfer = get_object_or_404(
        MemberTransfer.objects.select_related(
            "member", "from_church", "to_church", "requested_by", "processed_by"
        ),
        pk=pk,
    )
    if not user_can_view_transfer(request.user, transfer):
        raise PermissionDenied

    can_process = can_process_transfer(request.user, transfer)

    if request.method == "POST":
        if not can_manage_members(request.user):
            raise PermissionDenied
        action = request.POST.get("action")
        notes = request.POST.get("notes", "")
        try:
            if action == "complete" and can_process:
                complete_transfer(transfer, request.user, notes=notes)
                flash_success(request, "Transfer completed.")
                return redirect("members:transfer_detail", pk=pk)
            if action == "reject" and can_process:
                reject_transfer(transfer, request.user, notes=notes)
                flash_warning(request, "Transfer rejected.")
                return redirect("members:transfer_detail", pk=pk)
        except (ValueError, PermissionDenied) as exc:
            flash_exception(request, str(exc))

    return render(request, "members/transfer_detail.html", {
        "transfer": transfer,
        "can_process": can_process and can_manage_members(request.user),
    })


@login_required
def baptism_register(request):
    _require_view_members(request)
    records_qs = filter_by_church(
        Record.objects.filter(record_type=RecordType.BAPTISM).select_related("member", "church"),
        request,
    ).order_by("-event_date")
    export = request.GET.get("export", "")
    if export in ("csv", "excel"):
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
            for r in records_qs
        ]
        from reports.exporters import export_table_csv, export_table_excel

        if export == "csv":
            return export_table_csv(headers, rows, "baptism-register.csv")
        return export_table_excel(headers, rows, "baptism-register.xlsx", "Baptisms")

    paginator = Paginator(records_qs, 50)
    records = paginator.get_page(request.GET.get("page"))
    return render(request, "members/baptism_register.html", {
        "records": records,
        "page_obj": records,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def leadership_list(request):
    _require_view_members(request)
    roles_qs = filter_by_church(
        LeadershipRole.objects.select_related("member", "department", "church"), request
    ).order_by("-is_active", "title")
    paginator = Paginator(roles_qs, 50)
    roles = paginator.get_page(request.GET.get("page"))
    return render(request, "members/leadership_list.html", {
        "roles": roles,
        "page_obj": roles,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def leadership_add(request):
    _require_members(request)
    church = require_church(request)
    if request.method == "POST":
        form = LeadershipRoleForm(request.POST, church=church)
        if form.is_valid():
            role = form.save(commit=False)
            role.church = church
            role.full_clean()
            role.save()
            flash_success(request, "Leadership role assigned.")
            return redirect("members:leadership_list")
    else:
        form = LeadershipRoleForm(church=church)
    return render(request, "members/leadership_form.html", {"form": form})


@login_required
def spiritual_gift_list(request):
    _require_view_members(request)
    gifts = filter_by_church(SpiritualGift.objects.all(), request)
    return render(request, "members/spiritual_gifts.html", {
        "gifts": gifts,
        "can_manage": can_manage_members(request.user),
    })


@login_required
def spiritual_gift_add(request):
    _require_members(request)
    church = require_church(request)
    if request.method == "POST":
        form = SpiritualGiftForm(request.POST)
        if form.is_valid():
            gift = form.save(commit=False)
            gift.church = church
            gift.save()
            flash_success(request, "Spiritual gift added.")
            return redirect("members:spiritual_gift_list")
    else:
        form = SpiritualGiftForm()
    return render(request, "members/spiritual_gift_form.html", {"form": form})


@login_required
def member_assign_gift(request, member_id):
    _require_members(request)
    member = get_object_or_404(filter_by_church(Member.objects.all(), request), pk=member_id)
    if request.method == "POST":
        form = MemberGiftForm(request.POST, church=member.church)
        if form.is_valid():
            MemberSpiritualGift.objects.get_or_create(
                member=member,
                gift=form.cleaned_data["gift"],
                defaults={
                    "noted_at": form.cleaned_data.get("noted_at"),
                    "notes": form.cleaned_data.get("notes", ""),
                },
            )
            flash_success(request, "Gift assigned.")
            return redirect("members:detail", member_id=member.pk)
    else:
        form = MemberGiftForm(church=member.church)
    return render(request, "members/assign_gift.html", {"form": form, "member": member})
