# Phase 3 Security Design — Financial Integrity, Concurrency & Maker-Checker

**Status:** Implemented (code + migrations + tests; not committed until requested)  
**Date:** 15 August 2026  
**Phase 1 checkpoint:** `44f557534dcc0ca2c215c3b7b9057fc05c1ace40`  
**Phase 2 checkpoint:** `484abe850052ede00d4004f3ff445396c79ec88f` (`feature/sec-phase1-media-mfa-finance`)  
**Contract:** `docs/SECURITY_AUTHORIZATION_INVARIANTS.md`, `docs/SECURITY_REMEDIATION_DESIGN.md`, `docs/SECURITY_FINDINGS_REGISTER.md`  

Live Django code is the source of truth for Current behavior. This document was the implementation contract for Phase 3.

**PHASE 3 DESIGN STATUS:** **IMPLEMENTED (awaiting commit)**

---

## 1. Executive summary

Phase 1 hardened media ACL, MFA throttle, and remittance/recon **write wrappers**. Phase 2 closed announcement denomination isolation (CH-SEC-002 / CH-SEC-008). Phase 3 addresses **books-of-record integrity**: tenant hierarchy writes, journal posting/approval/void concurrency, shared financial idempotency, ledger write authorization, asset register vs GL consistency, contribution duplicate posts, welfare self-approval, and remittance/settlement races.

| Finding | Sev | Theme | Primary invariant(s) |
|---------|-----|-------|----------------------|
| CH-SEC-004 | HIGH | Tenant integrity | INV-TEN-05 |
| CH-SEC-005 | HIGH | Asset journals | INV-DATE-01, INV-SOD-01, INV-FIN-05 |
| CH-SEC-006 | HIGH | Contribution idempotency | INV-IDEM-01 |
| CH-SEC-011 | MEDIUM | Welfare SoD | INV-SOD-02 |
| CH-SEC-012 | MEDIUM | Void race | INV-SOD-04, INV-FIN-05 |
| CH-SEC-013 | MEDIUM | Incomplete idempotency keys | INV-IDEM-03 |
| INV-FIN-02 | — | Ledger read≠write | INV-FIN-01, INV-FIN-02 |
| CH-SEC-L3 | MEDIUM LIKELY | Remittance/settlement races | INV-IDEM-01/02, INV-SOD-01 |
| Maker-checker / SoD | — | Cross-cutting | INV-SOD-01…04 |

**Design principles (non-negotiable):**

1. **One shared idempotency primitive** — harden `transactions.idempotency.claim_financial_idempotency` once; reuse for receipts, expenses, remittance, ledger, payroll, welfare, and contributions. Do not invent parallel key tables.
2. **Reuse existing permissions** — do not invent `manage_transactions` / `manage_remittance`. Use `manage_finances`, `approve_transactions`, `void_transactions`, `manage_ledger_entries`, `view_ledger`, `manage_reconciliation`, `finalize_reconciliation`, `approve_welfare`, etc.
3. **Services enforce SoD and locks** — views authenticate/authorize; repositories persist; business rules and `select_for_update` live in services.
4. **Receipt auto-approve remains the only documented SoD exception** (capped, audited). It MUST NOT expand to expenses, remittance, ledger, assets, payroll, or welfare disbursement.
5. **Register state must not leap ahead of approved GL** for asset depreciation/disposal.

---

## 2. Current architecture map

### 2.1 Books of record

| Layer | App / module | Role |
|-------|--------------|------|
| GL | `transactions` (`Account`, `Transaction`, `TransactionLine`) | Sole books of record |
| UI templates | `ledger` | Category drafts → `post_ledger_entry` → same GL |
| Assets | `assets` | Register + CAPITAL journals into `transactions` |
| Contributions | `contributions` | Campaign gifts → `record_receipt` |
| Remittance / welfare | `remittance` | Settlements, district remittance, welfare cases |
| Reconciliation | `transactions` recon services | Bank worksheets (not GL posts) |
| Idempotency | `transactions.FinancialIdempotencyKey` | Dedup financial POSTs |

### 2.2 Shared primitives (Current)

| Primitive | Location | Current gap |
|-----------|----------|-------------|
| `claim_financial_idempotency` | `transactions/idempotency.py` | Incomplete keys returned without `select_for_update` (CH-SEC-013) |
| `approve_transaction` | `transactions/services.py` | SoD yes; no row lock (approve race residual) |
| `approve_module_journal` | same | Requires distinct checker; returns PENDING if none |
| `void_transaction` | same | Atomic but no `select_for_update` (CH-SEC-012) |
| `assert_period_open` / `assert_working_day_allows_posting` | `transactions` | Used by receipts/expenses/remittance/ledger/welfare disburse; **skipped** by asset dep/disposal |
| `assert_segregation_of_duties` | assets | Used on asset register approve only |
| `Church.clean()` | `organization/models.py` | Blocks cross-denom district moves **only if** `full_clean()` runs |

### 2.3 Approval lifecycle (Current product)

```text
CREATE (PENDING, unlocked)
    → optional AUTO-APPROVE (receipts only, policy-capped)
    → APPROVE (locked, FinancialAuditLog APPROVE)
    → VOID (reversal journal + original.is_voided)
```

Expenses, remittance, most ledger, asset dep/disposal, welfare case approval, settlements: no same-actor auto-approve (except broken paths noted below).

---

## 3. Finding-by-finding analysis

### 3.1 CH-SEC-004 — Tenant integrity (`Church.clean()` bypass)

**Current implementation**

- `Church.clean()` (`organization/models.py` ~159–171): on district change, reject if old/new conference denomination IDs differ.
- `organization.services.update_church` / `transfer_church`: call `full_clean()` (aligned).
- `sitecontrol.repositories.save_model` / `save_church`: `Model.save()` only — **no** `full_clean()`.
- `organization.repositories.save_church` / `get_or_create`: same gap.
- `TenantChurchForm` + `tenant_edit`: form `is_valid()` runs model clean for that HTTP path, but any future/alternate caller of `save_church` skips validation.
- Admin ModelForms typically `full_clean()`; management bootstrap (`setup_churchhub`) uses raw `get_or_create`.

**Current vulnerability**

Platform or service code can persist a church into another denomination’s district without invoking `Church.clean()`, violating the SaaS wall (INV-TEN-05). Form-only protection is insufficient (INV-OBJ / repository boundary).

**Authoritative invariant**

- INV-TEN-05 — Cross-denomination church transfer MUST DENY.
- Platform `CAP_MANAGE_TENANTS` does not authorize silent tenant relocation across denominations.

**Proposed remediation**

1. **Repository contract:** `sitecontrol.repositories.save_church` and `organization.repositories.save_church` MUST call `instance.full_clean()` before `save()` (or a named `save_church_validated` used by all callers).
2. **Form defense-in-depth:** constrain `TenantChurchForm.district` queryset to districts under denominations the operator may manage (`filter_churches_for_operator` / managed denominations) — never unrestricted `District.objects.all()`.
3. **View re-check:** after form clean, `tenant_edit` MUST assert destination district denomination equals source (or is explicitly allowed same-denom transfer).
4. **DB constraint (Recommended, additive):** PostgreSQL cannot easily express “church.district.zone.conference.denomination unchanged” across joins as a simple CHECK. Prefer **application `full_clean` on every write path** + optional trigger in a later phase. Do **not** drop historical rows.
5. **`create_church` / get_or_create:** run `full_clean()` on create and on any update of existing rows.

**Files / functions**

- `sitecontrol/repositories.py` — `save_model`, `save_church`
- `organization/repositories.py` — `save_church`, create helpers
- `sitecontrol/forms.py` — `TenantChurchForm`
- `sitecontrol/views.py` — `tenant_edit`
- Tests: platform tenant edit cross-denom DENY; repository-level save without form DENY

**HTTP / service behavior**

- Cross-denom district POST → 400/403 with unchanged church.
- Same-denom transfer → ALLOW if capability + scope permit.

**Migration risk:** None for schema if only `full_clean` + queryset. Optional DB trigger = higher risk, defer.

**Backwards compatibility:** Legitimate same-denom moves and org `transfer_church` preserved.

---

### 3.2 CH-SEC-005 — Asset depreciation / disposal journals

**Current implementation**

- Acquisition (`post_acquisition_to_ledger`): `assert_period_open` + `approve_module_journal`; **no** working-day assert today (gap vs INV-DATE-01).
- Depreciation (`post_depreciation_entry`): period checks; creates PENDING CAPITAL journal; updates accumulated depreciation / register **without** `approve_module_journal` or working-day assert.
- Disposal (`dispose_asset` / `post_disposal_to_ledger`): marks asset DISPOSED then posts PENDING journal without module approval / working day.
- Celery `run_church_depreciation_task` (`church_system/tasks.py`): may run without a human checker identity; SoD cannot invent a second user.

**Current vulnerability**

Asset register can show depreciated/disposed while GL remains PENDING/unlocked — books and register diverge (INV-SOD-01, INV-DATE-01, INV-FIN-05).

**Authoritative invariant**

- INV-DATE-01 — Asset depreciation/disposal CAPITAL journals MUST `assert_period_open` **and** `assert_working_day_allows_posting`.
- INV-SOD-01 — Must not treat register as posted while journal is PENDING; use `approve_module_journal` when a distinct checker exists; otherwise leave register unchanged / staged.
- INV-SOD-03 — Asset approve SoD helpers remain.

**Proposed remediation**

1. **Order of operations:** create balanced journal → require approved/locked journal → **then** update register (depreciation entry amounts, DISPOSED status, book value).
2. Call `assert_working_day_allows_posting` and `assert_period_open` on the posting date for acquisition, depreciation, and disposal (align acquisition with contract).
3. Call `approve_module_journal(txn, *candidates)` after create.
4. **If no distinct checker (Celery / single actor):**
   - **Do not** invent a fake checker.
   - Leave journal PENDING and **do not** mutate the asset register; surface “pending approval” to UI/ops.
   - Optional later product: scheduled “approve pending asset journals” queue for a human with `approve_transactions` (out of Phase 3 minimum if product chooses leave-pending).
5. Unique `(asset, year, month)` already exists for depreciation entries — keep; add `select_for_update` on asset (or entry) inside `atomic` before create to avoid dual journals racing.
6. Celery: pass initiating `user_id` when dispatching from UI; scheduled command runs as system path that only creates PENDING journals without register mutation until a human approves (preferred fail-closed).

**Files**

- `assets/services.py` — `post_depreciation_entry`, `post_disposal_to_ledger`, `dispose_asset`, `post_acquisition_to_ledger`
- `church_system/tasks.py` — `run_church_depreciation_task`
- `assets/management/commands/run_asset_depreciation.py`
- Views that mark dispose / run depreciation

**HTTP / service**

- Closed working day / locked period → DENY (no register change).
- Same actor only → journal may remain PENDING; register unchanged; flash/audit explains.
- Distinct checker available → journal APPROVED; register updates; audit.

**Migration / data:** No destructive migration. Existing PENDING asset journals with already-updated registers are **historical inconsistency** — document inventory SQL for ops; do not auto-rewrite GL in Phase 3 without explicit approval (out of auto-fix scope; see §14).

**Backwards compatibility:** Month-end jobs may stop updating registers until approval exists — intentional hardening.

---

### 3.3 CH-SEC-006 — Contribution idempotency

**Current implementation**

- `contributions.services.record_member_contribution` → `record_receipt` inside `atomic`.
- No `claim_financial_idempotency`; double-click / retry creates multiple approved receipts (auto-approve may apply).

**Authoritative invariant**

- INV-IDEM-01 — Member contribution MUST claim with action `CONTRIBUTION` (add to `FinancialIdempotencyKey.ACTION_CHOICES`).

**Proposed remediation**

1. Extend `ACTION_CHOICES` with `CONTRIBUTION` (additive migration).
2. Views: hidden idempotency key per form submit (UUID); bulk/import: stable per-line key (e.g. hash of import batch id + row number + member + amount + date).
3. Service: inside same `atomic` as receipt create — `claim_financial_idempotency(church, user, "CONTRIBUTION", key)` then `record_receipt` then `complete_financial_idempotency`.
4. On `IdempotencyReplay`: return existing contribution/transaction; no second receipt.
5. Depends on CH-SEC-013 hardening (incomplete-key lock) — implement primitive first.

**Files:** `contributions/services.py`, `contributions/views.py`, templates, `transactions/models.py` ACTION_CHOICES, `transactions/idempotency.py`

**Do not** rely on unique `(campaign, member, date, amount)` — legitimate duplicate gifts exist.

---

### 3.4 CH-SEC-011 — Welfare self-approval

**Current implementation**

- `remittance.welfare_services.approve_welfare_case`: sets approver; **no** `created_by_id == user.id` check.
- View: `can_approve_welfare` + church scope.
- Disbursement path already locks case, uses idempotency, working day/period, and `approve_module_journal` with distinct checker.

**Authoritative invariant**

- INV-SOD-02 — `approve_welfare_case`: creator MUST DENY.

**Proposed remediation**

1. In service (not only view): if `case.created_by_id == user.id` → raise `PermissionError` / domain error.
2. No emergency override in Phase 3 unless product documents break-glass (recommend: **none**; another leadership user must approve).
3. Audit APPROVE with case id, amounts, actor.
4. Optional: also deny if `reviewed_by_id == user.id` when that field means prior review step (only if product semantics require — default is creator-only rule per invariant).

**Files:** `remittance/welfare_services.py`, `remittance/views.py`, tests

**HTTP:** Self-approve POST → 403 (or redirect with flash); case remains pending.

**Cross-tenant:** unchanged — keep church-scoped lookup.

---

### 3.5 CH-SEC-012 — Concurrent void double-reversal

**Current implementation**

- `void_transaction` is `@atomic`, checks `is_voided` on the in-memory instance, creates reversal, marks original voided.
- No `select_for_update()` reload → two workers can both create reversals.

**Authoritative invariant**

- INV-SOD-04 — Concurrent double-void MUST be impossible (`select_for_update` / unique `reversal_of`).
- INV-FIN-05 — Posted journals immutable; corrections via reversal only.
- INV-DATE-05 — Period rules on void (already partially present).

**Proposed remediation**

1. Inside `atomic`:
   ```text
   txn = Transaction.objects.select_for_update().get(pk=transaction.pk)
   if txn.is_voided or txn.reversal_of_id: raise
   ... create reversal ...
   mark voided
   ```
2. **DB constraint (Recommended):** unique partial unique on `Transaction.reversal_of` where not null — at most one reversal per original (`UniqueConstraint` on `reversal_of`).
3. Permission remains `void_transactions`; creator MAY void if permitted (contract).
4. Audit VOID with original + reversal references.

**Files:** `transactions/services.py` `void_transaction`, `transactions/models.py` constraints, views unchanged aside from tests

**HTTP:** Second concurrent void → 400/conflict; exactly one reversal.

---

### 3.6 CH-SEC-013 — Incomplete idempotency key reuse

**Current implementation**

```text
claim_financial_idempotency:
  find existing without select_for_update
  if complete → IdempotencyReplay
  if incomplete → return same row to caller  # UNSAFE
  else create
```

Two concurrent first requests can both “own” the incomplete row and both post journals.

**Authoritative invariant**

- INV-IDEM-03 — In-flight key MUST NOT be returned for a second caller to continue; wait on lock or in-progress error.
- INV-IDEM-01 — Claim inside `atomic` with `select_for_update` on existing incomplete row; complete only after journal exists.

**Proposed remediation (shared primitive)**

1. On existing row:
   - `select_for_update()` the key row.
   - If `transaction_id` set → `IdempotencyReplay`.
   - If incomplete → raise **`IdempotencyInProgress`** (new) or block until timeout policy; **do not** return for parallel financial work.
2. Preferred simple contract for ChurchHub:
   - Incomplete + lock held by first transaction: second request waits (row lock) until first commits.
   - After wait: if completed → Replay with existing txn; if still incomplete (crash) → allow **same user** to retry reclaim after optional `updated_at` TTL (e.g. 15 minutes) — document TTL; default Phase 3: after unlock, if still incomplete, **same claimer may continue** only when `select_for_update` serializes; never two concurrent workers.
3. `complete_financial_idempotency`: set FK under same outer atomic as journal create.
4. Do not add payload hashing in Phase 3 minimum (optional Recommended later).

**Files:** `transactions/idempotency.py`, callers (receipts, expenses, remittance, ledger, payroll, welfare, contributions)

**Tests:** concurrent claims → one journal; completed key → replay; incomplete during flight → serialized / no duplicate.

---

### 3.7 INV-FIN-02 — Ledger authorization (`view_ledger` on writes)

**Current implementation**

- `ledger_finance_required` = any of `view_ledger` | `manage_ledger_entries` | `manage_finances`.
- `entry_create` additionally checks `can_manage_ledger_entries()`.
- `entry_confirm` POST uses **only** `ledger_finance_required` → `view_ledger` alone can POST session draft → `post_ledger_entry`.

**Authoritative invariant**

- INV-FIN-01 / INV-FIN-02 — Read permissions MUST NOT authorize writes. Split read vs write wrappers. Recheck write permission at mutation time.

**Proposed remediation**

1. Keep `ledger_finance_required` for **read** views only (or rename usage).
2. Add `ledger_write_required` = `manage_ledger_entries` **or** `manage_finances` (match product: registry already implies ledger manage via `manage_finances`).
3. Apply write decorator to `entry_create`, `entry_confirm`, and any other POST that mutates GL.
4. Inside `post_ledger_entry` service: re-assert `user_has_permission(user, "manage_ledger_entries") or manage_finances` (defense in depth).
5. BOARD_MEMBER with `view_ledger` only → DENY confirm POST (403).

**Files:** `ledger/views.py`, optionally `ledger/services.py` `post_ledger_entry`, tests

**No new permission codes.**

---

### 3.8 Maker-checker / SoD (cross-cutting)

See §4 matrix. Phase 3 must close gaps where Current allows same actor to both make and check **outside** the documented receipt auto-approve exception, or where register advances without an approved journal.

**Preserve:** capped receipt auto-approve + audit `sod_exception` / `auto_approved`.  
**Preserve:** `approve_transaction` creator≠approver except `is_superadmin` break-glass (document; do not expand).  
**Add:** welfare creator≠approver.  
**Add:** asset dep/disposal require approved journal before register mutation.  
**Harden:** void/approve concurrency locks (approve optional residual — Recommended `select_for_update` on approve for consistency).

---

### 3.9 CH-SEC-L3 — Settlement / district remittance races

**Current implementation**

- `create_settlement_draft`: exists-check without lock/unique → duplicate drafts.
- `post_settlement_batch`: atomic without locking batch → duplicate settlement journals.
- `record_district_remittance`: cutoff/audit existence checks without `select_for_update`; remittance view claims idempotency but incomplete-key bug (013) undermines it; month uniqueness via audit query is racy.

**Authoritative invariant**

- INV-IDEM-01 — Remittance payment claims `REMITTANCE`.
- INV-IDEM-02 — Settlement post MUST be single-post (row lock or unique constraint).
- INV-SOD-01 — Settlement posting already uses `approve_module_journal` when checker exists.

**Proposed remediation**

1. `post_settlement_batch`: `SettlementBatch.objects.select_for_update().get(pk=...)`; if already posted → idempotent return / error; else post once.
2. Unique constraint (Recommended): one open/posted batch per `(source_unit, offering_type, period)` as product defines — design with product before adding; minimum is row lock.
3. `record_district_remittance`: `select_for_update` on cutoff (or remittance control row) before transfer create; keep idempotency claim (after 013 fix).
4. `create_settlement_draft`: unique constraint or lock parent period row to prevent duplicate drafts.

**Files:** `remittance/services.py`, `transactions/services.py` `record_district_remittance`, models for constraints

---

## 4. Maker-checker matrix

| Domain | CREATE | SUBMIT | APPROVE / CHECK | POST effect | VOID / REVERSE | Same-actor maker+checker Current | Phase 3 target |
|--------|--------|--------|-----------------|-------------|----------------|----------------------------------|----------------|
| Receipt | `manage_finances` / manage_receipts | implicit | Auto if policy ≤ limit; else `approve_transactions` | Locked journal | `void_transactions` | Auto-approve **allowed** (exception) | Preserve capped exception + audit |
| Expense | `manage_finances` / manage_expenses | pending | `approve_transactions` SoD | Locked | void | DENY self-approve | Keep |
| Ledger entry | `manage_ledger_entries` / manage_finances | session draft | SoD / receipt-type auto | Locked | void | Confirm must not be `view_ledger` | Fix INV-FIN-02 |
| District remittance | `manage_finances` | — | `approve_module_journal` | Transfer | void | Distinct checker required | Keep + lock |
| Settlement batch | `manage_settlements` | draft | module journal | Posted batch | — | Distinct checker | + row lock |
| Bank recon | manage_reconciliation | — | finalize_reconciliation | Worksheet lock | — | No GL SoD required | Out of SoD journal rules |
| Contribution | manage_finances path | — | via receipt rules | Receipt | void | Dup posts | Idempotency |
| Asset acquisition | asset approve SoD | — | `approve_module_journal` | CAPITAL | void | Register after journal | + working day |
| Asset depreciation | manage policy / task | — | **missing** | Register early | — | Broken | Journal approve before register |
| Asset disposal | dispose | — | **missing** | Register early | — | Broken | Same |
| Welfare case | manage cases | pending | `approve_welfare` **no SoD** | Status | — | Self-approve possible | DENY creator |
| Welfare disburse | disburse perm | — | module journal | Expense | void | Distinct checker | Keep + locks |
| Announcement | (Phase 2) | pending | object SoD | — | archive | Pending exclude self | Done Phase 2 |
| Manual txn approve | — | — | `approve_transactions` | Lock | — | Creator DENY unless superadmin | Keep; optional lock |

**Lifecycle contract**

```text
CREATE → (optional SUBMIT) → APPROVE/CHECK → POSTED/LOCKED → VOID/REVERSE
```

Register modules (assets) MUST NOT skip APPROVE for GL-backed state changes.

---

## 5. Permission matrix (Phase 3 — no new codes)

| Action | Required permission(s) | Must NOT suffice alone |
|--------|------------------------|------------------------|
| Create receipt/expense/remittance pay/contribution | `manage_finances` (or specific manage_* where used) | `view_transactions` |
| Approve/reject journal | `approve_transactions` | `view_pending_approvals`, `manage_finances` |
| Void | `void_transactions` | approve-only |
| Ledger read | `view_ledger` | — |
| Ledger write / confirm | `manage_ledger_entries` **or** `manage_finances` | `view_ledger` |
| Recon mutate | `manage_reconciliation` | `view_reconciliation` |
| Recon finalize | `finalize_reconciliation` | view/manage alone if registry requires finalize |
| Welfare approve | `approve_welfare` + not creator | create-only |
| Welfare disburse | `disburse_welfare` (existing) + locks | — |
| Tenant church edit | `CAP_MANAGE_TENANTS` + denom rules | — |
| Asset policy / depreciation run | existing asset perms | — |

Platform operators remain on platform capabilities; they do not gain institution GL write via Phase 3.

---

## 6. Transaction / concurrency model

### 6.1 Required pattern

```text
@atomic
obj = Model.objects.select_for_update().get(...)
assert state allows transition
claim idempotency (if user-facing financial POST)
mutate / create balanced journal
approve_module_journal OR leave PENDING per SoD
complete idempotency
audit
```

### 6.2 Per-operation locks

| Operation | Lock target |
|-----------|-------------|
| Void | `Transaction` row (`select_for_update`) |
| Approve (Recommended) | `Transaction` row |
| Idempotency claim | `FinancialIdempotencyKey` row |
| Welfare disburse | case row (already) |
| Settlement post | `SettlementBatch` row |
| District remittance | cutoff / control row |
| Asset dep/dispose | `Asset` row before journal+register |
| Church save | N/A locking; validation required |

### 6.3 DB constraints to add (additive)

| Constraint | Purpose |
|------------|---------|
| `UniqueConstraint` on `Transaction.reversal_of` (non-null) | One reversal per original (CH-SEC-012) |
| `CONTRIBUTION` in idempotency ACTION_CHOICES | CH-SEC-006 |
| Settlement uniqueness (product-defined) | CH-SEC-L3 Recommended |
| Church cross-denom | Prefer app validation; trigger optional later |

---

## 7. Idempotency design (single primitive)

### 7.1 API (target)

| Function | Behavior |
|----------|----------|
| `normalize_idempotency_key` | Unchanged (≤64, non-empty) |
| `claim_financial_idempotency` | Atomic; `select_for_update` on existing; Replay if complete; serialize incomplete; create if missing |
| `complete_financial_idempotency` | Bind `transaction_id` once |
| `IdempotencyReplay` | Existing — return prior txn to UI |
| `IdempotencyInProgress` | Optional explicit error if non-blocking UX preferred |

### 7.2 Action catalog

| Action | Used by |
|--------|---------|
| RECEIPT | Teller receipts |
| EXPENSE | Expenses |
| REMITTANCE | District remittance payment |
| LEDGER | Ledger confirm |
| PAYROLL_POST / PAYROLL_PAY | Payroll |
| **CONTRIBUTION** | Member contributions / bulk lines (**new**) |
| Welfare | Existing welfare disbursement path (keep current action string as implemented) |

### 7.3 Scope key

`(church, user, action, idempotency_key)` remains. Different users with same client key are **not** deduped (Current contract). Document that UI keys must be per-session user.

### 7.4 Crash recovery

If process dies after journal insert but before complete: incomplete key + orphan PENDING/APPROVED journal. Phase 3 minimum: ops reconcile; Recommended follow-on: complete key in same `atomic` as journal save (already intended) so crash leaves incomplete only when journal rolled back.

---

## 8. Tenant-integrity design

| Control | Layer |
|---------|-------|
| `Church.clean()` denomination check | Model (existing) |
| `full_clean()` on every repository save | Repository (fix) |
| Constrained district queryset | Form (fix) |
| Destination re-assert in `tenant_edit` | View (fix) |
| Org `transfer_church` | Service (already aligned) |
| DB trigger | Recommended later only |

Fail closed: ambiguous denomination on district → DENY transfer.

---

## 9. Implementation dependency / order

Recommended order (matches safer dependency graph):

| Step | ID | Rationale |
|------|-----|-----------|
| **A** | CH-SEC-004 tenant integrity | Small; no finance dependency; stops silent SaaS wall breaks |
| **B** | CH-SEC-013 shared idempotency lock | Foundation for 006, remittance, ledger, welfare claims |
| **C** | INV-FIN-02 ledger write wrapper | Stops read→write; independent of assets |
| **D** | Maker-checker touch-ups | Welfare SoD (011); document receipt exception; optional approve row-lock |
| **E** | CH-SEC-005 asset journals | Needs working-day + approve_module_journal; Celery policy decision |
| **F** | CH-SEC-006 contributions | Needs B (`CONTRIBUTION` action + claim) |
| **G** | CH-SEC-011 welfare approve | Can ship with D; independent of E |
| **H** | CH-SEC-012 void `select_for_update` + unique reversal | Core GL safety |
| **I** | CH-SEC-L3 settlement/remittance locks | After B so remittance idempotency is trustworthy |

**Why not assets before idempotency?** Assets do not need idempotency keys for minimum fix; working-day + SoD first. Idempotency still early because contributions/remittance are high-frequency double-submit risks.

**Alternate ordering:** H (void) immediately after B if production void races are observed — still READY either way.

---

## 10. Migration strategy

| Change | Type | Risk |
|--------|------|------|
| Add `CONTRIBUTION` to idempotency actions | Additive choices / migrate | Low |
| UniqueConstraint on `reversal_of` | Additive; **preflight** for duplicate reversals | Medium if dirty data |
| Settlement unique (if chosen) | Additive; preflight duplicates | Medium |
| Church validation only | No schema | Low |
| Asset register repair | **Not** auto-migrated | Ops inventory |

**Preflight SQL (staging/production — do not run from this design phase remotely):**

```sql
-- Duplicate reversals (blocks unique constraint)
SELECT reversal_of_id, COUNT(*)
FROM transactions_transaction
WHERE reversal_of_id IS NOT NULL
GROUP BY reversal_of_id
HAVING COUNT(*) > 1;

-- Asset journals still PENDING while depreciation entries exist (inventory)
-- (exact joins depend on assets models linking transaction_id)

-- Churches whose district conference denomination differs from expected
-- (operator review; clean() would block new moves)
```

Rollback: reverse additive migrations; feature flags not required if services fail closed.

---

## 11. Test strategy

HTTP/service tests; avoid mocking authorization primitives.

| # | Scenario | Expect |
|---|----------|--------|
| 1 | Same actor approve own journal (non-superadmin) | DENY |
| 2 | Distinct checker with `approve_transactions` | ALLOW |
| 3 | Unauthorized checker | DENY |
| 4 | `view_ledger` POST `entry_confirm` | DENY |
| 5 | `manage_ledger_entries` confirm | ALLOW (subject to SoD/auto) |
| 6 | Cross-denomination tenant district move | DENY |
| 7 | Missing church/denomination on finance write | DENY / fail closed |
| 8 | Concurrent duplicate contribution same key | Exactly one receipt + one contribution |
| 9 | Retry completed idempotency key | Replay / same txn; no duplicate |
| 10 | Concurrent claims on incomplete key | One financial effect |
| 11 | Concurrent void | Exactly one reversal; second fails |
| 12 | Concurrent settlement post | Exactly one posted effect |
| 13 | Closed working day asset dep/disposal | DENY; register unchanged |
| 14 | Locked period post | DENY |
| 15 | Asset dep without distinct checker | PENDING journal; register unchanged |
| 16 | Welfare creator approves own case | DENY |
| 17 | Receipt under auto-approve limit | ALLOW exception + audit |
| 18 | Remittance concurrent pay same month | One transfer |

Concurrency tests: `ThreadingTestCase` / concurrent `atomic` calls as used elsewhere in repo.

---

## 12. Rollback considerations

- Feature is service-level: revert commit restores old behavior (undesirable security-wise).
- Additive DB constraints: reverse migration only if no dependency; never delete financial rows.
- If unique `reversal_of` blocked by dirty data: quarantine duplicates manually before deploy.
- Asset behavior change (no register update without approval) may surprise treasurers — release note required.

---

## 13. Production / staging safety gates

1. Confirm Phase 1 + Phase 2 commits deployed or co-deployed.
2. Run preflight SQL (§10); resolve duplicate reversals / settlement duplicates.
3. Staging: enable working-day assert on assets; run month-end depreciation dry-run; verify PENDING without register drift.
4. Confirm Celery worker identity policy with ops before forcing SoD on scheduled depreciation.
5. Deploy order: A→B→C→D→H early; E after Celery decision; F after B; I after B.
6. Monitor `FinancialAuditLog` for VOID/APPROVE spikes; idempotency Replay rates.
7. Do not run Phase 3 migrations on production from developer laptops without change control.

---

## 14. Explicitly OUT OF SCOPE for Phase 3

| Item | Why |
|------|-----|
| CH-SEC-001 S3/`FileField.url` | Media plane; remains OPEN from Phase 1 |
| CH-SEC-009 platform stats | Platform tenancy; separate phase |
| CH-SEC-010 portal enumeration | Auth UX |
| CH-SEC-014…022, L1, L2, L4, P* | Register backlog |
| Soft-delete / unified audit redesign | AGENTS Planned, not Current |
| DRF `/api/v1/` | Not in product |
| Rewriting chart of accounts / multi-currency | Architecture |
| Auto-healing historical asset register vs PENDING GL | Needs ops decision + data migration approval |
| Payload-hash idempotency | Recommended later |
| Removing receipt auto-approve | Documented exception — preserve |
| Redesigning reconciliation as GL | INV-IDEM-02 |
| Announcement / media (Phase 2 complete) | Done |
| Inventing new permission codenames | Forbidden unless gap proven |

---

## 15. Open questions (business decisions only)

1. **Celery / scheduled depreciation:** When no human checker exists, is “PENDING journal + no register update” acceptable for automated month-end, or must ops always supply a checker user id?
2. **Historical dirty voids:** If preflight finds multiple `reversal_of` for one original, who authorizes cleanup before unique constraint?
3. **Settlement uniqueness dimensions:** Exact business key for “one batch per period/unit/offering” — confirm with treasury before adding UniqueConstraint.
4. **Welfare reviewed_by:** Does product require reviewer ≠ approver in addition to creator ≠ approver? (Invariant only mandates creator ≠ approver.)

---

## 16. Definition of done (Phase 3 implementation)

- [ ] CH-SEC-004: all church save paths `full_clean`; tenant form scoped; tests DENY cross-denom
- [ ] CH-SEC-013: idempotency `select_for_update`; incomplete not double-executed
- [ ] INV-FIN-02: ledger confirm requires write permission
- [ ] CH-SEC-011: welfare self-approve DENY in service
- [ ] CH-SEC-012: void row lock + unique reversal constraint (after preflight)
- [ ] CH-SEC-006: `CONTRIBUTION` claim wired
- [ ] CH-SEC-005: working day + approve_module_journal; register after approved journal; Celery fail-closed
- [ ] CH-SEC-L3: settlement/remittance row locks (+ optional unique)
- [ ] Findings register updated FIXED/PARTIAL without erasing history
- [ ] Invariants §16 contradictions closed for these rows
- [ ] Focused tests green; full suite only when release-gated

**Do not implement from this document until an explicit Phase 3 implementation request.**
