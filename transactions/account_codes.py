"""
Stable GL account codes — prefer these over free-text names for lookups.

Remittance workflow (enterprise):
  1. RECEIPT (tithe/combined) → credit retain + remit payable (policy split)
  2. TRANSFER TRF_*_REMIT / settlement post → clear remit payable into
     District/Conference/Union remittance clearing accounts (not Main Bank)
  3. Bank remittance payment (record_district_remittance / cutoff) →
     debit remit payable (or clearing) and credit Bank/Cash when cash leaves
"""

from __future__ import annotations

# name → code for core + remittance clearing accounts
ACCOUNT_CODE_BY_NAME = {
    "Tithe": "TITHE",
    "Combined Offering": "COMBINED",
    "General Income": "INCOME",
    "General Expense": "EXPENSE",
    "District Payable": "DISTRICT_PAYABLE",
    "Tithe Remittance Payable": "TITHE_REMIT_PAYABLE",
    "Combined Remittance Payable": "COMBINED_REMIT_PAYABLE",
    "Combined Retention Income": "COMBINED_RETENTION",
    "Welfare Fund": "WELFARE_FUND",
    "Remittance Receivable": "REMITTANCE_RECEIVABLE",
    "Salaries & Allowances": "SALARY_EXPENSE",
    "Employer SSNIT Expense": "EMPLOYER_SSNIT_EXPENSE",
    "Salaries Payable": "SALARIES_PAYABLE",
    "PAYE Payable": "PAYE_PAYABLE",
    "SSNIT Payable": "SSNIT_PAYABLE",
    "Pension Payable": "PENSION_PAYABLE",
    "Main Bank": "BANK",
    "Cash": "CASH",
    "Property, Plant & Equipment": "FIXED_ASSET",
    "Accumulated Depreciation": "ACCUM_DEPR",
    "Depreciation Expense": "DEPR_EXPENSE",
    # Hierarchy remittance clearing (credit side of remittance transfers)
    "District Tithe Remittance": "DISTRICT_TITHE_REMIT",
    "Conference Tithe Remittance": "CONF_TITHE_REMIT",
    "Union Tithe Remittance": "UNION_TITHE_REMIT",
    "District Combined Remittance": "DISTRICT_COMBINED_REMIT",
    "Conference Combined Remittance": "CONF_COMBINED_REMIT",
    "Union Combined Remittance": "UNION_COMBINED_REMIT",
    # Extended seed accounts
    "Petty Cash": "PETTY_CASH",
    "Utilities Expense": "UTILITIES",
    "Rent Expense": "RENT",
    "Maintenance & Repairs": "MAINTENANCE",
    "Transport & Travel": "TRANSPORT",
    "Office Supplies": "SUPPLIES",
    "Missions & Outreach": "MISSIONS",
    "Welfare Assistance": "WELFARE_ASSIST",
    "Bank Charges": "BANK_CHARGES",
    "Thanksgiving Offering": "THANKSGIVING",
    "Building Fund": "BUILDING",
    "Mission Offering": "MISSION_OFFERING",
    "Special Project Income": "SPECIAL_PROJECT",
    "Accrued Expenses": "ACCRUED_EXPENSE",
}

# Settlement / transfer credit resolution: (unit_level, offering_type) → code
REMIT_CLEARING_CODES = {
    ("DISTRICT", "TITHE"): "DISTRICT_TITHE_REMIT",
    ("CONFERENCE", "TITHE"): "CONF_TITHE_REMIT",
    ("UNION", "TITHE"): "UNION_TITHE_REMIT",
    ("DISTRICT", "COMBINED"): "DISTRICT_COMBINED_REMIT",
    ("CONFERENCE", "COMBINED"): "CONF_COMBINED_REMIT",
    ("UNION", "COMBINED"): "UNION_COMBINED_REMIT",
}


def code_for_name(name: str) -> str | None:
    return ACCOUNT_CODE_BY_NAME.get(name)


def get_account_by_code(church, code: str):
    """Resolve an account by stable code; raises Account.DoesNotExist."""
    from transactions.models import Account

    return Account.objects.get(church=church, code=code)


def get_remit_clearing_account(church, offering_type: str, unit_level: str = "DISTRICT"):
    """
    Resolve hierarchy remittance clearing account for settlement/transfer credit.
    Falls back to District Payable if the coded account is not seeded yet.
    """
    from transactions.models import Account
    from transactions.services import _get_account

    code = REMIT_CLEARING_CODES.get((unit_level.upper(), offering_type.upper()))
    if code:
        account = Account.objects.filter(church=church, code=code).first()
        if account:
            return account
        # Name fallback for churches seeded before codes existed
        for name, mapped in ACCOUNT_CODE_BY_NAME.items():
            if mapped == code:
                account = Account.objects.filter(church=church, name=name).first()
                if account:
                    return account
    return _get_account(church, "DISTRICT_PAYABLE")
