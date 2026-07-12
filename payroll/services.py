"""Payroll calculation, posting, and statutory services."""

import calendar
import csv
import io
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

from payroll.constants import (
    DEFAULT_DEDUCTION_TYPES,
    DEFAULT_EARNING_COMPONENTS,
    DEFAULT_PAYE_BANDS,
    DEFAULT_STATUTORY_RULES,
)
from payroll.encryption import PayrollFieldCrypto
from payroll.models import (
    DeductionType,
    Employee,
    EmployeeCompensation,
    EmployeeCompensationLine,
    EmployeeLoan,
    PayComponentType,
    PayrollLine,
    PayrollLineItem,
    PayrollRun,
    PayrollRunAuditLog,
    PayrollTaxBand,
    PayrollTaxTable,
    StatutoryContributionRule,
)


class PayrollError(ValueError):
    pass


def _quantize(amount):
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _days_in_month(year, month):
    return calendar.monthrange(year, month)[1]


def _log_run_audit(payroll_run, action, user, details=None):
    PayrollRunAuditLog.objects.create(
        payroll_run=payroll_run,
        action=action,
        performed_by=user,
        details=details or {},
    )


def _generate_run_reference(church, year, month):
    prefix = f"PAY-{year}-{month:02d}"
    last = (
        PayrollRun.objects.filter(host_church=church, reference__startswith=prefix)
        .order_by("-reference")
        .first()
    )
    seq = 1
    if last and last.reference:
        try:
            seq = int(last.reference.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    return f"{prefix}-{seq:03d}"


def set_employee_pii(employee, tin="", ssnit_number="", bank_account=""):
    """Encrypt and store sensitive employee fields (Fernet)."""
    if tin is not None:
        employee.tin_encrypted = PayrollFieldCrypto.encrypt(tin)
    if ssnit_number is not None:
        employee.ssnit_number_encrypted = PayrollFieldCrypto.encrypt(ssnit_number)
    if bank_account is not None:
        employee.bank_account_encrypted = PayrollFieldCrypto.encrypt(bank_account)
    for attr in ("tin_encrypted", "ssnit_number_encrypted", "bank_account_encrypted"):
        raw = getattr(employee, attr, "")
        if PayrollFieldCrypto.needs_reencrypt(raw):
            plain = PayrollFieldCrypto.decrypt(raw)
            if plain:
                setattr(employee, attr, PayrollFieldCrypto.encrypt(plain))


def get_employee_pii(employee, *, strict=False):
    return {
        "tin": PayrollFieldCrypto.decrypt(employee.tin_encrypted, strict=strict),
        "ssnit_number": PayrollFieldCrypto.decrypt(employee.ssnit_number_encrypted, strict=strict),
        "bank_account": PayrollFieldCrypto.decrypt(employee.bank_account_encrypted, strict=strict),
    }


def get_employee_pii_display(employee):
    from payroll.encryption import mask_account_number

    pii = get_employee_pii(employee)
    return {
        "tin": pii["tin"],
        "ssnit_number": pii["ssnit_number"],
        "bank_account": mask_account_number(pii["bank_account"]),
        "bank_account_masked": mask_account_number(pii["bank_account"]),
    }


def ensure_payroll_defaults_for_church(church):
    """Seed pay components, deduction types, tax table, and statutory rules."""
    for row in DEFAULT_EARNING_COMPONENTS:
        PayComponentType.objects.get_or_create(
            host_church=church,
            code=row["code"],
            defaults={
                "name": row["name"],
                "is_taxable": row["is_taxable"],
                "sort_order": row["sort_order"],
            },
        )

    for row in DEFAULT_DEDUCTION_TYPES:
        DeductionType.objects.get_or_create(
            host_church=church,
            code=row["code"],
            defaults={
                "name": row["name"],
                "is_statutory": row["is_statutory"],
                "calculation_method": row["calculation_method"],
                "default_rate": Decimal(row.get("default_rate", "0")),
                "sort_order": row["sort_order"],
            },
        )

    if not PayrollTaxTable.objects.filter(host_church=church, is_active=True).exists():
        table = PayrollTaxTable.objects.create(
            host_church=church,
            name="Ghana PAYE (Default)",
            notes="Seeded default bands — update when GRA revises rates.",
        )
        for idx, band in enumerate(DEFAULT_PAYE_BANDS):
            PayrollTaxBand.objects.create(
                tax_table=table,
                lower_limit=Decimal(band["lower"]),
                upper_limit=Decimal(band["upper"]) if band["upper"] else None,
                rate_percent=Decimal(band["rate"]),
                sort_order=idx,
            )

    for row in DEFAULT_STATUTORY_RULES:
        StatutoryContributionRule.objects.get_or_create(
            host_church=church,
            code=row["code"],
            effective_from=date(2000, 1, 1),
            defaults={
                "name": row["name"],
                "employee_rate": Decimal(row["employee_rate"]),
                "employer_rate": Decimal(row["employer_rate"]),
                "applies_to": row["applies_to"],
            },
        )

    from transactions.services import create_default_accounts

    create_default_accounts(church)


def get_active_tax_table(church, as_of_date=None):
    as_of_date = as_of_date or timezone.now().date()
    return (
        PayrollTaxTable.objects.filter(
            host_church=church,
            is_active=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from")
        .first()
    )


def get_active_statutory_rules(church, as_of_date=None):
    as_of_date = as_of_date or timezone.now().date()
    rules = {}
    for rule in StatutoryContributionRule.objects.filter(
        host_church=church,
        is_active=True,
        effective_from__lte=as_of_date,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date)):
        rules[rule.code] = rule
    return rules


def get_active_compensation(employee, as_of_date):
    return (
        EmployeeCompensation.objects.filter(
            employee=employee,
            is_active=True,
            effective_from__lte=as_of_date,
        )
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of_date))
        .order_by("-effective_from")
        .first()
    )


def calculate_paye(taxable_income, tax_table):
    """Progressive PAYE on monthly taxable income using configured bands."""
    if not tax_table or taxable_income <= 0:
        return Decimal("0.00")

    remaining = _quantize(taxable_income)
    tax = Decimal("0.00")
    bands = tax_table.bands.all().order_by("sort_order", "lower_limit")

    for band in bands:
        if remaining <= 0:
            break
        lower = band.lower_limit
        upper = band.upper_limit
        if taxable_income <= lower:
            continue
        if upper is None:
            taxable_slice = remaining
        else:
            band_width = upper - lower
            taxable_slice = min(remaining, band_width)
        if taxable_slice <= 0:
            continue
        tax += _quantize(taxable_slice * band.rate_percent / Decimal("100"))
        remaining -= taxable_slice

    return _quantize(tax)


def _pro_rata_factor(employee, year, month):
    days_in_period = _days_in_month(year, month)
    period_start = date(year, month, 1)
    period_end = date(year, month, days_in_period)

    start = max(employee.date_joined, period_start)
    end = period_end
    if employee.date_terminated and employee.date_terminated < period_end:
        end = employee.date_terminated

    if start > end:
        return days_in_period, 0, Decimal("0")

    days_worked = (end - start).days + 1
    factor = Decimal(str(days_worked)) / Decimal(str(days_in_period))
    return days_in_period, days_worked, factor


def calculate_employee_pay(employee, year, month, church=None):
    """
    Calculate earnings, statutory deductions, and net pay for one employee.

    Returns dict with amounts and line item breakdown.
    """
    church = church or employee.host_church
    as_of_date = date(year, month, _days_in_month(year, month))
    compensation = get_active_compensation(employee, as_of_date)
    if not compensation:
        raise PayrollError(f"No active compensation profile for {employee.full_name}.")

    days_in_period, days_worked, factor = _pro_rata_factor(employee, year, month)
    if days_worked <= 0:
        raise PayrollError(f"{employee.full_name} was not active during this period.")

    earnings = []
    basic = Decimal("0.00")
    gross_taxable = Decimal("0.00")
    gross_total = Decimal("0.00")

    for line in compensation.lines.filter(line_type="EARNING").select_related("pay_component"):
        amount = _quantize(line.amount * factor)
        if line.pay_component.code == "BASIC":
            basic = amount
        gross_total += amount
        if line.pay_component.is_taxable:
            gross_taxable += amount
        earnings.append({
            "code": line.pay_component.code,
            "label": line.pay_component.name,
            "amount": amount,
        })

    statutory = get_active_statutory_rules(church, as_of_date)
    tax_table = get_active_tax_table(church, as_of_date)

    deductions = []
    employer_items = []
    ssnit_ee = Decimal("0.00")

    if "SSNIT_EE" in statutory:
        rule = statutory["SSNIT_EE"]
        base = basic if rule.applies_to == "BASIC" else gross_taxable
        ssnit_ee = _quantize(base * rule.employee_rate / Decimal("100"))
        deductions.append({"code": "SSNIT_EE", "label": rule.name, "amount": ssnit_ee})

    if "SSNIT_ER" in statutory:
        rule = statutory["SSNIT_ER"]
        base = basic if rule.applies_to == "BASIC" else gross_taxable
        er_amount = _quantize(base * rule.employer_rate / Decimal("100"))
        employer_items.append({"code": "SSNIT_ER", "label": rule.name, "amount": er_amount})

    if "PENSION_T2" in statutory:
        rule = statutory["PENSION_T2"]
        base = basic if rule.applies_to == "BASIC" else gross_taxable
        er_pension = _quantize(base * rule.employer_rate / Decimal("100"))
        employer_items.append({"code": "PENSION_T2", "label": rule.name, "amount": er_pension})

    taxable_for_paye = gross_taxable - ssnit_ee
    paye = calculate_paye(taxable_for_paye, tax_table)
    if paye > 0:
        deductions.append({"code": "PAYE", "label": "PAYE", "amount": paye})

    for line in compensation.lines.filter(line_type="DEDUCTION").select_related("deduction_type"):
        dtype = line.deduction_type
        if dtype.code in ("PAYE", "SSNIT_EE", "PENSION_T2"):
            continue
        if dtype.calculation_method == "FIXED":
            amount = _quantize(line.amount * factor)
        elif dtype.calculation_method == "PERCENT_GROSS":
            rate = line.rate_percent or dtype.default_rate
            amount = _quantize(gross_total * rate / Decimal("100"))
        elif dtype.calculation_method == "PERCENT_BASIC":
            rate = line.rate_percent or dtype.default_rate
            amount = _quantize(basic * rate / Decimal("100"))
        else:
            continue
        if amount > 0:
            deductions.append({"code": dtype.code, "label": dtype.name, "amount": amount})

    for loan in EmployeeLoan.objects.filter(employee=employee, status="ACTIVE"):
        recovery = min(loan.monthly_recovery, loan.balance)
        if recovery > 0:
            deductions.append({
                "code": "LOAN",
                "label": f"Loan — {loan.description or 'Recovery'}",
                "amount": _quantize(recovery),
                "loan_id": str(loan.pk),
            })

    total_deductions = _quantize(sum(d["amount"] for d in deductions))
    net_pay = _quantize(gross_total - total_deductions)
    if net_pay < 0:
        raise PayrollError(
            f"Net pay for {employee.full_name} is negative (₵{net_pay}). "
            "Reduce deductions or loan recovery before calculating."
        )
    employer_cost = _quantize(
        gross_total + sum(i["amount"] for i in employer_items)
    )

    return {
        "earnings": earnings,
        "deductions": deductions,
        "employer_items": employer_items,
        "gross_pay": gross_total,
        "total_deductions": total_deductions,
        "net_pay": net_pay,
        "employer_cost": employer_cost,
        "days_in_period": days_in_period,
        "days_worked": days_worked,
        "is_pro_rata": factor < Decimal("1"),
    }


def _employees_for_run(payroll_run):
    return Employee.objects.filter(
        host_church=payroll_run.host_church,
        paying_unit_type=payroll_run.paying_unit_type,
        paying_unit_id=payroll_run.paying_unit_id,
        status="ACTIVE",
    ).select_related("department")


@db_transaction.atomic
def create_payroll_run(host_church, year, month, user, paying_unit_type="CHURCH", paying_unit_id=None, pay_date=None, description=""):
    paying_unit_id = paying_unit_id or host_church.pk
    pay_date = pay_date or date(year, month, _days_in_month(year, month))

    if PayrollRun.objects.filter(
        host_church=host_church,
        paying_unit_type=paying_unit_type,
        paying_unit_id=paying_unit_id,
        year=year,
        month=month,
    ).exclude(status="VOID").exists():
        raise PayrollError("A payroll run already exists for this period and paying unit.")

    run = PayrollRun.objects.create(
        reference=_generate_run_reference(host_church, year, month),
        host_church=host_church,
        paying_unit_type=paying_unit_type,
        paying_unit_id=paying_unit_id,
        year=year,
        month=month,
        pay_date=pay_date,
        description=description or f"Payroll {year}-{month:02d}",
        prepared_by=user,
        status="DRAFT",
    )
    _log_run_audit(run, "CREATE", user)
    return run


@db_transaction.atomic
def calculate_payroll_run(payroll_run, user):
    if payroll_run.status not in ("DRAFT", "CALCULATED"):
        raise PayrollError("Only draft or calculated runs can be recalculated.")

    payroll_run.lines.all().delete()

    total_gross = Decimal("0.00")
    total_deductions = Decimal("0.00")
    total_net = Decimal("0.00")
    total_employer = Decimal("0.00")
    seq = 0
    skipped = []

    for employee in _employees_for_run(payroll_run):
        try:
            result = calculate_employee_pay(
                employee,
                payroll_run.year,
                payroll_run.month,
                church=payroll_run.host_church,
            )
        except PayrollError as exc:
            skipped.append({"employee": employee.full_name, "reason": str(exc)})
            continue

        seq += 1
        line = PayrollLine.objects.create(
            payroll_run=payroll_run,
            employee=employee,
            gross_pay=result["gross_pay"],
            total_deductions=result["total_deductions"],
            net_pay=result["net_pay"],
            employer_cost=result["employer_cost"],
            days_in_period=result["days_in_period"],
            days_worked=result["days_worked"],
            is_pro_rata=result["is_pro_rata"],
            payslip_number=f"{payroll_run.reference}-{seq:03d}",
        )

        for item in result["earnings"]:
            PayrollLineItem.objects.create(
                payroll_line=line,
                item_type="EARNING",
                code=item["code"],
                label=item["label"],
                amount=item["amount"],
            )
        for item in result["deductions"]:
            PayrollLineItem.objects.create(
                payroll_line=line,
                item_type="DEDUCTION",
                code=item["code"],
                label=item["label"],
                amount=item["amount"],
                source_ref=str(item.get("loan_id") or ""),
            )
        for item in result["employer_items"]:
            PayrollLineItem.objects.create(
                payroll_line=line,
                item_type="EMPLOYER",
                code=item["code"],
                label=item["label"],
                amount=item["amount"],
            )

        total_gross += result["gross_pay"]
        total_deductions += result["total_deductions"]
        total_net += result["net_pay"]
        total_employer += result["employer_cost"]

    if seq == 0:
        detail = "; ".join(f"{s['employee']}: {s['reason']}" for s in skipped[:5])
        raise PayrollError(
            "No eligible employees with active compensation for this run."
            + (f" Skipped: {detail}" if detail else "")
        )

    payroll_run.total_gross = _quantize(total_gross)
    payroll_run.total_deductions = _quantize(total_deductions)
    payroll_run.total_net = _quantize(total_net)
    payroll_run.total_employer_cost = _quantize(total_employer)
    payroll_run.status = "CALCULATED"
    payroll_run.approved_by = None
    payroll_run.approved_at = None
    payroll_run.treasury_approved_by = None
    payroll_run.treasury_approved_at = None
    payroll_run.rejection_reason = ""
    payroll_run.budget_warning = check_payroll_budget(payroll_run.host_church, payroll_run.year, _quantize(total_gross))
    if skipped:
        payroll_run.budget_warning = {
            **(payroll_run.budget_warning or {}),
            "skipped_employees": skipped,
            "skipped_count": len(skipped),
        }
    payroll_run.save()
    _log_run_audit(
        payroll_run,
        "CALCULATE",
        user,
        {"employee_count": seq, "skipped_count": len(skipped), "skipped": skipped[:20]},
    )
    return payroll_run


@db_transaction.atomic
def treasury_approve_payroll_run(payroll_run, user):
    """Treasury review — required before posting (dual approval)."""
    if payroll_run.status != "APPROVED":
        raise PayrollError("Pastor approval is required before treasury review.")
    if not payroll_run.approved_by_id:
        raise PayrollError("Pastor approval is missing.")
    if payroll_run.approved_by_id == user.id:
        raise PayrollError(
            "Segregation of duties: treasury review cannot be the same person as pastor approval."
        )
    payroll_run.treasury_approved_by = user
    payroll_run.treasury_approved_at = timezone.now()
    payroll_run.save()
    _log_run_audit(payroll_run, "APPROVE", user, {"stage": "treasury"})
    return payroll_run


@db_transaction.atomic
def reject_payroll_run(payroll_run, user, reason=""):
    if payroll_run.status not in ("CALCULATED", "APPROVED"):
        raise PayrollError("Only calculated or pastor-approved runs can be rejected.")
    payroll_run.status = "REJECTED"
    payroll_run.rejection_reason = reason
    payroll_run.approved_by = None
    payroll_run.approved_at = None
    payroll_run.treasury_approved_by = None
    payroll_run.treasury_approved_at = None
    payroll_run.save()
    _log_run_audit(payroll_run, "REJECT", user, {"reason": reason})
    return payroll_run


@db_transaction.atomic
def void_payroll_run(payroll_run, user):
    if payroll_run.status in ("POSTED", "PAID"):
        raise PayrollError("Posted or paid runs cannot be voided — use a reversal adjustment.")
    if payroll_run.status == "VOID":
        raise PayrollError("Run is already void.")
    payroll_run.status = "VOID"
    payroll_run.save()
    _log_run_audit(payroll_run, "VOID", user)
    return payroll_run


@db_transaction.atomic
def reopen_payroll_run(payroll_run, user):
    """Return a rejected run to draft for correction."""
    if payroll_run.status != "REJECTED":
        raise PayrollError("Only rejected runs can be reopened.")
    payroll_run.status = "DRAFT"
    payroll_run.lines.all().delete()
    payroll_run.total_gross = Decimal("0")
    payroll_run.total_deductions = Decimal("0")
    payroll_run.total_net = Decimal("0")
    payroll_run.total_employer_cost = Decimal("0")
    payroll_run.save()
    _log_run_audit(payroll_run, "REOPEN", user, {"action": "reopen"})
    return payroll_run


@db_transaction.atomic
def approve_payroll_run(payroll_run, user):
    if payroll_run.status != "CALCULATED":
        raise PayrollError("Only calculated runs can be approved.")
    if payroll_run.prepared_by_id and payroll_run.prepared_by_id == user.id:
        raise PayrollError(
            "Segregation of duties: the preparer cannot approve their own payroll run."
        )
    payroll_run.status = "APPROVED"
    payroll_run.approved_by = user
    payroll_run.approved_at = timezone.now()
    payroll_run.save()
    _log_run_audit(payroll_run, "APPROVE", user, {"stage": "pastor"})
    return payroll_run


def _balance_journal(transaction):
    """Apply penny adjustment to the salary expense line when rounding leaves a residual."""
    from transactions.models import TransactionLine

    total = sum(line.amount for line in transaction.lines.all())
    if total == Decimal("0.00"):
        return
    expense_line = (
        TransactionLine.objects.filter(
            transaction=transaction,
            account__account_type="SALARY_EXPENSE",
        )
        .order_by("id")
        .first()
    )
    if expense_line:
        expense_line.amount = _quantize(expense_line.amount - Decimal(str(total)))
        expense_line.save(update_fields=["amount"])


@db_transaction.atomic
def post_payroll_run(payroll_run, user, idempotency_key=None):
    """Post accrual journal to the general ledger."""
    from transactions.idempotency import (
        IdempotencyReplay,
        claim_financial_idempotency,
        complete_financial_idempotency,
        normalize_idempotency_key,
    )
    from transactions.models import Transaction, TransactionLine
    from transactions.services import (
        _get_account,
        _log_audit,
        assert_period_open,
        assert_working_day_allows_posting,
        resolve_transaction_date,
        validate_transaction_balance,
    )

    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)

    if payroll_run.status != "APPROVED":
        raise PayrollError("Only approved runs can be posted.")
    if not payroll_run.approved_by_id:
        raise PayrollError("Pastor approval is required before posting.")
    if not payroll_run.treasury_approved_by_id:
        raise PayrollError("Treasury review is required before posting.")
    if payroll_run.transaction_id:
        raise PayrollError("Payroll run is already posted.")
    if payroll_run.budget_warning.get("over_budget") and not payroll_run.budget_warning.get(
        "override_budget"
    ):
        # Soft block with clear message — allow override via flag set by approver path later
        pass

    key = normalize_idempotency_key(idempotency_key) or f"payroll-post-{payroll_run.pk}"
    try:
        idem_record = claim_financial_idempotency(
            payroll_run.host_church, user, "PAYROLL_POST", key
        )
    except IdempotencyReplay as replay:
        payroll_run.refresh_from_db()
        if payroll_run.transaction_id:
            return payroll_run
        raise PayrollError("Duplicate payroll post detected.") from replay

    church = payroll_run.host_church
    # Post to the open working day (pay_date remains on the run for period reference).
    posting_date = resolve_transaction_date(church)
    assert_period_open(church, posting_date)
    assert_working_day_allows_posting(church, posting_date)

    paye_total = Decimal("0.00")
    ssnit_ee_total = Decimal("0.00")
    ssnit_er_total = Decimal("0.00")
    pension_total = Decimal("0.00")
    loan_deductions = Decimal("0.00")
    other_deductions = Decimal("0.00")
    net_total = Decimal("0.00")

    for line in payroll_run.lines.prefetch_related("items"):
        for item in line.items.filter(item_type="DEDUCTION"):
            if item.code == "PAYE":
                paye_total += item.amount
            elif item.code == "SSNIT_EE":
                ssnit_ee_total += item.amount
            elif item.code == "LOAN":
                loan_deductions += item.amount
            else:
                other_deductions += item.amount
        for item in line.items.filter(item_type="EMPLOYER"):
            if item.code == "SSNIT_ER":
                ssnit_er_total += item.amount
            elif item.code == "PENSION_T2":
                pension_total += item.amount
        net_total += line.net_pay

    trx = Transaction.objects.create(
        transaction_type="PAYROLL",
        church=church,
        created_by=user,
        description=f"Payroll accrual — {payroll_run.reference}",
        date=posting_date,
        approval_status="APPROVED",
        approved_by=user,
        approved_at=timezone.now(),
        locked=False,
    )

    salary_expense = _get_account(church, "SALARY_EXPENSE")
    employer_expense = _get_account(church, "EMPLOYER_SSNIT_EXPENSE")
    salaries_payable = _get_account(church, "SALARIES_PAYABLE")
    paye_payable = _get_account(church, "PAYE_PAYABLE")
    ssnit_payable = _get_account(church, "SSNIT_PAYABLE")
    pension_payable = _get_account(church, "PENSION_PAYABLE")

    employer_total = ssnit_er_total + pension_total
    debit_salary = payroll_run.total_gross
    debit_employer = employer_total

    TransactionLine.objects.create(transaction=trx, account=salary_expense, amount=debit_salary)
    if debit_employer > 0:
        TransactionLine.objects.create(transaction=trx, account=employer_expense, amount=debit_employer)
    if paye_total > 0:
        TransactionLine.objects.create(transaction=trx, account=paye_payable, amount=-paye_total)
    ssnit_all = ssnit_ee_total + ssnit_er_total
    if ssnit_all > 0:
        TransactionLine.objects.create(transaction=trx, account=ssnit_payable, amount=-ssnit_all)
    if pension_total > 0:
        TransactionLine.objects.create(transaction=trx, account=pension_payable, amount=-pension_total)
    # Net + loan + other deductions = gross - PAYE - SSNIT_EE (salaries payable credit)
    payable_credit = net_total + loan_deductions + other_deductions
    if payable_credit > 0:
        TransactionLine.objects.create(transaction=trx, account=salaries_payable, amount=-payable_credit)

    _balance_journal(trx)
    validate_transaction_balance(trx)
    trx.locked = True
    trx.save(update_fields=["locked"])
    _log_audit(
        church,
        "CREATE",
        user,
        transaction=trx,
        details={
            "payroll_run": payroll_run.reference,
            "paye": str(paye_total),
            "ssnit": str(ssnit_all),
            "statutory_remittance_note": (
                "PAYE/SSNIT liabilities posted; settle via Finance remittance/statutory payment."
            ),
        },
    )

    payroll_run.transaction = trx
    payroll_run.status = "POSTED"
    payroll_run.posted_at = timezone.now()
    payroll_run.save()
    complete_financial_idempotency(idem_record, trx)
    _log_run_audit(payroll_run, "POST", user, {"transaction": trx.reference})
    return payroll_run


@db_transaction.atomic
def pay_payroll_run(payroll_run, user, payment_account_type="BANK", idempotency_key=None):
    """Clear salaries payable and record bank payment."""
    from transactions.idempotency import (
        IdempotencyReplay,
        claim_financial_idempotency,
        complete_financial_idempotency,
        normalize_idempotency_key,
    )
    from transactions.models import Transaction, TransactionLine
    from transactions.services import (
        _get_account,
        _log_audit,
        assert_period_open,
        assert_working_day_allows_posting,
        resolve_transaction_date,
        validate_transaction_balance,
    )

    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)

    if payroll_run.status != "POSTED":
        raise PayrollError("Only posted runs can be marked as paid.")
    if payroll_run.payment_transaction_id:
        raise PayrollError("Payroll run is already paid.")

    key = normalize_idempotency_key(idempotency_key) or f"payroll-pay-{payroll_run.pk}"
    try:
        idem_record = claim_financial_idempotency(
            payroll_run.host_church, user, "PAYROLL_PAY", key
        )
    except IdempotencyReplay as replay:
        payroll_run.refresh_from_db()
        if payroll_run.payment_transaction_id:
            return payroll_run
        raise PayrollError("Duplicate payroll payment detected.") from replay

    church = payroll_run.host_church
    posting_date = resolve_transaction_date(church)
    assert_period_open(church, posting_date)
    assert_working_day_allows_posting(church, posting_date)
    amount = payroll_run.total_net
    if amount <= 0:
        raise PayrollError("Net pay amount must be greater than zero.")

    trx = Transaction.objects.create(
        transaction_type="TRANSFER",
        church=church,
        created_by=user,
        description=f"Payroll payment — {payroll_run.reference}",
        date=posting_date,
        approval_status="APPROVED",
        approved_by=user,
        approved_at=timezone.now(),
        locked=False,
    )

    salaries_payable = _get_account(church, "SALARIES_PAYABLE")
    payment = _get_account(church, payment_account_type)

    TransactionLine.objects.create(transaction=trx, account=salaries_payable, amount=amount)
    TransactionLine.objects.create(transaction=trx, account=payment, amount=-amount)

    validate_transaction_balance(trx)
    trx.locked = True
    trx.save(update_fields=["locked"])
    _log_audit(church, "CREATE", user, transaction=trx, details={"payroll_payment": payroll_run.reference})

    for line in payroll_run.lines.prefetch_related("items"):
        for item in line.items.filter(item_type="DEDUCTION", code="LOAN"):
            loan = None
            if item.source_ref:
                loan = EmployeeLoan.objects.filter(
                    pk=item.source_ref, employee=line.employee
                ).first()
            if not loan:
                loan = EmployeeLoan.objects.filter(
                    employee=line.employee, status="ACTIVE"
                ).first()
            if loan:
                loan.balance = max(Decimal("0"), loan.balance - item.amount)
                if loan.balance == 0:
                    loan.status = "PAID"
                loan.save()

    payroll_run.payment_transaction = trx
    payroll_run.status = "PAID"
    payroll_run.paid_at = timezone.now()
    payroll_run.save()
    complete_financial_idempotency(idem_record, trx)
    _log_run_audit(payroll_run, "PAY", user, {"amount": str(amount)})
    return payroll_run


@db_transaction.atomic
def reverse_payroll_run(payroll_run, user, reason=""):
    """
    Reverse a POSTED or PAID payroll run via equal-and-opposite GL journals.
    Does not delete history; marks the run VOID after reversal.
    """
    from transactions.services import void_transaction

    payroll_run = PayrollRun.objects.select_for_update().get(pk=payroll_run.pk)
    if payroll_run.status not in ("POSTED", "PAID"):
        raise PayrollError("Only posted or paid runs can be reversed.")
    reason = (reason or "").strip() or "Payroll reversal"

    if payroll_run.payment_transaction_id and not payroll_run.payment_transaction.is_voided:
        void_transaction(payroll_run.payment_transaction, user)
    if payroll_run.transaction_id and not payroll_run.transaction.is_voided:
        void_transaction(payroll_run.transaction, user)

    # Restore loan balances for LOAN recoveries applied on pay
    if payroll_run.status == "PAID":
        for line in payroll_run.lines.prefetch_related("items"):
            for item in line.items.filter(item_type="DEDUCTION", code="LOAN"):
                if not item.source_ref:
                    continue
                loan = EmployeeLoan.objects.filter(pk=item.source_ref).first()
                if loan:
                    loan.balance = _quantize(loan.balance + item.amount)
                    if loan.status == "PAID" and loan.balance > 0:
                        loan.status = "ACTIVE"
                    loan.save()

    payroll_run.status = "VOID"
    payroll_run.save(update_fields=["status", "updated_at"])
    _log_run_audit(payroll_run, "REVERSE", user, {"reason": reason})
    return payroll_run


def payroll_register_rows(payroll_run):
    rows = []
    for line in payroll_run.lines.select_related("employee", "employee__department").prefetch_related("items"):
        rows.append({
            "employee_number": line.employee.employee_number,
            "name": line.employee.full_name,
            "department": str(line.employee.department) if line.employee.department_id else "—",
            "gross": line.gross_pay,
            "deductions": line.total_deductions,
            "net": line.net_pay,
            "employer_cost": line.employer_cost,
            "payslip": line.payslip_number,
            "line_pk": line.pk,
        })
    return rows


def statutory_schedule(payroll_run):
    """PAYE and SSNIT totals for filing schedules."""
    paye = Decimal("0.00")
    ssnit_ee = Decimal("0.00")
    ssnit_er = Decimal("0.00")
    for line in payroll_run.lines.prefetch_related("items"):
        for item in line.items.all():
            if item.code == "PAYE":
                paye += item.amount
            elif item.code == "SSNIT_EE":
                ssnit_ee += item.amount
            elif item.code == "SSNIT_ER":
                ssnit_er += item.amount
    return {
        "paye": _quantize(paye),
        "ssnit_employee": _quantize(ssnit_ee),
        "ssnit_employer": _quantize(ssnit_er),
        "ssnit_total": _quantize(ssnit_ee + ssnit_er),
    }


def bank_payment_csv(payroll_run, *, mask_accounts=False):
    """Generate CSV for bulk bank transfer."""
    from payroll.encryption import mask_account_number

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee Number", "Name", "Bank", "Branch", "Account", "Amount", "Reference"])
    for line in payroll_run.lines.select_related("employee"):
        pii = get_employee_pii(line.employee)
        account = pii["bank_account"]
        if mask_accounts:
            account = mask_account_number(account)
        writer.writerow([
            line.employee.employee_number,
            line.employee.full_name,
            line.employee.bank_name,
            line.employee.bank_branch,
            account,
            str(line.net_pay),
            line.payslip_number,
        ])
    return output.getvalue()


def generate_payslip_pdf(payroll_line):
    """Generate a payslip PDF using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    run = payroll_line.payroll_run
    employee = payroll_line.employee
    church = run.host_church

    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph(f"<b>{church.name}</b>", styles["Title"]))
    story.append(Paragraph("Payslip", styles["Heading2"]))
    story.append(Spacer(1, 12))

    info = [
        ["Employee", employee.full_name],
        ["Employee No.", employee.employee_number],
        ["Period", run.period_label],
        ["Pay Date", str(run.pay_date)],
        ["Payslip No.", payroll_line.payslip_number],
    ]
    t = Table(info, colWidths=[120, 300])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)
    story.append(Spacer(1, 16))

    earnings = [["Earnings", "Amount (₵)"]]
    for item in payroll_line.items.filter(item_type="EARNING"):
        earnings.append([item.label, f"{item.amount:.2f}"])
    earnings.append(["Gross Pay", f"{payroll_line.gross_pay:.2f}"])

    ded = [["Deductions", "Amount (₵)"]]
    for item in payroll_line.items.filter(item_type="DEDUCTION"):
        ded.append([item.label, f"{item.amount:.2f}"])
    ded.append(["Total Deductions", f"{payroll_line.total_deductions:.2f}"])

    for table_data, title in [(earnings, "Earnings"), (ded, "Deductions")]:
        tbl = Table(table_data, colWidths=[280, 140])
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 12))

    story.append(Paragraph(f"<b>Net Pay: ₵{payroll_line.net_pay:.2f}</b>", styles["Heading3"]))
    doc.build(story)
    buffer.seek(0)
    return buffer


def ytd_summary(employee, year):
    """Year-to-date totals for tax certificate (Phase 3)."""
    lines = PayrollLine.objects.filter(
        employee=employee,
        payroll_run__year=year,
        payroll_run__status__in=("POSTED", "PAID"),
    )
    gross = sum(l.gross_pay for l in lines)
    deductions = sum(l.total_deductions for l in lines)
    net = sum(l.net_pay for l in lines)
    paye = Decimal("0.00")
    for line in lines.prefetch_related("items"):
        for item in line.items.filter(code="PAYE"):
            paye += item.amount
    return {
        "year": year,
        "gross": _quantize(gross),
        "deductions": _quantize(deductions),
        "net": _quantize(net),
        "paye": _quantize(paye),
        "months_paid": lines.count(),
    }


def resolve_paying_unit_label(unit_type, unit_id):
    from organization.models import Church, Conference, District, GeneralConference, Union

    model_map = {
        "CHURCH": Church,
        "DISTRICT": District,
        "CONFERENCE": Conference,
        "UNION": Union,
        "GENERAL_CONFERENCE": GeneralConference,
    }
    model = model_map.get(unit_type)
    if not model:
        return unit_type
    obj = model.objects.filter(pk=unit_id).first()
    return str(obj) if obj else f"{unit_type} ({unit_id})"


def get_unit_choices(unit_type, church=None):
    """Return (uuid, label) tuples for paying unit picker."""
    from organization.models import Church, Conference, District, GeneralConference, Union

    if not church:
        return []
    if unit_type == "CHURCH":
        return [(str(church.pk), str(church))]
    if unit_type == "DISTRICT":
        return [(str(church.district.pk), str(church.district))]
    if unit_type == "CONFERENCE":
        return [(str(church.conference.pk), str(church.conference))]
    if unit_type == "UNION":
        if church.union:
            return [(str(church.union.pk), str(church.union))]
        return []
    if unit_type == "GENERAL_CONFERENCE":
        if church.general_conference:
            return [(str(church.general_conference.pk), str(church.general_conference))]
        return []
    return []


def resolve_paying_unit_id(church, unit_type, unit_id=None):
    """Resolve paying unit UUID from type and optional explicit selection."""
    choices = get_unit_choices(unit_type, church=church)
    if unit_id:
        return unit_id
    if choices:
        return choices[0][0]
    raise PayrollError(f"No paying unit available for {unit_type}.")


def check_payroll_budget(church, year, run_gross):
    """Compare payroll gross against salary budget and YTD spend."""
    from django.db.models import Sum

    from transactions.models import Account, Budget

    account = Account.objects.filter(church=church, account_type="SALARY_EXPENSE").first()
    if not account:
        return {}

    budget = Budget.objects.filter(church=church, year=year, account=account).first()
    ytd_posted = PayrollRun.objects.filter(
        host_church=church,
        year=year,
        status__in=("POSTED", "PAID"),
    ).aggregate(total=Sum("total_gross"))["total"] or Decimal("0")

    projected = _quantize(ytd_posted + run_gross)
    if not budget:
        return {
            "has_budget": False,
            "ytd_posted": str(ytd_posted),
            "projected": str(projected),
            "over_budget": False,
        }

    over = projected > budget.amount
    return {
        "has_budget": True,
        "budgeted": str(budget.amount),
        "ytd_posted": str(ytd_posted),
        "projected": str(projected),
        "variance": str(_quantize(budget.amount - projected)),
        "over_budget": over,
        "message": (
            f"Projected salary spend ₵{projected} exceeds budget ₵{budget.amount}."
            if over else ""
        ),
    }


def hierarchy_payroll_rollup(user, year=None, month=None):
    """Consolidated payroll totals across manageable churches for hierarchy users."""
    from permissions.scoping import get_manageable_churches

    year = year or timezone.now().year
    churches = get_manageable_churches(user)
    church_ids = list(churches.values_list("pk", flat=True))
    if not church_ids:
        return []

    qs = PayrollRun.objects.filter(
        year=year,
        host_church_id__in=church_ids,
    ).exclude(status__in=("DRAFT", "VOID", "REJECTED"))
    if month:
        qs = qs.filter(month=month)

    rows = []
    for church in churches.filter(pk__in=qs.values_list("host_church_id", flat=True).distinct()):
        church_runs = qs.filter(host_church=church)
        rows.append({
            "church": str(church),
            "district": str(church.district) if church.district_id else "",
            "runs": church_runs.count(),
            "gross": _quantize(sum(r.total_gross for r in church_runs)),
            "net": _quantize(sum(r.total_net for r in church_runs)),
            "employer_cost": _quantize(sum(r.total_employer_cost for r in church_runs)),
        })
    return sorted(rows, key=lambda r: r["church"])


def statutory_liability_summary(payroll_run):
    """PAYE/SSNIT payable snapshot for remittance handoff."""
    schedule = statutory_schedule(payroll_run)
    return {
        **schedule,
        "status": payroll_run.status,
        "reference": payroll_run.reference,
        "period": payroll_run.period_label,
        "remittance_hint": (
            "Settle PAYE and SSNIT from the posted payable balances via Finance. "
            "Schedules are available as PDF exports on the run detail page."
        ),
    }
