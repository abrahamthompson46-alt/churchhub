"""Built-in denomination deployment profiles for multi-tenant SaaS."""

DEFAULT_LEVEL_LABELS = {
    "general_conference": {
        "enabled": True,
        "label": "General Conference",
        "label_plural": "General Conferences",
    },
    "union": {"enabled": True, "label": "Union", "label_plural": "Unions"},
    "conference": {"enabled": True, "label": "Conference", "label_plural": "Conferences"},
    "zone": {"enabled": True, "label": "Zone", "label_plural": "Zones"},
    "district": {"enabled": True, "label": "District", "label_plural": "Districts"},
    "church": {"enabled": True, "label": "Church", "label_plural": "Churches"},
}

DEFAULT_SEED_CONFIG = {
    "offering_categories": [
        {"code": "TITHE", "name": "Tithe"},
        {"code": "COMBINED", "name": "Combined Offering"},
        {"code": "THANKSGIVING", "name": "Thanksgiving"},
        {"code": "BUILDING", "name": "Building Fund"},
        {"code": "MISSION", "name": "Mission Offering"},
        {"code": "WELFARE", "name": "Welfare Fund"},
    ],
    "enable_remittance": True,
    "enable_payroll": True,
    "payroll_jurisdiction": "ghana",
    "remittance_preset": "hierarchy_standard",
}

BUILTIN_DENOMINATIONS = [
    {
        "code": "sda",
        "name": "Seventh-day Adventist",
        "display_name": "SDA ChurchHub",
        "tagline": "Conference administration for Adventist churches",
        "hierarchy_labels": DEFAULT_LEVEL_LABELS,
        "seed_config": DEFAULT_SEED_CONFIG,
        "allow_public_registration": True,
        "is_default": True,
    },
    {
        "code": "methodist",
        "name": "Methodist Church",
        "display_name": "Methodist ChurchHub",
        "tagline": "Connexional church management",
        "hierarchy_labels": {
            **DEFAULT_LEVEL_LABELS,
            "general_conference": {
                "enabled": True,
                "label": "Connexional Body",
                "label_plural": "Connexional Bodies",
            },
            "union": {"enabled": False, "label": "Union", "label_plural": "Unions"},
            "conference": {"enabled": True, "label": "District", "label_plural": "Districts"},
            "zone": {"enabled": True, "label": "Circuit", "label_plural": "Circuits"},
            "district": {"enabled": True, "label": "Society", "label_plural": "Societies"},
            "church": {"enabled": True, "label": "Local Church", "label_plural": "Local Churches"},
        },
        "seed_config": {
            **DEFAULT_SEED_CONFIG,
            "offering_categories": [
                {"code": "TITHE", "name": "Ministerial Support"},
                {"code": "COMBINED", "name": "Weekly Offering"},
                {"code": "THANKSGIVING", "name": "Thanksgiving"},
                {"code": "BUILDING", "name": "Building Fund"},
                {"code": "MISSION", "name": "Mission"},
                {"code": "WELFARE", "name": "Welfare"},
            ],
            "enable_remittance": False,
        },
        "allow_public_registration": True,
    },
    {
        "code": "cop",
        "name": "Church of Pentecost",
        "display_name": "CoP ChurchHub",
        "tagline": "National assembly management for Church of Pentecost",
        "hierarchy_labels": {
            **DEFAULT_LEVEL_LABELS,
            "general_conference": {
                "enabled": False,
                "label": "General Council",
                "label_plural": "General Councils",
            },
            "union": {"enabled": False, "label": "Union", "label_plural": "Unions"},
            "conference": {"enabled": True, "label": "Area", "label_plural": "Areas"},
            "zone": {"enabled": True, "label": "District", "label_plural": "Districts"},
            "district": {"enabled": True, "label": "Section", "label_plural": "Sections"},
            "church": {"enabled": True, "label": "Assembly", "label_plural": "Assemblies"},
        },
        "seed_config": {
            **DEFAULT_SEED_CONFIG,
            "offering_categories": [
                {"code": "TITHE", "name": "Tithes"},
                {"code": "COMBINED", "name": "Offerings"},
                {"code": "THANKSGIVING", "name": "Thanksgiving"},
                {"code": "BUILDING", "name": "Building Project"},
                {"code": "MISSION", "name": "Missions"},
                {"code": "WELFARE", "name": "Welfare"},
            ],
            "remittance_preset": "area_district",
        },
        "allow_public_registration": True,
    },
    {
        "code": "generic",
        "name": "Independent / Other",
        "display_name": "ChurchHub",
        "tagline": "Flexible hierarchy for any Christian denomination",
        "hierarchy_labels": DEFAULT_LEVEL_LABELS,
        "seed_config": DEFAULT_SEED_CONFIG,
        "allow_public_registration": True,
    },
]
