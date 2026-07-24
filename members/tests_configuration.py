"""Tests for Administration configuration (occupations + member lists)."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import UserRole
from members.forms import MemberForm
from members.lookups import ensure_default_member_lookups, ensure_member_form_catalogs
from members.models import Department, Member, MemberLookupOption, Occupation
from organization.models import Church, Conference, District, Zone
from permissions.services import ensure_permission_matrix
from sitecontrol.models import SiteSettings

User = get_user_model()


class MemberConfigurationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SiteSettings.objects.update_or_create(
            singleton_id=1,
            defaults={"mfa_required_for_privileged": False},
        )
        ensure_permission_matrix()
        conf = Conference.objects.create(name="Cfg Conf", code="CFG")
        zone = Zone.objects.create(name="Cfg Zone", code="CFGZ", conference=conf)
        district = District.objects.create(name="Cfg Dist", code="CFGD", zone=zone)
        cls.church = Church.objects.create(
            name="Cfg Church", code="CFGC", district=district
        )
        cls.secretary = User.objects.create_user(
            username="cfgsec",
            password="pass12345",
            role=UserRole.SECRETARY,
            church=cls.church,
        )
        cls.member_user = User.objects.create_user(
            username="cfgmember",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
        )

    def setUp(self):
        self.client = Client()

    def test_secretary_can_manage_occupations(self):
        self.client.login(username="cfgsec", password="pass12345")
        session = self.client.session
        session["active_church_id"] = str(self.church.pk)
        session.save()
        url = reverse("members:occupation_add")
        response = self.client.post(url, {"name": "Teacher"}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Occupation.objects.filter(church=self.church, name="Teacher").exists()
        )

    def test_member_denied_occupations(self):
        self.client.login(username="cfgmember", password="pass12345")
        response = self.client.get(reverse("members:occupation_list"))
        self.assertEqual(response.status_code, 403)

    def test_secretary_can_update_member_list(self):
        ensure_default_member_lookups()
        self.client.login(username="cfgsec", password="pass12345")
        session = self.client.session
        session["active_church_id"] = str(self.church.pk)
        session.save()
        opt = MemberLookupOption.objects.filter(category="gender").first()
        self.assertIsNotNone(opt)
        url = reverse("members:member_lookup_edit", kwargs={"pk": opt.pk})
        response = self.client.post(
            url,
            {
                "category": opt.category,
                "code": opt.code,
                "label": "Updated Gender Label",
                "is_active": "on",
                "sort_order": opt.sort_order,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        opt.refresh_from_db()
        self.assertEqual(opt.label, "Updated Gender Label")

    def test_member_denied_lists(self):
        self.client.login(username="cfgmember", password="pass12345")
        response = self.client.get(reverse("members:member_lookup_list"))
        self.assertEqual(response.status_code, 403)

    def test_configuration_hub_renders_for_secretary(self):
        self.client.login(username="cfgsec", password="pass12345")
        session = self.client.session
        session["active_church_id"] = str(self.church.pk)
        session.save()
        response = self.client.get(reverse("members:configuration"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Occupations")
        self.assertContains(response, "Member lists")

    def test_member_form_seeds_dropdown_catalogs(self):
        MemberLookupOption.objects.all().delete()
        Occupation.objects.filter(church=self.church).delete()
        Department.objects.filter(church=self.church).delete()
        form = MemberForm(church=self.church)
        self.assertGreater(len(form.fields["gender"].choices), 1)
        self.assertGreater(len(list(form.fields["gender"].widget.choices)), 1)
        self.assertGreater(len(form.fields["membership_status"].choices), 1)
        self.assertGreater(len(list(form.fields["membership_status"].widget.choices)), 1)
        self.assertGreater(len(list(form.fields["family_relationship"].widget.choices)), 1)
        self.assertTrue(form.fields["occupation"].queryset.exists())
        self.assertTrue(form.fields["department"].queryset.exists())
        # Idempotent: second init does not duplicate church catalogs
        ensure_member_form_catalogs(self.church)
        self.assertEqual(
            Occupation.objects.filter(church=self.church).count(),
            form.fields["occupation"].queryset.count(),
        )

    def test_email_requires_dob_and_must_be_unique(self):
        from datetime import date

        Member.objects.create(
            church=self.church,
            first_name="Existing",
            last_name="Member",
            gender="Female",
            email="taken@example.com",
            date_of_birth=date(1991, 1, 1),
        )
        missing_dob = MemberForm(
            {
                "first_name": "New",
                "last_name": "Person",
                "gender": "Male",
                "membership_status": "Active",
                "email": "new.person@example.com",
                "family_relationship": "",
                "marital_status": "",
            },
            church=self.church,
        )
        self.assertFalse(missing_dob.is_valid())
        self.assertIn("date_of_birth", missing_dob.errors)

        duplicate = MemberForm(
            {
                "first_name": "Copy",
                "last_name": "Cat",
                "gender": "Female",
                "membership_status": "Active",
                "email": "TAKEN@example.com",
                "date_of_birth": "1992-02-02",
                "family_relationship": "",
                "marital_status": "",
            },
            church=self.church,
        )
        self.assertFalse(duplicate.is_valid())
        self.assertIn("email", duplicate.errors)
