"""Enterprise audit foundation — dual-write, tenancy, District Admin summary-only."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from audit.models import AuditEvent
from audit.services import emit_event
from organization.models import Church, Conference, District, Zone
from permissions.org_scope import apply_org_scope
from permissions.roles import UserRole
from permissions.services import ensure_permission_matrix
from sitecontrol.models import Denomination
from transactions.models import FinancialAuditLog
from transactions.repositories import create_audit_log

User = get_user_model()


class EnterpriseAuditFoundationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_permission_matrix()
        cls.denomination = Denomination.objects.create(
            code="aud-t1", name="Audit Test Denom", is_active=True
        )
        cls.conference = Conference.objects.create(
            code="AU", name="Audit Conf", denomination=cls.denomination
        )
        cls.zone = Zone.objects.create(conference=cls.conference, code="AZ", name="Audit Zone")
        cls.district = District.objects.create(zone=cls.zone, code="AD", name="Audit District")
        cls.church = Church.objects.create(district=cls.district, code="AC", name="Audit Church")
        cls.other_district = District.objects.create(
            zone=cls.zone, code="AD2", name="Other District"
        )
        cls.other_church = Church.objects.create(
            district=cls.other_district, code="OC", name="Other Church"
        )

        cls.treasury = User.objects.create_user(
            username="aud_treas",
            password="pass12345",
            role=UserRole.TREASURY,
            church=cls.church,
        )
        cls.member = User.objects.create_user(
            username="aud_mem",
            password="pass12345",
            role=UserRole.MEMBER,
            church=cls.church,
        )
        cls.district_admin = User.objects.create_user(
            username="aud_da",
            password="pass12345",
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
        )
        apply_org_scope(
            cls.district_admin,
            role=UserRole.DISTRICT_PASTOR,
            church=cls.church,
            district=cls.district,
        )
        cls.district_admin.save()
        cls.district_treasurer = User.objects.create_user(
            username="aud_dt",
            password="pass12345",
            role=UserRole.DISTRICT_TREASURY,
            church=cls.church,
        )
        apply_org_scope(
            cls.district_treasurer,
            role=UserRole.DISTRICT_TREASURY,
            church=cls.church,
            district=cls.district,
        )
        cls.district_treasurer.save()

    def _login(self, username):
        from accounts.mfa import SESSION_MFA_VERIFIED

        client = Client()
        client.login(username=username, password="pass12345")
        session = client.session
        session[SESSION_MFA_VERIFIED] = True
        session.save()
        return client

    def test_financial_audit_dual_writes_enterprise_event(self):
        log = create_audit_log(
            church=self.church,
            action="CREATE",
            user=self.treasury,
            details={"password": "secret", "amount": "10.00"},
        )
        self.assertTrue(FinancialAuditLog.objects.filter(pk=log.pk).exists())
        event = AuditEvent.objects.get(source="financial_audit_log", source_id=str(log.pk))
        self.assertEqual(event.action, "journal.create")
        self.assertEqual(event.church_id, self.church.pk)
        self.assertEqual(event.after["details"]["password"], "[redacted]")
        self.assertEqual(event.after["details"]["amount"], "10.00")
        self.assertTrue(event.event_hash)

    def test_audit_event_is_immutable(self):
        event = emit_event(
            domain="finance",
            action="journal.create",
            actor=self.treasury,
            church=self.church,
            after={"ok": True},
        )
        self.assertIsNotNone(event)
        with self.assertRaises(ValueError):
            event.action = "tamper"
            event.save()
        with self.assertRaises(ValueError):
            event.delete()

    def test_scoped_events_exclude_other_churches(self):
        create_audit_log(church=self.church, action="APPROVE", user=self.treasury)
        create_audit_log(church=self.other_church, action="APPROVE", user=self.treasury)
        from audit.selectors import scoped_events_qs

        ids = set(scoped_events_qs(self.treasury).values_list("church_id", flat=True))
        self.assertIn(self.church.pk, ids)
        self.assertNotIn(self.other_church.pk, ids)

    def test_member_cannot_open_controls(self):
        client = self._login("aud_mem")
        response = client.get(reverse("audit:controls_home"))
        self.assertEqual(response.status_code, 403)

    def test_district_admin_summary_only_no_event_drilldown(self):
        create_audit_log(church=self.church, action="CREATE", user=self.treasury)
        client = self._login("aud_da")
        home = client.get(reverse("audit:controls_home"))
        self.assertEqual(home.status_code, 200)
        self.assertFalse(home.context["can_detail"])
        self.assertNotContains(home, reverse("audit:event_list"))
        listing = client.get(reverse("audit:event_list"))
        self.assertEqual(listing.status_code, 403)
        event = AuditEvent.objects.filter(church=self.church).first()
        detail = client.get(reverse("audit:event_detail", args=[event.pk]))
        self.assertEqual(detail.status_code, 403)

    def test_district_treasurer_sees_detail_in_district_not_other(self):
        mine = create_audit_log(church=self.church, action="VOID", user=self.treasury)
        create_audit_log(church=self.other_church, action="VOID", user=self.treasury)
        client = self._login("aud_dt")
        listing = client.get(reverse("audit:event_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, "journal.void")
        mine_event = AuditEvent.objects.get(source_id=str(mine.pk))
        ok = client.get(reverse("audit:event_detail", args=[mine_event.pk]))
        self.assertEqual(ok.status_code, 200)
        other = AuditEvent.objects.get(church=self.other_church)
        denied = client.get(reverse("audit:event_detail", args=[other.pk]))
        self.assertEqual(denied.status_code, 404)

    def test_new_permissions_do_not_grant_posting(self):
        from permissions.checks import (
            can_approve_transactions,
            can_export_enterprise_audit,
            can_manage_receipts,
            can_view_enterprise_audit,
            can_view_enterprise_controls,
        )

        self.assertTrue(can_view_enterprise_controls(self.district_admin))
        self.assertFalse(can_view_enterprise_audit(self.district_admin))
        self.assertTrue(can_view_enterprise_audit(self.district_treasurer))
        self.assertTrue(can_export_enterprise_audit(self.district_treasurer))
        self.assertFalse(can_manage_receipts(self.district_admin))
        self.assertFalse(can_manage_receipts(self.district_treasurer))
        self.assertFalse(can_approve_transactions(self.district_admin))
        self.assertFalse(can_approve_transactions(self.district_treasurer))

    def test_denomination_wall_hides_foreign_church_events(self):
        foreign_denom = Denomination.objects.create(
            code="aud-fx", name="Foreign Denom", is_active=True
        )
        foreign_conf = Conference.objects.create(
            code="FX", name="Foreign Conf", denomination=foreign_denom
        )
        foreign_zone = Zone.objects.create(
            conference=foreign_conf, code="FZ", name="Foreign Zone"
        )
        foreign_district = District.objects.create(
            zone=foreign_zone, code="FD", name="Foreign District"
        )
        foreign_church = Church.objects.create(
            district=foreign_district, code="FC", name="Foreign Church"
        )
        foreign_log = create_audit_log(
            church=foreign_church, action="APPROVE", user=self.treasury
        )
        from audit.selectors import scoped_events_qs

        ids = set(scoped_events_qs(self.district_treasurer).values_list("pk", flat=True))
        foreign_event = AuditEvent.objects.get(source_id=str(foreign_log.pk))
        self.assertNotIn(foreign_event.pk, ids)
        client = self._login("aud_dt")
        denied = client.get(reverse("audit:event_detail", args=[foreign_event.pk]))
        self.assertEqual(denied.status_code, 404)

    def test_dual_write_failure_does_not_drop_financial_audit(self):
        with patch(
            "audit.services.emit_from_financial_audit",
            side_effect=RuntimeError("dual-write boom"),
        ):
            log = create_audit_log(
                church=self.church, action="CREATE", user=self.treasury
            )
        self.assertTrue(FinancialAuditLog.objects.filter(pk=log.pk).exists())
