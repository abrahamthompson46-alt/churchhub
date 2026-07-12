"""Default payroll templates — seeding only, never used directly in calculation."""

UNIT_TYPES = [
    ("CHURCH", "Church"),
    ("DISTRICT", "District"),
    ("CONFERENCE", "Conference"),
    ("UNION", "Union"),
    ("GENERAL_CONFERENCE", "General Conference"),
]

DEFAULT_EARNING_COMPONENTS = [
    {"code": "BASIC", "name": "Basic Salary", "is_taxable": True, "sort_order": 10},
    {"code": "HOUSING", "name": "Housing Allowance", "is_taxable": True, "sort_order": 20},
    {"code": "TRANSPORT", "name": "Transport Allowance", "is_taxable": True, "sort_order": 30},
    {"code": "RESPONSIBILITY", "name": "Responsibility Allowance", "is_taxable": True, "sort_order": 40},
    {"code": "STIPEND", "name": "Pastoral Stipend", "is_taxable": True, "sort_order": 50},
    {"code": "BONUS", "name": "Bonus", "is_taxable": True, "sort_order": 60},
    {"code": "ARREARS", "name": "Arrears / Back Pay", "is_taxable": True, "sort_order": 70},
    {"code": "THIRTEENTH", "name": "13th Month / Gratuity", "is_taxable": True, "sort_order": 80},
    {"code": "OTHER", "name": "Other Allowance", "is_taxable": True, "sort_order": 90},
]

DEFAULT_DEDUCTION_TYPES = [
    {"code": "PAYE", "name": "PAYE", "is_statutory": True, "calculation_method": "COMPUTED", "sort_order": 10},
    {"code": "SSNIT_EE", "name": "SSNIT (Employee)", "is_statutory": True, "calculation_method": "PERCENT_BASIC", "default_rate": "5.50", "sort_order": 20},
    {"code": "PENSION_T2", "name": "Tier 2 Pension", "is_statutory": True, "calculation_method": "PERCENT_BASIC", "default_rate": "5.00", "sort_order": 30},
    {"code": "PENSION_T3", "name": "Tier 3 Pension (Voluntary)", "is_statutory": False, "calculation_method": "FIXED", "sort_order": 35},
    {"code": "LOAN", "name": "Loan Recovery", "is_statutory": False, "calculation_method": "FIXED", "sort_order": 40},
    {"code": "WELFARE", "name": "Welfare Levy", "is_statutory": False, "calculation_method": "FIXED", "sort_order": 50},
    {"code": "OTHER", "name": "Other Deduction", "is_statutory": False, "calculation_method": "FIXED", "sort_order": 90},
]

# Ghana monthly PAYE bands (cedis) — update via admin when GRA revises rates.
DEFAULT_PAYE_BANDS = [
    {"lower": "0", "upper": "490", "rate": "0"},
    {"lower": "490", "upper": "600", "rate": "5"},
    {"lower": "600", "upper": "730", "rate": "10"},
    {"lower": "730", "upper": "3896.67", "rate": "17.5"},
    {"lower": "3896.67", "upper": "19896.67", "rate": "25"},
    {"lower": "19896.67", "upper": None, "rate": "30"},
]

DEFAULT_STATUTORY_RULES = [
    {
        "code": "SSNIT_EE",
        "name": "SSNIT Employee Contribution",
        "employee_rate": "5.50",
        "employer_rate": "0",
        "applies_to": "BASIC",
    },
    {
        "code": "SSNIT_ER",
        "name": "SSNIT Employer Contribution",
        "employee_rate": "0",
        "employer_rate": "13.00",
        "applies_to": "BASIC",
    },
    {
        "code": "PENSION_T2",
        "name": "Tier 2 Pension (Employer)",
        "employee_rate": "0",
        "employer_rate": "5.00",
        "applies_to": "BASIC",
    },
]
