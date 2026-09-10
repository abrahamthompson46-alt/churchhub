"""Persistence for risk policy and alerts."""

from __future__ import annotations

from django.db import IntegrityError, transaction

from intelligence.models import RiskAlert, RiskPolicy


def get_or_create_policy(*, church, defaults=None):
    return RiskPolicy.objects.get_or_create(church=church, defaults=defaults or {})


def save_policy(policy, *, update_fields):
    policy.save(update_fields=update_fields)
    return policy


def create_alert(**kwargs):
    try:
        with transaction.atomic():
            return RiskAlert.objects.create(**kwargs), True
    except IntegrityError:
        existing = RiskAlert.objects.filter(
            church=kwargs["church"],
            rule_code=kwargs["rule_code"],
            fingerprint=kwargs["fingerprint"],
        ).first()
        return existing, False


def save_alert(alert, *, update_fields):
    alert.save(update_fields=update_fields)
    return alert
