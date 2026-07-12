"""Central catalog of available ChurchHub reports."""

REPORT_CATALOG = {
    "financial_summary": {
        "label": "Financial Summary",
        "description": "Tithe, offerings, income, and expense totals for the period.",
        "icon": "bi-cash-stack",
        "permission": "finance",
    },
    "member_summary": {
        "label": "Member Summary",
        "description": "Membership counts by status, gender, and department.",
        "icon": "bi-people",
        "permission": "members",
    },
    "tithe_report": {
        "label": "Tithe & Offering Report",
        "description": "Member-level tithe and combined offering contributions.",
        "icon": "bi-wallet2",
        "permission": "finance",
    },
    "transfer_report": {
        "label": "Member Transfers",
        "description": "Pending and completed member transfers.",
        "icon": "bi-arrow-left-right",
        "permission": "members",
    },
    "attendance_summary": {
        "label": "Attendance Summary",
        "description": "Worship and event attendance roll-up.",
        "icon": "bi-calendar-check",
        "permission": "members",
    },
    "hierarchy_rollup": {
        "label": "District Roll-up",
        "description": "Tithe and offering totals by district across your organization.",
        "icon": "bi-bar-chart-steps",
        "permission": "overseer",
    },
    "payroll_summary": {
        "label": "Payroll Summary",
        "description": "Employer cost and net pay by church for the period.",
        "icon": "bi-currency-exchange",
        "permission": "finance",
        "requires_feature": "payroll",
    },
    "trial_balance": {
        "label": "Trial Balance",
        "description": "Debit and credit balances for every GL account as of the period end.",
        "icon": "bi-balance",
        "permission": "finance",
        "requires_advanced": True,
    },
    "balance_sheet": {
        "label": "Balance Sheet",
        "description": "Assets, liabilities, and fund balances at period end.",
        "icon": "bi-file-earmark-spreadsheet",
        "permission": "finance",
        "requires_advanced": True,
    },
    "income_statement": {
        "label": "Income Statement",
        "description": "Revenue and expense activity for the selected period.",
        "icon": "bi-graph-up-arrow",
        "permission": "finance",
        "requires_advanced": True,
    },
    "cash_position": {
        "label": "Cash & Bank Position",
        "description": "Cash and bank account balances across the organization.",
        "icon": "bi-bank",
        "permission": "finance",
        "requires_advanced": True,
    },
    "asset_register": {
        "label": "Fixed Asset Register",
        "description": "Capital assets, costs, accumulated depreciation, and net book value.",
        "icon": "bi-box-seam",
        "permission": "finance",
        "requires_feature": "assets",
    },
    "depreciation_schedule": {
        "label": "Depreciation Schedule",
        "description": "Monthly depreciation posted by asset across the organization.",
        "icon": "bi-calendar-month",
        "permission": "finance",
        "requires_feature": "assets",
    },
    "asset_hierarchy_rollup": {
        "label": "Asset Hierarchy Roll-up",
        "description": "Active asset counts and net book value by church and district.",
        "icon": "bi-bar-chart-steps",
        "permission": "overseer",
        "requires_feature": "assets",
    },
    "welfare_register": {
        "label": "Welfare Register",
        "description": "Member contributions, assistance cases, and fund activity for the period.",
        "icon": "bi-heart-pulse",
        "permission": "finance",
        "requires_feature": "remittance",
    },
    "budget_vs_actual": {
        "label": "Budget vs Actual",
        "description": "Annual budget performance by account with favorable variance indicators.",
        "icon": "bi-pie-chart",
        "permission": "finance",
        "requires_feature": "budgets",
    },
}

PERIOD_CHOICES = [
    ("weekly", "Weekly"),
    ("monthly", "Monthly"),
    ("quarterly", "Quarterly"),
    ("semi_annual", "Semi-Annual"),
    ("annual", "Annual"),
    ("custom", "Custom Range"),
]
