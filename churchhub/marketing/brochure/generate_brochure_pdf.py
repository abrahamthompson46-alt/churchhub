#!/usr/bin/env python3
"""
Generate ChurchHub Enterprise brochure PDF (print-ready).

Usage (from repo root):
  python churchhub/marketing/brochure/generate_brochure_pdf.py

Output:
  churchhub/marketing/brochure/ChurchHub_Enterprise_Brochure.pdf
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    FrameBreak,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "ChurchHub_Enterprise_Brochure.pdf"

# Brand palette (enterprise navy / trust blue — not purple gradients)
NAVY = colors.HexColor("#0f172a")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748b")
LINE = colors.HexColor("#e2e8f0")
SOFT = colors.HexColor("#f8fafc")
BLUE = colors.HexColor("#1d4ed8")
TEAL = colors.HexColor("#047857")
WHITE = colors.white
ACCENT_BAR = colors.HexColor("#1e3a5f")


def _styles():
    base = getSampleStyleSheet()
    styles = {
        "cover_brand": ParagraphStyle(
            "cover_brand",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=6,
            tracking=2,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            textColor=colors.HexColor("#cbd5e1"),
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "cover_headline": ParagraphStyle(
            "cover_headline",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=WHITE,
            alignment=TA_CENTER,
            leading=26,
            spaceAfter=14,
        ),
        "cover_body": ParagraphStyle(
            "cover_body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            textColor=colors.HexColor("#e2e8f0"),
            alignment=TA_CENTER,
            leading=15,
            spaceAfter=10,
        ),
        "cover_meta": ParagraphStyle(
            "cover_meta",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#94a3b8"),
            alignment=TA_CENTER,
            leading=13,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=NAVY,
            spaceBefore=4,
            spaceAfter=10,
            leading=20,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            textColor=BLUE,
            spaceBefore=10,
            spaceAfter=6,
            leading=14,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            textColor=SLATE,
            alignment=TA_JUSTIFY,
            leading=13.5,
            spaceAfter=7,
        ),
        "body_left": ParagraphStyle(
            "body_left",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            textColor=SLATE,
            alignment=TA_LEFT,
            leading=13.5,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.2,
            textColor=SLATE,
            leading=12.5,
            leftIndent=2,
        ),
        "table_header": ParagraphStyle(
            "table_header",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=WHITE,
            leading=10,
        ),
        "table_cell": ParagraphStyle(
            "table_cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=SLATE,
            leading=10.5,
        ),
        "table_cell_b": ParagraphStyle(
            "table_cell_b",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=NAVY,
            leading=10.5,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=7.5,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "section_kicker": ParagraphStyle(
            "section_kicker",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=BLUE,
            spaceAfter=2,
            tracking=1,
        ),
        "quote": ParagraphStyle(
            "quote",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=MUTED,
            leading=12,
            leftIndent=8,
            spaceBefore=4,
            spaceAfter=8,
        ),
        "cta": ParagraphStyle(
            "cta",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceBefore=8,
            spaceAfter=4,
        ),
    }
    return styles


def _p(text: str, style) -> Paragraph:
    return Paragraph(text.replace("\n", "<br/>"), style)


def _bullets(items: list[str], styles) -> ListFlowable:
    return ListFlowable(
        [ListItem(_p(i, styles["bullet"]), leftIndent=12, bulletColor=BLUE) for i in items],
        bulletType="bullet",
        start="•",
        leftIndent=14,
        bulletFontSize=8,
        spaceBefore=2,
        spaceAfter=8,
    )


def _kv_table(rows: list[tuple[str, str]], styles, col_widths=None) -> Table:
    data = [
        [_p(f"<b>{k}</b>", styles["table_cell_b"]), _p(v, styles["table_cell"])]
        for k, v in rows
    ]
    t = Table(data, colWidths=col_widths or [38 * mm, 132 * mm])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.4, LINE),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return t


def _data_table(headers: list[str], rows: list[list[str]], styles, col_widths) -> Table:
    head = [_p(h, styles["table_header"]) for h in headers]
    body = []
    for row in rows:
        body.append(
            [
                _p(c, styles["table_cell_b"] if i == 0 else styles["table_cell"])
                for i, c in enumerate(row)
            ]
        )
    t = Table([head] + body, colWidths=col_widths, repeatRows=1)
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("BOX", (0, 0), (-1, -1), 0.5, NAVY),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(body) + 1):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    t.setStyle(TableStyle(style_cmds))
    return t


def _section_header(canvas, doc, title: str):
    canvas.saveState()
    # Top accent bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, A4[1] - 14 * mm, A4[0], 14 * mm, fill=1, stroke=0)
    canvas.setFillColor(BLUE)
    canvas.rect(0, A4[1] - 15.2 * mm, A4[0], 1.2 * mm, fill=1, stroke=0)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(18 * mm, A4[1] - 9 * mm, "CHURCHHUB ENTERPRISE")
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 18 * mm, A4[1] - 9 * mm, title)
    # Footer
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.4)
    canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(18 * mm, 9 * mm, "Confidential · Prospective partners")
    canvas.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {doc.page}")
    canvas.restoreState()


def _cover_page(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    # Accent stripe
    canvas.setFillColor(BLUE)
    canvas.rect(0, A4[1] * 0.38, A4[0], 3.5 * mm, fill=1, stroke=0)
    canvas.setFillColor(TEAL)
    canvas.rect(0, A4[1] * 0.38 - 2 * mm, A4[0], 2 * mm, fill=1, stroke=0)
    # Bottom band
    canvas.setFillColor(ACCENT_BAR)
    canvas.rect(0, 0, A4[0], 28 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.HexColor("#94a3b8"))
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(
        A4[0] / 2,
        12 * mm,
        "Brochure Edition  ·  Churches · Conferences · Unions · Denominational Networks",
    )
    canvas.restoreState()


def build_story(styles):
    story = []
    W = 170 * mm

    # ── COVER ──────────────────────────────────────────────
    story.append(NextPageTemplate("cover"))
    story.append(Spacer(1, 55 * mm))
    story.append(_p("CHURCHHUB", styles["cover_brand"]))
    story.append(_p("Enterprise Church Management System", styles["cover_sub"]))
    story.append(Spacer(1, 8 * mm))
    story.append(
        _p(
            "One platform. Complete hierarchy.<br/>Books you can trust.",
            styles["cover_headline"],
        )
    )
    story.append(
        _p(
            "Govern membership, treasury, remittance, and church life—from the local "
            "congregation to conference and union scale—with role-based security, "
            "denomination isolation, and double-entry financial integrity.",
            styles["cover_body"],
        )
    )
    story.append(Spacer(1, 10 * mm))
    story.append(
        _p(
            "<b>Scale:</b> 100 members → 100,000+ &nbsp;|&nbsp; "
            "<b>For:</b> Clerks · Treasurers · Pastors · Overseers · Operators",
            styles["cover_meta"],
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(
        _p(
            "Request a Demo  ·  Talk to Sales  ·  Pilot Program",
            styles["cover_meta"],
        )
    )

    # ── 01 COMPANY ─────────────────────────────────────────
    story.append(NextPageTemplate("interior"))
    story.append(PageBreak())
    story.append(_p("01  ·  COMPANY INTRODUCTION", styles["section_kicker"]))
    story.append(_p("Enterprise discipline for ministry operations", styles["h1"]))
    story.append(
        _p(
            "ChurchHub was built for a simple reality: <b>church administration is "
            "enterprise work</b>. Membership records, tithes and offerings, remittance "
            "obligations, pastoral meetings, and multi-level governance cannot be managed "
            "with spreadsheets and disconnected tools. Financial mistakes are not "
            "“IT issues”—they are trust issues.",
            styles["body"],
        )
    )
    story.append(
        _p(
            "ChurchHub Enterprise is a purpose-built Church Management System (ChMS) that unifies:",
            styles["body_left"],
        )
    )
    story.append(
        _bullets(
            [
                "<b>People &amp; pastoral operations</b>",
                "<b>Treasury &amp; double-entry accounting</b>",
                "<b>Hierarchical organization</b> (General Conference → Union → Conference → Zone → District → Local Church)",
                "<b>Denomination-level multi-tenancy</b> for SaaS and network deployments",
                "<b>Auditability</b> that leadership, finance committees, and reviewers can rely on",
            ],
            styles,
        )
    )
    story.append(
        _p(
            "We design for institutions that expect the same discipline they would demand "
            "from a financial system—not a consumer app with a church skin.",
            styles["quote"],
        )
    )

    # ── 02 OVERVIEW ────────────────────────────────────────
    story.append(_p("02  ·  PRODUCT OVERVIEW", styles["section_kicker"]))
    story.append(_p("A role-aware operations platform", styles["h1"]))
    story.append(
        _p(
            "ChurchHub is a <b>server-rendered, enterprise-grade operations platform</b> "
            "delivered through a secure web application. Staff work in a role-aware "
            "control center; members engage through a dedicated member portal.",
            styles["body"],
        )
    )
    story.append(_p("What leaders get on day one", styles["h2"]))
    story.append(
        _data_table(
            ["Capability", "Outcome"],
            [
                ["Mission Control dashboard", "Role-aware KPIs, action queues, teller console, pastoral pulse"],
                ["Membership lifecycle", "Directory, families, visitors, baptisms, transfers, leadership, gifts"],
                ["Church Life", "Announcements, calendar, meetings & minutes, church history chronicle"],
                ["Books of record", "Double-entry journals, approvals, voids via reversal, periods & working days"],
                ["Stewardship stack", "Receipts, expenses, budgets, giving statements, remittance & settlements"],
                ["Operations modules", "Payroll, fixed assets, welfare, reconciliation, reporting center"],
                ["Platform control plane", "Denominations, subscriptions, tenant applications, operator tooling"],
            ],
            styles,
            [48 * mm, 122 * mm],
        )
    )
    story.append(Spacer(1, 4 * mm))
    story.append(
        _p(
            "ChurchHub scales <b>with your structure</b>—not by forcing every congregation "
            "into a flat, single-site template.",
            styles["body"],
        )
    )

    # ── 03 BENEFITS ────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p("03  ·  KEY BENEFITS", styles["section_kicker"]))
    story.append(_p("Value at every scale", styles["h1"]))

    story.append(_p("Local church (100–2,000 members)", styles["h2"]))
    story.append(
        _bullets(
            [
                "Replace fragmented tools with one <b>permissioned workspace</b>",
                "Record offerings with <b>confirmation slips</b> treasurers can print and retain",
                "Keep pastoral follow-ups visible: visitors, birthdays, transfers, meetings",
                "Give members a <b>portal</b> for profile, announcements, and live/online meetings",
            ],
            styles,
        )
    )
    story.append(_p("District & conference (2,000–50,000 members)", styles["h2"]))
    story.append(
        _bullets(
            [
                "Enforce <b>scope</b>: users only see churches they are authorized to manage",
                "Roll up giving and remittance obligations across the hierarchy",
                "Standardize approval workflows and period controls",
                "Operate a <b>teller console</b> for high-volume service processing",
            ],
            styles,
        )
    )
    story.append(_p("Unions, networks & denominations (50,000–100,000+)", styles["h2"]))
    story.append(
        _bullets(
            [
                "Isolate tenants with a <b>denomination wall</b> (SaaS multi-tenancy)",
                "Provision churches with financial defaults and subscription awareness",
                "Run a separate <b>platform lane</b> for operators—without mixing institution data",
                "Deploy with PostgreSQL, Redis, Celery, HTTPS, and health checks",
            ],
            styles,
        )
    )
    story.append(_p("Cross-cutting value", styles["h2"]))
    story.append(
        _data_table(
            ["Benefit", "Why it matters"],
            [
                ["Financial integrity", "Debits equal credits; approved journals locked; corrections via reversals"],
                ["Least privilege", "RBAC matrix with implies/overrides—not “everyone is admin”"],
                ["Audit trails", "Domain audit logs for finance, organization, communications, and more"],
                ["Operational clarity", "Dashboards that tell staff what to do next—not just charts"],
                ["Institutional memory", "Church History chronicle for milestones that outlive any officer"],
            ],
            styles,
            [42 * mm, 128 * mm],
        )
    )

    # ── 04 MODULES ─────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p("04  ·  CORE MODULES", styles["section_kicker"]))
    story.append(_p("A complete institutional suite", styles["h1"]))
    story.append(
        _data_table(
            ["Module", "What it delivers"],
            [
                ["Accounts & Access", "Users, invitations, roles, activity logs, session security"],
                ["Organization", "GC → Union → Conference → Zone → District → Church; onboarding & transfers"],
                ["Members", "Profiles, families, visitors, baptisms, departments, leadership, gifts, records"],
                ["Meetings (Events)", "Scheduling, attendance, minutes workflow, online join links"],
                ["Announcements", "Draft → approve → publish; calendar of birthdays, meetings & events"],
                ["Church History", "Searchable institutional chronicle scoped by church or conference"],
                ["Transactions (GL)", "Chart of accounts, receipts/expenses, approvals, voids, working day, periods"],
                ["Ledger UI", "Category-driven journal posting templates into the books of record"],
                ["Budgets", "Planning and variance visibility against operational spend"],
                ["Giving", "Member giving visibility and statements (permission-controlled)"],
                ["Remittance", "Policies, cut-offs, settlements, welfare workflows"],
                ["Payroll", "Staff/pastor payroll integrated with accounting patterns"],
                ["Assets", "Fixed asset register, policy, lifecycle controls"],
                ["Reports", "Report center with export formats for leadership review"],
                ["Dashboard", "Mission Control, notifications, cut-off workspace"],
                ["Member Portal", "Login, profile, announcements, live meetings"],
                ["Site Control", "Denominations, subscriptions, payments, platform announcements"],
            ],
            styles,
            [42 * mm, 128 * mm],
        )
    )

    # ── 05 SECURITY ────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p("05  ·  SECURITY", styles["section_kicker"]))
    story.append(_p("Security is the operating model", styles["h1"]))
    story.append(
        _p(
            "Security is not a feature toggle. ChurchHub treats identity, authorization, "
            "and financial immutability as first-class product requirements.",
            styles["body"],
        )
    )
    story.append(_p("Identity & access", styles["h2"]))
    story.append(
        _bullets(
            [
                "Django session authentication with CSRF protection on mutating requests",
                "Role-based access control with a curated permission registry",
                "Hierarchy-aware scoping (church → district → conference → …)",
                "Platform operators use a <b>separate control plane</b>—not institution superuser shortcuts",
            ],
            styles,
        )
    )
    story.append(_p("Financial controls", styles["h2"]))
    story.append(
        _bullets(
            [
                "Maker-aware approval paths for sensitive postings",
                "Period lock and working-day gates for treasury discipline",
                "Idempotency on critical financial POSTs to prevent duplicate submissions",
                "Void via <b>reversing entries</b>—never silent edits of posted history",
            ],
            styles,
        )
    )
    story.append(_p("Data protection & operations", styles["h2"]))
    story.append(
        _bullets(
            [
                "Password hashing via Django’s framework (never plaintext)",
                "Upload validation (type, size, extension allowlists)",
                "Audit practices designed to avoid logging secrets or payroll PII",
                "Optional MFA for privileged roles (policy-configurable)",
                "Environment-based secrets; production posture: HTTPS, secure cookies, debug disabled",
            ],
            styles,
        )
    )

    # ── 06 MULTI-TENANT ────────────────────────────────────
    story.append(_p("06  ·  MULTI-TENANT ARCHITECTURE", styles["section_kicker"]))
    story.append(_p("Denomination wall. Church-scoped books.", styles["h1"]))
    story.append(
        _p(
            "ChurchHub supports <b>true institutional multi-tenancy</b> without collapsing "
            "every church into one shared inbox of data.",
            styles["body"],
        )
    )
    story.append(
        _p(
            "<b>Platform (/platform/)</b> → <b>Denomination</b> (SaaS boundary) → "
            "<b>Conference → Zone → District → Church</b> → church-owned records "
            "(members, journals, meetings, …)",
            styles["quote"],
        )
    )
    story.append(
        _data_table(
            ["Principle", "Implementation"],
            [
                ["Denomination wall", "Tenant isolation at the SaaS boundary"],
                ["Church as operational tenant", "Day-to-day books and membership bind to local church"],
                ["Server-side enforcement", "Scope filters on queries—never UI-only hiding"],
                ["Dual lanes", "Institution apps vs platform operator console"],
                ["Subscription awareness", "Church provisioning and plan limits for network operators"],
            ],
            styles,
            [48 * mm, 122 * mm],
        )
    )

    # ── 07 CLOUD ───────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p("07  ·  CLOUD DEPLOYMENT", styles["section_kicker"]))
    story.append(_p("Production-grade by design", styles["h1"]))
    story.append(
        _data_table(
            ["Layer", "Technology"],
            [
                ["Application", "Django (church_system)"],
                ["Web tier", "Gunicorn · Nginx"],
                ["Database", "PostgreSQL"],
                ["Cache / broker", "Redis"],
                ["Background jobs", "Celery · Celery Beat"],
                ["Static assets", "WhiteNoise"],
                ["Containers", "Docker · Docker Compose (prod profiles)"],
                ["Observability", "Health endpoints · optional Sentry · metrics-ready posture"],
            ],
            styles,
            [42 * mm, 128 * mm],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        _p(
            "Operations teams receive environment-separated settings, deployment checklists, "
            "runbooks, and process unit examples for web and workers—favoring predictable, "
            "auditable deployments over opaque black boxes.",
            styles["body"],
        )
    )

    # ── 08 MOBILE ──────────────────────────────────────────
    story.append(_p("08  ·  MOBILE SUPPORT", styles["section_kicker"]))
    story.append(_p("Responsive staff app + member portal", styles["h1"]))
    story.append(
        _bullets(
            [
                "Bootstrap 5 interface optimized for laptop, tablet, and phone browsers",
                "Critical treasury and pastoral workflows usable on smaller screens",
                "Member portal: secure login, announcements, profile, live/online meeting details",
                "Portal device confirmation for new browsers; privileged session hygiene",
            ],
            styles,
        )
    )
    story.append(
        _p(
            "ChurchHub is a <b>responsive web platform</b> (staff app + member portal). "
            "Native store apps can be a future roadmap item—not a dependency for go-live.",
            styles["quote"],
        )
    )

    # ── 09 ANALYTICS ───────────────────────────────────────
    story.append(_p("09  ·  ANALYTICS & INSIGHT", styles["section_kicker"]))
    story.append(_p("Workflow-native intelligence", styles["h1"]))
    story.append(
        _bullets(
            [
                "<b>Mission Control KPIs</b> — tithe, combined offering, remittance payable, action items",
                "<b>Teller Console</b> — live per-teller day performance",
                "<b>Church Performance</b> — hierarchy-aware giving visibility for overseers",
                "<b>District roll-ups</b> &amp; multi-month income vs expense trends",
                "<b>This Week Pulse</b> — visitors, birthdays, transfers, meetings",
                "<b>Report Center</b> — scoped exports for leadership packs and committees",
            ],
            styles,
        )
    )
    story.append(
        _p(
            "Insights sit next to the buttons that clear the queue—approve a transaction, "
            "follow up a visitor, process a remittance—not in a separate tool nobody opens.",
            styles["body"],
        )
    )

    # ── 10 PRICING ─────────────────────────────────────────
    story.append(PageBreak())
    story.append(_p("10  ·  PRICING PLACEHOLDERS", styles["section_kicker"]))
    story.append(_p("Commercial packaging for sales conversations", styles["h1"]))
    story.append(
        _p(
            "Commercial packaging is finalized per deployment model. The tiers below are "
            "<b>placeholders</b> for structured sales discussions.",
            styles["body"],
        )
    )
    story.append(
        _data_table(
            ["", "Parish", "Conference", "Network / Enterprise"],
            [
                ["Best for", "Single church · 100–1,500", "Multi-church conference", "Unions · denominations · SaaS"],
                ["Members", "Up to 1,500", "Up to 25,000", "25,000–100,000+"],
                ["Churches", "1", "Up to ___", "Unlimited*"],
                ["Core ChMS + Finance", "Included", "Included", "Included"],
                ["Hierarchy roll-ups", "—", "Included", "Included"],
                ["Platform / multi-denom", "—", "Optional", "Included"],
                ["Member portal", "Included", "Included", "Included"],
                ["Support", "Standard", "Priority", "Named CSM + SLA"],
                ["Deployment", "Cloud shared", "Dedicated / VPC", "Cloud or private"],
                ["Price", "$___ / month", "$___ / month", "Custom"],
            ],
            styles,
            [38 * mm, 42 * mm, 45 * mm, 45 * mm],
        )
    )
    story.append(Spacer(1, 2 * mm))
    story.append(
        _p(
            "*Subject to infrastructure sizing and fair-use policies.",
            styles["quote"],
        )
    )
    story.append(_p("Professional services (optional)", styles["h2"]))
    story.append(
        _bullets(
            [
                "Data migration &amp; chart-of-accounts mapping",
                "Treasurer &amp; clerk enablement workshops",
                "Custom report packs",
                "Pilot go-live hypercare (30–90 days)",
            ],
            styles,
        )
    )

    # ── 11 CONTACT ─────────────────────────────────────────
    story.append(Spacer(1, 4 * mm))
    story.append(_p("11  ·  CONTACT", styles["section_kicker"]))
    story.append(_p("Let’s build the operating system for your ministry network", styles["h1"]))
    story.append(
        _p(
            "ChurchHub Enterprise is ready for pilots, conference rollouts, and "
            "denomination-scale deployments.",
            styles["body"],
        )
    )
    story.append(
        _kv_table(
            [
                ("Sales", "sales@churchhub.example"),
                ("Partnerships", "partners@churchhub.example"),
                ("Support", "support@churchhub.example"),
                ("Web", "www.churchhub.example"),
                ("Demo", "Request a guided Mission Control walkthrough"),
            ],
            styles,
        )
    )
    story.append(_p("Pilot checklist (recommended)", styles["h2"]))
    story.append(
        _bullets(
            [
                "Select 1–3 churches for a 30–60 day pilot",
                "Provision hierarchy + chart of accounts",
                "Train treasurer, clerk, and pastor roles",
                "Validate remittance cut-off and approval workflows",
                "Enable member portal for a controlled group",
                "Review audit &amp; reporting packs with leadership",
            ],
            styles,
        )
    )
    story.append(Spacer(1, 8 * mm))
    story.append(_p("ChurchHub Enterprise", styles["cta"]))
    story.append(
        _p(
            "<i>Secure. Hierarchical. Financially accountable.</i>",
            styles["cover_meta"],
        )
    )
    story.append(Spacer(1, 3 * mm))
    story.append(
        _p(
            "© ChurchHub · All rights reserved · Brochure for prospective customers",
            styles["footer"],
        )
    )
    return story


def main():
    styles = _styles()
    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        title="ChurchHub Enterprise Brochure",
        author="ChurchHub",
        subject="Enterprise Church Management System product brochure",
    )

    cover_frame = Frame(
        18 * mm,
        35 * mm,
        A4[0] - 36 * mm,
        A4[1] - 70 * mm,
        id="cover",
    )
    interior_frame = Frame(
        18 * mm,
        18 * mm,
        A4[0] - 36 * mm,
        A4[1] - 36 * mm,
        id="interior",
    )

    def make_cover(canvas, doc):
        _cover_page(canvas, doc)

    def make_interior(canvas, doc):
        # Infer section from page roughly; keep generic header
        titles = {
            2: "Company · Product",
            3: "Benefits",
            4: "Modules",
            5: "Security · Tenancy",
            6: "Cloud · Mobile · Analytics",
            7: "Pricing · Contact",
        }
        _section_header(canvas, doc, titles.get(doc.page, "Product Brochure"))

    doc.addPageTemplates(
        [
            PageTemplate(id="cover", frames=[cover_frame], onPage=make_cover),
            PageTemplate(id="interior", frames=[interior_frame], onPage=make_interior),
        ]
    )

    doc.build(build_story(styles))
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
