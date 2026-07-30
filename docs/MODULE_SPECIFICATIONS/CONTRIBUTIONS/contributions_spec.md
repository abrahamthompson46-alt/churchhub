# Contribution Campaigns module specification

**App:** `contributions`  
**Mount:** `/contributions/` (staff), `/portal/contributions/` (member portal)  
**Role:** Time-bound giving drives with per-member tracking and portal visibility  
**Companions:** `../TRANSACTIONS/transactions_spec.md`, `../GIVING/giving_spec.md`

| Label | Meaning |
|-------|---------|
| **Current** | Implemented in Phase 1 |
| **Planned** | Bulk grid, reminders, online pay |

---

## Purpose

Churches open **contribution campaigns** (harvest, rent, building, etc.) with a **purpose**, **deadline**, and linked **offering category**. Staff record member gifts through normal receipt posting; members view open campaigns and their own history on the portal.

## Architecture

- **Books of record:** `transactions.Transaction` / `TransactionLine` (via `record_receipt`)
- **Campaign metadata:** `contributions.ContributionCampaign`
- **Member participation:** `contributions.MemberContribution` → FK to receipt
- **Portal:** read-only via `portal` views + `contributions.services`

## Feature flag

`contribution_campaigns` — gated globally, per denomination, and per subscription plan.

## Permissions

| Codename | Purpose |
|----------|---------|
| `manage_contribution_campaigns` | CRUD, open/close/archive |
| `record_contributions` | Post member gifts while campaign is open |
| `view_contribution_reports` | Dashboard list/detail/export |
| `view_own_contributions` | Portal self-service |

## Business rules (Current)

- Campaign must link to a church-scoped active `OfferingCategory`.
- Gifts post as balanced receipts using the category code in `special_offerings`.
- Recording allowed only when campaign status is **OPEN**.
- Manual close blocks new entries; archived campaigns are read-only.
- Portal shows only **OPEN** + `portal_visible=True` campaigns.
- Member totals include approved, non-voided linked receipts.
- Church-wide progress on portal is optional per campaign (`show_church_progress`).
- Optional **default member target** plus per-member overrides (`MemberCampaignTarget`).
- **Bulk entry** and **Excel import** post receipts in atomic batches (all-or-nothing on import).
- **Deadline reminders** at 7/3/1/0 days and overdue via in-app notifications; email when SMTP configured (`send_email_reminders`).

## Phase 2 operations

| Feature | Path / command |
|---------|----------------|
| Bulk grid | `/contributions/<uuid>/bulk/` |
| Excel import | `/contributions/<uuid>/import/` |
| Member targets | `/contributions/<uuid>/targets/` |
| Scheduled reminders | `python manage.py send_contribution_reminders` |

Add `--no-email` to skip email and send in-app notifications only.

## URLs

| Path | Name |
|------|------|
| `/contributions/` | `contributions:campaign_list` |
| `/contributions/add/` | `contributions:campaign_create` |
| `/contributions/<uuid>/` | `contributions:campaign_detail` |
| `/portal/contributions/` | `portal:contributions` |
| `/portal/contributions/<uuid>/` | `portal:contribution_campaign` |
