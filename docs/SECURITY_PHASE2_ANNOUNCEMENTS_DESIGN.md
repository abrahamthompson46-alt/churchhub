# Phase 2 Security Design — Announcement Denomination Isolation (CH-SEC-002)

**Status:** IMPLEMENTED (local working tree; not yet committed/deployed at last update)  
**Date:** 14 August 2026  
**Phase 1 checkpoint:** `44f557534dcc0ca2c215c3b7b9057fc05c1ace40` (`feature/sec-phase1-media-mfa-finance`)  
**Finding:** CH-SEC-002 (HIGH) — general announcements cross the denomination wall  
**Related:** CH-SEC-008 (MEDIUM) — staff announcement detail IDOR for capability-only approvers  
**Contract:** `docs/SECURITY_AUTHORIZATION_INVARIANTS.md` §5 (INV-ANN-01…04), INV-OBJ-02, INV-TEN-07, INV-DENY-01  

This document was the implementation contract for Phase 2. Live Django code is the source of truth for Current behavior after implementation.

**PHASE 2 IMPLEMENTATION STATUS:** **COMPLETE (pending commit)**

Ownership model shipped:
- `Announcement.denomination` FK (nullable only for quarantined legacy rows)
- GENERAL: `church=NULL`, denomination required for live rows
- CHURCH: church + denomination required; denomination must match church
- Authorization never derives from `creator.denomination`
- Media ACL uses `announcement.denomination`
- S3 `FileField.url` remains **OPEN** under CH-SEC-001

---

## 1. Executive summary

Institution announcements (`announcements.Announcement`) previously treated `visibility="general"` as **global** (`church=NULL` with **no denomination owner`). List/feed selectors OR all general rows into every church-scoped query. Users with `view_all_churches` or institution `is_superadmin` received the **entire** approved queryset with no denomination bound. Staff detail loaded by global PK and treated capability `can_approve_announcements(user)` as object authorization (CH-SEC-008).

**Phase 2 goal (achieved in code):** Make the SaaS denomination wall authoritative for all announcement read, write, approve, archive, export, and media paths.

**Model:** Explicit `denomination` ForeignKey on `Announcement`.

| Visibility | Church | Denomination |
|------------|--------|--------------|
| `church` | Required | Required; MUST equal `get_church_denomination(church)` |
| `general` | MUST be null | Required; means **denomination-wide**, not platform-wide |

`view_all_churches` means churches in the actor’s manageable denomination/subtree — **not** all denominations.

**Out of scope for this finding (do not conflate):** `sitecontrol.PlatformAnnouncement` (platform banners / `CAP_MANAGE_ANNOUNCEMENTS`).

Local development inventory at design time had **0** announcement rows. Staging/production must still run the inventory SQL in §5 before applying the data migration. Empty or fully backfillable datasets are not a design blocker; non-deterministic rows must be quarantined fail-closed, not guessed.

---

## 2. Current vulnerability

### 2.1 CH-SEC-002 — Cross-denomination disclosure

1. **No ownership for general posts.** `Announcement.clean()` / `save()` clear `church` when `visibility=="general"` and never set a denomination (`announcements/models.py`).
2. **Selector OR-leak.** `announcements_for_church_ids()` / `announcements_for_church()` include **every** `visibility="general"` row:

```50:55:announcements/selectors.py
def announcements_for_church_ids(qs, church_ids):
    return qs.filter(Q(visibility="general") | Q(church_id__in=church_ids))
```

3. **Unfiltered super-scope.** `visible_announcements()` sets `scoped = qs` when `can_view_all_churches(user) or is_superadmin(user)` — entire approved table, all denominations (`announcements/services.py` ~116–118).
4. **Unscoped fallback.** Users with no manageable churches and no home church get `general_visibility_only(qs)` — still **all** general rows (~130).
5. **Pending queue for top-level.** `pending_for_user()` returns **all** pending rows for `is_top_level_approver` with no denomination predicate (~76–80).
6. **Object approve for general.** `can_approve_announcement()` for general only checks `is_top_level_approver(user)` — no denomination match (~44–45).
7. **Exports / calendar** inherit `visible_announcements()` and therefore the same leak.

### 2.2 CH-SEC-008 — Detail IDOR (in scope for Phase 2)

```192:202:announcements/views.py
def announcement_detail(request, pk):
    announcement = selectors.get_announcement_detail_or_404(pk)
    can_see = (
        announcement.created_by_id == request.user.id
        or can_approve_announcements(request.user)
        or selectors.announcement_exists_in_qs(visible_announcements(request.user), pk)
    )
```

Any user with the **capability** `approve_announcements` can read arbitrary PKs (pending/rejected/other denomination) before mutation gates apply. Violates INV-OBJ-02 / INV-ANN-03.

### 2.3 Media inconsistency (Phase 1 residual)

`church_system/media_authorization.py` `_announcement_image` already tries creator-denomination for general images. Feeds can still **list/detail** cross-denomination content while images 404 — disclosure of title/body remains. After Phase 2, media MUST authorize via **`announcement.denomination`**, not creator heuristic.

### 2.4 Attack scenario (confirmed pattern)

Actor in denomination A with `view_announcements` (default for staff/board/member) opens `/announcements/`. Any approved general announcement created in denomination B appears in the feed and calendar; staff with `approve_announcements` can also open B’s pending PKs via `/announcements/<pk>/`.

---

## 3. Complete code-path analysis

### 3.1 Model surface

| Object | Path | Notes |
|--------|------|-------|
| `Announcement` | `announcements/models.py` | Integer PK; `church` nullable; **no denomination**; visibility `general`\|`church` |
| `AnnouncementImage` | same | `upload_to="announcements/"` |
| `AnnouncementDepartment` | same | Audience M2M; no denom check on departments |
| `AnnouncementView` | same | Read receipts |
| `AnnouncementAuditLog` | same | Stores nullable `church` only |

**No** announcement signals, Celery tasks, or DRF/JSON APIs. HTML + session only.

### 3.2 HTTP routes (`/announcements/` + portal)

| Method | Name | View | Current authz | Leak / gap |
|--------|------|------|---------------|------------|
| GET | `announcement_list` | `views.announcement_list` | `view_announcements` + `visible_announcements` | Cross-denom general in feed; export inherits |
| GET | `upcoming_calendar` | calendar via `visible_announcements` | `view_announcements` | Same |
| GET/POST | `create_announcement` | create | `create_announcements` + service | General OK for top-level; **no denom assigned** |
| GET | `my_announcements` | mine | `create_announcements`; `created_by=user` | OK for ownership; no defensive denom |
| GET | `pending_approvals` | pending | `approve_announcements` + `pending_for_user` | Top-level sees all denoms |
| GET | `announcement_detail` | detail | Global PK + capability OR | **IDOR** |
| GET/POST | `edit_announcement` | edit | Global PK then `can_edit_announcement` | Edit form can flip to general without create-time top-level guard parity |
| POST | `approve_announcement` | approve | Global PK; service object check | Service missing denom match for general |
| POST | `reject_announcement` | reject | Same | Same |
| POST | `archive_announcement` | archive | Global PK; service | Creator/archive paths need denom wall |
| GET | `track_view` | track | From `visible_announcements` | Safer; inherits feed leak |
| GET | `portal:announcement_detail` | portal | From `visible_announcements` | Safer lookup; inherits feed leak |
| GET | `/media/announcements/...` | `protected_media` | Phase 1 ACL + creator-denom | Must switch to FK |

### 3.3 Permission defaults (`permissions/registry.py`)

| Codename | Default roles |
|----------|---------------|
| `view_announcements` | All staff + BOARD_MEMBER + MEMBER |
| `create_announcements` | Leadership + SECRETARY + MEMBER |
| `approve_announcements` | Leadership |
| `archive_announcements` | Leadership + SECRETARY |
| `export_announcements` | Leadership + SECRETARY |

`is_top_level_approver`: institution superadmin **or** scope level in `{DENOMINATION, GENERAL_CONFERENCE, UNION}` (`permissions/scoping_checks.py`). **Does not** compare announcement denomination today.

### 3.4 Platform lane

| System | App | Scope |
|--------|-----|-------|
| Institution announcements | `announcements` | Denomination wall (this design) |
| Platform banners | `sitecontrol.PlatformAnnouncement` | Platform `CAP_MANAGE_ANNOUNCEMENTS`; intentionally global banners |

Platform users (`is_platform_user`) MUST remain **denied** institution announcement private media (Phase 1 media ACL). They do not gain institution `Announcement` access via platform announcement capability.

### 3.5 Admin

`announcements/admin.py` church-filters queryset; `church=NULL` general rows are invisible to non-global operators. After Phase 2, admin queryset MUST filter by operator-managed denominations (or OWNER break-glass only), never “all general”.

---

## 4. Data model recommendation

### Decision: **Option A — explicit `denomination` FK**

| Option | Verdict |
|--------|---------|
| **A. `Announcement.denomination` FK** | **Adopt.** Matches INV-ANN-01; supports church-less general posts; media/list/detail share one owner key. |
| B. Derive only from `church` | Reject for general (`church` is forced null). |
| C. Other org ownership | Reject; denomination is the SaaS wall. |

### Recommended fields & invariants

```text
denomination = ForeignKey(sitecontrol.Denomination, on_delete=PROTECT, null=True, blank=True, db_index=True)
# After backfill + clean enforcement: treat as required for all live rows.
# Prefer null=False after data migration succeeds; if rollout needs two steps,
# keep null=True briefly but FAIL CLOSED in selectors/services when NULL.
```

**Enforcement in `Announcement.clean()` / service layer (must):**

1. `visibility == "church"` → `church_id` required; `denomination_id` required; `denomination_id == get_church_denomination(church).pk`.
2. `visibility == "general"` → `church_id` is null; `denomination_id` required.
3. Changing visibility church→general: clear church; keep or set denomination from actor’s denomination (must match); require `is_top_level_approver` **and** same denomination.
4. Changing general→church: require church in actor scope; set denomination from that church.
5. DB constraints (Recommended, additive): CheckConstraint / partial uniqueness as practical; at minimum application `full_clean()` on create/update paths.

**Indexes:** `(denomination, visibility, status, is_archived)`, `(denomination, is_approved, publish_at)` for feed queries.

**Audience departments:** When linking `AnnouncementDepartment`, department.church (or church denom) MUST be in announcement denomination; reject cross-denom targets.

---

## 5. Migration / backfill strategy

### 5.1 Inventory (read-only; run on staging/production before migrate)

Local design-time DB counts: **all zeros**. Production/staging MUST run:

```sql
-- Counts
SELECT visibility, COUNT(*) FROM announcements_announcement GROUP BY visibility;
SELECT COUNT(*) FROM announcements_announcement WHERE visibility='general' AND church_id IS NULL;
SELECT COUNT(*) FROM announcements_announcement WHERE visibility='church' AND church_id IS NULL;
SELECT COUNT(*) FROM announcements_announcement WHERE created_by_id IS NULL;
SELECT COUNT(*) FROM announcements_announcementimage;
```

Plus ORM pass classifying each row:

| Class | Rule | Action |
|-------|------|--------|
| **A. Church-scoped resolvable** | `church_id` set; church→conference→denomination exists | Set `denomination_id` from church |
| **B. General resolvable** | `visibility=general`; `get_user_denomination(created_by)` non-null | Set from creator denomination |
| **C. Conflict** | Church denom ≠ creator denom | Prefer **church** denom for `visibility=church`; for general prefer creator; log both |
| **D. Unresolvable** | No church denom and no creator denom (deleted user, platform creator, orphan) | **Do not guess.** Leave `denomination_id` NULL **or** quarantine (`is_archived=True` + audit note). Selectors MUST exclude NULL denomination |

Images do not need path remapping; ownership follows parent announcement FK.

### 5.2 Migration shape (design; not generated here)

1. **Schema migration:** add nullable `denomination` FK + index.
2. **Data migration:** deterministic classes A/B; write `PlatformAuditLog` or announcement audit entry for each backfilled PK; emit report of class D PKs.
3. **Follow-up schema (same release or immediate next):** `null=False` only if class D count is 0; else keep nullable and fail-closed in code until ops assigns denoms.
4. **No destructive deletes** of announcement history.

### 5.3 Fail-closed rule during/after backfill

Any query path: `denomination_id IS NULL` → **invisible** to institution users (except break-glass Django admin OWNER reviewing quarantine list). Creates/updates without resolvable denomination → **reject**.

---

## 6. Authorization matrix

Legend: **ALLOW** / **DENY**. “Same denom” = actor `get_user_denomination` equals announcement.denomination. “Church scope” = church ∈ `get_manageable_churches(actor)` (already denomination-bounded when actor has denom).

### 6.1 READ LIST / calendar / export

| Actor | Same-denom general | Other-denom general | Same-denom church (in scope) | Other-denom church |
|-------|--------------------|---------------------|------------------------------|--------------------|
| SECRETARY / staff with `view_announcements` | ALLOW (audience) | **DENY** | ALLOW (audience) | **DENY** |
| BOARD_MEMBER | ALLOW (audience) | **DENY** | ALLOW if church in scope | **DENY** |
| MEMBER (portal/staff role) | ALLOW (audience) | **DENY** | ALLOW if own church + audience | **DENY** |
| Conference admin `view_all_churches` (denom A) | ALLOW all **A** generals + A churches in scope | **DENY B** | ALLOW A | **DENY B** |
| Institution SUPER_ADMIN with denom A | Same as bound A | **DENY B** | ALLOW A | **DENY B** |
| Unanchored SUPER_ADMIN (no denom) | **DENY** (fail closed; CH-SEC-L1 remains separate) | **DENY** | **DENY** | **DENY** |
| Platform operator | **DENY** institution feed | **DENY** | **DENY** | **DENY** |

`view_all_churches` MUST filter:  
`(visibility=church AND church_id ∈ manageable) OR (visibility=general AND denomination_id = user_denom)`.  
**Never** `scoped = qs`.

### 6.2 READ DETAIL

| Actor | Condition | Result |
|-------|-----------|--------|
| Creator | Same user; prefer same denom (creator without denom: DENY unless row visible another way) | ALLOW own drafts |
| Published audience | Row ∈ `visible_announcements` (post-fix) | ALLOW |
| Approver | `can_approve_announcement(user, obj)` **object-scoped** including denom match | ALLOW pending/rejected in scope |
| Capability-only `approve_announcements` | Without object scope | **DENY** (fix CH-SEC-008) |
| Cross-denom PK guess | Any | **DENY** → prefer **404** (no existence leak) |

### 6.3 CREATE

| Actor | Church-scoped | General |
|-------|---------------|---------|
| MEMBER / SECRETARY with `create_announcements` | ALLOW if church in scope; set denomination from church | **DENY** |
| Leadership / top-level in denom A | ALLOW in scope | ALLOW if `is_top_level_approver` **and** denomination set to A (never null) |
| Cross-denom church | **DENY** | **DENY** |

### 6.4 UPDATE / ARCHIVE

| Actor | Same denom in edit rules | Other denom |
|-------|--------------------------|-------------|
| Creator of pending | ALLOW per existing `can_edit_announcement`; cannot set visibility general unless top-level + same denom | **DENY** (404/403 before edit) |
| Approver object-scoped | ALLOW | **DENY** |
| Flip church→general | Top-level + same denom only | **DENY** |

### 6.5 APPROVE / REJECT

| Actor | Same denom general | Other denom general | Church in `can_approve_for_church` |
|-------|--------------------|---------------------|-------------------------------------|
| Leadership top-level denom A | ALLOW | **DENY** | per church scope |
| Local pastor church A | **DENY** general (not top-level) | **DENY** | ALLOW church A |

Self-approve: keep existing maker-checker exclusion in `pending_for_user` (`exclude created_by`).

### 6.6 IMAGE ACCESS

Same rules as detail visibility / object approve / creator — via `announcement.denomination_id`, not creator heuristic. Unknown prefix still DENY (Phase 1).

---

## 7. Media implications

| Item | Action |
|------|--------|
| `_announcement_image` | Resolve `AnnouncementImage` → `announcement.denomination`; require `get_user_denomination(user).pk == denomination_id` for general; church path keep `_church_in_scope` |
| Creator shortcut | Allowed only if creator’s denom matches announcement denom (defense in depth) |
| `can_approve_announcement` | Already object-level; after denom fix, media follows |
| S3 `.url` | Still open (CH-SEC-001 remainder); Phase 2 does not claim S3 fixed |
| Templates | Continue `img.image.url`; filesystem `/media/` hits ACL |

---

## 8. API implications

**Current:** No DRF `/api/v1/` announcement API; no AJAX announcement endpoints found.

**Phase 2:** No new public API. If future JSON helpers are added, they MUST reuse `visible_announcements` / object-scoped can_* — never raw PK.

Portal HTML detail already uses scoped queryset; after feed fix it becomes correct.

---

## 9. Test plan

HTTP-level tests (two real denominations, two churches, users per role). Prefer **404** on cross-tenant detail.

| # | Invariant | Test outline |
|---|-----------|--------------|
| 1 | INV-ANN-01 list | Denom A user must not see denom B general in list HTML |
| 2 | INV-ANN-03 detail | Denom A cannot GET `/announcements/<B_pk>/` (404/403) |
| 3 | INV-ANN-02 | User with `view_all_churches` in A still DENY B general and B church |
| 4 | Bound superadmin | SUPER_ADMIN with denom A DENY B; optional unanchored DENY all |
| 5 | Same-denom general | A general appears for A users with audience match |
| 6 | Church-scoped | Church announcement visible only in correct church scope |
| 7 | Missing denom | Row with `denomination_id` NULL invisible; create without denom rejected |
| 8 | Media | `/media/announcements/...` 404 cross-denom; 200 same-denom when otherwise allowed |
| 9 | Approve | A approver cannot approve B pending (403); pending queue omits B |
| 10 | Mutate | A cannot edit/archive B |
| 11 | Regression | Portal detail still works for in-scope published; create church flow; track_view; export only in-scope rows |
| 12 | CH-SEC-008 | Leadership in A with `approve_announcements` cannot read B pending by PK |
| 13 | Top-level create | Only top-level can create general; denomination auto-set to actor denom |
| 14 | Edit flip | Non-top-level cannot change visibility to general |

Update/remove any test that encoded “global general” as correct — **do not weaken invariants to preserve tests**.

---

## 10. Rollback strategy

1. **Code rollback:** Revert Phase 2 commit(s); feeds revert to leaky behavior (undesirable but known).
2. **Schema:** Prefer expand/contract — keep `denomination` column if already backfilled (harmless if unused). Do **not** drop column in emergency rollback without explicit approval.
3. **Data:** Backfill is additive; reversing assignments requires restoring from backup only if bad denoms were written — inventory report is the recovery map.
4. **Feature flag (optional):** Temporary setting `ANNOUNCEMENTS_DENOMINATION_ENFORCE=1` to switch selectors; default on in production after verify.

---

## 11. Deployment considerations

1. Confirm Phase 1 commit is deployed or co-deployed (media ACL).
2. Run inventory SQL on **staging**, then **production** replica/read-only.
3. Deploy schema + data migration in maintenance window if large tables; otherwise online additive OK.
4. Deploy application code that fail-closes NULL denomination **in the same release** as backfill.
5. Smoke: create church announcement; create general as union/denom admin; cross-denom list empty; detail 404; image 404/200.
6. Review class-D quarantine list with ops before `null=False`.

---

## 12. Risks

| Risk | Mitigation |
|------|------------|
| Unresolvable historical general rows disappear from UI | Quarantine report; ops assign denomination; fail closed intentionally |
| Creator moved denominations after post | Ownership is **announcement.denomination**, not live creator denom |
| `view_all_churches` product expectation “see everything” | Contract forbids cross-denom; document for stakeholders |
| Pin limits for general currently global | Scope pin limits **per denomination** |
| Edit form allows general without service parity | Align form + service in same PR |
| Admin bulk actions swallow exceptions | Fix or leave; do not expand admin power |
| CH-SEC-L1 unanchored superadmin | Fail closed for announcements; do not use Phase 2 to invent global access |
| Test suite baseline failures (unrelated) | Do not “fix” by weakening announcement isolation |

---

## 13. Exact implementation sequence

1. Add failing HTTP tests from §9 (red).
2. Schema migration: nullable `Announcement.denomination` + indexes.
3. Data migration: backfill A/B; report D.
4. Model `clean()` / `save()` invariants; repository/service set denomination on create/update.
5. Rewrite selectors:  
   - replace naked `visibility=general` OR with `(visibility=general AND denomination_id=…)`;  
   - remove `scoped = qs` for `view_all_churches` / superadmin; bind to user denomination + manageable churches.
6. Fix `pending_for_user` / `can_approve_announcement` / `can_edit` / `can_archive` with denomination match.
7. Fix `announcement_detail` / edit / approve / reject / archive: load via scoped queryset or object check **before** body; capability-alone forbidden.
8. Align create/edit forms (general choice + denomination assignment).
9. Update `_announcement_image` to use `announcement.denomination`.
10. Pin-limit helpers scoped by denomination.
11. Admin queryset denomination filter.
12. Green tests; update `docs/SECURITY_FINDINGS_REGISTER.md` / invariants §16 **in the implementation PR** (not this design-only task).
13. Optional: make `denomination` non-null when D=0.

---

## 14. Files expected to change (implementation PR)

| File | Change |
|------|--------|
| `announcements/models.py` | `denomination` FK; `clean()` invariants |
| `announcements/migrations/0005_*.py` | Schema + data (new) |
| `announcements/selectors.py` | Denom-safe filters; scoped get helpers |
| `announcements/services.py` | `visible_announcements`, pending, can_*, create/update |
| `announcements/views.py` | Detail/edit/approve/reject/archive load path |
| `announcements/forms.py` | Visibility rules; denomination assignment |
| `announcements/admin.py` | Denom-filtered queryset |
| `announcements/repositories.py` | Persist denomination if needed |
| `church_system/media_authorization.py` | Announcement image owner = FK |
| `announcements/tests*.py` / new `tests_denomination_isolation.py` | §9 tests |
| `portal/views.py` | Only if portal assumes old visibility (likely none beyond feed fix) |
| `docs/SECURITY_FINDINGS_REGISTER.md` | Mark CH-SEC-002 / CH-SEC-008 fixed when verified |
| `docs/SECURITY_AUTHORIZATION_INVARIANTS.md` | Refresh §16 contradictions |
| `docs/AI_CONTEXT/DOCUMENT_INDEX.md` | Link this design when indexed |

**Not expected:** `sitecontrol` platform announcement models; finance/MFA/media core beyond announcement image handler.

---

## 15. Security invariants satisfied

| Invariant | How Phase 2 satisfies |
|-----------|------------------------|
| INV-ANN-01 | Explicit denomination owner for general |
| INV-ANN-02 | No unfiltered `Announcement` queryset for `view_all_churches` / superadmin |
| INV-ANN-03 / INV-OBJ-02 | Detail uses object-scoped visibility; capability-alone removed |
| INV-ANN-04 | Create/approve/archive denomination-bound |
| INV-TEN-07 | SaaS wall on announcement domain |
| INV-DENY-01 | Missing denomination → deny |
| INV-MED (announcement images) | Media derives from announcement denomination |

---

## Appendix A — Selector rewrite sketch (non-normative)

```python
def announcements_visible_for_user_scope(qs, user):
    denom = get_user_denomination(user)
    if not denom:
        return qs.none()
    churches = get_manageable_churches(user)
    church_ids = list(churches.values_list("pk", flat=True))
    return qs.filter(
        Q(visibility="church", church_id__in=church_ids)
        | Q(visibility="general", denomination_id=denom.pk)
    )
```

`can_view_all_churches` / `is_superadmin` use the **same** helper (manageable churches already denomination-bounded when user has denom). No bypass branch.

---

## Appendix B — Local inventory note

At design time on the developer database:

- `Announcement` rows: **0**
- `AnnouncementImage` rows: **0**

Treat production counts as unknown until §5 inventory runs. Design remains **READY FOR IMPLEMENTATION** with a **deployment gate**: do not force `null=False` until class D is empty or explicitly quarantined.

---

**PHASE 2 DESIGN STATUS: READY FOR IMPLEMENTATION**
