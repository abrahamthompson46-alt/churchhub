from django.contrib import admin

from approvals.models import (
    ApprovalCase,
    ApprovalDelegation,
    ApprovalEscalation,
    ApprovalPolicy,
    ApprovalStep,
)


@admin.register(ApprovalPolicy)
class ApprovalPolicyAdmin(admin.ModelAdmin):
    list_display = ["church", "required_steps", "is_active", "updated_at"]


@admin.register(ApprovalCase)
class ApprovalCaseAdmin(admin.ModelAdmin):
    list_display = ["transaction", "church", "status", "current_step", "required_steps", "maker"]
    list_filter = ["status"]


@admin.register(ApprovalStep)
class ApprovalStepAdmin(admin.ModelAdmin):
    list_display = ["case", "step_number", "status", "action", "actor", "decided_at"]


@admin.register(ApprovalDelegation)
class ApprovalDelegationAdmin(admin.ModelAdmin):
    list_display = ["grantor", "grantee", "church", "valid_from", "valid_until", "max_amount", "is_revoked"]


@admin.register(ApprovalEscalation)
class ApprovalEscalationAdmin(admin.ModelAdmin):
    list_display = ["case", "requested_by", "created_at"]
