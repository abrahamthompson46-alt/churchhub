"""Clerk-assisted birthday flyer desk — tenancy, permissions, no turning age."""

from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from announcements.birthday_services import birthday_caption, prepare_birthday_flyer
from announcements.models import BirthdayWishDispatch
from church_system.media_authorization import user_may_access_media
from members.models import Member
from organization.models import Church, Conference, District, Zone
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination

User = get_user_model()


class BirthdayFlyerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="bday-t1", name="Birthday Test Denom", is_active=True
        )
        cls.conference = Conference.objects.create(
            code="BD1", name="Bday Conference", denomination=cls.denomination
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="BZ1", name="Bday Zone")
        cls.district = District.objects.create(zone=cls.zone, code="BD1", name="Bday District")
        cls.church = Church.objects.create(district=cls.district, code="BC1", name="Hope Chapel")
        cls.other_church = Church.objects.create(
            district=cls.district, code="BC2", name="Other Chapel"
        )
        today = timezone.localdate()
        cls.today = today
        cls.member = Member.objects.create(
            church=cls.church,
            first_name="Ada",
            last_name="Lovelace",
            gender="Female",
            date_of_birth=date(today.year - 41, today.month, today.day),
            is_active=True,
        )
        cls.other_member = Member.objects.create(
            church=cls.other_church,
            first_name="Other",
            last_name="Person",
            gender="Male",
            date_of_birth=date(today.year - 20, today.month, today.day),
            is_active=True,
        )
        cls.secretary = User.objects.create_user(
            username="bday_sec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.member_user = User.objects.create_user(
            username="bday_mem",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
        )
        cls.other_sec = User.objects.create_user(
            username="bday_sec2",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.other_church,
        )

    def setUp(self):
        self.client = Client()

    def test_caption_has_no_turning_age(self):
        caption = birthday_caption(member=self.member, church=self.church)
        self.assertIn("Ada Lovelace", caption)
        self.assertIn("Hope Chapel", caption)
        self.assertNotIn("Turning", caption)
        self.assertNotIn("41", caption)
        self.assertNotIn(str(self.member.date_of_birth.year), caption)

    def test_prepare_png_has_no_age_text_and_is_png(self):
        dispatch = prepare_birthday_flyer(
            user=self.secretary,
            church=self.church,
            member=self.member,
            occurrence_date=self.today,
        )
        self.assertTrue(dispatch.flyer)
        raw = dispatch.flyer.read()
        self.assertTrue(raw.startswith(b"\x89PNG"))
        Image.open(BytesIO(raw)).verify()

    def test_desk_requires_staff_not_portal_member(self):
        self.client.login(username="bday_mem", password="pass12345")
        response = self.client.get(reverse("announcements:birthday_desk"))
        self.assertEqual(response.status_code, 403)

    def test_secretary_sees_today_birthday(self):
        self.client.login(username="bday_sec", password="pass12345")
        response = self.client.get(reverse("announcements:birthday_desk"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ada Lovelace")
        self.assertNotContains(response, "Other Person")
        self.assertNotContains(response, "Turning")

    def test_prepare_and_download_same_church(self):
        self.client.login(username="bday_sec", password="pass12345")
        response = self.client.post(
            reverse("announcements:birthday_prepare"),
            {
                "member_id": str(self.member.pk),
                "occurrence_date": self.today.isoformat(),
                "window": "today",
            },
        )
        self.assertEqual(response.status_code, 302)
        dispatch = BirthdayWishDispatch.objects.get(member=self.member)
        download = self.client.get(
            reverse("announcements:birthday_download", kwargs={"pk": dispatch.pk})
        )
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "image/png")
        dispatch.refresh_from_db()
        self.assertEqual(dispatch.status, BirthdayWishDispatch.STATUS_DOWNLOADED)

    def test_other_church_cannot_download(self):
        dispatch = prepare_birthday_flyer(
            user=self.secretary,
            church=self.church,
            member=self.member,
            occurrence_date=self.today,
        )
        self.client.login(username="bday_sec2", password="pass12345")
        response = self.client.get(
            reverse("announcements:birthday_download", kwargs={"pk": dispatch.pk})
        )
        self.assertEqual(response.status_code, 404)

    def test_media_acl_denies_other_church_and_portal(self):
        dispatch = prepare_birthday_flyer(
            user=self.secretary,
            church=self.church,
            member=self.member,
            occurrence_date=self.today,
        )
        path = dispatch.flyer.name
        self.assertTrue(user_may_access_media(self.secretary, path))
        self.assertFalse(user_may_access_media(self.other_sec, path))
        self.assertFalse(user_may_access_media(self.member_user, path))

    def test_remind_command_notifies_secretary(self):
        from announcements.birthday_services import notify_church_birthday_desk
        from dashboard.models import Notification

        sent = notify_church_birthday_desk(self.church, today=self.today)
        self.assertGreaterEqual(sent, 1)
        self.assertTrue(
            Notification.objects.filter(
                user=self.secretary, event_key=f"birthday.desk.{self.church.pk}.{self.today.isoformat()}"
            ).exists()
        )
