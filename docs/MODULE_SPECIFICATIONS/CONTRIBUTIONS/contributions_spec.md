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
- Staff do not enter a campaign code. `generate_campaign_code` assigns `CMP-YYYY-NN` (or `FUN-YYYY-NN` for district funerals), unique per church. Existing codes are not changed on edit.
- Gifts post as balanced receipts using the category code in `special_offerings`.
- Recording allowed only when campaign status is **OPEN**.
- Manual close blocks new entries; archived campaigns are read-only.
- Portal shows only **OPEN** + `portal_visible=True` campaigns.
- Member totals include approved, non-voided linked receipts.
- Church-wide progress on portal is optional per campaign (`show_church_progress`).
- Optional **default member target** plus per-member overrides (`MemberCampaignTarget`).
- **Bulk entry** and **Excel import** post receipts in atomic batches (all-or-nothing on import).
- **Deadline reminders** at 7/3/1/0 days and overdue via in-app notifications; email when SMTP configured (`send_email_reminders`).
- **District funeral collections** use `CampaignKind.DISTRICT_FUNERAL` and offering category `DISTRICT_FUNERAL` (GL **District Funeral Holding**, `INCOME`). They are **not** welfare cases or `WELFARE` receipts.
- Funeral gifts post via `record_receipt` `special_offerings={"DISTRICT_FUNERAL": amount}` (no remittance split).
- Church treasurers **manually remit** outstanding holdings: TRANSFER DR holding CR cash/bank (`record_designated_holding_remittance`), journal **PENDING** for a checker. Remit **defaults to Cash**. `CampaignRemittance` stores the send. Settlement Desk does **not** auto-push this; district does **not** receive a GL entry.
- Campaign list and **Campaign Register** (`campaign_register`) are scoped to manageable churches so district/conference officers can compare raised vs remitted by church. Report Center **defaults to district funeral collections**; choose All types (or Church campaigns) to widen the list.
- Idempotency action for gifts and funeral remits: `CONTRIBUTION`.

## District funeral workflow (Current)

1. New campaign → type **District funeral collection** (list CTA `?kind=DISTRICT_FUNERAL`).
2. Open campaign; record member gifts like any campaign.
3. On the campaign page, **Remit to district** posts the holding transfer (amount ≤ outstanding; blocked while a remit journal is pending) and opens a **remit slip** (amount, Cash/Bank, campaign, working day, who posted). Reprint the slip after checker approval.
4. Approve the journal under the usual maker-checker path.
5. Keep the campaign as the church’s record of who gave and what was sent. **Print collection pack** is a one-page sheet: church, who gave, totals, remitted vs still to send, journal refs.

**Recommended later:** district-side funeral case with automatic payable. Not implemented.

**Not this path:** Welfare Register, Union/GC settlement GL.

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
| `/contributions/<uuid>/pack/` | `contributions:campaign_pack` |
| `/contributions/<uuid>/remit/` | `contributions:campaign_remit` (POST) |
| `/contributions/<uuid>/remit/<uuid>/` | `contributions:campaign_remit_slip` |
| `/portal/contributions/` | `portal:contributions` |
| `/portal/contributions/<uuid>/` | `portal:contribution_campaign` |
