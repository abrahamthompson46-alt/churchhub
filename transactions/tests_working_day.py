"""Tests for per-church working day open/close."""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from transactions.services import (
    WorkingDayClosedError,
    close_working_day,
    open_working_day,
    record_receipt,
)

User = get_user_model()


class WorkingDayTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="WD Conf", code="WDC")
        zone = Zone.objects.create(name="WD Zone", code="WDZ", conference=conf)
        district = District.objects.create(name="WD District", code="WDD", zone=zone)
        self.church = Church.objects.create(name="WD Church", code="WDC1", district=district)
        self.treasurer = User.objects.create_user(
            username="wd_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="wd_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        self.client = Client()
        self.today = timezone.localdate()

    def test_open_and_close_working_day(self):
        day = open_working_day(self.church, self.today, self.pastor)
        self.assertEqual(day.status, "OPEN")
        closed = close_working_day(self.church, self.pastor)
        self.assertEqual(closed.status, "CLOSED")

    def test_receipt_blocked_without_open_day(self):
        with self.assertRaises(WorkingDayClosedError):
            record_receipt(
                church=self.church,
                created_by=self.treasurer,
                tithe_amount=Decimal("10.00"),
            )

    def test_receipt_allowed_when_day_open(self):
        open_working_day(self.church, self.today, self.pastor)
        txn = record_receipt(
            church=self.church,
            created_by=self.treasurer,
            tithe_amount=Decimal("10.00"),
        )
        self.assertEqual(txn.date, self.today)

    def test_cannot_open_second_day_without_closing(self):
        open_working_day(self.church, self.today, self.pastor)
        yesterday = self.today - timedelta(days=1)
        with self.assertRaises(ValueError):
            open_working_day(self.church, yesterday, self.pastor)

    def test_period_list_shows_working_day_section(self):
        open_working_day(self.church, self.today, self.pastor)
        self.client.login(username="wd_pastor", password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()
        response = self.client.get(reverse("transactions:period_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Working Day")

    def test_treasurer_can_open_day_via_post(self):
        self.client.login(username="wd_pastor", password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()
        response = self.client.post(
            reverse("transactions:working_day_open"),
            {"date": self.today.isoformat(), "notes": "Sunday service"},
        )
        self.assertEqual(response.status_code, 302)
        from transactions.models import WorkingDay

        self.assertTrue(
            WorkingDay.objects.filter(church=self.church, date=self.today, status="OPEN").exists()
        )

    def test_navbar_shows_working_day_chip(self):
        open_working_day(self.church, self.today, self.pastor)
        self.client.login(username="wd_treasury", password="pass12345")
        session = self.client.session
        session["current_church_id"] = str(self.church.pk)
        session.save()
        response = self.client.get(reverse("dashboard:home"))
        self.assertContains(response, "workspace-status-pill")
        self.assertContains(response, "is-open")
        self.assertContains(response, "Open")
