"""Secretary screens for location care groups and one-to-one pairing."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse

from church_system.church_scope import require_church
from church_system.flash import flash_exception, flash_success
from members.access import require_manage_care_groups, require_view_members
from members.care_group_services import (
    active_membership_for_member,
    add_member_to_care_group,
    delete_care_group,
    delete_member_location,
    mark_awaiting_partner,
    pair_care_members,
    remove_member_from_care_group,
    save_care_group,
    save_member_location,
    unpair_care_members,
)
from members.forms import (
    CareGroupAddMemberForm,
    CareGroupForm,
    CarePartnershipForm,
    MemberLocationForm,
)
from members.services import MemberServiceError
from members import selectors
from permissions.checks import can_manage_care_groups


@login_required
def care_group_list(request):
    require_view_members(request)
    can_manage = can_manage_care_groups(request.user)
    return render(request, "members/care_group_list.html", {
        "groups": selectors.care_groups_qs(request),
        "locations": selectors.member_locations_qs(request),
        "can_manage": can_manage,
        "can_manage_care_groups": can_manage,
    })


@login_required
def location_add(request):
    require_manage_care_groups(request)
    church = require_church(request)
    form = MemberLocationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        location = form.save(commit=False)
        location.church = church
        save_member_location(location=location, user=request.user, is_new=True)
        flash_success(request, f"Location “{location.name}” created.")
        return redirect("members:care_group_list")
    return render(request, "members/care_location_form.html", {"form": form, "title": "Add location"})


@login_required
def location_edit(request, pk):
    require_manage_care_groups(request)
    location = selectors.member_location_for_request(request, pk)
    form = MemberLocationForm(request.POST or None, instance=location)
    if request.method == "POST" and form.is_valid():
        location = form.save(commit=False)
        save_member_location(location=location, user=request.user, is_new=False)
        flash_success(request, f"Location “{location.name}” updated.")
        return redirect("members:care_group_list")
    return render(request, "members/care_location_form.html", {
        "form": form,
        "title": "Edit location",
        "location": location,
    })


@login_required
def location_delete(request, pk):
    require_manage_care_groups(request)
    location = selectors.member_location_for_request(request, pk)
    if request.method == "POST":
        name = location.name
        try:
            delete_member_location(location, request.user)
        except MemberServiceError as exc:
            flash_exception(request, exc)
            return redirect("members:care_group_list")
        flash_success(request, f"Location “{name}” removed.")
        return redirect("members:care_group_list")
    return render(request, "members/confirm_delete.html", {
        "object": location,
        "object_label": location.name,
        "title": "Remove location",
        "cancel_href": reverse("members:care_group_list"),
    })


@login_required
def care_group_add(request):
    require_manage_care_groups(request)
    church = require_church(request)
    form = CareGroupForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        group.church = church
        save_care_group(group=group, user=request.user, is_new=True)
        flash_success(request, f"Care group “{group.name}” created.")
        return redirect("members:care_group_detail", pk=group.pk)
    return render(request, "members/care_group_form.html", {"form": form, "title": "Add care group"})


@login_required
def care_group_edit(request, pk):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    form = CareGroupForm(request.POST or None, instance=group, church=group.church)
    if request.method == "POST" and form.is_valid():
        group = form.save(commit=False)
        save_care_group(group=group, user=request.user, is_new=False)
        flash_success(request, f"Care group “{group.name}” updated.")
        return redirect("members:care_group_detail", pk=group.pk)
    return render(request, "members/care_group_form.html", {
        "form": form,
        "title": "Edit care group",
        "group": group,
    })


@login_required
def care_group_delete(request, pk):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    if request.method == "POST":
        name = group.name
        try:
            delete_care_group(group, request.user)
        except MemberServiceError as exc:
            flash_exception(request, exc)
            return redirect("members:care_group_detail", pk=group.pk)
        flash_success(request, f"Care group “{name}” removed.")
        return redirect("members:care_group_list")
    return render(request, "members/confirm_delete.html", {
        "object": group,
        "object_label": group.name,
        "title": "Remove care group",
        "cancel_href": reverse("members:care_group_detail", kwargs={"pk": group.pk}),
    })


def _detail_context(request, group):
    roster = list(selectors.care_group_roster(group))
    partnerships = list(selectors.care_group_partnerships(group))
    unpaired = selectors.unpaired_members_in_group(group)
    roster_members = [row.member for row in roster]
    can_manage = can_manage_care_groups(request.user)
    return {
        "group": group,
        "roster": roster,
        "partnerships": partnerships,
        "unpaired": unpaired,
        "suggestions": selectors.members_suggested_for_care_group(group),
        "can_manage": can_manage,
        "can_manage_care_groups": can_manage,
        "add_form": CareGroupAddMemberForm(church=group.church),
        "pair_form": CarePartnershipForm(members=roster_members),
    }


@login_required
def care_group_detail(request, pk):
    require_view_members(request)
    group = selectors.care_group_for_request(request, pk)
    return render(request, "members/care_group_detail.html", _detail_context(request, group))


@login_required
def care_group_add_member(request, pk):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    if request.method != "POST":
        return redirect("members:care_group_detail", pk=group.pk)
    form = CareGroupAddMemberForm(request.POST, church=group.church)
    if not form.is_valid():
        ctx = _detail_context(request, group)
        ctx["add_form"] = form
        return render(request, "members/care_group_detail.html", ctx)
    member = form.cleaned_data["member"]
    previous = active_membership_for_member(member)
    previous_name = previous.group.name if previous and previous.group_id != group.pk else None
    try:
        add_member_to_care_group(
            group=group,
            member=member,
            user=request.user,
            role=form.cleaned_data["role"],
            move=form.cleaned_data["move_if_needed"],
        )
    except MemberServiceError as exc:
        flash_exception(request, exc)
        return redirect("members:care_group_detail", pk=group.pk)
    if previous_name:
        flash_success(request, f"{member.full_name} moved from {previous_name} to this group.")
    else:
        flash_success(request, f"{member.full_name} added to the group.")
    return redirect("members:care_group_detail", pk=group.pk)


@login_required
def care_group_remove_member(request, pk, member_id):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    member = selectors.member_for_request(request, member_id)
    if request.method != "POST":
        return redirect("members:care_group_detail", pk=group.pk)
    try:
        remove_member_from_care_group(group=group, member=member, user=request.user)
    except MemberServiceError as exc:
        flash_exception(request, exc)
        return redirect("members:care_group_detail", pk=group.pk)
    flash_success(request, f"{member.full_name} removed from the group.")
    return redirect("members:care_group_detail", pk=group.pk)


@login_required
def care_group_pair(request, pk):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    if request.method != "POST":
        return redirect("members:care_group_detail", pk=group.pk)
    roster_members = [row.member for row in selectors.care_group_roster(group)]
    form = CarePartnershipForm(request.POST, members=roster_members)
    if not form.is_valid():
        ctx = _detail_context(request, group)
        ctx["pair_form"] = form
        return render(request, "members/care_group_detail.html", ctx)
    try:
        pair_care_members(
            group=group,
            first=form.cleaned_data["first"],
            second=form.cleaned_data["second"],
            user=request.user,
            notes=form.cleaned_data.get("notes") or "",
        )
    except MemberServiceError as exc:
        flash_exception(request, exc)
        return redirect("members:care_group_detail", pk=group.pk)
    flash_success(request, "Members linked one to one in this group.")
    return redirect("members:care_group_detail", pk=group.pk)


@login_required
def care_group_unpair(request, pk, partnership_id):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    partnership = selectors.care_partnership_for_request(request, group, partnership_id)
    if request.method != "POST":
        return redirect("members:care_group_detail", pk=group.pk)
    try:
        unpair_care_members(partnership=partnership, user=request.user)
    except MemberServiceError as exc:
        flash_exception(request, exc)
        return redirect("members:care_group_detail", pk=group.pk)
    flash_success(request, "Partnership ended.")
    return redirect("members:care_group_detail", pk=group.pk)


@login_required
def care_group_awaiting(request, pk, member_id):
    require_manage_care_groups(request)
    group = selectors.care_group_for_request(request, pk)
    member = selectors.member_for_request(request, member_id)
    if request.method != "POST":
        return redirect("members:care_group_detail", pk=group.pk)
    waiting = request.POST.get("waiting", "1") != "0"
    try:
        mark_awaiting_partner(group=group, member=member, user=request.user, waiting=waiting)
    except MemberServiceError as exc:
        flash_exception(request, exc)
        return redirect("members:care_group_detail", pk=group.pk)
    if waiting:
        flash_success(request, f"{member.full_name} is waiting for a partner.")
    else:
        flash_success(request, f"{member.full_name} is no longer marked as waiting.")
    return redirect("members:care_group_detail", pk=group.pk)


@login_required
def care_group_desk(request):
    require_view_members(request)
    desk = selectors.care_group_desk(request)
    can_manage = can_manage_care_groups(request.user)
    return render(request, "members/care_group_desk.html", {
        "ungrouped": desk["ungrouped"][:50],
        "unpaired": desk["unpaired"][:50],
        "can_manage": can_manage,
        "can_manage_care_groups": can_manage,
    })
