"""Default policy templates — used only by seeding, never by posting logic."""

CHURCH_DEFAULT_POLICIES = [
    {
        "offering_type": "TITHE",
        "application_scope": "GROSS_COLLECTION",
        "retain_percent": "0.00",
        "remit_percent": "100.00",
    },
    {
        "offering_type": "COMBINED",
        "application_scope": "GROSS_COLLECTION",
        "retain_percent": "50.00",
        "remit_percent": "50.00",
    },
    {
        "offering_type": "WELFARE",
        "application_scope": "GROSS_COLLECTION",
        "retain_percent": "100.00",
        "remit_percent": "0.00",
    },
]

SETTLEMENT_DEFAULT_POLICIES = [
    {
        "offering_type": "TITHE",
        "application_scope": "SETTLEMENT_FROM_BELOW",
        "retain_percent": "10.00",
        "remit_percent": "90.00",
    },
    {
        "offering_type": "COMBINED",
        "application_scope": "SETTLEMENT_FROM_BELOW",
        "retain_percent": "10.00",
        "remit_percent": "90.00",
    },
]
