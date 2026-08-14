# ChurchHub Security Remediation Design

**Type:** Read-only design review (no application, config, database, or git changes)  
**Date:** 14 August 2026  
**Commit reviewed:** `8eb5730f91b18212e17f48b3550afa952492437b` (`main`)  
**Companions:** `docs/SECURITY_AUDIT_REPORT.md`, `docs/SECURITY_FINDINGS_REGISTER.md`, `docs/SECURITY_REMEDIATION_ROADMAP.md`  

This document designs how to fix confirmed P0/P1 findings. It does not implement them.

Every finding below was re-checked against source. Where the original audit was imprecise, the refinement is stated explicitly.

---

## Verification notes (audit vs source)

| Finding | Audit claim | Source verification |
|---------|-------------|---------------------|
| CH-SEC-001 | Any authenticated user can GET any non-branding `/media/` path | **Confirmed.** `protected_media()` (`church_system/media_views.py` 46–64) returns `_deliver()` after `is_authenticated` only. Tests lock this in (`church_system/tests_media_access.py` 77–82). |
| CH-SEC-002 | General announcements leak across denominations | **Confirmed, and broader.** `announcements_for_church_ids()` ORs `visibility="general"`. Additionally, `visible_announcements()` (`announcements/services.py` 116–117) assigns `scoped = qs` (the entire approved set) when `can_view_all_churches(user)` or `is_superadmin(user)` — hierarchy roles therefore see **church-scoped** announcements from other denominations, not only general ones. |
| CH-SEC-003 | MFA verify unthrottled | **Confirmed.** `LoginRateLimitMiddleware.LOGIN_PATHS` is only `/accounts/login` and `/portal/login`. Email OTP **send** is limited (3 / 15 min); **verify** is not. TOTP `valid_window=2` accepts five 30-second steps. |
| CH-SEC-004 | Tenant edit skips `Church.clean()` | **Confirmed.** `TenantChurchForm` exposes unrestricted `district`. `repo.save_church` → `Model.save()` without `full_clean()`. `Church.clean()` (159–171) would block cross-denomination moves if invoked. |
| CH-SEC-005 | Asset depreciation/disposal leave journals pending | **Confirmed.** Acquisition already calls `approve_module_journal`. Depreciation (`post_depreciation_entry` 376–417) and disposal (`post_disposal_to_ledger` 477–511) create CAPITAL journals, `validate_transaction_balance`, then update the register **without** `approve_module_journal` or `assert_working_day_allows_posting`. |
| CH-SEC-006 | Contribution recording has no idempotency | **Confirmed.** `record_member_contribution` calls `record_receipt` with no `FinancialIdempotencyKey`. `contributions/` has zero references to `claim_financial_idempotency`. |
| CH-SEC-007 | Remittance/recon use a read-oriented wrapper | **Confirmed, attacker refined.** `_finance_required` ORs `can_manage_finances` / `can_view_transactions` / `can_manage_receipts` / `can_manage_expenses`. `can_manage_reconciliation` is **imported in `transactions/views.py` and never used**. Default `SECRETARY` already has `manage_finances` (`permissions/registry.py` 198–202, `_ROLE_ALL_STAFF`), so requiring `can_manage_finances` on remittance would **not** stop a default secretary. The clear vertical escalation is **BOARD_MEMBER** (has `view_transactions`, not `manage_finances` / `manage_reconciliation`) and any override that grants only view. |
| CH-SEC-008 | Announcement detail IDOR for approvers | **Confirmed.** `get_announcement_detail_or_404(pk)` is global; `can_see` is true if `can_approve_announcements(user)` with no object scope. |
| CH-SEC-009 | Platform stats unscoped | **Confirmed.** `dashboard()` calls `platform_stats()` and `tenant_health_alerts()` with no operator argument. Recent lists **are** filtered via `filter_churches_for_operator` / `filter_audit_for_operator`. `READONLY` has `CAP_VIEW`. |

**Do not treat UUID opacity as a control.** Media paths use original `FileField` names under shared prefixes. Django may suffix `_1` on collision; names remain guessable.

---

## Shared architectural rule

ChurchHub already has the right layers for HTML modules: view authenticates → `can_*` / capability → church/denomination selector → service → repository.

The P0/P1 defects are places that **skip the selector** and authorize on:

- authentication alone (media),
- a capability flag without an object (announcement detail, platform aggregates),
- a wrapper that ORs read and write permissions (finance),
- `Model.save()` instead of `full_clean()` (tenant district),
- a satellite posting path that does not reuse `approve_module_journal` / working-day / idempotency.

Remediation should **reuse those existing primitives**, not invent a second RBAC system.

---

# CH-SEC-001 — Private media object- and tenant-level authorization

## A. Every mechanism that can serve, download, or display a private file

| Mechanism | Path | Authz today |
|-----------|------|-------------|
| Django `protected_media` | `GET /media/<path:path>` (`church_system/urls.py` 55) | Authenticated ⇒ deliver |
| Nginx `X-Accel-Redirect` | Django sets `X-Accel-Redirect: /internal-media/<rel>`; Nginx `location /internal-media/ { internal; alias MEDIA_ROOT }` | Relies entirely on Django having authorized |
| Nginx public aliases | `/media/platform/branding/`, `/media/denominations/branding/` | Anonymous by design (login logos) |
| Templates `{{ field.url }}` | Member photos, announcement images, meeting attachments, welfare files | URL is `/media/...` → same view |
| `reports.views.export_job_download` | `GET /reports/exports/<uuid>/download/` | **Owner-scoped** (`export_job_for_user`). Not the IDOR. The **same bytes** remain reachable via `/media/exports/reports/<filename>`. |
| In-memory CSV/PDF | payroll, assets CSV, contributions export, transaction reporting | Never hits MEDIA_ROOT. Out of CH-SEC-001. |
| Optional S3 (`church_system/storage.py`) | If `AWS_STORAGE_BUCKET_NAME` is set, `FileField.url` becomes an S3 URL, **not** `/media/` | `protected_media` uses local `Path(MEDIA_ROOT)` and would 404; templates would emit S3 URLs. `AWS_QUERYSTRING_AUTH` defaults true; `AWS_DEFAULT_ACL = None`. If query-string auth is disabled or the bucket is public, this is a **full bypass** of Django. Production at `mychurch.zreta.com` is filesystem + Nginx unless ops enabled S3. |
| Django admin | Break-glass `/admin/` can open related FileFields | Intended break-glass; still uses `.url` → `/media/` or S3 |
| Direct disk / misconfigured Nginx | Serving `MEDIA_ROOT` as a public alias | Not in repo config (`deploy/nginx/churchhub.conf` proxies `/media/` to Django). Live host must keep that. |

Middleware exemptions that **must not** be mistaken for authorization:

- `UserScopeMiddleware` exempts all `/media/` so platform operators are not bounced to `/platform/` (`sitecontrol/middleware.py` 27–29).
- `PermissionCacheMiddleware` exempts `/media/` so missing church assignment does not block bytes (`permissions/middleware.py` 21–23).
- `MfaEnforcementMiddleware` exempts **only branding** prefixes. Pending-MFA users cannot fetch private media until verified. Users who **do not** require MFA (default: most staff and all portal members) can.

## B. Models that own private media

| Prefix | Model | Tenant/owner link |
|--------|--------|-------------------|
| `members/profile_pictures/` | `members.Member.profile_picture` | `Member.church` |
| `records/` | `members.RecordImage.image` M2M from `Record` | `Record.church` / `Record.member`. **Image row has no church FK.** |
| `history/` | `members.HistoryImage.image` M2M from `History` | `History.church`. Same orphan-image problem. |
| `meetings/attachments/` | `meetings.MeetingAttachment.file` | `attachment.meeting.church` |
| `welfare/cases/%Y/%m/` | `remittance.WelfareCaseAttachment.file` | `attachment.case.church` |
| `announcements/` | `announcements.AnnouncementImage.image` | `image.announcement.church` **or** `announcement.visibility=="general"` (no church; denomination missing — CH-SEC-002) |
| `exports/reports/` | `reports.ReportExportJob.export_file` | `job.user` (owner). Church is only in `params` JSON, not a FK. |
| `platform/branding/`, `denominations/branding/` | `SiteSettings`, `Denomination.logo` | **Public.** Institution branding writes denomination logos here (`accounts.views.institution_branding`). |

No other `upload_to=` prefixes exist in current models.

## C. How ownership is represented

- SaaS wall: `Church.district.zone.conference.denomination`.
- Institution scope: `permissions.scoping.get_manageable_churches(user)` (denomination-bounded for superadmin **if** denomination is set).
- Portal: `request.user.member` and that member’s church.
- Report exports: job owner, not church FK.
- Record/History images: ownership is **only** via M2M parent. Unlinked files remain on disk with no row.

UUIDs are used as PKs on meetings/welfare/export jobs. **File names are not UUIDs.**

## D. URLs / views that retrieve files

1. `protected_media` — the choke point for all `MEDIA_URL` links.
2. `reports:export_job_download` — authorized duplicate channel for export bytes.
3. Nginx branding aliases — public.
4. (Conditional) S3 object URLs from `FileField.url`.

There is no DRF media API.

## E. Where authorization is enforced today

| Layer | Private media |
|-------|----------------|
| URL | Route exists; no permission decorator |
| View | `is_authenticated` only |
| Service | None |
| Queryset | None (path is not loaded through a model) |
| Storage | Filesystem/Nginx `internal` — confidentiality depends on Django |
| Middleware | MFA for privileged roles only; scope middleware **exempts** `/media/` |

## F. Bypass paths a naive fix would miss

1. **Prefix not in the allow-map** — deny-by-default is mandatory. Unknown prefixes must 404.
2. **Orphan `RecordImage` / `HistoryImage`** after M2M unlink — lookup by `image`/`file` name must still find a parent or deny.
3. **`exports/reports/` via `/media/`** after locking down `export_job_download` only.
4. **Announcement images for `visibility=general`** until CH-SEC-002 adds a denomination owner (otherwise “any authenticated user in any tenant” remains the only possible rule).
5. **Platform operators** (`READONLY`, `SUPPORT`) hitting `/media/` because `UserScopeMiddleware` exempts it — they must be scoped with `filter_churches_for_operator` / owner, not “platform ⇒ all files”.
6. **Portal members** — authenticated, usually no MFA, church-scoped for HTML, unconstrained for media.
7. **S3 `.url`** if object storage is enabled later — templates must stop emitting raw storage URLs for private fields.
8. **Nginx `/internal-media/` losing `internal`** on the live host — ops check, not app code.
9. **Filename collision suffixes** (`photo_1.jpg`) — authorization by DB field value (`name=`), not string prefix guessing.
10. **Case / slash normalization** — keep using `normalize_media_relative_path`; authorize the normalized relative name that Django stored on the field.

## G. Why existing tests permit cross-tenant access

`ProtectedMediaViewTests.test_authenticated_can_fetch_private_media` (77–82):

- Creates a **bare** `User` (`create_user(username="mediauser", ...)`) with **no church, no denomination, no member**.
- Writes a JPEG under `members/profile_pictures/p.jpg` that is **not attached to any Member**.
- Asserts HTTP 200 and the file bytes.

That test encodes “login is the ACL.” It never creates two denominations. A correct suite must fail that assertion and add two-tenant fixtures.

`test_x_accel_redirect_header` (89–102) likewise logs in an unscoped user and expects 200 + header. After the fix, X-Accel is only set **after** object authorization.

Helpers tests (traversal + public branding) remain valid.

## H. Centralized authorization model

**Deny by default.** Public prefixes stay anonymous. Everything else:

```
relative_path
  → find owning row(s) by stored FileField.name == relative_path
  → resolve church / denomination / owner user
  → decide allow using existing scope helpers
  → 404 on deny (do not 403 — reduces path enumeration)
```

Suggested decision table:

| Prefix | Lookup | Allow if |
|--------|--------|----------|
| Public branding | none | always |
| `members/profile_pictures/` | `Member.objects.filter(profile_picture=path)` | staff: church in `get_manageable_churches`; portal: `user.member_id == member.pk` **or** same church **and** `can_view_members` |
| `records/` | `Record.objects.filter(images__image=path)` | church in manageable set; portal: own member record only |
| `history/` | `History.objects.filter(images__image=path)` | same |
| `meetings/attachments/` | `MeetingAttachment.objects.filter(file=path)` | church in manageable set; portal only if meeting is portal-visible **and** user’s church matches |
| `welfare/cases/` | `WelfareCaseAttachment.objects.filter(file=path)` | staff with welfare view/manage **and** church in scope; portal: attachment’s case.member == user.member |
| `announcements/` | `AnnouncementImage.objects.filter(image=path)` | image’s announcement is in `visible_announcements(user)` **or** user is creator / object-scoped approver (reuse CH-SEC-002/008 helpers). Do not use global `can_approve_announcements`. |
| `exports/reports/` | `ReportExportJob.objects.filter(export_file=path)` | `job.user_id == request.user.id` only (match `export_job_for_user`). Platform operators do not get other tenants’ exports via media. |
| anything else | — | deny |

Multiple rows sharing one stored name (unlikely but possible if copied): **allow only if at least one row authorizes**; do not leak because another row exists.

Prefer adding `upload_to` callables that store `{prefix}/{uuid}{ext}` going forward so names are not guessable. That is defense in depth, **not** a substitute for object checks. Existing files keep old names; authorization must work for both.

## I. Where the control should live

| Layer | Role |
|-------|------|
| **Dedicated media-access service** (new `church_system/media_authorization.py`) | Single map prefix → lookup → `user_may_access_media(user, relative_path) -> bool`. This is the source of truth. |
| **View** `protected_media` | Normalize path, public short-circuit, then call the service; 404 or `_deliver`. |
| **Querysets inside the service** | All lookups church/owner scoped via existing helpers — do not `Member.objects.get(id=...)`. |
| **Storage** | Keep Nginx `internal` + optional short-lived S3 URLs **issued only after** the service allows. Do not put tenant logic in the storage backend (it has no `request.user`). |
| **Middleware** | Do **not** implement object ACL in middleware (no model context). Keep `/media/` scope-exempt so the view can run. Optionally **stop** treating private `/media/` as MFA-exempt for branding-only (already the case). |
| **Templates** | Continue using `.url` **as long as** `MEDIA_URL` is `/media/` and Django storage is filesystem. If S3 is enabled, wrap private fields so `.url` is not a public object URL. |

**Rejected:** `if request.user.is_authenticated`. That is the vulnerability.

**Rejected:** “staff vs member role is enough.” Portal members and `READONLY` operators would still cross tenants.

**Rejected:** UUID filenames alone. Guessing becomes harder; leaked HTML still contains the URL.

---

### CH-SEC-001 — 13-point remediation plan

1. **Current architecture:** One view, path sanitization, public-prefix allowlist, authn gate, X-Accel.
2. **Vulnerable path:** Login as Church A portal member or BOARD_MEMBER → `GET /media/members/profile_pictures/<name>` for Church B → 200.
3. **Root cause:** Media plane is global; authorization was never bound to the owning model.
4. **Proposed secure architecture:** Central `user_may_access_media` + deny-by-default prefix map; 404; owner-only exports; later UUID `upload_to`.
5. **Files:** `church_system/media_authorization.py` (new), `church_system/media_views.py`, `church_system/tests_media_access.py`, optionally `church_system/uploads.py` / model `upload_to` callables, `docs` security pages.
6. **Functions:** `protected_media`, new `user_may_access_media` / per-prefix resolvers; rewrite `test_authenticated_can_fetch_private_media`.
7. **Database:** None required for the ACL. Optional later: UUID filenames (no schema). Optional `ReportExportJob.church` FK is **not** required if owner-only remains the rule.
8. **API:** None (no DRF). Behavior change: 200 → 404 for unauthorized `/media/` GET.
9. **Backward compatibility:** Legitimate in-app `<img src="{{ member.profile_picture.url }}">` keeps working for authorized users. Bookmarks to other churches’ files break (desired). Platform support viewing a tenant file via raw URL **stops working** unless they impersonate or we add an explicit platform capability + denomination scope — **do not** restore “platform ⇒ all files”.
10. **Regression tests:** Two denominations, two churches, two members; cross-tenant 404 for photo, welfare file, meeting attachment, announcement image, export file; same-church staff 200; portal self-photo 200; other member same church per `can_view_members`; anonymous branding 200; anonymous private 302; traversal 404; unmapped prefix 404; X-Accel only after allow.
11. **Migration risks:** None for ACL. UUID `upload_to` is additive.
12. **Deployment risks:** If the map misses a prefix used in production, those files 404 for everyone (fail closed). Inventory `MEDIA_ROOT` prefixes before deploy. Confirm live Nginx still uses `internal` on `/internal-media/`.
13. **Rollback:** Revert the view/service; tests will fail closed-to-open — keep the deny tests on the branch.

**Complexity:** HIGH (mapping + portal vs staff vs platform + orphans).  
**Auth required to exploit:** Yes. **Cross-tenant:** Yes.

---

# CH-SEC-003 — MFA verification throttling

## A. Full verification flow (source)

```
POST /accounts/login/  (or portal login)
  LoginRateLimitMiddleware  ← counts failures here only
  MfaAwareLoginMixin.form_valid
    if user_requires_mfa and mfa_enabled:
      if trusted-device cookie valid → login() + mark_mfa_verified
      else session[mfa_pending_user_id] = pk   ← user is NOT logged in yet
           redirect /accounts/mfa/verify/
    if requires MFA but not enrolled → login() with mfa_verified=False → enroll
    else login() + mark_mfa_verified

GET/POST /accounts/mfa/verify/
  _challenge_user = request.user OR pending session user
  trusted device → _complete_mfa_login
  POST action=send_email → send_mfa_email_otp (send counter in cache)
  POST token → verify_user_mfa:
      TOTP (window=2) OR email OTP OR consume recovery code
  success → login() if needed, mark_mfa_verified, optional trusted-device cookie
```

`MfaEnforcementMiddleware` redirects pending (not logged in) users to verify, except exempt prefixes.

## B. Where attempts are counted

| Event | Counted? |
|-------|----------|
| Password failure | Yes — `LoginRateLimitMiddleware` (IP + identifier) |
| MFA verify failure | **No** |
| MFA enroll TOTP failure | **No** |
| Email OTP send | Yes — `EMAIL_OTP_SEND_LIMIT = 3` / 900s per **user pk** |
| Email OTP verify failure | **No** |
| Recovery code failure | **No** (success consumes; failure is unlimited) |
| TOTP success | No used-code cache (same code reusable for ~150s) |

## C. Throttle dimensions today

Absent for verify. Send is **per-user** cache key `mfa_email_otp_send:{pk}` only (not per-IP).

## D. Challenge expiry

- Email OTP: 600s cache TTL; overwritten on resend.
- TOTP: rolling 30s; `valid_window=2` ⇒ current ± 2 steps.
- Pending session: lives as long as the session (`SESSION_COOKIE_AGE` 4h, or `SiteSettings.session_timeout_minutes` once authenticated — pending user is **not** authenticated, so Django session expiry for anonymous+pending applies).
- Recovery codes: until consumed.
- Trusted device: 30 days.

## E. Success retires the challenge?

- Email OTP: `cache.delete` on success. **Yes.**
- TOTP: not retired; valid until the window elapses.
- Recovery: consumed. **Yes.**
- Pending session keys popped in `mark_mfa_verified`. **Yes.**
- Failed verify does not invalidate the pending user id (correct).

## F. Replay

- Capture a TOTP and replay within ~150s: **works** (standard TOTP; mitigate with a short “last used step” cache per user).
- Email OTP replay after success: **blocked**.
- Recovery replay: **blocked**.
- Script 000000–999999 against email OTP in 10 minutes: **practical** (~1e6, unthrottled). This is the HIGH issue.

## G. Safest remediation (do not lock out treasurers)

Do **not** only add `/accounts/mfa` to `LOGIN_PATHS` with the same identifier lockout: MFA POSTs do not submit a username; the user id is in the session. A naive path add would key on IP only or on empty identifier.

**Design:**

1. New helpers in `accounts/mfa.py` (not only middleware):  
   `mfa_verify_allowed(user, ip) -> (ok, retry_after)`  
   `record_mfa_failure(user, ip)` / `clear_mfa_failures(user, ip)` on success.
2. Keys: `mfa_verify_fail:user:{pk}` **and** `mfa_verify_fail:ip:{ip}`. Both must allow. User key stops targeted OTP brute force; IP key stops rotating-user spraying from one host.
3. Limits: align with staff login (SiteSettings lockout, default 5) for the **user** key; slightly higher for IP (e.g. 20) so a NAT of pastors is not locked together. After lock, return the same generic “Invalid code” **plus** HTTP 429 or a form error “Too many attempts; try in N minutes” — do not reveal remaining guesses.
4. Apply to: `mfa_verify` POST (all actions except maybe GET), `mfa_send_email` (already has send cap; also count IP), `mfa_enroll` POST token verify.
5. On success: clear user+IP failure counters; keep email OTP delete; add TOTP timestep cache `mfa_totp_used:{user}:{step}` TTL 120s to block immediate replay.
6. Keep `hmac.compare_digest` on email OTP / recovery hashes.
7. Do **not** reduce `valid_window` to 0 without NTP confidence (comment in `verify_totp` already cites VPS clock skew). Window=1 is an optional later hardening.
8. Trusted-device skip stays; it is cookie + hashed DB token. Throttling trusted-device GETs is unnecessary if token entropy stays `token_urlsafe(32)`.

**Do not** invalidate the pending session on first failure (UX + no extra account enumeration).

---

### CH-SEC-003 — 13-point plan

1. **Current:** Password gated; MFA challenge unlimited; email send limited.
2. **Vulnerable path:** Phished password → pending session → loop POST `token=NNNNNN` on `/accounts/mfa/verify/`.
3. **Root cause:** Rate limiter never attached to the second factor.
4. **Proposed:** Per-user + per-IP cache lockout in `verify_user_mfa` callers; TOTP used-step cache; generic errors.
5. **Files:** `accounts/mfa.py`, `accounts/mfa_views.py`, `sitecontrol/middleware.py` (optional path note / reuse cache helpers), MFA tests (new).
6. **Functions:** `verify_user_mfa` / `mfa_verify` / `mfa_enroll` / `send_mfa_email_otp`; new fail-counter helpers.
7. **Database:** None (cache/Redis). Optional later: persist lockouts if cache flush must not reset MFA brute-force state — not required if Redis is the session/cache store already used for login limits.
8. **API:** None. UX: 429 or form error after N failures.
9. **Compatibility:** Legitimate users who mistype 4 times then succeed still work if N≥5. NAT: IP limit higher than user limit.
10. **Tests:** N failures then lock; valid code during lock rejected; success clears lock; email send still capped; enroll locked similarly; login limiter still does not need to parse MFA tokens.
11. **Migration:** None.
12. **Deploy:** Redis must be up (already required in production validator). Cache flush resets counters (same as login limiter).
13. **Rollback:** Revert helpers; users regain unlimited retries (the vulnerability).

**Complexity:** LOW–MEDIUM.  
**Auth:** Password + pending session. **Cross-tenant:** No.

---

# Finance / remittance / reconciliation (CH-SEC-007) — request traces

## Wrapper under review

```83:94:transactions/views.py
def _finance_required(view_func):
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not (
            can_manage_finances(request.user)
            or can_view_transactions(request.user)
            or can_manage_receipts(request.user)
            or can_manage_expenses(request.user)
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped
```

This wrapper is appropriate for **read** views (`transaction_list`, `audit_log`, `pending_approvals` GET). It is not appropriate for **writes**.

`can_manage_reconciliation` is imported and unused — the intended write gate already exists in `permissions.checks`.

Related pattern (not P1 unless product wants it): `ledger_finance_required` ORs `view_ledger` with `manage_ledger_entries` and wraps **posting** views. Treat as a follow-on of the same “read wrapper on write” bug class.

Default role facts (must drive the design, not slogans):

| Permission | Default roles |
|------------|----------------|
| `view_transactions` | `_ROLE_ALL_STAFF` **+ BOARD_MEMBER** |
| `manage_finances` | `_ROLE_ALL_STAFF` (includes SECRETARY, TREASURY, LOCAL_PASTOR, hierarchy) **not BOARD_MEMBER** |
| `manage_expenses` / `manage_receipts` | `_ROLE_ALL_STAFF` |
| `manage_reconciliation` | `_ROLE_TREASURY_OPS` + LOCAL_PASTOR + DISTRICT_PASTOR |
| `finalize_reconciliation` | `_ROLE_LEADERSHIP` + TREASURY |
| `approve_transactions` | `_ROLE_LEADERSHIP` |

### Trace 1 — District remittance POST

| Step | What happens |
|------|----------------|
| URL | `POST /transactions/remittance/` (`transactions:record_remittance`) |
| Auth | `_finance_required` → login + OR of four perms |
| Permission (intended) | Create: `can_manage_finances` (or a dedicated remittance-pay permission — **none exists**). Approve: `can_approve_transactions` on a later POST. |
| Permission (actual) | Any of the four, including **view-only**. |
| Tenant / org | `require_church(request)` — active church in session, already scoped. Not cross-tenant. |
| Maker/checker | Service creates a **pending** TRANSFER (`record_district_remittance`). Creator cannot self-approve (`approve_transaction` 861–862). SoD holds on **approve**, not on **create**. |
| Business date | `resolve_transaction_date` + `assert_period_open` + `assert_working_day_allows_posting` inside the service. **OK.** |
| Atomic | `@db_transaction.atomic` on the service. |
| Locking | Duplicate month check is a queryset on `FinancialAuditLog` **without** `select_for_update` (CH-SEC-L3). Idempotency key claimed first (CH-SEC-013 incomplete-key reuse). |
| Audit | Service writes `FinancialAuditLog` REMIT. |
| State | Pending until leadership approves; cutoff marked transferred only on approve. |

**Product decision:** If secretaries are supposed to **initiate** remittance, keep `can_manage_finances` (they already have it). The security fix is blocking **BOARD_MEMBER / view-only**. Do not advertise “secretaries cannot remit” unless product also removes `manage_finances` from SECRETARY.

### Trace 2 — Bank reconciliation create

| Step | Detail |
|------|--------|
| URL | `POST /transactions/reconciliation/new/` (`reconciliation_create`) |
| Auth | `_finance_required` |
| Permission (intended) | `can_manage_reconciliation` |
| Permission (actual) | view OR receipts OR expenses OR manage_finances |
| Tenant | `require_church`; `BankReconciliationForm(church=...)`; service checks `bank_account.church_id == church.pk` |
| Maker/checker | None on create. Finalize is separate. |
| Business date | Statement date from form; no working-day gate (worksheet, not GL post). Acceptable. |
| Atomic | Yes. |
| Audit | `_log_audit` CREATE. |
| State | `is_reconciled=False` |

### Trace 3 — Reconciliation match (WRITE on a GET-capable view)

| Step | Detail |
|------|--------|
| URL | `POST /transactions/reconciliation/<pk>/` action=`match` |
| Auth | `_finance_required` on `reconciliation_detail` (also used for GET) |
| Permission (intended) | `can_manage_reconciliation` |
| Permission (actual) | same OR wrapper; **finalize** correctly checks `can_finalize_reconciliation` |
| Object | `selectors.reconciliation_for_request` (church-scoped) |
| Audit | **`update_reconciliation_matches` does not write FinancialAuditLog** |
| State | Refuses if `is_reconciled` |

This is the textbook “read view that accepts POST.” Split GET/POST permissions.

### Trace 4 — Finalize (already stricter)

POST action=`finalize` requires `can_finalize_reconciliation`. Keep.

---

### CH-SEC-007 — 13-point plan

1. **Current:** One OR-wrapper for list/report **and** remittance/recon mutations.
2. **Vulnerable path:** BOARD_MEMBER (or view-only override) POST remittance or recon match in their church.
3. **Root cause:** View permission treated as mutate; unused `can_manage_reconciliation`.
4. **Proposed:**  
   - Remittance GET+POST: `@login_required` + `can_manage_finances` (or new `record_district_remittance` implied by manage_finances).  
   - Recon list GET: `can_view_reconciliation` OR manage/finalize.  
   - Recon create + match POST: `can_manage_reconciliation`.  
   - Finalize: keep `can_finalize_reconciliation`.  
   - Add audit log on match.  
   - Do not reuse `_finance_required` on any POST that creates GL or recon rows.
5. **Files:** `transactions/views.py`, `transactions/urls.py` (if split), `church_system/navigation.py` (already closer to the right remittance predicate), tests.
6. **Functions:** `_finance_required` (narrow or split into `_finance_view_required` / `_finance_mutate_required`), `record_remittance_view`, `reconciliation_create`, `reconciliation_detail`, `update_reconciliation_matches`.
7. **Database:** None.
8. **API:** None. Same HTML URLs; 403 for view-only POST.
9. **Compatibility:** Default SECRETARY/TREASURY remittance **unchanged** if gate is `can_manage_finances`. BOARD_MEMBER recon matching **stops** (desired). Custom roles that only had view will lose write (desired). Document in changelog.
10. **Tests:** User with only `view_transactions` → 403 remittance POST, 403 recon create, 403 match; 200 recon list. User with `manage_reconciliation` but not finalize → match OK, finalize 403. Treasury with manage_finances → remittance 200/302 success pending.
11. **Migration:** None. Optional data: none.
12. **Deploy:** No downtime. Train board members who used match-by-accident.
13. **Rollback:** Restore wrapper; re-opens the hole.

**Complexity:** LOW.  
**Auth:** Yes. **Cross-tenant:** No.

---

# CH-SEC-002 + CH-SEC-008 — Announcement tenant isolation

## Current architecture

- `Announcement.church` nullable; `visibility=general` **forces `church=None`** in `clean()` and `save()`.
- **No `denomination` FK.**
- Selectors OR all general rows into every church-id filter.
- `visible_announcements`: hierarchy `view_all_churches` / institution superadmin → **unfiltered approved queryset** (cross-tenant church announcements too).
- `announcement_detail`: global PK fetch; `can_approve_announcements` without `can_approve_announcement(user, obj)`.

Create-time for general: `is_top_level_approver` only — that is per-user hierarchy, still not denomination-tagged on the row.

## Vulnerable paths

1. Church clerk in denom B sees denom A’s approved general titles/bodies in the list and portal.
2. Conference admin in denom A with `view_all_churches` sees denom B **church** announcements.
3. Any user with `approve_announcements` opens `/announcements/<uuid>/` for a pending item in another denomination (CH-SEC-008). Images then load via `/media/announcements/...` (CH-SEC-001).

## Root cause

Tenant identity for “conference-wide” content was modeled as `church=NULL` instead of `denomination_id=...`. List/detail then fail closed to “global.”

## Proposed secure architecture

1. Add `Announcement.denomination` FK (`null=True` only for a short backfill).  
   - `visibility=church` ⇒ denomination = `church.conference.denomination` (set in `clean()` / service).  
   - `visibility=general` ⇒ `church=None`, **denomination required**.
2. Backfill: church rows from `church.district.zone.conference.denomination`; general rows from `created_by` denomination / first manageable denomination; **quarantine** rows that cannot be attributed (exclude from all feeds until an operator assigns).
3. Replace `announcements_for_church_ids` with:  
   `(church_id ∈ scoped_ids) OR (visibility=general AND denomination_id = user_denomination)`.  
   Never `OR visibility=general` alone.
4. Remove `scoped = qs` for `can_view_all_churches`. Superadmin/hierarchy still use `get_manageable_churches` (already denomination-bounded when `get_user_denomination` is set). If L1 unanchored superadmin exists, media/announcements inherit that bug — fix L1 on save, do not special-case “all announcements.”
5. `announcement_detail`: load from `visible_announcements | my_announcements | pending_for_user` union, or `get_object_or_404` after `can_approve_announcement(user, obj)` / creator check. **Never** `can_approve_announcements` alone.
6. Media map (CH-SEC-001) must call the same visibility helper so images cannot bypass the list.

Prefer the FK over “forbid church-less rows.” Product explicitly wants general/conference-wide posts (`is_top_level_approver`).

### 13-point extras

5. **Files:** `announcements/models.py`, new migration, `selectors.py`, `services.py`, `views.py`, `forms.py`, portal announcement views if they reuse selectors, tests, `docs/AI_CONTEXT` / module spec.
6. **Functions:** `visible_announcements`, `announcements_for_church_ids`, `announcements_for_church`, `announcement_detail`, `create` path that currently sets `church=None`.
7. **Database:** Additive FK + index `(denomination, visibility, status)`. Data migration required. **Not** dropping `church`.
8. **API:** None. Feeds shrink for users who were incorrectly seeing foreign rows.
9. **Compatibility:** General posts remain; they become denomination-wide. Cross-tenant readers lose them (desired).
10. **Tests:** Two denoms; general in A invisible in B; church announcement in A invisible to B clerk; B approver 404 on A pending PK; A top-level approver sees A general; media 404 for B user on A image.
11. **Migration risks:** Orphan general rows (creator left / no denom) — quarantine, do not attach to a random denomination. Downtime: none if additive + default null then backfill then require in a follow-up migration (two-step).
12. **Deploy:** Run data migration; smoke portal + staff feeds.
13. **Rollback:** Reverse migration only if the follow-up `null=False` has not run; keeping the FK nullable is safe rollback of filtering code.

**Complexity:** MEDIUM (schema + backfill). CH-SEC-008 is LOW if done in the same detail queryset change.

---

# CH-SEC-009 — Platform dashboard statistics isolation

Roadmap listed this as P2. Isolation class is the same as CH-SEC-002 (scoped operator, global aggregate). Include it in the **P1 isolation batch** (user-requested focus). It is MEDIUM impact (counts + up to five church **names**), not file/PII dump.

## Current

`dashboard()` (`sitecontrol/views.py` 102–106): `platform_stats()` and `tenant_health_alerts()` take **no user**. `platform_stats()` uses global `selectors.church_count()`, `active_institution_user_count()`, etc. Over-limit loop (`services.py` 757–768) appends `sub.church.name` for **every** active subscription.

Lists on the same page **are** operator-filtered. The KPI cards and alert text are not.

`READONLY` / `SUPPORT` / `BILLING` with `managed_denominations` still have `CAP_VIEW`. Owners/superusers **should** see global stats (`operator_has_global_access`).

## Proposed

- Change signatures: `platform_stats(user)`, `tenant_health_alerts(user)`.
- When `operator_has_global_access(user)`: current behavior.
- Else: counts via `filter_churches_for_operator`, subscriptions via `filter_subscriptions_for_operator`, applications via denomination filter, over-limit names only from scoped churches.
- Pending applications: reuse whatever selector the application list already uses for operators.

### 13-point extras

5. **Files:** `sitecontrol/services.py`, `sitecontrol/views.py`, `sitecontrol/selectors.py` (count helpers), tests.
6. **Functions:** `platform_stats`, `tenant_health_alerts`, `dashboard`.
7. **Database:** None.
8. **API:** None.
9. **Compatibility:** OWNER unchanged. Scoped operators see smaller numbers (desired).
10. **Tests:** Operator limited to denom A: stats.churches == A’s count; alert detail must not contain church B’s name; owner sees both.
11. **Migration:** None.
12. **Deploy:** None.
13. **Rollback:** Revert service signatures.

**Complexity:** LOW.

---

# Remaining confirmed HIGH (P1)

## CH-SEC-004 — Tenant district reassignment

1. **Current:** `tenant_edit` loads church via `church_tenant_access_qs()` (all churches) then `_require_tenant_access` on **source** denomination. Form `district` queryset is unrestricted ModelForm FK. Persist: `form.save(commit=False)` + `repo.save_church` → `Church.save()` **no `full_clean()`**.
2. **Path:** SUPPORT/BILLING (`CAP_MANAGE_TENANTS`) POST a district PK from another denomination.
3. **Root cause:** Validation lives in `Church.clean()`; this write path never calls it; destination not re-checked with `operator_can_access_denomination`.
4. **Proposed:** Constrain `TenantChurchForm.__init__` district queryset to districts in `get_operator_denominations(user)` (owners: all). `save_church`: `full_clean()` before save. After assign, `_require_tenant_access` on the **new** conference denomination (reject if operator cannot access destination). Do not use “transfer workflow” here — cross-denomination remains forbidden.
5. **Files:** `sitecontrol/forms.py` (`TenantChurchForm`), `sitecontrol/repositories.py` (`save_model` / `save_church`), `sitecontrol/views.py` `tenant_edit`.
6. **Functions:** as above. Prefer `full_clean()` in `save_church` so other callers cannot skip it.
7. **Database:** None.
8. **API:** None.
9. **Compatibility:** Same-denomination district moves still work. Cross-denomination POSTs error.
10. **Tests:** Operator A cannot set district in denom B; church.district unchanged; `ValidationError` surfaces as form/flash; owner still cannot cross denominations (model rule).
11. **Migration:** None.
12. **Deploy:** None.
13. **Rollback:** Revert form/repo.

**Risk of `full_clean()` on all `save_church`:** other platform edits might trip unrelated model validation. Safer: `save_church(..., *, validate=True)` used by tenant_edit first; then expand.

**Complexity:** LOW.

## CH-SEC-005 — Asset journals

1. **Current:** Acquisition: `approve_module_journal` after balance check. Depreciation/disposal: create CAPITAL, balance, update asset **pending**. Period open only; no working day. Disposal has no SoD (any `manage_assets` user).
2. **Path:** Post depreciation on a closed working day inside an unlocked month; register NBV changes; GL stays pending.
3. **Root cause:** Satellite path did not reuse posting primitive.
4. **Proposed:** After `validate_transaction_balance`, call `assert_working_day_allows_posting(church, period_date)` and `approve_module_journal(trx, user)`. If still PENDING (no distinct checker), **do not** update `accumulated_depreciation` / `DISPOSED` — leave a pending journal and a pending depreciation draft, **or** refuse with the same AssetError acquisition uses (299–302). Prefer refuse: register and GL stay consistent. SoD on dispose: `user.id != asset.created_by_id` or require `can_approve_transactions` for the GL step.
5. **Files:** `assets/services.py` (`post_depreciation_entry`, `post_disposal_to_ledger`, `dispose_asset`), assets tests.
6. **Functions:** those three; reuse `approve_module_journal`, `assert_working_day_allows_posting`.
7. **Database:** None required. Existing pending CAPITAL rows from past depreciation need an **ops/data** decision (approve in-app vs leave) — not a schema change. Document in runbook.
8. **API:** None.
9. **Compatibility:** Same-user depreciation may start failing (desired SoD). Month-end jobs (`run_monthly_depreciation` / Celery) must run as a checker distinct from `created_by` or pass a system checker — **design the Celery user carefully** or journals stay pending and the register will not update (fail closed).
10. **Tests:** Closed working day raises; success ⇒ `approval_status=APPROVED` and `locked=True`; register amount matches; second post same period still unique; dispose by creator without checker does not mark DISPOSED.
11. **Migration:** None. Historical pending CAPITAL: financial review.
12. **Deploy:** Celery beat depreciation must use a user that can pass SoD or depreciation silently skips register updates — **test in staging**.
13. **Rollback:** Revert service; register may again diverge.

**Complexity:** MEDIUM (Celery/SoD interaction).

## CH-SEC-006 — Contribution idempotency

1. **Current:** `campaign_record_contribution` POST → `record_member_contribution` → `record_receipt` (GL path with period/working-day/SoD on approve as implemented in `record_receipt`). No key. Bulk and import call the same function.
2. **Path:** Double-click or replay POST → two receipts + two `MemberContribution` rows.
3. **Root cause:** Feature never wired to `claim_financial_idempotency`.
4. **Proposed:** View generates a hidden idempotency key (campaign, member, date, amount, nonce) like remittance. Service claims key action `"CONTRIBUTION"` before `record_receipt`, completes after create. Bulk: one key per line. Import: stable key from row identity. Optional unique constraint on `(campaign, member, contribution_date, amount, transaction)` is **not** sufficient (legitimate two gifts same day same amount). Prefer client nonce + server claim.
5. **Files:** `contributions/views.py`, `contributions/services.py`, templates with the form, `transactions/idempotency.py` (reuse).
6. **Functions:** `record_member_contribution`, `record_bulk_contributions`, import helper, `campaign_record_contribution`.
7. **Database:** None if using existing `FinancialIdempotencyKey`. Optional later unique on key table already exists per church/user/action/key.
8. **API:** Hidden field on HTML form.
9. **Compatibility:** Old tabs without a key fail closed (`MissingIdempotencyKey`) — same as receipts. Refresh the page.
10. **Tests:** Two identical POSTs with same key → one contribution; different nonce → two (legitimate). Import replay does not duplicate.
11. **Migration:** None.
12. **Deploy:** None.
13. **Rollback:** Revert; duplicates return.

**Also:** CH-SEC-013 (incomplete key reuse) will undermine this if not fixed soon. **Implement contribution claim using `select_for_update` on the key row** (small extra in the same PR or immediately after). That simultaneously hardens remittance/receipts.

**Complexity:** LOW–MEDIUM.

---

# Dependency graphs

## Media (CH-SEC-001)

```
CH-SEC-001
  ↓
church_system/media_authorization.py  (deny-by-default map)
  ↓
protected_media + (optional) S3 signed URL helper
  ↓
Rewrite tests_media_access.py  (cross-tenant deny)
  ↓
Announcement image rule depends on CH-SEC-002 visibility helper
  ↓
UUID upload_to (optional, after ACL)
```

Do **not** ship UUID filenames before the ACL — it only shuffles paths.

## MFA (CH-SEC-003)

```
CH-SEC-003
  ↓
accounts/mfa.py failure counters + TOTP step cache
  ↓
mfa_verify / mfa_enroll / mfa_send_email
  ↓
MFA lockout tests
```

Independent of media. Can land in parallel.

## Financial authorization (CH-SEC-007)

```
CH-SEC-007
  ↓
Split _finance_required into view vs mutate
  ↓
record_remittance_view → can_manage_finances
reconciliation_create / match → can_manage_reconciliation
  ↓
audit on match
  ↓
403 tests for BOARD_MEMBER / view-only
  ↓
(follow-on) ledger_finance_required same split
```

Independent of media. Same “permission OR” lesson as announcement detail.

## Isolation batch (CH-SEC-002, 008, 009, 004)

```
get_user_denomination / filter_churches_for_operator / Church.clean
        ↓
CH-SEC-002 denomination FK + selector rewrite ──┬── CH-SEC-008 detail queryset
        ↓                                       └── CH-SEC-001 announcement images
CH-SEC-009 platform_stats(user)
CH-SEC-004 form queryset + full_clean  (independent, same “operator scope” helpers)
```

## Asset + contribution integrity

```
approve_module_journal + assert_working_day   ← already used by acquisition / receipts
        ↓
CH-SEC-005 depreciation/disposal
        ↓
Celery depreciation user / SoD

claim_financial_idempotency (+ select_for_update)   ← remittance already claims
        ↓
CH-SEC-006 contributions
        ↓
CH-SEC-013 incomplete-key lock (P2, but do with 006)
```

---

# Fixes that collapse multiple findings

| Component | Findings closed together |
|-----------|--------------------------|
| `user_may_access_media` | CH-SEC-001; reduces impact of CH-SEC-002 images; aligns with export owner rule |
| Denomination on `Announcement` + scoped `visible_announcements` | CH-SEC-002, CH-SEC-008, announcement branch of CH-SEC-001 |
| `filter_churches_for_operator` passed into stats | CH-SEC-009; same helper as CH-SEC-004 destination check |
| Stop OR-ing view+mutate | CH-SEC-007; template for ledger wrapper |
| `approve_module_journal` + working day | CH-SEC-005; same primitive as acquisition |
| Idempotency claim + row lock | CH-SEC-006 and CH-SEC-013 |
| `full_clean()` on church save | CH-SEC-004; related L1 if User.save also validates |

---

# A. P0 remediation plan

**P0-1 CH-SEC-001** — Media authorization service + view + rewrite tests. Fail closed on unknown prefixes. Do not wait for UUID filenames. Announcement images: allow if `visible_announcements` **or** temporary “same church as announcement.church_id” until FK ships; **deny all `visibility=general` images to other denominations** even before the FK by denying general images unless `get_user_denomination(user)` matches `get_user_denomination(announcement.created_by)` (heuristic). Replace heuristic when CH-SEC-002 FK exists.

**P0-2 CH-SEC-003** — Per-user + per-IP MFA verify lockout; apply to enroll and email send IP; TOTP used-step cache.

Ship as two PRs (unrelated blast radius). Both are hotfixes for production `mychurch.zreta.com`.

---

# B. P1 remediation plan

Order inside P1:

1. **CH-SEC-007** permission split (small, no schema).
2. **CH-SEC-004** tenant_edit validation (small, no schema).
3. **CH-SEC-009** platform_stats(user) (small; isolation).
4. **CH-SEC-002 + 008** announcement denomination FK (schema; unblocks correct media rule for general images).
5. **CH-SEC-006** contribution idempotency **with** idempotency row lock (pulls CH-SEC-013 forward).
6. **CH-SEC-005** asset journal finalize (Celery/SoD staging).

---

# C. Recommended implementation order

```
Week 0  P0-1 media ACL tests-first
        P0-2 MFA throttle          } parallel

Week 1  P1 CH-SEC-007
        P1 CH-SEC-004
        P1 CH-SEC-009

Week 2  P1 CH-SEC-002/008 + tighten media announcement rule
        P1 CH-SEC-006 + key row lock

Week 3  P1 CH-SEC-005 on staging with Celery identity
        Then P2 (void lock, welfare SoD, portal enumeration)
```

Do not start CH-SEC-005 on production until the Celery actor is decided.

---

# D. Estimated complexity

| ID | Complexity |
|----|------------|
| CH-SEC-001 | HIGH |
| CH-SEC-003 | LOW–MEDIUM |
| CH-SEC-007 | LOW |
| CH-SEC-004 | LOW |
| CH-SEC-009 | LOW |
| CH-SEC-002 / 008 | MEDIUM |
| CH-SEC-006 | LOW–MEDIUM |
| CH-SEC-005 | MEDIUM |

---

# E. Security regression-test strategy

1. **Tests first** for CH-SEC-001: convert `test_authenticated_can_fetch_private_media` to expect 404; add two-tenant fixtures before changing production logic if possible (red → green).
2. **Tenant pair fixture** reused across media, announcements, platform stats, tenant_edit.
3. **Role matrix** for finance: BOARD_MEMBER, SECRETARY, TREASURY, view-only override.
4. **Concurrency:** contribution double POST; optional void `select_for_update` when P2 starts — use `TransactionTestCase` / threads carefully on SQLite; prefer PostgreSQL in CI for lock tests.
5. **Do not** add tests that assert the old “any authenticated user may fetch private media” behavior.

---

# F. Risks of fixing incorrectly

| Mistake | Result |
|---------|--------|
| Authn-only “hardening” comments | Vulnerability remains |
| Allow all staff files in-denomination without portal split | Members scrape all photos |
| Allow all platform operators | SUPPORT/READONLY dump all tenants |
| Fail open on unknown prefix | Next `upload_to` is instantly public-to-authn |
| 403 instead of 404 on media | Path oracle |
| MFA lockout keyed only on IP | Shared office NAT locks treasurers |
| MFA lockout keyed only on user with high limit | Still brute-forceable |
| Remittance gated to TREASURY only without product sign-off | Secretaries lose a workflow they have via `manage_finances` |
| Announcement FK backfill to the wrong denomination | Cross-tenant **write** of identity; worse than leak |
| `visible_announcements` still `scoped = qs` after FK | CH-SEC-002 not actually fixed |
| Asset `approve_module_journal` but still update register when PENDING | CH-SEC-005 remains |
| Celery user = same as created_by | Depreciation never posts |
| Contribution unique(member, date, amount) | Blocks two legitimate gifts |
| `full_clean()` on every `save_model` | Unrelated platform saves start failing |

---

# G. Local first vs deployment branch

**Remediate locally on a feature branch from `main`, not directly on the live deployment branch / VPS.**

Reasons:

- CH-SEC-001 will 404 files if the prefix map is incomplete — that is a user-facing outage. Needs a local/staging pass over real `MEDIA_ROOT`-shaped fixtures.
- CH-SEC-002 needs a data migration that must be rehearsed on a copy of production (orphan general rows).
- CH-SEC-005 can stall month-end depreciation if Celery identity is wrong.
- MFA throttle needs Redis behavior identical to production.

Suggested git flow (when implementation is approved): `feature/sec-p0-media`, `feature/sec-p0-mfa`, then `feature/sec-p1-isolation`, `feature/sec-p1-finance`. Merge to `main` after tests; deploy to `mychurch.zreta.com` behind the existing Nginx `internal` media location.

Do **not** hotfix production by editing `media_views.py` on the server without the test rewrite — the current test suite would green-light the hole again.

---

## Out of scope for this design (P2/P3)

CH-SEC-010–022, L1–L4, P1–P4 remain as in the register/roadmap. The only P2 item pulled forward is **CH-SEC-013** (idempotency row lock) because CH-SEC-006 is incomplete without it.

CH-SEC-L1 (unanchored SUPER_ADMIN) should be scheduled immediately after P1 isolation: media and announcements both call `get_manageable_churches`, which returns **all churches** when superadmin has no denomination (`permissions/scoping.py` 16–22).
