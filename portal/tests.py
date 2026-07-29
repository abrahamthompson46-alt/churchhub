"""Member portal smoke and auth tests."""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import UserRole
from members.forms import MemberForm
from members.models import Member
from organization.models import Church, Conference, District, Zone
from portal.services import (
    authenticate_portal_credentials,
    build_confirm_token,
    canonical_dob_password,
)

User = get_user_model()


class PortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.conference = Conference.objects.create(code="PC", name="Portal Conf")
        cls.zone = Zone.objects.create(conference=cls.conference, code="PZ", name="Portal Zone")
        cls.district = District.objects.create(zone=cls.zone, code="PD", name="Portal Dist")
        cls.church = Church.objects.create(district=cls.district, code="PCH", name="Portal Church")
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Member",
            email="ada.member@example.com",
            date_of_birth=date(1990, 5, 21),
            gender="Female",
        )
        cls.member_user = User.objects.create_user(
            username="portal_member",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
            member=cls.member,
            email="ada.member@example.com",
        )
        cls.staff = User.objects.create_user(
            username="portal_staff",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )

    def test_portal_login_page(self):
        response = self.client.get(reverse("portal:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Member sign in")
        self.assertContains(response, "Email")

    def test_staff_login_links_to_portal(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("portal:login"))

    def test_member_portal_home(self):
        self.client.login(username="portal_member", password="pass12345")
        response = self.client.get(reverse("portal:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Member")

    def test_member_can_submit_prayer_request(self):
        self.client.login(username="portal_member", password="pass12345")
        response = self.client.post(
            reverse("portal:prayer_request"),
            {"body": "Please pray for my family during this time of need.", "is_anonymous": "on"},
        )
        self.assertEqual(response.status_code, 302)
        from portal.models import SpiritualSubmission, SpiritualSubmissionKind

        self.assertEqual(
            SpiritualSubmission.objects.filter(
                member=self.member, kind=SpiritualSubmissionKind.PRAYER
            ).count(),
            1,
        )

    def test_pastor_sees_portal_alerts_on_dashboard(self):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        pastor = User.objects.create_user(
            username="portal_pastor",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        from portal.models import SpiritualSubmission, SpiritualSubmissionKind
        from portal.spiritual_services import create_spiritual_submission

        create_spiritual_submission(
            user=self.member_user,
            member=self.member,
            kind=SpiritualSubmissionKind.PRAYER,
            body="Please pray for safe travels this Sabbath.",
        )
        self.client.login(username="portal_pastor", password="pass12345")
        from accounts.mfa import SESSION_MFA_VERIFIED

        session = self.client.session
        session[SESSION_MFA_VERIFIED] = True
        session["current_church_id"] = str(self.church.id)
        session.save()
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prayer requests")
        self.assertContains(response, reverse("portal:staff_submissions"))

    def test_login_uses_site_branding_fields(self):
        from sitecontrol.services import clear_settings_cache, get_site_settings

        settings_obj = get_site_settings()
        settings_obj.site_name = "FaithOS"
        settings_obj.site_tagline = "Secure church ops"
        settings_obj.login_highlights = "Highlight A\nHighlight B"
        settings_obj.save()
        clear_settings_cache()
        response = self.client.get(reverse("login"))
        self.assertContains(response, "FaithOS")
        self.assertContains(response, "Secure church ops")
        self.assertContains(response, "Highlight A")

    def test_portal_live_meeting_join_page(self):
        from datetime import timedelta

        from django.utils import timezone
        from meetings.models import Meeting, MeetingStatus, MeetingType

        meeting = Meeting.objects.create(
            church=self.church,
            title="Friday Prayer Live",
            meeting_type=MeetingType.ONLINE_SERVICE,
            scheduled_at=timezone.now() + timedelta(hours=2),
            status=MeetingStatus.SCHEDULED,
            join_url="https://zoom.us/j/555",
            join_passcode="pray1",
            show_on_portal=True,
        )
        hidden = Meeting.objects.create(
            church=self.church,
            title="Board Only",
            meeting_type=MeetingType.BOARD,
            scheduled_at=timezone.now() + timedelta(hours=3),
            status=MeetingStatus.SCHEDULED,
            join_url="https://zoom.us/j/999",
            show_on_portal=False,
        )
        self.client.login(username="portal_member", password="pass12345")
        home = self.client.get(reverse("portal:home"))
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, "Friday Prayer Live")
        self.assertNotContains(home, "Board Only")

        live = self.client.get(reverse("portal:meeting_live", args=[meeting.pk]))
        self.assertEqual(live.status_code, 200)
        self.assertContains(live, "Join on Zoom")
        self.assertContains(live, "pray1")

        blocked = self.client.get(reverse("portal:meeting_live", args=[hidden.pk]))
        self.assertEqual(blocked.status_code, 404)

    def test_submission_creates_audit_log_and_notification(self):
        from dashboard.models import Notification
        from portal.models import SpiritualSubmissionAuditLog, SpiritualSubmissionKind
        from portal.spiritual_services import create_spiritual_submission
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        pastor = User.objects.create_user(
            username="portal_pastor_audit",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        sub = create_spiritual_submission(
            user=self.member_user,
            member=self.member,
            kind=SpiritualSubmissionKind.PRAYER,
            body="Please pray for healing and peace this week.",
        )
        self.assertTrue(
            SpiritualSubmissionAuditLog.objects.filter(
                submission=sub, action=SpiritualSubmissionAuditLog.Action.CREATED
            ).exists()
        )
        self.assertTrue(Notification.objects.filter(user=pastor).exists())

    def test_rate_limit_blocks_excessive_submissions(self):
        from django.core.cache import cache

        from portal.models import SpiritualSubmissionKind

        cache.clear()
        self.client.login(username="portal_member", password="pass12345")
        for i in range(12):
            response = self.client.post(
                reverse("portal:prayer_request"),
                {"body": f"Prayer request number {i} for our church family."},
            )
            self.assertEqual(response.status_code, 302, msg=i)
        blocked = self.client.post(
            reverse("portal:prayer_request"),
            {"body": "This thirteenth request should be rate limited."},
        )
        self.assertEqual(blocked.status_code, 200)
        self.assertContains(blocked, "recently")

    def test_staff_csv_export_requires_permission(self):
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        pastor = User.objects.create_user(
            username="portal_pastor_csv",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        self.client.login(username="portal_pastor_csv", password="pass12345")
        response = self.client.get(reverse("portal:staff_submissions") + "?export=csv")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_praise_wall_shows_reviewed_entries_only(self):
        from portal.models import SpiritualSubmission, SpiritualSubmissionKind, SpiritualSubmissionStatus
        from permissions.services import ensure_permission_matrix

        ensure_permission_matrix()
        pastor = User.objects.create_user(
            username="portal_pastor_wall",
            password="pass12345",
            role=UserRole.LOCAL_PASTOR,
            church=self.church,
        )
        pending = SpiritualSubmission.objects.create(
            church=self.church,
            member=self.member,
            submitted_by=self.member_user,
            kind=SpiritualSubmissionKind.THANKSGIVING,
            body="Thank God for provision.",
            status=SpiritualSubmissionStatus.NEW,
        )
        reviewed = SpiritualSubmission.objects.create(
            church=self.church,
            member=self.member,
            submitted_by=self.member_user,
            kind=SpiritualSubmissionKind.TESTIMONY,
            title="Grace",
            body="God answered prayer.",
            status=SpiritualSubmissionStatus.REVIEWED,
        )
        self.client.login(username="portal_member", password="pass12345")
        response = self.client.get(reverse("portal:praise_wall"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reviewed.body)
        self.assertNotContains(response, pending.body)


class PortalAuthFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(code="PAC", name="Portal Auth Conf")
        zone = Zone.objects.create(conference=conf, code="PAZ", name="Portal Auth Zone")
        district = District.objects.create(zone=zone, code="PAD", name="Portal Auth Dist")
        cls.church = Church.objects.create(district=district, code="PACH", name="Portal Auth Church")
        cls.dob = date(1988, 3, 14)
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Kwame",
            last_name="Asante",
            email="kwame.asante@example.com",
            date_of_birth=cls.dob,
            gender="Male",
        )

    def setUp(self):
        self.client = Client()

    def test_member_form_select_widgets_have_options(self):
        form = MemberForm(church=self.church)
        for name in ("gender", "marital_status", "membership_status", "family_relationship"):
            field = form.fields[name]
            self.assertGreater(len(list(field.choices)), 1, name)
            self.assertGreater(len(list(field.widget.choices)), 1, name)

    def test_authenticate_email_and_dob_provisions_user(self):
        user = authenticate_portal_credentials(
            "kwame.asante@example.com",
            canonical_dob_password(self.dob),
        )
        self.assertEqual(user.role, UserRole.MEMBER)
        self.assertEqual(user.member_id, self.member.pk)
        self.assertEqual(user.username, "kwame.asante@example.com")
        self.assertTrue(user.must_change_password)

    @override_settings(DEBUG=True)
    def test_first_login_requires_email_confirmation(self):
        response = self.client.post(
            reverse("portal:login"),
            {
                "username": "kwame.asante@example.com",
                "password": "1988-03-14",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("portal:confirm_sent"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)

        user = User.objects.get(email__iexact="kwame.asante@example.com")
        token = build_confirm_token(user)
        confirm = self.client.get(reverse("portal:confirm_device", kwargs={"token": token}))
        self.assertEqual(confirm.status_code, 302)
        self.assertEqual(confirm.url, reverse("portal:password_change"))

        # Session should now be authenticated
        home = self.client.get(reverse("portal:home"))
        self.assertEqual(home.status_code, 302)
        self.assertEqual(home.url, reverse("portal:password_change"))

    @override_settings(DEBUG=True)
    def test_password_change_after_confirm(self):
        user = authenticate_portal_credentials("kwame.asante@example.com", "1988-03-14")
        token = build_confirm_token(user)
        self.client.get(reverse("portal:confirm_device", kwargs={"token": token}))
        response = self.client.post(
            reverse("portal:password_change"),
            {
                "old_password": "1988-03-14",
                "new_password1": "SecurePass1",
                "new_password2": "SecurePass1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("portal:home"))
        user.refresh_from_db()
        self.assertFalse(user.must_change_password)
        self.assertTrue(user.check_password("SecurePass1"))
