# ChurchHub — Enterprise Findings Register (12 October 2026)

**Scope:** Whole-product assessment of branch `feature/dashboard-member-summary` @ `f6c9721` plus noted working-tree diffs.  
**Does not replace:** `docs/SECURITY_FINDINGS_REGISTER.md` (14 Aug 2026 security program). Historical CH-SEC-* IDs remain there.  
**IDs in this file:** `CH-ENT-*`.  
**Severity:** Critical / High / Medium / Low / Informational.  
**Confidence:** Confirmed / Strongly Indicated / Unverified.  
**Class:** Security | Accounting-control | Workflow | Usability | Technical debt | Ops | Documentation | Opportunity.

No Critical exploit was **confirmed** from source inspection alone. Highest items are operational High and accounting-control High.

---

## Inventory

| ID | Sev | Confidence | Class | Title |
|----|-----|------------|-------|-------|
| CH-ENT-001 | High | Strongly Indicated | Ops / Security | Live media/TLS edge unverified; stale KL-OPS-01 can undo the Django media gate |
| CH-ENT-002 | High | Confirmed | Accounting-control | Module journals skip HTTP ApprovalCase / actor_may_decide |
| CH-ENT-003 | Medium | Confirmed | Accounting-control | Enterprise audit dual-write is best-effort; hash chain is Python-only |
| CH-ENT-004 | Medium | Confirmed | Workflow / Usability | Pending reject has no reason; bulk approve lacks preflight |
| CH-ENT-005 | Medium | Confirmed | Documentation | SYSTEM_OVERVIEW / CURSOR_AUDIT still describe MFA stub and missing selectors |
| CH-ENT-006 | Medium | Confirmed | Accounting-control | Settlement post does not require an open working day |
| CH-ENT-007 | Medium | Confirmed | Accounting-control | Reconciliation match+finalize same actor; matches unaudited |
| CH-ENT-008 | Medium | Confirmed | Workflow | Remittance desk GET vs nav mismatch on HEAD |
| CH-ENT-009 | Medium | Confirmed | Ops | CI/deploy gaps (branch filter, 50% coverage, non-blocking audit, placeholder deploy) |
| CH-ENT-010 | Medium | Confirmed | Usability | Three remittance surfaces easy to confuse cash vs reclass |
| CH-ENT-011 | Low | Strongly Indicated | Security (footgun) | Generic remittance `*_by_pk` selectors are unscoped |
| CH-ENT-012 | Low | Strongly Indicated | Security (tests) | CSRF middleware on; authenticated CSRF-negative tests narrow |
| CH-ENT-013 | Medium | Strongly Indicated | Accounting-control | Audit immutability bypassable with privileged DB / bulk ORM |
| CH-ENT-014 | Medium | Confirmed | Ops | Render blueprint omits MFA_ENCRYPTION_KEY and durable media |
| CH-ENT-015 | Low | Confirmed | Usability | Inconsistent empty states and page-shell |
| CH-ENT-016 | Medium | Strongly Indicated | Performance | Welfare/budget reports can N+1 across churches |
| CH-ENT-017 | Low | Confirmed | Usability | 403 page does not explain capability or church context |
| CH-ENT-018 | Low | Confirmed | Accessibility | Skip-link present; remaining unlabeled filters and icon-only portal nav |
| CH-ENT-019 | Informational | Confirmed | Opportunity | UNION/GC settlement GL still refused (product, not a bug) |
| CH-ENT-020 | Informational | Confirmed | Opportunity | No payment gateway; subscriptions are manual references |
| CH-ENT-021 | Low | Confirmed | Documentation | Invariants §16 vs findings register FIXED rows |
| CH-ENT-022 | Medium | Unverified | Ops | Restore drill, offsite backup, and Beat-in-prod not demonstrated here |

---

## CH-ENT-001 — High — Live edge and stale media-ops guidance

1. **Domain / module:** Deployment, Nginx, `church_system.media_views`  
2. **What exists:** Django always routes `media/<path:path>` to `protected_media` (`church_system/urls.py` lines 82–85). Production settings force HTTPS cookies/HSTS (`church_system/settings/production.py` 29–54). Repo Nginx template sends private media through Django (`deploy/nginx/churchhub.conf`). Historical CH-SEC-001 is FIXED in `docs/SECURITY_FINDINGS_REGISTER.md`. CH-SEC-P2 remains OPEN (hostname template vs live host).  
3. **What is wrong:** Live vhost, `X-Accel-Redirect` `internal`, and bucket policy cannot be proven from git. `docs/KNOWN_LIMITATIONS.md` KL-OPS-01 still says media is **not** served by Django when `DEBUG=False`, which contradicts `urls.py`. An operator following KL-OPS-01 could point Nginx at disk and **bypass** object ACL.  
4. **Impact:** Cross-tenant PII/export files if the edge skips Django.  
5. **Confidence:** Strongly Indicated (code vs docs Confirmed; live host Unverified).  
6. **Verify without destruction:** Compare live Nginx to `deploy/nginx/churchhub.conf`; request a foreign-church `/media/` path as a low-privilege user on **staging**; confirm 404 and no `X-Accel` on deny (pattern in `church_system/tests_media_access.py`).  
7. **Remediation:** Fix KL-OPS-01; run production-readiness checklist; keep Django as the only ACL gate.  
8. **Tests:** Existing media ACL tests; add a deploy-doc review checkbox. Migration: no.  
9. **Class:** Ops / Security  

---

## CH-ENT-002 — High — Module journals bypass ApprovalCase

1. **Module:** `transactions.services.approve_module_journal`, callers in `payroll/services.py`, `remittance/services.py`, assets depreciation.  
2. **What exists:** HTTP pending queue uses `actor_may_decide` + `record_approval` (`approvals/services.py` 104–207; `transactions/views.py` 153–168). `approve_module_journal` ( `transactions/services.py` 949–960 ) picks the first checker ≠ maker and calls `approve_transaction` directly. Docs (`SYSTEM_OVERVIEW.md` approvals row) already state Phase-2 policy does not cover programmatic posters.  
3. **What is wrong:** Multi-step policy, delegation amount limits, and ApprovalCase audit steps do not wrap payroll/settlement/asset journals. Maker-checker **identity** SoD still runs inside `approve_transaction` (`_assert_not_self_maker`). If `resolve_journal_checker` finds any other user object, RBAC/`actor_may_decide` is not re-applied inside the helper.  
4. **Impact:** Programmatic path can approve with a checker who would fail the HTTP queue (wrong church, District Pastor, no `approve_transactions`, expired delegation) depending on how callers pass candidates. Accounting still balances and periods still lock.  
5. **Confidence:** Confirmed for bypass of ApprovalCase; Strongly Indicated for weak-checker selection — inspect each caller’s candidate list before claiming an exploit.  
6. **Verify:** Unit tests that pass a District Pastor or out-of-scope user as the only checker candidate to `approve_module_journal`; confirm Current vs intended policy.  
7. **Remediation (Recommended):** Keep receipt auto-approve unchanged. Either (A) document and test the programmatic exception as accepted, or (B) route module journals through `actor_may_decide` + optional ApprovalCase. **Policy approval required** before (B).  
8. **Tests:** New service tests per caller. No migration if (A); maybe none if (B) reuses cases.  
9. **Class:** Accounting-control  

---

## CH-ENT-003 — Medium — Dual-write audit gap

1. **Module:** `transactions/repositories.py` 29–45; `audit/services.py`.  
2. **What exists:** `FinancialAuditLog` is created first; `emit_from_financial_audit` is try/except; failure is logged; financial row remains. `AuditEvent` is hash-chained per church with row locking.  
3. **Impact:** Controls dashboard / enterprise search can miss a material posting that still exists on the books and in `FinancialAuditLog`.  
4. **Verify:** Force `emit_from_financial_audit` to raise in a test; assert journal + FinancialAuditLog persist and a warning is logged.  
5. **Remediation:** Outbox table, or fail the financial transaction if enterprise audit is in-policy required (product decision: Current is fail-open on enterprise audit). Do not silently delete financial history.  
6. **Class:** Accounting-control  

---

## CH-ENT-004 — Medium — Pending reject/bulk UX

**Status (2026-11-26):** Addressed on `main` — HTTP reject requires POST `reason`; pending list shows church, maker, longer description, bulk JS confirm, expandable reject forms; CSRF-negative tests on approve/reject (`transactions/tests_pending_workflow.py`).

1. **Module:** `templates/transactions/pending.html`; `transactions/views.py` reject/bulk paths.  
2. **Class:** Workflow / Usability  

---

## CH-ENT-005 — Medium — Stale architecture docs

1. **Evidence:** `docs/AI_CONTEXT/SYSTEM_OVERVIEW.md` lines 56–58, 184 (selectors absent; MFA stub) vs `accounts/mfa.py`, widespread `selectors.py`.  
2. **Impact:** Agents and operators disable or skip real MFA/media/selector work.  
3. **Remediation:** Rewrite overview Current sections from code; mark CURSOR_AUDIT historical.  
4. **Class:** Documentation  

---

## CH-ENT-006 — Medium — Settlement vs working day

1. **Evidence:** Remittance settlement post: period assert without working-day assert (inspect `remittance/services.py` ~730 and ~817). Cash remittance requires open working day (`transactions` remittance record path; desk copy in `templates/dashboard/cutoff.html`).  
2. **Impact:** Liability reclass can post on a closed business date while cash path is blocked — books vs treasurer mental model diverge.  
3. **Remediation:** Product choice: apply `assert_working_day_allows_posting` to settlement, or document settlement as period-only.  
4. **Class:** Accounting-control  

---

## CH-ENT-007 — Medium — Reconciliation SoD

1. **Evidence:** `finalize_reconciliation` implies `manage_reconciliation` (`permissions/registry.py` ~273–290). Match updates in `transactions/services.py` ~1208–1255 lack a dedicated audit action comparable to create/finalize.  
2. **Impact:** Same user can build and lock a rec; match tampering has weaker trail.  
3. **Remediation:** Policy: require distinct finalizer **or** accept implied permission. Add match audit events.  
4. **Class:** Accounting-control  

---

## CH-ENT-008 — Medium — Remittance desk 403 vs nav

1. **HEAD Current:** Nav shows Remittance desk when `can_run_cutoff or can_view_dashboard_finance` (`church_system/navigation.py` ~261–264, ~869). View `cutoff` on committed `dashboard/views.py` at `f6c9721` required `can_manage_finances` (accounts.permissions). District Treasurer has `view_dashboard_finance` and not `manage_finances` (`permissions/tests.py` ~122–144).  
2. **Working tree:** Uncommitted `dashboard/views.py` widens GET and keeps snapshot POST restricted. Not shipped.  
3. **Remediation:** Ship the GET/nav alignment; do not grant posting. Tests already drafted in uncommitted `dashboard/tests.py`.  
4. **Class:** Workflow  

---

## CH-ENT-009 — Medium — CI and release engineering

1. **Evidence:** `.github/workflows/ci.yml` `on.push/pull_request` branches `main|master|develop`; coverage `--fail-under=50`; `dependency-audit` `continue-on-error: true`; `deploy-production.yml` is a manual placeholder.  
2. **Impact:** This feature branch may merge with only local tests; dependency CVEs can ship; no automated prod deploy/rollback.  
3. **Remediation:** PR into `develop`; raise coverage gate gradually; make audit blocking for High CVEs; document manual Render rollback.  
4. **Class:** Ops  

---

## CH-ENT-010 — Medium — Remittance cognitive load

1. **Evidence:** Desk stepper (`templates/dashboard/cutoff.html`); Settlement Desk (`templates/remittance/settlements.html`); payment (`templates/transactions/record_remittance.html`). Cross-path in `remittance/cross_path.py`. Spec: `docs/MODULE_SPECIFICATIONS/REMITTANCE/remittance_spec.md`.  
2. **Impact:** Treasurer may think settlement “sent the money.”  
3. **Remediation:** Stronger “no cash / cash leaves” visual language; keep tables separate.  
4. **Class:** Usability  

---

## CH-ENT-011 — Low — Unscoped PK helpers

1. **Evidence:** `remittance/selectors.py` `policy_by_pk` / `settlement_by_pk` (~41–42, ~231–232). Callers currently re-check scope (`remittance/views.py` ~208–220, ~467–489). Safer pattern: `members/selectors.py` scoped get.  
2. **Remediation:** Scoped selectors; cross-tenant PK tests.  
3. **Class:** Security (footgun)  

---

## CH-ENT-012 — Low — CSRF test breadth

1. **Evidence:** `CsrfViewMiddleware` in `church_system/settings/base.py` ~157–183; no `csrf_exempt` hits in this review; focused public CSRF test in `sitecontrol/tests_marketing.py`. Writes use `@require_POST` (e.g. approve/reject).  
2. **Remediation:** `Client(enforce_csrf_checks=True)` on finance, MFA, church switch.  
3. **Class:** Security (tests)  

---

## CH-ENT-013 — Medium — Python-only audit immutability

1. **Evidence:** `FinancialAuditLog` / `AuditEvent` override save/delete. No DB trigger in inspected migrations.  
2. **Impact:** DBA or `QuerySet.update/delete` can break hash chain without UI.  
3. **Remediation:** PostgreSQL REVOKE + triggers if board requires; accept Python-only for pilot with access control. **Migration + DBA approval.**  
4. **Class:** Accounting-control  

---

## CH-ENT-014 — Medium — Render blueprint gaps

1. **Evidence:** `render.yaml` has no `MFA_ENCRYPTION_KEY` (grep empty). Production settings require the key (`church_system/settings/production.py` ~99–114). Media defaults to filesystem; no Disk in blueprint.  
2. **Impact:** Fresh Render deploy fails closed on MFA **or** succeeds with ephemeral uploads if key is injected but disk is not.  
3. **Remediation:** Document required env; add Disk or S3; never commit secrets.  
4. **Class:** Ops  

---

## CH-ENT-015 — Low — Empty state / page-shell inconsistency

1. **Evidence:** Shared `templates/includes/empty_state.html`; many lists still `text-muted`. ~26 `page-shell` vs ~100 `page-container`.  
2. **Class:** Usability / technical debt  

---

## CH-ENT-016 — Medium — Report N+1 risk

1. **Evidence:** `reports/services.py` welfare-per-church; `budgets/services.py` `_account_actual` per line. No `assertNumQueries`. KL-QA-01.  
2. **Confidence:** Strongly Indicated (pattern, not measured latency).  
3. **Class:** Performance  

---

## CH-ENT-017 — Low — 403 content

1. **Evidence:** `templates/403.html`; `church_system/urls.py` `handler403`.  
2. **Remediation:** Safe message: required action class + “switch church” + dashboard link. Do not leak permission codenames to members.  
3. **Class:** Usability  

---

## CH-ENT-018 — Low — Accessibility leftovers

1. **Evidence:** Skip-link in `templates/base.html`; portal navbar titles without `aria-label`; some reports/audit filters render widgets without `id`/`for`.  
2. **Class:** Accessibility  

---

## CH-ENT-019 — Informational — UNION/GC settlement

Current: drafts stay review-only; posting raises policy error. Recommended only with CoA design. Not a defect.

---

## CH-ENT-020 — Informational — No card processor

Billing is payment-reference. Do not add a gateway in the first remediation phase.

---

## CH-ENT-021 — Low — Invariants §16 stale vs register FIXED

`docs/SECURITY_AUTHORIZATION_INVARIANTS.md` ~657–659 vs register CH-SEC-014/016 FIXED. Reconcile.

---

## CH-ENT-022 — Medium — Restore/Beat unverified

Commands exist (`backup_database.py`, `restore_database.py` with DESTROY gate). Drill not evidenced in this engagement. KL-OPS-03.

---

## Historical Highs (not re-opened without new evidence)

Treat CH-SEC-001 through CH-SEC-022 (except P2) and L1–L4 as **FIXED in code at inspection**, per `docs/SECURITY_FINDINGS_REGISTER.md` plus media/MFA/tenancy tests cited in the assessment. Re-test on staging before GA rather than assuming git equals production.
