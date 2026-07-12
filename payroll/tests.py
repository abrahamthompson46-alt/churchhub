"""Payroll tests."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from organization.models import Church, Conference, District, Zone
from payroll.encryption import PayrollFieldCrypto, mask_account_number
from payroll.models import (
    Employee,
    EmployeeCompensation,
    EmployeeCompensationLine,
    EmployeeLoan,
    PayComponentType,
    PayrollRun,
)
from payroll.reports import department_cost_report, generate_paye_schedule_pdf, payroll_register_csv
from payroll.services import (
    PayrollError,
    approve_payroll_run,
    calculate_employee_pay,
    calculate_payroll_run,
    calculate_paye,
    check_payroll_budget,
    create_payroll_run,
    ensure_payroll_defaults_for_church,
    get_active_tax_table,
    get_employee_pii,
    hierarchy_payroll_rollup,
    pay_payroll_run,
    post_payroll_run,
    reject_payroll_run,
    reopen_payroll_run,
    reverse_payroll_run,
    set_employee_pii,
    treasury_approve_payroll_run,
)
from transactions.models import Account, Budget, Transaction
from transactions.services import open_working_day, validate_transaction_balance

User = get_user_model()


class PayrollTests(TestCase):
    def setUp(self):
        conf = Conference.objects.create(name="Conf", code="CF")
        zone = Zone.objects.create(name="Zone", code="ZN", conference=conf)
        district = District.objects.create(name="District", code="DT", zone=zone)
        self.church = Church.objects.create(name="Church", code="CH", district=district)
        ensure_payroll_defaults_for_church(self.church)

        self.treasury = User.objects.create_user(
            username="payroll_treasury",
            password="pass12345",
            role="TREASURY",
            church=self.church,
        )
        self.pastor = User.objects.create_user(
            username="payroll_pastor",
            password="pass12345",
            role="LOCAL_PASTOR",
            church=self.church,
        )
        open_working_day(self.church, timezone.localdate(), self.pastor)

        self.employee = Employee.objects.create(
            host_church=self.church,
            paying_unit_type="CHURCH",
            paying_unit_id=self.church.pk,
            employee_number="E001",
            first_name="Sam",
            last_name="Worker",
            employment_type="FULL_TIME",
            date_joined=date(2020, 1, 1),
            status="ACTIVE",
        )

        basic = PayComponentType.objects.get(host_church=self.church, code="BASIC")
        comp = EmployeeCompensation.objects.create(
            employee=self.employee,
            effective_from=date(2020, 1, 1),
            is_active=True,
        )
        EmployeeCompensationLine.objects.create(
            compensation=comp,
            line_type="EARNING",
            pay_component=basic,
            amount=Decimal("3000.00"),
        )

    def test_paye_uses_configured_bands(self):
        table = get_active_tax_table(self.church)
        tax = calculate_paye(Decimal("3000.00"), table)
        self.assertGreater(tax, Decimal("0"))

    def test_calculate_employee_pay(self):
        result = calculate_employee_pay(self.employee, 2026, 6, church=self.church)
        self.assertEqual(result["gross_pay"], Decimal("3000.00"))
        self.assertGreater(result["total_deductions"], Decimal("0"))
        self.assertLess(result["net_pay"], result["gross_pay"])

    def test_fernet_pii_roundtrip_and_mask(self):
        set_employee_pii(self.employee, tin="C123", ssnit_number="S999", bank_account="1234567890")
        self.employee.save()
        self.assertTrue(self.employee.bank_account_encrypted.startswith("f1:"))
        pii = get_employee_pii(self.employee)
        self.assertEqual(pii["bank_account"], "1234567890")
        self.assertEqual(mask_account_number(pii["bank_account"]), "******7890")
        # Legacy signed value still decrypts
        legacy = PayrollFieldCrypto.salt
        from django.core import signing

        signed = signing.dumps("LEGACY-TIN", salt=legacy, compress=True)
        self.assertEqual(PayrollFieldCrypto.decrypt(signed), "LEGACY-TIN")

    def test_full_payroll_workflow_dual_approval(self):
        run = create_payroll_run(
            host_church=self.church,
            year=2026,
            month=6,
            user=self.treasury,
        )
        calculate_payroll_run(run, self.treasury)
        with self.assertRaises(PayrollError):
            approve_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        with self.assertRaises(PayrollError):
            post_payroll_run(run, self.treasury)
        with self.assertRaises(PayrollError):
            treasury_approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury)
        run.refresh_from_db()
        self.assertEqual(run.status, "POSTED")
        validate_transaction_balance(run.transaction)

        pay_payroll_run(run, self.treasury)
        run.refresh_from_db()
        self.assertEqual(run.status, "PAID")
        validate_transaction_balance(run.payment_transaction)

    def test_post_idempotent(self):
        run = create_payroll_run(self.church, 2026, 5, self.treasury)
        calculate_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury, idempotency_key="post-once")
        run.refresh_from_db()
        first_trx = run.transaction_id
        with self.assertRaises(PayrollError):
            post_payroll_run(run, self.treasury, idempotency_key="post-once")
        run.refresh_from_db()
        self.assertEqual(run.transaction_id, first_trx)

    def test_loan_recovery_uses_source_ref(self):
        loan_a = EmployeeLoan.objects.create(
            employee=self.employee,
            principal=Decimal("500.00"),
            balance=Decimal("500.00"),
            monthly_recovery=Decimal("100.00"),
            start_date=date(2026, 1, 1),
            description="Loan A",
            status="ACTIVE",
        )
        loan_b = EmployeeLoan.objects.create(
            employee=self.employee,
            principal=Decimal("200.00"),
            balance=Decimal("200.00"),
            monthly_recovery=Decimal("50.00"),
            start_date=date(2026, 1, 1),
            description="Loan B",
            status="ACTIVE",
        )
        run = create_payroll_run(self.church, 2026, 4, self.treasury)
        calculate_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury)
        pay_payroll_run(run, self.treasury)
        loan_a.refresh_from_db()
        loan_b.refresh_from_db()
        self.assertEqual(loan_a.balance, Decimal("400.00"))
        self.assertEqual(loan_b.balance, Decimal("150.00"))

    def test_reverse_posted_run(self):
        run = create_payroll_run(self.church, 2026, 3, self.treasury)
        calculate_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury)
        reverse_payroll_run(run, self.treasury, reason="Correction")
        run.refresh_from_db()
        self.assertEqual(run.status, "VOID")
        self.assertTrue(run.transaction.is_voided)

    def test_reject_and_reopen(self):
        run = create_payroll_run(self.church, 2026, 9, self.treasury)
        calculate_payroll_run(run, self.treasury)
        reject_payroll_run(run, self.pastor, reason="Incorrect amounts")
        run.refresh_from_db()
        self.assertEqual(run.status, "REJECTED")
        reopen_payroll_run(run, self.treasury)
        run.refresh_from_db()
        self.assertEqual(run.status, "DRAFT")

    def test_budget_check(self):
        account = Account.objects.get(church=self.church, account_type="SALARY_EXPENSE")
        Budget.objects.create(church=self.church, year=2026, account=account, amount=Decimal("1000.00"))
        warning = check_payroll_budget(self.church, 2026, Decimal("3000.00"))
        self.assertTrue(warning["over_budget"])

    def test_duplicate_run_blocked(self):
        create_payroll_run(self.church, 2026, 7, self.treasury)
        with self.assertRaises(PayrollError):
            create_payroll_run(self.church, 2026, 7, self.treasury)

    def test_payroll_transaction_type(self):
        run = create_payroll_run(self.church, 2026, 8, self.treasury)
        calculate_payroll_run(run, self.treasury)
        approve_payroll_run(run, self.pastor)
        treasury_approve_payroll_run(run, self.treasury)
        post_payroll_run(run, self.treasury)
        run.refresh_from_db()
        trx = Transaction.objects.get(pk=run.transaction_id)
        self.assertEqual(trx.transaction_type, "PAYROLL")

    def test_reports_generated(self):
        run = create_payroll_run(self.church, 2026, 10, self.treasury)
        calculate_payroll_run(run, self.treasury)
        self.assertTrue(payroll_register_csv(run))
        self.assertTrue(generate_paye_schedule_pdf(run).read())
        self.assertEqual(len(department_cost_report(run)), 1)

    def test_hierarchy_rollup(self):
        run = create_payroll_run(self.church, 2026, 11, self.treasury)
        calculate_payroll_run(run, self.treasury)
        rows = hierarchy_payroll_rollup(self.treasury, year=2026, month=11)
        self.assertEqual(len(rows), 1)
        self.assertGreater(rows[0]["gross"], Decimal("0"))
