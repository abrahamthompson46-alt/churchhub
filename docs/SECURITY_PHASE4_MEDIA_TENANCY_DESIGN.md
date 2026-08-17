# Phase 4 Security Design — Media Bypass, Unanchored Tenancy & Platform Stats

**Status:** Implemented on working tree (Phase 4 code + focused tests; not committed in design-only sense superseded)  
**Date:** 15 August 2026  
**Baseline:** `71aa74cf1294d598d0f608e91c66623f16389541` (`feature/sec-phase1-media-mfa-finance`, Phase 3 committed)  
**Contract:** `docs/SECURITY_AUTHORIZATION_INVARIANTS.md`, `docs/SECURITY_FINDINGS_REGISTER.md`  

Live Django code is the source of truth. This document is the implementation contract for Phase 4 only.

**PHASE 4 DESIGN STATUS:** IMPLEMENTED (Option A for CH-SEC-009)

---

## 1. Executive summary

Phases 1–3 closed private-media ACL on the Django `/media/` gate, MFA throttle, remittance/recon write wrappers, announcement denomination isolation, and financial integrity / maker-checker. Phase 4 closes three remaining tenancy/media gaps:

| Finding | Sev | Theme | Primary invariant(s) |
|---------|-----|-------|----------------------|
| CH-SEC-001 (residual) | HIGH | S3 / `FileField.url` bypass of `protected_media` | INV-MED-01…04 |
| CH-SEC-L1 | HIGH | Unanchored `SUPER_ADMIN` / break-glass `is_superuser` → all churches | INV-TEN-02, INV-TEN-18 |
| CH-SEC-009 | MEDIUM | Global `platform_stats` / health alerts for scoped operators | INV-TEN-03 § platform KPIs |

**Non-goals for Phase 4:** CH-SEC-010 portal enumeration, CH-SEC-014 activity-log delete, CSV export audit, MFA policy changes, financial SoD (done in Phase 3).

---

## 2. CH-SEC-001 — Private media & S3 / `FileField.url`

### 2.1 Current state (filesystem — production default)

| Layer | Behavior |
|-------|----------|
| URL | `church_system/urls.py` → `path("media/<path:path>", protected_media)` |
| Gate | `church_system/media_views.protected_media` → public branding OR auth + `user_may_access_media` → 404 on deny |
| ACL | `church_system/media_authorization.py` — deny-by-default prefix handlers |
| Public | `platform/branding/`, `denominations/branding/` (`media_access.PUBLIC_MEDIA_PREFIXES`) |
| Nginx | `deploy/nginx/churchhub.conf`: public branding aliased; other `/media/` proxied to Django; bytes via internal `/internal-media/` + `X-Accel-Redirect` |
| Storage default | `FileSystemStorage` unless bucket env is set (`church_system/storage.py`) |

**Phase 1 fixed:** authentication-only serve is gone; object/tenant ACL + export-owner check exist for the Django path.

### 2.2 Is S3 actually enabled?

| Signal | Finding |
|--------|---------|
| Code | `build_storages()` switches to `storages.backends.s3boto3.S3Boto3Storage` when `AWS_STORAGE_BUCKET_NAME` or `S3_BUCKET` is non-empty **and** `django-storages` imports |
| Settings | `apply_s3_settings`: `AWS_DEFAULT_ACL = None`; `AWS_QUERYSTRING_AUTH` defaults **true** |
| Docs / `.env.example` | Optional; commented out |
| Tests | `church_system/tests_infra.py` asserts filesystem backend by default |

**Conclusion:** S3 is **optional / off by default**. Current production notes (`mychurch.zreta.com`) describe filesystem + Nginx. Residual risk activates **as soon as ops set a bucket** — then templates emit S3 URLs and `protected_media` still opens `Path(MEDIA_ROOT)` (broken for S3 objects).

### 2.3 Private media inventory (authorized prefixes)

| Prefix | Model / field | Handler | Notes |
|--------|---------------|---------|-------|
| `members/profile_pictures/` | `Member.profile_picture` | `_members_photo` | Portal self OR `view_members` + church scope |
| `records/` | `Record` images | `_record_image` | Portal self OR `view_member_records` + scope |
| `history/` | `History` images | `_history_image` | Same |
| `meetings/attachments/` | `MeetingAttachment.file` | `_meeting_attachment` | `view_meetings` or portal + `show_on_portal` |
| `welfare/cases/` | `WelfareCaseAttachment.file` | `_welfare_attachment` | Portal case member OR `view_welfare` |
| `announcements/` | `AnnouncementImage.image` | `_announcement_image` | Denomination FK required; audience/approver/creator rules |
| `exports/reports/` | `ReportExportJob.export_file` | `_export_file` | **Owner only** (`user=user`) |

Unknown prefixes → deny (`INV-DENY-01`). Platform users → deny private media (`user_may_access_media`).

### 2.4 Paths that bypass `protected_media` when storage URL ≠ `/media/`

**Mechanism:** Django `FieldFile.url` returns the storage backend URL. With filesystem + `MEDIA_URL=/media/`, that is still the Django gate. With S3Boto3Storage, `.url` is an absolute S3/custom-domain URL — **never hits** `protected_media`.

**Emitters (private — must remain gated):**

| Location | Field |
|----------|--------|
| `templates/members/detail.html`, `list.html`, `transfer_form.html` | `profile_picture.url` |
| `templates/includes/member_picker.html` | initial photo URL |
| `templates/portal/home.html`, `profile.html` | avatar |
| `templates/announcements/*.html`, `portal/announcement_detail.html` | `img.image.url` |
| `templates/announcements/upcoming_calendar.html` | member photo |
| `templates/meetings/detail.html` | `file.file.url` |
| `templates/remittance/welfare_case_detail.html` | `att.file.url` |
| `members/views.py` search JSON | `photo_url`: `profile_picture.url` |

**Public branding (must stay anonymous-OK):**

| Location | Field |
|----------|--------|
| Login / portal / navbar / `base.html` favicon | `site_logo`, `site_favicon`, `denomination_logo`, `tenant_logo` |
| `templates/accounts/institution_branding.html`, sitecontrol branding | denomination / platform logos under `*/branding/` |

**Broken when S3 on:** `protected_media._media_file` uses local `MEDIA_ROOT` only — cannot serve S3 keys even if clients used `/media/…`.

### 2.5 Proposed remediation (authorization-preserving S3)

**Recommended architecture (safest, preserves Phase 1 ACL):**

1. **Custom default storage** (e.g. `ChurchHubPrivateMediaStorage` wrapping S3 or filesystem):
   - For **private** keys: `.url` MUST return **relative** `/media/<key>` (never a public/guessable S3 URL).
   - For **public branding** prefixes only: may return CDN/S3 public URL **or** still `/media/…` served anonymously (prefer consistency with Nginx public aliases when on disk).
2. **`protected_media` delivery:**
   - After ACL: open via `default_storage.open(relative)` (works for FS and S3).
   - Optional: 302 to **short-lived signed GET** (`AWS_QUERYSTRING_AUTH`) **only after** `user_may_access_media` — never embed long-lived signed URLs in HTML.
   - Keep `X-Accel-Redirect` path for filesystem + Nginx only.
3. **Bucket policy:** deny public `s3:GetObject` on private prefixes; branding prefixes may be public-read if product chooses CDN logos.
4. **Preserve:** export-owner rule; public branding anonymous; 404 on deny; no platform-operator private-media browse.
5. **Do not:** set `AWS_DEFAULT_ACL=public-read` globally; do not disable query-string auth and rely on public buckets for private trees.

**Filesystem-only deployments:** still implement storage `.url` → `/media/` helper so templates stay correct if S3 is enabled later; fix `_deliver` to use storage API even when backend is FS (optional hardening).

### 2.6 Tests (CH-SEC-001)

- With mocked S3 backend: `FieldFile.url` for member photo starts with `/media/`, not `https://`.
- After ACL allow: deliver or signed redirect succeeds; deny → 404; no object bytes without ACL.
- Public branding anonymous 200; private unauth → login redirect.
- Export path: user A 404 on user B export key; owner OK.
- Announcement image still requires `Announcement.denomination` (Phase 2).

### 2.7 Migrations

None required unless a data migration renames keys (not proposed). Settings/storage class change only.

---

## 3. CH-SEC-L1 — Unanchored superadmin / all-tenant access

### 3.1 Authoritative contract

- **INV-TEN-18 / INV-TEN-02:** If `is_superadmin(user)` (or break-glass institution `is_superuser`) but `get_user_denomination(user)` is missing → `get_manageable_churches` MUST be **empty**. Fail-open “all churches” is forbidden.
- `User.clean()` already requires denomination or church for `OrgScopeLevel.DENOMINATION` (default for `SUPER_ADMIN`); **`save()` does not call `full_clean()`**.

### 3.2 Exact fail-open code

```text
permissions/scoping.py get_manageable_churches:
  is_superadmin(user):
    if user_denom: filter denomination
    else: return qs   # ← ALL churches (CH-SEC-L1)
  is_superuser and not platform:
    if user_denom: filter
    else: return qs   # ← ALL active churches
```

Same pattern in `get_manageable_users` for unanchored superadmin → all institution users.

### 3.3 Callers that inherit all-tenant scope when unanchored

High-impact consumers of `get_manageable_churches` (non-exhaustive; any church-owned query using this helper):

| Area | Examples |
|------|----------|
| Church context | `church_system/church_scope.py` (`get_active_church`, switch) |
| Members | `members/selectors.py`, `members/views.py`, services |
| Dashboard / reports | `dashboard/services.py`, `reports/selectors.py`, `reports/services.py` |
| Org | `organization/views.py`, `organization/selectors.py` |
| Remittance | `remittance/views.py`, `settlement_desk.py` |
| Assets / payroll | `assets/rbac.py`, `payroll/services.py` |
| Announcements | forms/services (church pickers) |
| Media ACL | `_church_in_scope` — **mitigated:** `user_may_access_media` already requires denomination first |
| Celery | `church_system/tasks.py` depreciation scope |

**Dashboard pending announcements** already fail-closed for unanchored superuser (`dashboard/selectors.py` — Phase 2/3 hardening). That does **not** fix `get_manageable_churches` itself.

### 3.4 Proposed remediation

1. **`get_manageable_churches`:** if `is_superadmin` or institution `is_superuser` and **no** `get_user_denomination(user)` → return `empty_churches()` (same as unauthenticated empty).
2. **`get_manageable_users`:** mirror — unanchored superadmin → empty (or self-only if product requires profile access; prefer empty + self via separate path).
3. **Persist path:** `User.save()` for non-platform users call `full_clean()` before save (or dedicated `save_user_validated` used by admin/forms/services) so unanchored `SUPER_ADMIN` cannot be persisted.
4. **Do not** invent a new “global institution superadmin” role. Platform lane remains `is_platform_user` + capabilities.
5. Inventory existing unanchored rows (ops SQL); quarantine assign denomination or deactivate — **do not** silently invent denomination from guesses.

### 3.5 Tests (CH-SEC-L1)

- Unanchored `SUPER_ADMIN` / `is_superuser`: `get_manageable_churches` empty; church switch / member list empty or 403.
- Anchored SUPER_ADMIN: only own denomination churches.
- `User` create/save without denom/church for DENOMINATION scope → `ValidationError`.
- Regression: dashboard pending still empty for unanchored (already tested).
- Media: unanchored still 404 private files (already).

### 3.6 Migrations

Optional **data** migration: list/count users with `role=SUPER_ADMIN`, `is_platform_user=False`, `church_id IS NULL`, `denomination_id IS NULL` — report only or set inactive. No automatic denomination assignment without business approval.

---

## 4. CH-SEC-009 — Platform stats & cross-denomination aggregates

### 4.1 Current behavior

| Function | Scope today | Exposed to |
|----------|-------------|------------|
| `sitecontrol.services.platform_stats()` | **Global** counts (churches, conferences, zones, districts, subscriptions, users, operators, plans, pending apps) | Any `CAP_VIEW` dashboard / ops views |
| `tenant_health_alerts()` | Global missing/suspended/expired subs; **church names** in over-limit list (up to 5) | Same |
| `organization_tree_summary()` | Global `church_count` | Control-room org views |
| Contrast | `filter_churches_for_operator` / `filter_subscriptions_for_operator` / `filter_audit_for_operator` | Used for **lists**, not for `platform_stats` |

Invariant §16 / test matrix item 13: **Scoped platform READONLY MUST NOT see other denominations’ church names or global counts; OWNER MAY see global.**

### 4.2 Business decision required (blocking product choice)

| Option | Behavior |
|--------|----------|
| **A (recommended, matches invariant)** | OWNER (and break-glass Django superuser on platform) → global KPIs. All other roles → stats/alerts filtered by `managed_denominations` / `filter_churches_for_operator`. Never leak unmanaged church names. |
| **B** | All `CAP_VIEW` operators see global SaaS KPIs by design (counts only, no names). **Rejects** current invariant wording — would require updating `SECURITY_AUTHORIZATION_INVARIANTS.md` before implement. |
| **C** | Split widgets: “My denominations” (scoped) + “Platform totals” (OWNER-only). |

Phase 4 implementation MUST NOT ship Option B without an explicit contract amendment.

### 4.3 Proposed remediation (assuming Option A)

1. `platform_stats(user)` / `tenant_health_alerts(user)` take the operator; apply denomination/church filters consistent with `filter_churches_for_operator`.
2. Over-limit alert: only churches in operator scope; never other tenants’ names.
3. Pending applications / subscriptions: reuse existing operator filters.
4. OWNER / global break-glass: unchanged global aggregates.
5. Update dashboard + any other `CAP_VIEW` consumer (`sitecontrol/views.py` dashboard ~105, setup/ops paths that call `platform_stats`).

### 4.4 Tests

- READONLY with `managed_denominations={A}`: counts exclude denom B; detail string has no denom B church names.
- OWNER: may see global totals.
- SUPPORT scoped: same as READONLY for stats (no unmanaged names).

### 4.5 Migrations

None.

---

## 5. Cross-check Phase 1–3 (regressions)

| Phase | Invariant / finding | Phase 4 interaction |
|-------|---------------------|---------------------|
| 1 Media ACL | INV-MED-01 on `/media/` | Must remain; S3 work must call same `user_may_access_media` |
| 1 MFA | INV-MFA-* | Untouched |
| 1 Remit/recon writes | INV-FIN-01/03/04 | Untouched |
| 2 Announcements | INV-ANN-01/03 | Media handler already uses `Announcement.denomination`; keep |
| 2 Pending dashboard | Fail-closed unanchored | Keep; L1 aligns underlying church helper |
| 3 Financial / SoD | INV-FIN-02, SOD, idempotency, settlement | Untouched |
| 3 Tenant church | INV-TEN-05 `full_clean` | Pattern to reuse for `User.save` |

**No Phase 1–3 regressions identified as introduced by baseline `71aa74c`.** Remaining §16 contradictions for Phase 4 scope: INV-MED-03 (S3), INV-TEN-02/18, INV-TEN-03 platform stats.

---

## 6. Implementation order

1. **CH-SEC-L1** — fail-closed `get_manageable_churches` / users + User persist validation (reduces blast radius everywhere).  
2. **CH-SEC-001** — storage `.url` + `protected_media` storage-backed deliver / post-ACL signed redirect; branding exception.  
3. **CH-SEC-009** — scoped platform stats/alerts after **business decision A/B/C**.

Dependencies: L1 before relying on media `_church_in_scope` for edge users; S3 work independent of 009; 009 needs product choice first.

---

## 7. Residual risks (after Phase 4)

- Historical unanchored SUPER_ADMIN rows until inventory/quarantine.
- Signed URL window (if used): shareable until expiry — keep TTL short (minutes).
- Public branding CDN still guessable by URL (accepted for logos).
- Nginx filesystem aliases for branding diverge from S3 branding strategy — document ops matrix.
- Out of scope: portal login enumeration (CH-SEC-010), admin activity-log delete, unaudited CSVs.

---

## 8. Explicit business decisions required

1. **Platform KPIs (CH-SEC-009):** Option **A** (OWNER global / others scoped — matches invariant), **B** (amend invariant), or **C** (split widgets)?  
2. **S3 private delivery (CH-SEC-001):** Prefer **proxy/stream through Django after ACL** vs **302 to short-lived signed URL after ACL** (both OK if `.url` never public)?  
3. **Unanchored SUPER_ADMIN data repair:** deactivate vs force denomination assignment (manual ops) — no automatic guess?

---

## 9. Definition of done (Phase 4 implement)

- [x] L1: unanchored institution superadmin/superuser → empty manageable churches; save rejects.  
- [x] Media: private `FieldFile.url` → `/media/…`; S3 objects not publicly listable via `.url`; ACL unchanged; branding public via gate; exports owner-only.  
- [x] Platform stats/alerts match Option A and tests.  
- [x] Focused tests green; findings register + invariants §16 updated.  
- [x] No silent historical deletes; no production migrate in design phase.

---

PHASE 4 DESIGN STATUS: IMPLEMENTED
