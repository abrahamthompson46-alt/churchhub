# ChurchHub — Authentication

**Audience:** Security reviewers, architects, AI agents  
**Source of truth:** Live Django auth code and settings  
**Companions:** `AUTHORIZATION.md`, `AUDIT_COMPLIANCE.md`, `docs/ARCHITECTURE/SECURITY_ARCHITECTURE.md`, `docs/MODULE_SPECIFICATIONS/ACCOUNTS/accounts_spec.md`, `docs/MODULE_SPECIFICATIONS/SITE_CONTROL/site_control_spec.md`, root `SECURITY.md`, `AGENTS.md` §4

| Label | Meaning |
|-------|---------|
| **Current** | Implemented in code |
| **Planned (AGENTS.md)** | Enterprise authentication constitution |
| **Recommended** | Hardening next steps |

---

## 1. Login architecture (Current)

ChurchHub uses **Django session authentication** with a custom user model. There is **no** OAuth/OpenID provider and **no** DRF / API token auth surface.

```mermaid
flowchart TD
  A[Browser] --> B["/accounts/login/"]
  B --> C{LoginRateLimitMiddleware}
  C -->|locked| D[Redirect + error]
  C -->|ok| E[ChurchHubLoginView]
  E -->|invalid| F[Form errors]
  E -->|valid| G[Django login + session cookie]
  G --> H[user_logged_in signal]
  H --> I{User type}
  I -->|is_platform_user| J["/platform/"]
  I -->|role MEMBER| K["/portal/"]
  I -->|else| L["/dashboard/"]
```

| Item | Detail |
|------|--------|
| Primary login | `/accounts/login/` → `church_system.auth.ChurchHubLoginView` |
| Portal login | `/portal/login/` → `portal.views.portal_login` (member email + DOB/password) |
| Backend | Default `ModelBackend` for staff; portal verifies against `members.Member` then establishes a session |
| Settings | `LOGIN_URL=/accounts/login/`; `LOGIN_REDIRECT_URL=/dashboard/` (overridden by view) |
| Root | `""` redirects to `login` |
| Also mounted | `django.contrib.auth.urls` under `/accounts/` (staff password reset/change); portal reset under `/portal/password/` |

### Member portal credentials (Current)

| Step | Behavior |
|------|----------|
| Username | Member **email** (must match an active `members.Member.email`) |
| First password | Member **date of birth** as `YYYY-MM-DD` — **only while** `must_change_password` is true (first sign-in) |
| After password set | DOB login is **permanently disabled**; use chosen password or reset flow |
| Match rule | Email and DOB must both match the member directory before a portal session is issued |
| Provisioning | First successful match creates/links a `User` (`role=MEMBER`, `must_change_password=True`) |
| New device / first login | Confirmation email link (`/portal/confirm/?token=…`) before session; **single-use**, **1 hour** TTL; trusted-device cookie afterward |
| Portal login throttling | Stricter cap (**3** failed attempts per 15 minutes per IP/email on `/portal/login/`); honeypot field rejects bots |
| Email link base URL | Set **`CHURCHHUB_PUBLIC_URL`** to your live HTTPS **site root** only (example: `https://churchhub.pythonanywhere.com`) — **not** a path like `/dashboard/`. If unset or left at `localhost`, confirmation links in email will not work on phones or other devices. After changing it, redeploy and request a **new** confirmation email. Production also falls back to `DJANGO_CSRF_TRUSTED_ORIGINS` when the public URL is still localhost. Confirm links use `/portal/confirm/?token=…` so email clients handle signed tokens reliably. |
| After login | Forced password change when `must_change_password`; change at `/portal/password/change/`; reset at `/portal/password/reset/` |

### Success redirects (`post_login_url`)

| Condition | Destination |
|-----------|-------------|
| `is_platform_user` | `sitecontrol:dashboard` |
| `role == MEMBER` | `portal:home` |
| Otherwise | `dashboard:home` |

Portal login additionally sends users with `member_id` to the portal.

---

## 2. Custom User model (Current)

**Model:** `accounts.User` (`AUTH_USER_MODEL`) — extends `AbstractUser`, UUID PK.

| Field / attribute | Security relevance |
|-------------------|--------------------|
| `username`, `email`, `password` | Credentials (Django hashed password) |
| `is_active` | Inactive users cannot authenticate |
| `is_staff` / `is_superuser` | Admin / break-glass (further constrained for platform) |
| `last_login` | Django-managed |
| `role` | Institution RBAC role (`UserRole`) |
| `scope_level` + scope FKs | Org authorization scope |
| `church` | Home church for local roles |
| `denomination` | Institution denomination binding |
| `is_platform_user` | Platform lane (`/platform/`) |
| `platform_role` | OWNER / SECURITY / BILLING / SUPPORT / READONLY |
| `managed_denominations` | M2M — operator denomination access |
| `mfa_enabled` | Enrolled MFA flag (enforced only when site MFA policy requires the user’s audience) |
| `member` | Optional OneToOne to `members.Member` |
| `must_change_password` | Portal users must set a non-DOB password after first confirmed sign-in |

Password hashing: Django’s password framework only — never plaintext.

See `docs/MODULE_SPECIFICATIONS/ACCOUNTS/accounts_spec.md`.

---

## 3. Password policy (Current)

**Validators** (`AUTH_PASSWORD_VALIDATORS` in `church_system/settings.py`):

1. `UserAttributeSimilarityValidator`  
2. `accounts.validators.PlatformMinimumLengthValidator` — `SiteSettings.password_min_length` (default 8, range 6–128)  
3. `accounts.validators.PlatformUppercaseValidator` — if `SiteSettings.password_require_uppercase`  
4. `CommonPasswordValidator`  
5. `NumericPasswordValidator`  

**In-session change:** profile view uses Django `PasswordChangeForm`, `update_session_auth_hash`, logs `PASSWORD_CHANGE` on `UserActivityLog`.

### Planned (AGENTS.md)

Lowercase / special character / password history / expiration / reuse prevention — **not** SiteSettings fields today.

### Recommended

Expand SiteSettings (or a policy model) for complexity and history; force reset after invite for privileged roles.

---

## 4. Session management (Current)

| Setting | Value |
|---------|-------|
| `SESSION_COOKIE_AGE` | 4 hours (`60 * 60 * 4`) |
| `SESSION_EXPIRE_AT_BROWSER_CLOSE` | `False` |
| Effective idle timeout | `PlatformSessionMiddleware` sets `session.set_expiry(session_timeout_minutes * 60)` from `SiteSettings` (default **240** minutes; allowed 5–1440) |

### Production cookie hardening (`DEBUG=False`)

- `SESSION_COOKIE_SECURE = True`
- `CSRF_COOKIE_SECURE = True`
- `SECURE_SSL_REDIRECT` (env `SECURE_SSL_REDIRECT`, default True)
- `SECURE_HSTS_SECONDS = 31536000` + include subdomains
- `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`

Always: `X_FRAME_OPTIONS=DENY`, `SECURE_CONTENT_TYPE_NOSNIFF=True`, `SECURE_BROWSER_XSS_FILTER=True`.

### Planned (AGENTS.md)

Absolute session timeout, logout-from-all-devices, device tracking, broader invalidate-on-password-change.

### Recommended

Document absolute max lifetime; add “logout all sessions” for privileged roles; rotate session on privilege elevation.

---

## 5. Authentication-related middleware (Current)

Order (relevant excerpt from `settings.MIDDLEWARE`):

```mermaid
sequenceDiagram
  participant R as Request
  participant Auth as AuthenticationMiddleware
  participant PC as PermissionCacheMiddleware
  participant RE as RoleEnforcementMiddleware
  participant DC as DenominationContextMiddleware
  participant US as UserScopeMiddleware
  participant PS as PlatformSessionMiddleware
  participant MM as MaintenanceModeMiddleware
  participant LR as LoginRateLimitMiddleware

  R->>Auth: Attach request.user
  R->>PC: Bind permission cache
  R->>RE: Church required for local roles
  R->>DC: Denomination wall
  R->>US: Platform vs institution lanes
  R->>PS: Apply SiteSettings session expiry
  R->>MM: Maintenance logout / block
  R->>LR: Login POST throttle
```

| Middleware | Auth role |
|------------|-----------|
| `AuthenticationMiddleware` | Loads session user |
| `PlatformSessionMiddleware` | Idle timeout from SiteSettings |
| `MaintenanceModeMiddleware` | Logs out non-platform users when maintenance on |
| `LoginRateLimitMiddleware` | Throttles failed login POSTs |
| `UserScopeMiddleware` | Lane isolation after auth (see AUTHORIZATION) |
| `RoleEnforcementMiddleware` | Redirects local roles without church to profile |

CSRF: `CsrfViewMiddleware` globally enabled — never disable globally.

---

## 6. Login / logout flow (Current)

### Login side effects

`accounts/signals.py` `on_user_login` (`user_logged_in`):

- Calls `sync_role_groups` (**no-op** — Django Groups retired)  
- Writes `UserActivityLog` action `LOGIN`

### Logout

| Path | Behavior |
|------|----------|
| Primary UI | `/dashboard/logout/` → `dashboard.views.custom_logout` |
| Steps | Capture denomination id → `logout(request)` → restore `active_denomination_id` → `logged_out.html` |
| Signal | `on_user_logout` → `UserActivityLog` `LOGOUT` |
| Also | Django `/accounts/logout/` → `LOGOUT_REDIRECT_URL=/accounts/login/` |
| Forced | Maintenance middleware logs out non-platform users |

---

## 7. Platform users vs institution users (Current)

```mermaid
flowchart TD
  U[Authenticated user] --> P{is_platform_user?}
  P -->|yes| PL["Platform lane /platform/"]
  PL --> CAP[platform_role capabilities]
  P -->|no| INST[Institution lane]
  INST --> RBAC[Role + permission matrix]
  INST --> HOME[dashboard / portal]
```

| Aspect | Platform | Institution |
|--------|----------|-------------|
| Flag | `is_platform_user=True` | `False` |
| Home after login | `/platform/` | `/dashboard/` or `/portal/` |
| Authz system | `sitecontrol.rbac` capabilities | `permissions` matrix + overrides |
| Django admin | Only if also `is_superuser` (`can_access_django_admin`) | Not via platform break-glass path |
| Institution apps | Blocked by `UserScopeMiddleware` (except limited `/accounts/` profile paths) | Normal access within scope |

Detail: `AUTHORIZATION.md` § Platform vs institution; `docs/MODULE_SPECIFICATIONS/SITE_CONTROL/site_control_spec.md`.

---

## 8. Password reset (Current)

Via:

```text
path("accounts/", include("django.contrib.auth.urls"))
```

Standard Django reset views; templates under `templates/registration/password_reset_*.html`. Login page links `{% url 'password_reset' %}`.

Email delivery depends on platform SMTP / env (`EMAIL_*`, `EMAIL_BACKEND`, `CHURCHHUB_PUBLIC_URL`, SiteSettings SMTP including optional encrypted password).

HTML messages use a shared branded layout (`templates/emails/base_email.html`) driven by **Platform → Site settings** (site name, colors, logo, support email) and the public site URL for links and logo assets.

**Rate limiting:** `LoginRateLimitMiddleware` covers staff login, portal login, and password-reset POSTs (request + confirm).

---

## 9. Account activation / invitations (Current)

There is **no** separate email-activation token for open signup. Institution users are typically created via **invitation**.

```mermaid
sequenceDiagram
  participant Admin
  participant Svc as accounts.services
  participant Invitee

  Admin->>Svc: create_invitation
  Svc-->>Invitee: email with token URL
  Invitee->>Svc: /accounts/invite/accept/uuid/
  Svc->>Svc: validate_password + create_user
  Svc->>Svc: apply_org_scope
  Svc-->>Invitee: redirect to login
```

| Item | Detail |
|------|--------|
| Accept URL | `/accounts/invite/accept/<uuid:token>/` |
| Validity | Not accepted (single-use), not expired, not revoked (`UserInvitation.is_valid`) |
| Default validity | **1 hour** (`accounts.services.INVITATION_VALIDITY`); resend issues a **new token** + fresh 1-hour window |
| Activation toggle | `activate_user` / `deactivate_user` set `is_active` |
| Audit | INVITE_*, USER_CREATE on `UserActivityLog` |
| Gates | `sitecontrol` invite limits / `institution_invites_allowed()` |

Public tenant onboarding: `/apply/` → platform approve → church provision + invitation — see Site Control spec.

---

## 10. MFA status

| State | Detail |
|-------|--------|
| **Current** | MFA is **on by default** for privileged audiences. Platform owners configure audiences under **Platform → Security** (`SiteSettings.mfa_required_for_privileged`, default **True**) and choose **who**: institution roles (`mfa_institution_roles`), platform roles (`mfa_platform_roles`), and optionally Django superusers (`mfa_include_django_superusers`). Recommended starter audiences: OWNER/SECURITY + SUPER_ADMIN/TREASURY. Methods: **TOTP** (QR enroll), **email OTP**, **recovery codes**. **Trusted device** cookie skips MFA for 30 days when checked. Secrets stored encrypted. **Impersonation** requires MFA enrollment + verified session when policy applies. |
| **Planned (AGENTS.md)** | Optional SMS OTP, richer device management UI |
| **Recommended** | Dedicated `MFA_ENCRYPTION_KEY`; rate-limit TOTP verify attempts |

Login flow: password success → trusted device (if cookie valid) → home; else if site policy requires MFA for that user and enrolled → `/accounts/mfa/verify/` (TOTP, email code, or recovery) → if required and not enrolled → `/accounts/mfa/enroll/` (scannable QR). `MfaEnforcementMiddleware` blocks the rest of the app until verified (or trusted device). When enforcement is off, MFA is not required even if a user has enrolled.

---

## 11. Login rate limiting (Current)

**Middleware:** `sitecontrol.middleware.LoginRateLimitMiddleware`  
**Scope:** `POST` to:

| Path | Behavior |
|------|----------|
| `/accounts/login` | Fail counters by IP + username; clear on successful auth (incl. MFA pending) |
| `/portal/login/` | **Stricter:** max **3** failed attempts per IP/email (independent of `login_max_attempts`); honeypot field; lock redirects to portal login |
| `/apply/` | Registration POST throttled (**5** attempts / lockout window per IP) |
| `/accounts/password_reset/` | Attempt counters by IP + email (`reset_*` keys) |
| `/accounts/reset/<uidb64>/<token>/` | Same reset counters (confirm POSTs) |

| Cache key | Purpose |
|-----------|---------|
| `login_fail:{ip}` / `login_fail_user:{username}` | Login fail counters |
| `login_lock:{ip}` / `login_lock_user:{username}` | Login lock flags |
| `reset_fail:{ip}` / `reset_fail_email:{email}` | Password-reset attempt counters |
| `reset_lock:{ip}` / `reset_lock_email:{email}` | Password-reset lock flags |

| SiteSettings | Default | Range |
|--------------|---------|-------|
| `login_max_attempts` | 5 | 3–20 |
| `login_lockout_minutes` | 15 | 1–120 |

On login success: fail keys cleared. Cache: Redis if `REDIS_URL`, else LocMem (locks not shared across processes on LocMem).

**No** automatic `is_active=False` lockout model — only cache lockout + manual deactivate / tenant offboard.

---

## 12. Environment & SiteSettings controls (Current)

| Variable / setting | Effect |
|--------------------|--------|
| `DJANGO_SECRET_KEY` | Required when `DEBUG=False` |
| `DJANGO_DEBUG` | Must be False in production; unset defaults False when `DATABASE_URL`/Render markers present |
| `DJANGO_ALLOW_DEBUG_IN_PROD` | Temporary override only |
| `DJANGO_ALLOWED_HOSTS` | Host allowlist |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | CSRF trusted origins |
| `SECURE_SSL_REDIRECT` | When not DEBUG |
| `REDIS_URL` | Shared cache for rate limits |
| `EMAIL_*` / `DEFAULT_FROM_EMAIL` | Reset / invites |
| `CHURCHHUB_PUBLIC_URL` | Absolute links |
| `SENTRY_DSN` | Errors (`send_default_pii=False`) |

SiteSettings also: session timeout, login attempts/lockout, password min length / uppercase, maintenance mode, platform IP allowlist.

---

## 13. Current vs Planned vs Recommended

| Topic | Current | Planned (AGENTS.md) | Recommended |
|-------|---------|---------------------|-------------|
| Auth style | Session + custom User | + MFA, OAuth readiness, API tokens | Keep session; add MFA before tokens |
| Password | Min length + optional uppercase + Django defaults | History, expiry, full complexity | Expand SiteSettings validators |
| Lockout | Cache rate-limit | Account lock + admin unlock | Persist lock events; unlock UI |
| Sessions | Idle via SiteSettings | Absolute + logout-all + devices | Absolute timeout + logout-all |
| MFA | TOTP + email OTP + recovery; trusted device 30d | SMS OTP | Expand optional roles |
| Portal | Email + DOB bootstrap, device confirm, forced password change, portal reset | Richer member auth / optional portal MFA | Keep lane separation; enforce unique member email + DOB |

---

## 14. Security recommendations

1. Dedicated MFA encryption key separate from `SECRET_KEY`; rate-limit TOTP verify attempts.
2. Require Redis in production for shared login lockout.  
3. Keep `DJANGO_DEBUG=False` in production (startup + `/health/` already reject unsafe DEBUG).
4. Set **`CHURCHHUB_HEALTH_TOKEN`** in production — `/health/`, `/health/live/`, and `/health/ready/` require `?token=` or `X-Health-Token` header when configured.
5. **Platform `/platform/` access:** prefer **MFA** for operators on dynamic home ISPs — leave `platform_ip_allowlist` empty (production default does **not** require a list). Set `CHURCHHUB_REQUIRE_PLATFORM_IP_ALLOWLIST=true` only when you maintain a **static or dedicated VPN** IP allowlist.  
4. Rate-limit password reset / invite accept endpoints.  
5. Password history + optional expiry for finance/platform roles.  
6. Session absolute timeout + logout-all.  
7. Keep CSRF enabled globally.  
8. Never log passwords, reset tokens, or SMTP secrets.

---

## 15. Related documents

- `AUTHORIZATION.md` — what happens after identity is established  
- `AUDIT_COMPLIANCE.md` — login/activity audit  
- `docs/ARCHITECTURE/SECURITY_ARCHITECTURE.md`  
- `docs/MODULE_SPECIFICATIONS/ACCOUNTS/accounts_spec.md`  
- `docs/MODULE_SPECIFICATIONS/SITE_CONTROL/site_control_spec.md`  
- `docs/AI_CONTEXT/CODING_GUIDE.md`  
