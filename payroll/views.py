"""Payroll views."""

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from church_system.church_scope import get_active_church, require_church
from church_system.flash import flash_exception, flash_success, flash_warning
from sitecontrol.checks import require_feature
from permissions.checks import (
    can_approve_payroll,
    can_manage_payroll,
    can_manage_payroll_policy,
    can_pay_payroll,
    can_post_payroll,
    can_view_all_churches,
    can_view_own_payslips,
)
from payroll.forms import (
    CompensationForm,
    EmployeeForm,
    EmployeeLoanForm,
    PayrollRunForm,
    RejectPayrollForm,
    StatutoryRuleForm,
    TaxBandForm,
)
from payroll.models import (
    DeductionType,
    Employee,
    EmployeeCompensation,
    EmployeeCompensationLine,
    PayComponentType,
    PayrollLine,
    PayrollRun,
    PayrollTaxBand,
    PayrollTaxTable,
    StatutoryContributionRule,
)
from payroll.reports import (
    department_cost_report,
    employer_cost_report,
    generate_paye_schedule_pdf,
    generate_ssnit_schedule_pdf,
    generate_tax_certificate_pdf,
    payroll_register_csv,
)
from payroll.services import (
    PayrollError,
    approve_payroll_run,
    bank_payment_csv,
    calculate_payroll_run,
    create_payroll_run,
    generate_payslip_pdf,
    hierarchy_payroll_rollup,
    pay_payroll_run,
    payroll_register_rows,
    post_payroll_run,
    reject_payroll_run,
    reopen_payroll_run,
    resolve_paying_unit_id,
    resolve_paying_unit_label,
    reverse_payroll_run,
    statutory_liability_summary,
    statutory_schedule,
    treasury_approve_payroll_run,
    void_payroll_run,
    ytd_summary,
)
from payroll.services import _log_run_audit


def _payroll_access(view_func):
    decorated = require_feature("payroll")(view_func)

    @login_required
    def _wrapped(request, *args, **kwargs):
        if not can_manage_payroll(request.user):
            raise PermissionDenied
        return decorated(request, *args, **kwargs)
    return _wrapped


@_payroll_access
def index(request):
    church = require_church(request)
    runs = PayrollRun.objects.filter(host_church=church).order_by("-year", "-month")[:20]
    employees = Employee.objects.filter(host_church=church, status="ACTIVE").count()
    over_budget = PayrollRun.objects.filter(
        host_church=church,
        budget_warning__over_budget=True,
    ).exclude(status__in=("VOID", "PAID")).count()
    return render(request, "payroll/index.html", {
        "runs": runs,
        "employee_count": employees,
        "over_budget_count": over_budget,
        "active_church": church,
        "can_policy": can_manage_payroll_policy(request.user),
        "can_hierarchy": can_view_all_churches(request.user),
    })


@_payroll_access
def hierarchy_dashboard(request):
    if not can_view_all_churches(request.user):
        raise PermissionDenied
    year = int(request.GET.get("year", timezone.now().year))
    month = request.GET.get("month")
    month = int(month) if month else None
    rows = hierarchy_payroll_rollup(request.user, year=year, month=month)
    return render(request, "payroll/hierarchy.html", {
        "rows": rows,
        "year": year,
        "month": month,
        "active_church": get_active_church(request),
    })


@_payroll_access
def employee_list(request):
    church = require_church(request)
    employees = Employee.objects.filter(host_church=church).select_related("department", "member", "user")
    unit_type = request.GET.get("unit_type")
    if unit_type:
        employees = employees.filter(paying_unit_type=unit_type)
    status = request.GET.get("status")
    if status:
        employees = employees.filter(status=status)
    return render(request, "payroll/employee_list.html", {
        "employees": employees,
        "active_church": church,
        "status_filter": status,
        "unit_type_filter": unit_type,
    })


@_payroll_access
def employee_create(request):
    church = require_church(request)
    form = EmployeeForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        employee = form.save(commit=False)
        employee.created_by = request.user
        employee.save()
        flash_success(request, f"Employee {employee.full_name} added.")
        return redirect("payroll:employee_detail", pk=employee.pk)
    return render(request, "payroll/employee_form.html", {
        "form": form,
        "title": "Add Employee",
        "active_church": church,
    })


@_payroll_access
def employee_detail(request, pk):
    church = require_church(request)
    employee = get_object_or_404(Employee, pk=pk, host_church=church)
    compensations = employee.compensations.prefetch_related("lines__pay_component", "lines__deduction_type").order_by("-effective_from")
    loans = employee.loans.filter(status="ACTIVE")
    ytd = ytd_summary(employee, timezone.now().year)
    return render(request, "payroll/employee_detail.html", {
        "employee": employee,
        "compensations": compensations,
        "loans": loans,
        "ytd": ytd,
        "unit_label": resolve_paying_unit_label(employee.paying_unit_type, employee.paying_unit_id),
        "active_church": church,
    })


@_payroll_access
def employee_edit(request, pk):
    church = require_church(request)
    employee = get_object_or_404(Employee, pk=pk, host_church=church)
    form = EmployeeForm(request.POST or None, instance=employee, church=church)
    if request.method == "POST" and form.is_valid():
        form.save()
        flash_success(request, "Employee updated.")
        return redirect("payroll:employee_detail", pk=pk)
    return render(request, "payroll/employee_form.html", {
        "form": form,
        "title": "Edit Employee",
        "employee": employee,
        "active_church": church,
    })


@_payroll_access
def compensation_create(request, employee_pk):
    church = require_church(request)
    employee = get_object_or_404(Employee, pk=employee_pk, host_church=church)
    comp_form = CompensationForm(request.POST or None, initial={"effective_from": timezone.now().date()})
    components = PayComponentType.objects.filter(host_church=church, is_active=True)
    deductions = DeductionType.objects.filter(
        host_church=church, is_active=True, is_statutory=False,
    ).exclude(code__in=("PAYE", "SSNIT_EE", "PENSION_T2"))

    if request.method == "POST" and comp_form.is_valid():
        compensation = EmployeeCompensation.objects.create(
            employee=employee,
            effective_from=comp_form.cleaned_data["effective_from"],
            notes=comp_form.cleaned_data.get("notes", ""),
        )
        for component in components:
            amount = request.POST.get(f"amount_{component.code}")
            if amount and Decimal(str(amount)) > 0:
                line = EmployeeCompensationLine(
                    compensation=compensation,
                    line_type="EARNING",
                    pay_component=component,
                    amount=Decimal(str(amount)),
                )
                line.full_clean()
                line.save()
        for dtype in deductions:
            amount = request.POST.get(f"deduction_{dtype.code}")
            if amount and Decimal(str(amount)) > 0:
                line = EmployeeCompensationLine(
                    compensation=compensation,
                    line_type="DEDUCTION",
                    deduction_type=dtype,
                    amount=Decimal(str(amount)),
                )
                line.full_clean()
                line.save()
        EmployeeCompensation.objects.filter(employee=employee).exclude(pk=compensation.pk).update(is_active=False)
        flash_success(request, "Compensation profile saved.")
        return redirect("payroll:employee_detail", pk=employee.pk)

    return render(request, "payroll/compensation_form.html", {
        "employee": employee,
        "comp_form": comp_form,
        "components": components,
        "deductions": deductions,
        "active_church": church,
    })


@_payroll_access
def loan_create(request, employee_pk):
    church = require_church(request)
    employee = get_object_or_404(Employee, pk=employee_pk, host_church=church)
    form = EmployeeLoanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        loan = form.save(commit=False)
        loan.employee = employee
        loan.save()
        flash_success(request, "Loan/advance recorded.")
        return redirect("payroll:employee_detail", pk=employee.pk)
    return render(request, "payroll/loan_form.html", {
        "form": form,
        "employee": employee,
        "active_church": church,
    })


@_payroll_access
def tax_certificate_pdf(request, pk):
    church = require_church(request)
    employee = get_object_or_404(Employee, pk=pk, host_church=church)
    year = int(request.GET.get("year", timezone.now().year))
    pdf = generate_tax_certificate_pdf(employee, year)
    response = HttpResponse(pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="tax-cert-{employee.employee_number}-{year}.pdf"'
    return response


@_payroll_access
def run_list(request):
    church = require_church(request)
    runs = PayrollRun.objects.filter(host_church=church).order_by("-year", "-month")
    return render(request, "payroll/run_list.html", {
        "runs": runs,
        "active_church": church,
        "can_approve": can_approve_payroll(request.user),
        "can_post": can_post_payroll(request.user),
        "can_pay": can_pay_payroll(request.user),
    })


@_payroll_access
def run_create(request):
    church = require_church(request)
    form = PayrollRunForm(request.POST or None, church=church)
    if request.method == "POST" and form.is_valid():
        try:
            unit_id = resolve_paying_unit_id(
                church,
                form.cleaned_data["paying_unit_type"],
                form.cleaned_data.get("paying_unit_id"),
            )
            run = create_payroll_run(
                host_church=church,
                year=form.cleaned_data["year"],
                month=form.cleaned_data["month"],
                user=request.user,
                paying_unit_type=form.cleaned_data["paying_unit_type"],
                paying_unit_id=unit_id,
                pay_date=form.cleaned_data["pay_date"],
                description=form.cleaned_data.get("description", ""),
            )
            flash_success(request, f"Payroll run {run.reference} created.")
            return redirect("payroll:run_detail", pk=run.pk)
        except PayrollError as exc:
            flash_exception(request, exc)
    return render(request, "payroll/run_form.html", {
        "form": form,
        "title": "New Payroll Run",
        "active_church": church,
    })


@_payroll_access
def run_detail(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    register = payroll_register_rows(run)
    statutory = statutory_schedule(run) if run.status not in ("DRAFT", "REJECTED", "VOID") else None
    dept_costs = department_cost_report(run) if run.lines.exists() else []
    employer_costs = employer_cost_report(run) if run.lines.exists() else []
    reject_form = RejectPayrollForm()
    statutory_liabilities = (
        statutory_liability_summary(run) if run.status in ("POSTED", "PAID") else None
    )
    return render(request, "payroll/run_detail.html", {
        "run": run,
        "register": register,
        "statutory": statutory,
        "statutory_liabilities": statutory_liabilities,
        "dept_costs": dept_costs,
        "employer_costs": employer_costs,
        "reject_form": reject_form,
        "unit_label": resolve_paying_unit_label(run.paying_unit_type, run.paying_unit_id),
        "active_church": church,
        "can_approve": can_approve_payroll(request.user),
        "can_post": can_post_payroll(request.user),
        "can_pay": can_pay_payroll(request.user),
        "skipped_count": (run.budget_warning or {}).get("skipped_count", 0),
    })


@_payroll_access
@require_POST
def run_action(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    action = request.POST.get("action")
    idem_key = request.POST.get("idempotency_key") or f"{action}-{run.pk}-{request.user.pk}"

    try:
        if action == "calculate":
            calculate_payroll_run(run, request.user)
            run.refresh_from_db()
            skipped = (run.budget_warning or {}).get("skipped_count", 0)
            if run.budget_warning.get("over_budget"):
                flash_warning(request, run.budget_warning.get("message", "Payroll exceeds salary budget."))
            elif skipped:
                flash_warning(request, f"Payroll calculated with {skipped} employee(s) skipped.")
            else:
                flash_success(request, "Payroll calculated.")
        elif action == "approve":
            if not can_approve_payroll(request.user):
                raise PermissionDenied
            approve_payroll_run(run, request.user)
            flash_success(request, "Pastor approval recorded.")
        elif action == "treasury_approve":
            if not can_post_payroll(request.user):
                raise PermissionDenied
            treasury_approve_payroll_run(run, request.user)
            flash_success(request, "Treasury review complete.")
        elif action == "reject":
            if not (can_approve_payroll(request.user) or can_post_payroll(request.user)):
                raise PermissionDenied
            form = RejectPayrollForm(request.POST)
            if form.is_valid():
                reject_payroll_run(run, request.user, reason=form.cleaned_data["reason"])
                flash_success(request, "Payroll run rejected.")
            else:
                flash_exception(request, "Rejection reason is required.")
                return redirect("payroll:run_detail", pk=pk)
        elif action == "reopen":
            reopen_payroll_run(run, request.user)
            flash_success(request, "Run reopened as draft.")
        elif action == "void":
            if not can_approve_payroll(request.user):
                raise PermissionDenied
            void_payroll_run(run, request.user)
            flash_success(request, "Payroll run voided.")
        elif action == "reverse":
            if not (can_post_payroll(request.user) or can_approve_payroll(request.user)):
                raise PermissionDenied
            reverse_payroll_run(run, request.user, reason=request.POST.get("reason", ""))
            flash_success(request, "Payroll run reversed and voided.")
        elif action == "post":
            if not can_post_payroll(request.user):
                raise PermissionDenied
            post_payroll_run(run, request.user, idempotency_key=idem_key)
            flash_success(request, "Payroll posted to ledger.")
        elif action == "pay":
            if not can_pay_payroll(request.user):
                raise PermissionDenied
            pay_payroll_run(run, request.user, idempotency_key=idem_key)
            flash_success(request, "Payroll marked as paid.")
    except PayrollError as exc:
        flash_exception(request, exc)

    return redirect("payroll:run_detail", pk=pk)


@_payroll_access
def run_export_csv(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    if not can_pay_payroll(request.user):
        raise PermissionDenied("Bank payment export requires pay-payroll permission.")
    content = bank_payment_csv(run, mask_accounts=False)
    _log_run_audit(
        run,
        "EXPORT",
        request.user,
        {"format": "bank_csv", "lines": run.lines.count()},
    )
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{run.reference}-bank.csv"'
    return response


@_payroll_access
def run_export_register(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    content = payroll_register_csv(run)
    _log_run_audit(run, "EXPORT", request.user, {"format": "register_csv"})
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{run.reference}-register.csv"'
    return response


@_payroll_access
def run_paye_pdf(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    pdf = generate_paye_schedule_pdf(run)
    _log_run_audit(run, "EXPORT", request.user, {"format": "paye_pdf"})
    response = HttpResponse(pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{run.reference}-paye.pdf"'
    return response


@_payroll_access
def run_ssnit_pdf(request, pk):
    church = require_church(request)
    run = get_object_or_404(PayrollRun, pk=pk, host_church=church)
    pdf = generate_ssnit_schedule_pdf(run)
    _log_run_audit(run, "EXPORT", request.user, {"format": "ssnit_pdf"})
    response = HttpResponse(pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{run.reference}-ssnit.pdf"'
    return response


@login_required
@require_feature("payroll")
def payslip_pdf(request, line_pk):
    line = get_object_or_404(
        PayrollLine.objects.select_related("payroll_run", "employee", "employee__user"),
        pk=line_pk,
    )
    employee = line.employee
    if can_view_own_payslips(request.user) and employee.user_id == request.user.id:
        pass
    elif can_manage_payroll(request.user):
        church = require_church(request)
        if line.payroll_run.host_church_id != church.pk:
            raise PermissionDenied
    else:
        raise PermissionDenied
    pdf = generate_payslip_pdf(line)
    response = HttpResponse(pdf.read(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{line.payslip_number}.pdf"'
    return response


@login_required
@require_feature("payroll")
def my_payslips(request):
    if not can_view_own_payslips(request.user):
        raise PermissionDenied
    employee = getattr(request.user, "employee_profile", None)
    if not employee:
        return render(request, "payroll/my_payslips.html", {
            "lines": [],
            "message": "No employee profile is linked to your account.",
        })
    lines = PayrollLine.objects.filter(
        employee=employee,
        payroll_run__status__in=("POSTED", "PAID"),
    ).select_related("payroll_run").order_by("-payroll_run__year", "-payroll_run__month")
    ytd = ytd_summary(employee, timezone.now().year)
    return render(request, "payroll/my_payslips.html", {
        "lines": lines,
        "employee": employee,
        "ytd": ytd,
    })


def _policy_required(view_func):
    @login_required
    @require_feature("payroll")
    def _wrapped(request, *args, **kwargs):
        if not can_manage_payroll_policy(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped


@_policy_required
def policy_index(request):
    church = get_active_church(request) or require_church(request)
    rules = StatutoryContributionRule.objects.filter(host_church=church).order_by("code", "-effective_from")
    tables = PayrollTaxTable.objects.filter(host_church=church).prefetch_related("bands")
    return render(request, "payroll/policy_index.html", {
        "rules": rules,
        "tables": tables,
        "active_church": church,
    })


@_policy_required
def policy_rule_create(request):
    church = require_church(request)
    form = StatutoryRuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        rule = form.save(commit=False)
        rule.host_church = church
        rule.save()
        flash_success(request, "Statutory rule saved.")
        return redirect("payroll:policy_index")
    return render(request, "payroll/policy_form.html", {
        "form": form,
        "title": "Add Statutory Rule",
        "active_church": church,
    })


@_policy_required
def policy_band_add(request, table_pk):
    church = require_church(request)
    table = get_object_or_404(PayrollTaxTable, pk=table_pk, host_church=church)
    form = TaxBandForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        band = form.save(commit=False)
        band.tax_table = table
        band.save()
        flash_success(request, "Tax band added.")
        return redirect("payroll:policy_index")
    return render(request, "payroll/policy_form.html", {
        "form": form,
        "title": f"Add Band — {table.name}",
        "active_church": church,
    })
