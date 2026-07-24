"""Member dropdown catalogs — platform-editable without code changes."""

from __future__ import annotations

from .models import (
    Department,
    Gender,
    LookupCategory,
    MaritalStatus,
    MemberLookupOption,
    MembershipStatus,
    Occupation,
    RecordStatus,
    RecordType,
    SpiritualGift,
)

_SEED = (
    (LookupCategory.GENDER, Gender.choices, True),
    (LookupCategory.MARITAL_STATUS, MaritalStatus.choices, True),
    (LookupCategory.MEMBERSHIP_STATUS, MembershipStatus.choices, True),
    (LookupCategory.RECORD_TYPE, RecordType.choices, True),
    (LookupCategory.RECORD_STATUS, RecordStatus.choices, True),
)

# Typical church ministry defaults — church-scoped, additive only when empty.
DEFAULT_OCCUPATIONS = (
    "Teacher",
    "Nurse",
    "Doctor",
    "Farmer",
    "Trader",
    "Civil servant",
    "Student",
    "Artisan",
    "Electrician",
    "Builder",
    "Engineer",
    "Accountant",
    "Lawyer",
    "Business owner",
    "Musician",
    "Clergy",
    "Retired",
    "Homemaker",
    "Unemployed",
    "Other",
)

DEFAULT_DEPARTMENTS = (
    "Sabbath School",
    "Youth",
    "Pathfinders",
    "Adventurers",
    "Children's Ministries",
    "Women's Ministries",
    "Men's Ministries",
    "Personal Ministries",
    "Music",
    "Deacons & Deaconesses",
    "Stewardship",
    "Health Ministries",
    "Family Ministries",
    "Communication",
    "Education",
    "Publishing",
    "Community Services",
    "Prayer Ministry",
    "Religious Liberty",
    "Possibility Ministries",
)

DEFAULT_SPIRITUAL_GIFTS = (
    "Teaching",
    "Leadership",
    "Mercy",
    "Administration",
    "Hospitality",
    "Evangelism",
    "Music",
    "Service",
    "Counseling",
    "Giving",
    "Helps",
    "Discernment",
)


def ensure_default_member_lookups() -> int:
    """Seed system lookup options from legacy TextChoices. Returns created count."""
    created = 0
    for category, choices, is_system in _SEED:
        for order, (code, label) in enumerate(choices):
            _, was_created = MemberLookupOption.objects.get_or_create(
                category=category,
                code=code,
                defaults={
                    "label": label,
                    "is_active": True,
                    "is_system": is_system,
                    "sort_order": order * 10,
                },
            )
            if was_created:
                created += 1
    return created


def ensure_default_occupations(church) -> int:
    """Seed common occupations for a church when the list is empty."""
    if church is None:
        return 0
    if Occupation.objects.filter(church=church).exists():
        return 0
    created = 0
    for name in DEFAULT_OCCUPATIONS:
        _, was_created = Occupation.objects.get_or_create(church=church, name=name)
        if was_created:
            created += 1
    return created


def ensure_default_departments(church) -> int:
    """Seed common departments for a church when the list is empty."""
    if church is None:
        return 0
    if Department.objects.filter(church=church).exists():
        return 0
    created = 0
    for name in DEFAULT_DEPARTMENTS:
        _, was_created = Department.objects.get_or_create(church=church, name=name)
        if was_created:
            created += 1
    return created


def ensure_default_spiritual_gifts(church) -> int:
    """Seed common spiritual gifts for a church when the catalog is empty."""
    if church is None:
        return 0
    if SpiritualGift.objects.filter(church=church).exists():
        return 0
    created = 0
    for name in DEFAULT_SPIRITUAL_GIFTS:
        _, was_created = SpiritualGift.objects.get_or_create(church=church, name=name)
        if was_created:
            created += 1
    return created


def ensure_member_form_catalogs(church=None) -> dict[str, int]:
    """Ensure Add/Edit Member dropdowns and ministry catalogs have usable options."""
    return {
        "lookups": ensure_default_member_lookups(),
        "occupations": ensure_default_occupations(church),
        "departments": ensure_default_departments(church),
        "spiritual_gifts": ensure_default_spiritual_gifts(church),
    }


def lookup_choice_tuples(category: str, *, include_blank: str | None = None, blank_label: str = "—"):
    """
    Return [(code, label), ...] for forms.

    Falls back to TextChoices when the catalog is empty (pre-migrate / first boot).
    """
    qs = MemberLookupOption.objects.filter(
        category=category, is_active=True
    ).order_by("sort_order", "label")
    choices = [(opt.code, opt.label) for opt in qs]
    if not choices:
        fallback = {
            LookupCategory.GENDER: Gender.choices,
            LookupCategory.MARITAL_STATUS: MaritalStatus.choices,
            LookupCategory.MEMBERSHIP_STATUS: MembershipStatus.choices,
            LookupCategory.RECORD_TYPE: RecordType.choices,
            LookupCategory.RECORD_STATUS: RecordStatus.choices,
        }.get(category, ())
        choices = list(fallback)
    if include_blank is not None:
        return [(include_blank, blank_label)] + choices
    return choices


def apply_lookup_choices(field, category: str, *, blank: bool = False, blank_label: str = "—"):
    """Bind a form field + Select widget to the live catalog.

    CharField + Select (ModelForm default for plain CharFields) does not sync
    widget.choices when only field.choices is assigned — options render empty.
    """
    if blank:
        choices = lookup_choice_tuples(category, include_blank="", blank_label=blank_label)
    else:
        choices = lookup_choice_tuples(category)
    field.choices = choices
    field.widget.choices = choices


def apply_static_choices(field, choices, *, blank: bool = False, blank_label: str = "—"):
    """Bind TextChoices (or similar) to a CharField Select widget."""
    pairs = list(choices)
    if blank:
        pairs = [("", blank_label)] + pairs
    field.choices = pairs
    field.widget.choices = pairs
