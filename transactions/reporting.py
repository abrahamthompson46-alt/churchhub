"""Financial report export utilities."""

import csv
from decimal import Decimal
from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from church_system.money import money_export_value, quantize_money


def build_statement_rows(transactions):
    """Build running-balance statement rows from approved transactions."""
    rows = []
    running_balance = Decimal("0.00")
    total_receipt = Decimal("0.00")
    total_expense = Decimal("0.00")

    for t in transactions.prefetch_related("lines__account"):
        cash_delta = sum(
            (line.amount for line in t.lines.all()
             if line.account.account_type in ("CASH", "BANK")),
            Decimal("0.00"),
        )
        receipt = cash_delta if cash_delta > 0 else Decimal("0.00")
        expense = abs(cash_delta) if cash_delta < 0 else Decimal("0.00")
        total_receipt += receipt
        total_expense += expense
        running_balance += cash_delta

        rows.append({
            "date": t.date,
            "reference": t.reference,
            "description": t.description,
            "type": t.transaction_type,
            "receipt": quantize_money(receipt),
            "expense": quantize_money(expense),
            "balance": quantize_money(running_balance),
        })

    return (
        rows,
        quantize_money(total_receipt),
        quantize_money(total_expense),
        quantize_money(running_balance),
    )


def export_statement_csv(rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="financial_statement.csv"'
    writer = csv.writer(response)
    writer.writerow(["Date", "Reference", "Type", "Description", "Receipt", "Expense", "Balance"])
    for row in rows:
        writer.writerow([
            row["date"], row["reference"], row["type"], row["description"],
            money_export_value(row["receipt"]),
            money_export_value(row["expense"]),
            money_export_value(row["balance"]),
        ])
    return response


def export_statement_excel(rows, title="Financial Statement"):
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement"
    ws.append(["Date", "Reference", "Type", "Description", "Receipt", "Expense", "Balance"])
    for row in rows:
        ws.append([
            str(row["date"]), row["reference"], row["type"], row["description"],
            money_export_value(row["receipt"]),
            money_export_value(row["expense"]),
            money_export_value(row["balance"]),
        ])
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="financial_statement.xlsx"'
    return response


def export_statement_pdf(rows, church_name="", period=""):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("ChurchHub Financial Statement", styles["Title"]),
        Paragraph(f"{church_name} — {period}", styles["Normal"]),
        Spacer(1, 12),
    ]
    table_data = [["Date", "Ref", "Type", "Receipt", "Expense", "Balance"]]
    for row in rows:
        table_data.append([
            str(row["date"]),
            row["reference"] or "",
            row["type"],
            money_export_value(row["receipt"]),
            money_export_value(row["expense"]),
            money_export_value(row["balance"]),
        ])
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    doc.build(story)
    buffer.seek(0)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="financial_statement.pdf"'
    return response
