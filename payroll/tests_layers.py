"""Characterization tests for payroll selectors / repositories layering."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.http import Http404
from django.test import TestCase
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from payroll import repositories as repo
from payroll import selectors
from payroll.models import Employee, PayComponentType
from payroll.services import (
    calculate_payroll_run,
    create_payroll_run,
    ensure_payroll_defaults_for_church,
)
from transactions.services import create_default_accounts, open_working_day

User = get_user_model()


class PayrollLayerTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Pay Layer Conf", code="PLC")
        zone = Zone.objects.create(name="Pay Layer Zone", code="PLZ", conference=conf)
        district = District.objects.create(name="Pay Layer Dist", code="PLD", zone=zone)
        self.church = Church.objects.create(
            name="Pay Layer Church", code="PLCH", district=district
        )
        other_conf = Conference.objects.create(name="Other Pay Conf", code="OPC")
        other_zone = Zone.objects.create(
            name="Other Pay Zone", code="OPZ", conference=other_conf
        )
        other_dist = District.objects.create(
            name="Other Pay Dist", code="OPD", zone=other_zone
        )
        self.other_church = Church.objects.create(
            name="Other Pay Church", code="OPCH", district=other_dist
        )
        create_default_accounts(self.church)
        ensure_payroll_defaults_for_church(self.church)
        self.treasury = User.objects.create_user(
            username="pay_layer_tr",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="pay_layer_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)
        self.employee = Employee.objects.create(
            host_church=self.church,
            employee_number="E001",
            first_name="Ada",
            last_name="Lovelace",
            employment_type="FULL_TIME",
            date_joined=date(2020, 1, 1),
            paying_unit_type="CHURCH",
            paying_unit_id=self.church.pk,
            status="ACTIVE",
        )
        basic = PayComponentType.objects.get(host_church=self.church, code="BASIC")
        from payroll.models import EmployeeCompensation, EmployeeCompensationLine

        comp = EmployeeCompensation.objects.create(
            employee=self.employee,
            effective_from=date(2020, 1, 1),
            is_active=True,
        )
        EmployeeCompensationLine.objects.create(
            compensation=comp,
            line_type="EARNING",
            pay_component=basic,
            amount=Decimal("1000.00"),
        )

    def test_selector_employee_and_run_church_scope(self):
        found = selectors.employee_for_church(self.church, self.employee.pk)
        self.assertEqual(found.pk, self.employee.pk)
        with self.assertRaises(Http404):
            selectors.employee_for_church(self.other_church, self.employee.pk)

        run = create_payroll_run(
            host_church=self.church,
            year=timezone.now().year,
            month=timezone.now().month,
            user=self.treasury,
        )
        scoped = selectors.run_for_church(self.church, run.pk)
        self.assertEqual(scoped.pk, run.pk)
        with self.assertRaises(Http404):
            selectors.run_for_church(self.other_church, run.pk)

    def test_repository_audit_and_calculate_path(self):
        run = create_payroll_run(
            host_church=self.church,
            year=timezone.now().year,
            month=1 if timezone.now().month == 12 else timezone.now().month + 1,
            user=self.treasury,
        )
        log = repo.create_run_audit(
            payroll_run=run,
            action="CREATE",
            performed_by=self.treasury,
            details={"ref": run.reference},
        )
        self.assertEqual(log.action, "CREATE")
        calculate_payroll_run(run, self.treasury)
        run.refresh_from_db()
        self.assertEqual(run.status, "CALCULATED")
        self.assertGreater(run.total_gross, Decimal("0"))

    def test_selector_active_employee_count_isolated(self):
        self.assertEqual(selectors.active_employee_count(self.church), 1)
        self.assertEqual(selectors.active_employee_count(self.other_church), 0)
