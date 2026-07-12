"""Payroll PDF and CSV report generators."""

import csv
import io
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from payroll.services import get_employee_pii, payroll_register_rows, statutory_schedule, ytd_summary


def _pdf_table(data, col_widths=None):
    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
    ]))
    return tbl


def _build_pdf(title, church_name, subtitle, tables):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{church_name}</b>", styles["Title"]),
        Paragraph(title, styles["Heading2"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 16),
    ]
    for table_data, widths in tables:
        story.append(_pdf_table(table_data, widths))
        story.append(Spacer(1, 12))
    doc.build(story)
    buffer.seek(0)
    return buffer


def paye_schedule_rows(payroll_run):
    rows = []
    for line in payroll_run.lines.select_related("employee").prefetch_related("items"):
        paye = Decimal("0")
        gross = line.gross_pay
        for item in line.items.filter(code="PAYE"):
            paye = item.amount
        pii = get_employee_pii(line.employee)
        rows.append({
            "employee_number": line.employee.employee_number,
            "name": line.employee.full_name,
            "tin": pii["tin"] or "—",
            "gross": gross,
            "paye": paye,
        })
    return rows


def ssnit_schedule_rows(payroll_run):
    rows = []
    for line in payroll_run.lines.select_related("employee").prefetch_related("items"):
        ssnit_ee = ssnit_er = Decimal("0")
        for item in line.items.all():
            if item.code == "SSNIT_EE":
                ssnit_ee = item.amount
            elif item.code == "SSNIT_ER":
                ssnit_er = item.amount
        pii = get_employee_pii(line.employee)
        rows.append({
            "employee_number": line.employee.employee_number,
            "name": line.employee.full_name,
            "ssnit": pii["ssnit_number"] or "—",
            "basic": line.gross_pay,
            "employee": ssnit_ee,
            "employer": ssnit_er,
            "total": ssnit_ee + ssnit_er,
        })
    return rows


def generate_paye_schedule_pdf(payroll_run):
    church = payroll_run.host_church
    rows = paye_schedule_rows(payroll_run)
    totals = statutory_schedule(payroll_run)
    data = [["Employee No.", "Name", "TIN", "Gross (₵)", "PAYE (₵)"]]
    for row in rows:
        data.append([
            row["employee_number"], row["name"], row["tin"],
            f"{row['gross']:.2f}", f"{row['paye']:.2f}",
        ])
    data.append(["", "", "TOTAL", "", f"{totals['paye']:.2f}"])
    return _build_pdf(
        "PAYE Remittance Schedule",
        church.name,
        f"Period: {payroll_run.period_label} | Reference: {payroll_run.reference}",
        [(data, [80, 180, 100, 80, 80])],
    )


def generate_ssnit_schedule_pdf(payroll_run):
    church = payroll_run.host_church
    rows = ssnit_schedule_rows(payroll_run)
    totals = statutory_schedule(payroll_run)
    data = [["Employee No.", "Name", "SSNIT No.", "Gross (₵)", "EE (₵)", "ER (₵)", "Total (₵)"]]
    for row in rows:
        data.append([
            row["employee_number"], row["name"], row["ssnit"],
            f"{row['basic']:.2f}", f"{row['employee']:.2f}",
            f"{row['employer']:.2f}", f"{row['total']:.2f}",
        ])
    data.append(["", "", "TOTAL", "", f"{totals['ssnit_employee']:.2f}",
                 f"{totals['ssnit_employer']:.2f}", f"{totals['ssnit_total']:.2f}"])
    return _build_pdf(
        "SSNIT Contribution Schedule",
        church.name,
        f"Period: {payroll_run.period_label} | Reference: {payroll_run.reference}",
        [(data, [70, 150, 90, 70, 60, 60, 60])],
    )


def generate_tax_certificate_pdf(employee, year):
    church = employee.host_church
    summary = ytd_summary(employee, year)
    pii = get_employee_pii(employee)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(f"<b>{church.name}</b>", styles["Title"]),
        Paragraph(f"Annual Tax Certificate — {year}", styles["Heading2"]),
        Spacer(1, 12),
    ]
    info = [
        ["Employee", employee.full_name],
        ["Employee No.", employee.employee_number],
        ["TIN", pii["tin"] or "—"],
        ["SSNIT No.", pii["ssnit_number"] or "—"],
        ["Months Paid", str(summary["months_paid"])],
    ]
    story.append(_pdf_table(info, [120, 300]))
    story.append(Spacer(1, 16))
    totals = [
        ["Description", "Amount (₵)"],
        ["Total Gross Earnings", f"{summary['gross']:.2f}"],
        ["Total Deductions", f"{summary['deductions']:.2f}"],
        ["Total PAYE Withheld", f"{summary['paye']:.2f}"],
        ["Total Net Pay", f"{summary['net']:.2f}"],
    ]
    story.append(_pdf_table(totals, [280, 140]))
    story.append(Spacer(1, 24))
    story.append(Paragraph(
        "<i>This certificate is issued for income tax purposes. "
        "Retain for GRA filing and personal records.</i>",
        styles["Normal"],
    ))
    doc.build(story)
    buffer.seek(0)
    return buffer


def payroll_register_csv(payroll_run):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Employee Number", "Name", "Department", "Gross", "Deductions",
        "Net Pay", "Employer Cost", "Payslip No.",
    ])
    for row in payroll_register_rows(payroll_run):
        writer.writerow([
            row["employee_number"], row["name"], row["department"],
            str(row["gross"]), str(row["deductions"]), str(row["net"]),
            str(row["employer_cost"]), row["payslip"],
        ])
    return output.getvalue()


def employer_cost_report(payroll_run):
    """Employer cost breakdown by employee."""
    rows = []
    for line in payroll_run.lines.select_related("employee").prefetch_related("items"):
        employer_charges = sum(
            i.amount for i in line.items.filter(item_type="EMPLOYER")
        )
        rows.append({
            "name": line.employee.full_name,
            "gross": line.gross_pay,
            "employer_charges": employer_charges,
            "total_cost": line.employer_cost,
        })
    return rows


def department_cost_report(payroll_run):
    """Roll up payroll costs by department."""
    from collections import defaultdict

    buckets = defaultdict(lambda: {
        "gross": Decimal("0"), "net": Decimal("0"), "employer_cost": Decimal("0"), "count": 0,
    })
    for line in payroll_run.lines.select_related("employee", "employee__department"):
        dept = str(line.employee.department) if line.employee.department_id else "Unassigned"
        buckets[dept]["gross"] += line.gross_pay
        buckets[dept]["net"] += line.net_pay
        buckets[dept]["employer_cost"] += line.employer_cost
        buckets[dept]["count"] += 1
    return [
        {"department": dept, **vals}
        for dept, vals in sorted(buckets.items())
    ]
