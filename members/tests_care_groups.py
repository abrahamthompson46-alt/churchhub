"""Tests for location care groups and one-to-one pairing."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.care_group_services import (
    add_member_to_care_group,
    pair_care_members,
    save_care_group,
    save_member_location,
)
from members.models import (
    CareGroup,
    CarePartnership,
    Gender,
    Member,
    MemberLocation,
)
from members.services import MemberServiceError
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix

User = get_user_model()


class CareGroupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        conf = Conference.objects.create(code="CG1", name="Care Conf")
        zone = Zone.objects.create(conference=conf, code="CG1", name="Care Zone")
        dist = District.objects.create(zone=zone, code="CG1", name="Care Dist")
        cls.church = Church.objects.create(district=dist, code="CG1", name="Care Church")
        cls.other_church = Church.objects.create(district=dist, code="CG2", name="Other Care Church")
        cls.secretary = User.objects.create_user(
            username="care_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.outsider = User.objects.create_user(
            username="care_out",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.other_church,
        )
        cls.alice = Member.objects.create(
            church=cls.church, first_name="Alice", last_name="Adu", gender=Gender.FEMALE
        )
        cls.ben = Member.objects.create(
            church=cls.church, first_name="Ben", last_name="Boateng", gender=Gender.MALE
        )
        cls.cynthia = Member.objects.create(
            church=cls.church, first_name="Cynthia", last_name="Mensah", gender=Gender.FEMALE
        )
        cls.foreign = Member.objects.create(
            church=cls.other_church, first_name="Other", last_name="Member", gender=Gender.MALE
        )

    def setUp(self):
        self.client = Client()
        self.location = save_member_location(
            location=MemberLocation(church=self.church, name="East Legon"),
            user=self.secretary,
            is_new=True,
        )
        self.group = save_care_group(
            group=CareGroup(
                church=self.church,
                location=self.location,
                name="East Legon cell",
            ),
            user=self.secretary,
            is_new=True,
        )

    def test_secretary_can_open_care_group_list(self):
        self.client.login(username="care_sec", password="pass12345")
        response = self.client.get(reverse("members:care_group_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "East Legon cell")

    def test_add_and_pair_members(self):
        add_member_to_care_group(group=self.group, member=self.alice, user=self.secretary)
        add_member_to_care_group(group=self.group, member=self.ben, user=self.secretary)
        pair = pair_care_members(
            group=self.group, first=self.ben, second=self.alice, user=self.secretary
        )
        self.assertTrue(pair.is_active)
        self.assertEqual({pair.member_a_id, pair.member_b_id}, {self.alice.pk, self.ben.pk})
        self.assertLess(pair.member_a_id, pair.member_b_id)

    def test_one_active_group_per_member(self):
        add_member_to_care_group(group=self.group, member=self.alice, user=self.secretary)
        other = save_care_group(
            group=CareGroup(
                church=self.church,
                location=self.location,
                name="Madina cell",
            ),
            user=self.secretary,
            is_new=True,
        )
        with self.assertRaises(MemberServiceError):
            add_member_to_care_group(group=other, member=self.alice, user=self.secretary)

    def test_cannot_pair_across_groups_or_twice(self):
        add_member_to_care_group(group=self.group, member=self.alice, user=self.secretary)
        add_member_to_care_group(group=self.group, member=self.ben, user=self.secretary)
        add_member_to_care_group(group=self.group, member=self.cynthia, user=self.secretary)
        pair_care_members(group=self.group, first=self.alice, second=self.ben, user=self.secretary)
        with self.assertRaises(MemberServiceError):
            pair_care_members(group=self.group, first=self.alice, second=self.cynthia, user=self.secretary)

    def test_cannot_add_other_church_member(self):
        with self.assertRaises(MemberServiceError):
            add_member_to_care_group(group=self.group, member=self.foreign, user=self.secretary)

    def test_outsider_cannot_see_group(self):
        self.client.login(username="care_out", password="pass12345")
        response = self.client.get(reverse("members:care_group_detail", kwargs={"pk": self.group.pk}))
        self.assertEqual(response.status_code, 404)

    def test_pair_via_view(self):
        add_member_to_care_group(group=self.group, member=self.alice, user=self.secretary)
        add_member_to_care_group(group=self.group, member=self.ben, user=self.secretary)
        self.client.login(username="care_sec", password="pass12345")
        response = self.client.post(
            reverse("members:care_group_pair", kwargs={"pk": self.group.pk}),
            {"first": str(self.alice.pk), "second": str(self.ben.pk), "notes": "Prayer partners"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(CarePartnership.objects.filter(group=self.group, is_active=True).exists())
        detail = self.client.get(reverse("members:care_group_detail", kwargs={"pk": self.group.pk}))
        self.assertContains(detail, "Alice Adu")
        self.assertContains(detail, "Ben Boateng")

    def test_profile_shows_group_and_partner(self):
        add_member_to_care_group(group=self.group, member=self.alice, user=self.secretary)
        add_member_to_care_group(group=self.group, member=self.ben, user=self.secretary)
        pair_care_members(group=self.group, first=self.alice, second=self.ben, user=self.secretary)
        self.client.login(username="care_sec", password="pass12345")
        response = self.client.get(reverse("members:detail", kwargs={"member_id": self.alice.pk}))
        self.assertContains(response, "East Legon cell")
        self.assertContains(response, "Ben Boateng")
