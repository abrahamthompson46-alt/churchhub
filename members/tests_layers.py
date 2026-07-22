"""Characterization tests for members selectors / repositories layering."""

from datetime import date

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import RequestFactory, TestCase

from accounts.models import UserRole
from members import repositories as repo
from members import selectors
from members.models import Gender, Member, MembershipStatus, TransferStatus
from members.services import create_member, request_transfer
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix

User = get_user_model()


class MembersLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        conf = Conference.objects.create(name="Layer Conf", code="MLC")
        zone = Zone.objects.create(name="Layer Zone", code="MLZ", conference=conf)
        district = District.objects.create(name="Layer Dist", code="MLD", zone=zone)
        cls.church = Church.objects.create(
            name="Layer Church", code="MLCH", district=district
        )
        other_conf = Conference.objects.create(name="Other Conf", code="MOC")
        other_zone = Zone.objects.create(
            name="Other Zone", code="MOZ", conference=other_conf
        )
        other_dist = District.objects.create(
            name="Other Dist", code="MOD", zone=other_zone
        )
        cls.other_church = Church.objects.create(
            name="Other Church", code="MOCH", district=other_dist
        )

    def setUp(self):
        self.user = User.objects.create_user(
            username="layer_mem",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.church,
        )
        self.other_user = User.objects.create_user(
            username="layer_other",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=self.other_church,
        )
        self.factory = RequestFactory()
        self.member = create_member(
            self.church,
            performed_by=self.user,
            first_name="Ada",
            last_name="Lovelace",
            gender=Gender.FEMALE,
            phone="0200000001",
        )

    def _request(self, user, church=None):
        request = self.factory.get("/")
        request.user = user
        request.session = {}
        request.church = church or user.church
        return request

    def test_selector_directory_includes_local_member(self):
        request = self._request(self.user)
        qs = selectors.member_directory_qs(request)
        self.assertIn(self.member, qs)

    def test_selector_member_for_request_scopes_church(self):
        foreign = create_member(
            self.other_church,
            performed_by=self.other_user,
            first_name="Foreign",
            last_name="Member",
            gender=Gender.MALE,
            phone="0200000002",
        )
        request = self._request(self.user)
        with self.assertRaises(Http404):
            selectors.member_for_request(request, foreign.pk)

    def test_repository_create_audit_and_member(self):
        member = repo.create_member(
            church=self.church,
            created_by=self.user,
            first_name="Repo",
            last_name="Member",
            gender=Gender.MALE,
            phone="0200000003",
        )
        self.assertEqual(member.church_id, self.church.pk)
        log = repo.create_audit_log(
            church=self.church,
            action="CREATE",
            performed_by=self.user,
            member=member,
            details={"name": member.full_name},
        )
        self.assertEqual(log.action, "CREATE")
        self.assertEqual(log.member_id, member.pk)

    def test_transfer_selector_and_pending_flag(self):
        self.assertFalse(selectors.pending_transfer_exists(self.member))
        transfer = request_transfer(
            member=self.member,
            to_church=self.other_church,
            transfer_date=date.today(),
            requested_by=self.user,
            reason="Move",
        )
        self.assertTrue(selectors.pending_transfer_exists(self.member))
        qs = selectors.transfers_for_user_qs(self.user)
        self.assertIn(transfer, qs)
        self.assertEqual(transfer.status, TransferStatus.PENDING)

    def test_search_selector_finds_by_name(self):
        request = self._request(self.user)
        qs = selectors.member_search_results_qs(request, q="Ada")
        self.assertIn(self.member, qs)
        foreign_request = self._request(self.other_user)
        foreign_qs = selectors.member_search_results_qs(foreign_request, q="Ada")
        self.assertNotIn(self.member, foreign_qs)

    def test_directory_stats_via_selectors(self):
        request = self._request(self.user)
        base = selectors.members_base_qs(request)
        from members.services import get_member_directory_stats

        stats = get_member_directory_stats(base, church=self.church)
        self.assertGreaterEqual(stats["total"], 1)
        self.assertGreaterEqual(stats["active"], 1)
        self.assertEqual(self.member.membership_status, MembershipStatus.ACTIVE)
