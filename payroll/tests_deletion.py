"""Payroll draft line purge guards."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from payroll.models import Employee, EmployeeCompensation, EmployeeCompensationLine, PayComponentType, PayrollRunAuditLog
from payroll.services import (
    PayrollError,
    _clear_draft_payroll_lines,
    approve_payroll_run,
    calculate_payroll_run,
    create_payroll_run,
    ensure_payroll_defaults_for_church,
    post_payroll_run,
    treasury_approve_payroll_run,
)
from transactions.services import open_working_day

User = get_user_model()


class PayrollLinePurgeGuardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        conf = Conference.objects.create(name="Pay Conf", code="PAYC")
        zone = Zone.objects.create(conference=conf, name="Pay Z", code="PAYZ")
        dist = District.objects.create(zone=zone, name="Pay D", code="PAYD")
        cls.church = Church.objects.create(district=dist, name="Pay Church", code="PAYCH")
        ensure_payroll_defaults_for_church(cls.church)
        cls.treasury = User.objects.create_user(
            username="pay_treasury",
            password="pass12345",
            role="TREASURY",
            church=cls.church,
        )
        cls.pastor = User.objects.create_user(
            username="pay_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=cls.church,
        )
        open_working_day(cls.church, timezone.localdate(), cls.pastor)
        employee = Employee.objects.create(
            host_church=cls.church,
            paying_unit_type="CHURCH",
            paying_unit_id=cls.church.pk,
            employee_number="E001",
            first_name="Sam",
            last_name="Worker",
            employment_type="FULL_TIME",
            date_joined=date(2020, 1, 1),
            status="ACTIVE",
        )
        basic = PayComponentType.objects.get(host_church=cls.church, code="BASIC")
        comp = EmployeeCompensation.objects.create(
            employee=employee,
            effective_from=date(2020, 1, 1),
            is_active=True,
        )
        EmployeeCompensationLine.objects.create(
            compensation=comp,
            line_type="EARNING",
            pay_component=basic,
            amount=Decimal("3000.00"),
        )

    def test_posted_run_cannot_clear_lines(self):
        run = create_payroll_run(self.church, timezone.now().year, 4, self.treasury)
        calculate_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury)
        run.refresh_from_db()
        line_count = run.lines.count()
        self.assertGreater(line_count, 0)
        with self.assertRaises(PayrollError):
            _clear_draft_payroll_lines(run, self.treasury, reason="blocked")
        self.assertEqual(run.lines.count(), line_count)

    def test_recalculate_clears_draft_lines_with_audit(self):
        run = create_payroll_run(self.church, timezone.now().year, 5, self.treasury)
        calculate_payroll_run(run, self.treasury)
        self.assertGreater(run.lines.count(), 0)
        before_logs = PayrollRunAuditLog.objects.filter(payroll_run=run, action="CALCULATE").count()
        calculate_payroll_run(run, self.treasury)
        self.assertGreater(
            PayrollRunAuditLog.objects.filter(payroll_run=run, action="CALCULATE").count(),
            before_logs,
        )
