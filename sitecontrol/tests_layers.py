"""Characterization tests for sitecontrol selectors / repositories layering."""

from django.contrib.auth import get_user_model
from django.test import TestCase

from organization.models import Church, Conference, District, Zone
from sitecontrol import repositories as repo
from sitecontrol import selectors
from sitecontrol.models import (
    Denomination,
    PlatformAuditLog,
    SiteSettings,
    SubscriptionPlan,
    TenantApplication,
    TenantSubscription,
)
from sitecontrol.platform_access import (
    filter_churches_for_operator,
    operator_can_access_denomination,
)
from sitecontrol.registration_services import (
    reject_tenant_application,
    submit_tenant_application,
)
from sitecontrol.services import (
    assign_subscription,
    clear_settings_cache,
    ensure_default_plans,
    log_platform_action,
    suspend_tenant,
)

User = get_user_model()


class SiteControlLayerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_default_plans()
        cls.denom_a = Denomination.objects.create(
            name="SC Layer Denom A",
            code="sclda",
            is_active=True,
            allow_public_registration=True,
        )
        cls.denom_b = Denomination.objects.create(
            name="SC Layer Denom B",
            code="scldb",
            is_active=True,
            allow_public_registration=True,
        )
        cls.conf_a = Conference.objects.create(
            code="SCLA1", name="SC Layer Conf A", denomination=cls.denom_a
        )
        cls.conf_b = Conference.objects.create(
            code="SCLB1", name="SC Layer Conf B", denomination=cls.denom_b
        )
        cls.zone_a = Zone.objects.create(
            conference=cls.conf_a, code="SCLZA", name="SC Zone A"
        )
        cls.zone_b = Zone.objects.create(
            conference=cls.conf_b, code="SCLZB", name="SC Zone B"
        )
        cls.district_a = District.objects.create(
            zone=cls.zone_a, code="SCLDA1", name="SC Dist A"
        )
        cls.district_b = District.objects.create(
            zone=cls.zone_b, code="SCLDB1", name="SC Dist B"
        )
        cls.church_a = Church.objects.create(
            district=cls.district_a, code="SCLCHA", name="SC Church A"
        )
        cls.church_b = Church.objects.create(
            district=cls.district_b, code="SCLCHB", name="SC Church B"
        )
        cls.plan = SubscriptionPlan.objects.filter(is_active=True).first()
        settings_obj = SiteSettings.load()
        settings_obj.allow_church_self_registration = True
        settings_obj.auto_provision_public_trials = False
        settings_obj.save(update_fields=["allow_church_self_registration", "auto_provision_public_trials"])
        clear_settings_cache()

    def setUp(self):
        self.owner = User.objects.create_user(
            username="sc_layer_owner",
            password="pass12345",
            email="sc_layer_owner@test.com",
            is_platform_user=True,
            platform_role="OWNER",
            is_staff=True,
            is_superuser=True,
        )
        self.scoped = User.objects.create_user(
            username="sc_layer_scoped",
            password="pass12345",
            email="sc_layer_scoped@test.com",
            is_platform_user=True,
            platform_role="SUPPORT",
            is_staff=True,
        )
        self.scoped.managed_denominations.add(self.denom_a)

    def test_selector_denomination_isolation_reads(self):
        self.assertEqual(
            selectors.denomination_by_code(code="sclda").pk, self.denom_a.pk
        )
        self.assertEqual(
            selectors.church_count_for_denomination(self.denom_a), 1
        )
        self.assertEqual(
            selectors.church_count_for_denomination(self.denom_b), 1
        )
        districts_a = list(selectors.districts_for_denomination(self.denom_a))
        self.assertEqual([d.pk for d in districts_a], [self.district_a.pk])

    def test_platform_user_access_scoping(self):
        self.assertTrue(
            operator_can_access_denomination(self.owner, self.denom_b)
        )
        self.assertTrue(
            operator_can_access_denomination(self.scoped, self.denom_a)
        )
        self.assertFalse(
            operator_can_access_denomination(self.scoped, self.denom_b)
        )
        qs = filter_churches_for_operator(
            selectors.churches_tenant_list_base(), self.scoped
        )
        ids = set(qs.values_list("pk", flat=True))
        self.assertIn(self.church_a.pk, ids)
        self.assertNotIn(self.church_b.pk, ids)

    def test_selector_plan_and_subscription_reads(self):
        self.assertTrue(selectors.active_plan_exists())
        self.assertIsNotNone(
            selectors.default_active_plan() or selectors.first_active_plan_by_sort()
        )
        assign_subscription(self.church_a, self.plan, user=self.owner)
        sub = selectors.get_subscription_or_404(
            TenantSubscription.objects.get(church=self.church_a).pk
        )
        self.assertEqual(sub.church_id, self.church_a.pk)
        self.assertEqual(sub.status, "ACTIVE")
        self.assertGreaterEqual(selectors.active_subscription_count(), 1)

    def test_subscription_state_via_service_and_repo(self):
        assign_subscription(self.church_a, self.plan, user=self.owner)
        suspend_tenant(self.church_a, self.owner, reason="layer test")
        sub = TenantSubscription.objects.get(church=self.church_a)
        self.assertEqual(sub.status, "SUSPENDED")

    def test_tenant_application_workflow_via_layers(self):
        application = submit_tenant_application(
            {
                "denomination": self.denom_a,
                "application_type": "EXISTING_DISTRICT",
                "church_name": "Apply Church",
                "church_code": "SCLAPP",
                "district": self.district_a,
                "contact_name": "Applicant",
                "contact_email": "applicant_layer@test.com",
                "applicant_username": "applicant_layer",
                "applicant_notes": "",
                "address": "",
                "contact_phone": "",
            },
            ip_address="127.0.0.1",
        )
        self.assertEqual(application.status, "PENDING")
        self.assertTrue(
            selectors.pending_application_for_email("applicant_layer@test.com")
        )
        self.assertGreaterEqual(selectors.pending_application_count(), 1)
        reject_tenant_application(
            application, reviewer=self.owner, review_notes="not now"
        )
        application.refresh_from_db()
        self.assertEqual(application.status, "REJECTED")

    def test_repository_audit_creation(self):
        class ReqRequest:
            user = self.owner
            META = {"REMOTE_ADDR": "127.0.0.1"}

        log_platform_action(
            ReqRequest(),
            "SETTINGS_UPDATE",
            "Layer characterization audit",
            target_model="Denomination",
            target_id=self.denom_a.pk,
            denomination=self.denom_a,
        )
        self.assertTrue(
            PlatformAuditLog.objects.filter(
                action="SETTINGS_UPDATE",
                denomination=self.denom_a,
                summary="Layer characterization audit",
            ).exists()
        )

    def test_repository_save_subscription_and_application(self):
        sub = TenantSubscription(
            church=self.church_b,
            plan=self.plan,
            status="TRIAL",
        )
        repo.save_subscription(sub)
        self.assertTrue(
            TenantSubscription.objects.filter(
                church=self.church_b, status="TRIAL"
            ).exists()
        )
        app = TenantApplication(
            denomination=self.denom_b,
            application_type="EXISTING_DISTRICT",
            church_name="Repo Church",
            church_code="SCLREP",
            district=self.district_b,
            contact_name="Repo",
            contact_email="repo_layer@test.com",
            applicant_username="repo_layer",
            status="PENDING",
        )
        repo.save_application(app)
        self.assertTrue(
            TenantApplication.objects.filter(
                church_code="SCLREP", status="PENDING"
            ).exists()
        )

    def test_selector_audit_and_application_list_reads(self):
        repo.create_platform_audit(
            user=self.owner,
            action="SETTINGS_UPDATE",
            summary="list read",
            denomination=self.denom_a,
        )
        qs = selectors.platform_audit_list_base()
        self.assertTrue(qs.filter(summary="list read").exists())
        apps = selectors.applications_list_base()
        self.assertEqual(apps.model, TenantApplication)
