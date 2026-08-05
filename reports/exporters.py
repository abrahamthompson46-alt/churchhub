"""Generic table export utilities for reports."""

import csv
from io import BytesIO

from django.http import HttpResponse
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def export_table_csv(headers, rows, filename="report.csv"):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    return response


def export_table_excel(headers, rows, filename="report.xlsx", sheet_title="Report"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]
    ws.append(headers)
    for row in rows:
        ws.append([_cell_value(c) for c in row])
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def export_table_pdf(headers, rows, title="ChurchHub Report", subtitle="", filename="report.pdf"):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 12),
    ]
    table_data = [headers] + [[str(_cell_value(c)) for c in row] for row in rows]
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
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _cell_value(val):
    from church_system.money import money_export_value

    return money_export_value(val)


def build_export_bytes(export_fmt, headers, rows, title, subtitle, report_key):
    """Build export file bytes for async jobs. Returns (bytes, content_type, filename)."""
    slug = report_key.replace("_", "-")
    if export_fmt == "csv":
        from io import StringIO

        text = StringIO()
        writer = csv.writer(text)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_cell_value(c) for c in row])
        content = text.getvalue().encode("utf-8")
        return content, "text/csv", f"{slug}.csv"
    if export_fmt == "excel":
        wb = Workbook()
        ws = wb.active
        ws.title = title[:31]
        ws.append(headers)
        for row in rows:
            ws.append([_cell_value(c) for c in row])
        buffer = BytesIO()
        wb.save(buffer)
        return (
            buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            f"{slug}.xlsx",
        )
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = [
        Paragraph(title, styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Spacer(1, 12),
    ]
    table_data = [headers] + [[str(_cell_value(c)) for c in row] for row in rows]
    table = Table(table_data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue(), "application/pdf", f"{slug}.pdf"
