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


def statement_pdf_bytes(data):
    """Return (bytes, content_type) for statement-style PDF."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    document = data.get("document") or {}
    stmt = data.get("statement") or {}
    subtitle = (
        f"{document.get('scope_label', '')} · "
        f"{data.get('period_label', '')} · "
        f"{data.get('start_date', '')} to {data.get('end_date', '')}"
    )
    story = [
        Paragraph(data.get("title", "Financial report"), styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Paragraph(
            f"Prepared by {document.get('prepared_by', '')}",
            styles["Normal"],
        ),
        Spacer(1, 10),
    ]
    for kpi in stmt.get("kpis") or []:
        val = _cell_value(kpi.get("value"))
        story.append(Paragraph(f"<b>{kpi.get('label', '')}:</b> {val}", styles["Normal"]))
    story.append(Spacer(1, 8))

    multi = document.get("multi_church", False)
    for section in stmt.get("sections") or []:
        story.append(Paragraph(section.get("title", "Section"), styles["Heading2"]))
        layout = section.get("layout") or stmt.get("layout")
        if layout == "trial_balance":
            table_data = [["Account", "Type", "Debit", "Credit"]]
            for line in section.get("lines") or []:
                table_data.append([
                    line.get("label", ""),
                    line.get("account_type", ""),
                    _cell_value(line.get("debit") or ""),
                    _cell_value(line.get("credit") or ""),
                ])
            table_data.append([
                "Total",
                "",
                _cell_value(section.get("total")),
                _cell_value(section.get("total_credit")),
            ])
        else:
            headers = ["Account"]
            if multi:
                headers.append("Church")
            headers.append("Amount")
            table_data = [headers]
            for line in section.get("lines") or []:
                row = [line.get("label", "")]
                if multi:
                    row.append(line.get("church", ""))
                row.append(_cell_value(line.get("amount")))
                table_data.append(row)
            total_row = ["Total"]
            if multi:
                total_row.append("")
            total_row.append(_cell_value(section.get("total")))
            table_data.append(total_row)
        table = Table(table_data, repeatRows=1)
        table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ])
        )
        story.append(table)
        story.append(Spacer(1, 8))

    for row in stmt.get("footer_totals") or []:
        story.append(
            Paragraph(
                f"<b>{row.get('label', '')}:</b> {_cell_value(row.get('amount'))}",
                styles["Normal"],
            )
        )
    for note in stmt.get("notes") or []:
        story.append(Spacer(1, 4))
        story.append(Paragraph(str(note), styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue(), "application/pdf"


def export_statement_pdf(data, filename="report.pdf"):
    """PDF export aligned with on-screen statement sections."""
    content, content_type = statement_pdf_bytes(data)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def ledger_pdf_bytes(data):
    """PDF for general ledger — journals grouped by business date."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    document = data.get("document") or {}
    ledger = data.get("ledger") or {}
    multi = document.get("multi_church", False)
    subtitle = (
        f"{document.get('scope_label', '')} · "
        f"{data.get('period_label', '')} · "
        f"{data.get('start_date', '')} to {data.get('end_date', '')}"
    )
    story = [
        Paragraph(data.get("title", "Detailed Financial Report"), styles["Title"]),
        Paragraph(subtitle, styles["Normal"]),
        Paragraph(f"Prepared by {document.get('prepared_by', '')}", styles["Normal"]),
        Spacer(1, 10),
    ]
    stmt = data.get("statement") or {}
    for kpi in stmt.get("kpis") or []:
        val = _cell_value(kpi.get("value"))
        story.append(Paragraph(f"<b>{kpi.get('label', '')}:</b> {val}", styles["Normal"]))
    story.append(Spacer(1, 8))

    groups = ledger.get("groups") or [{"date": "", "journals": ledger.get("journals") or []}]
    for day in groups:
        if day.get("date"):
            story.append(Paragraph(str(day["date"]), styles["Heading2"]))
        for journal in day.get("journals") or []:
            meta = [journal.get("reference", ""), journal.get("type", "")]
            if multi:
                meta.append(journal.get("church", ""))
            story.append(
                Paragraph(
                    " · ".join(m for m in meta if m) or "Journal",
                    styles["Heading3"],
                )
            )
            if journal.get("narration"):
                story.append(Paragraph(journal["narration"], styles["Normal"]))
            table_data = [["Account", "Debit", "Credit"]]
            for line in journal.get("lines") or []:
                table_data.append([
                    line.get("account", ""),
                    _cell_value(line.get("debit") or ""),
                    _cell_value(line.get("credit") or ""),
                ])
            table = Table(table_data, repeatRows=1)
            table.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a5f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ])
            )
            story.append(table)
            story.append(Spacer(1, 6))

    for note in stmt.get("notes") or []:
        story.append(Paragraph(str(note), styles["Italic"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue(), "application/pdf"


def export_ledger_pdf(data, filename="general-ledger.pdf"):
    content, content_type = ledger_pdf_bytes(data)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def statement_excel_bytes(data):
    """Return (bytes, content_type) for statement-style Excel."""
    document = data.get("document") or {}
    stmt = data.get("statement") or {}
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    summary.append(["Report", data.get("title", "")])
    summary.append(["Scope", document.get("scope_label", "")])
    summary.append(["Period", data.get("period_label", "")])
    summary.append(["From", str(data.get("start_date", ""))])
    summary.append(["To", str(data.get("end_date", ""))])
    summary.append(["Prepared by", document.get("prepared_by", "")])
    summary.append([])
    summary.append(["KPI", "Value"])
    for kpi in stmt.get("kpis") or []:
        summary.append([kpi.get("label", ""), _cell_value(kpi.get("value"))])

    detail = wb.create_sheet("Detail")
    multi = document.get("multi_church", False)
    if any(s.get("layout") == "trial_balance" for s in (stmt.get("sections") or [])):
        detail.append(["Section", "Account", "Type", "Debit", "Credit"])
        for section in stmt.get("sections") or []:
            for line in section.get("lines") or []:
                detail.append([
                    section.get("title", ""),
                    line.get("label", ""),
                    line.get("account_type", ""),
                    _cell_value(line.get("debit") or ""),
                    _cell_value(line.get("credit") or ""),
                ])
    else:
        headers = ["Section", "Account"]
        if multi:
            headers.append("Church")
        headers.append("Amount")
        detail.append(headers)
        for section in stmt.get("sections") or []:
            for line in section.get("lines") or []:
                row = [section.get("title", ""), line.get("label", "")]
                if multi:
                    row.append(line.get("church", ""))
                row.append(_cell_value(line.get("amount")))
                detail.append(row)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return (
        buffer.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def export_statement_excel(data, filename="report.xlsx"):
    """Excel export: Summary + Detail sheets for statement reports."""
    content, content_type = statement_excel_bytes(data)
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def build_export_bytes(export_fmt, headers, rows, title, subtitle, report_key, data=None):
    """Build export file bytes for async jobs. Returns (bytes, content_type, filename)."""
    slug = report_key.replace("_", "-")
    payload = data or {}
    stmt = payload.get("statement") or {}
    if export_fmt == "pdf" and stmt.get("sections"):
        content, content_type = statement_pdf_bytes(payload)
        return content, content_type, f"{slug}.pdf"
    ledger = payload.get("ledger") or {}
    if export_fmt == "pdf" and ledger.get("journals"):
        content, content_type = ledger_pdf_bytes(payload)
        return content, content_type, f"{slug}.pdf"
    if export_fmt == "excel" and stmt.get("sections"):
        content, content_type = statement_excel_bytes(payload)
        return content, content_type, f"{slug}.xlsx"
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
