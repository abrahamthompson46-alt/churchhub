# Wave 1 — Infrastructure Security Hardening Plan

**Status:** IMPLEMENTED (templates + docs in repo; VPS apply is operator step)  
**Date:** 6 August 2026  
**Area:** Fail2Ban + UFW + verification commands  
**Detail plan retained below; §12 lists shipped files.**

---

## 12. Implementation shipped

| Path | Role |
|------|------|
| `deploy/fail2ban/jail.d/churchhub-sshd.conf` | SSH jail overlay (enabled) |
| `deploy/fail2ban/filter.d/churchhub-nginx-auth.conf` | POST auth-path filter |
| `deploy/fail2ban/jail.d/churchhub-nginx-auth.conf` | HTTP jail (**enabled = false**) |
| `deploy/fail2ban/README.md` | Install / real-IP gate / rollback |
| `deploy/firewall/ufw-churchhub.sh` | `--status` `--plan` `--apply` `--check-exposure` |
| `deploy/scripts/wave1_infra_verify.sh` | Read-only verify bundle |
| `docs/DEVELOPMENT/DEPLOYMENT_NOTES.md` | Phase C + rollback |
| `docs/PRODUCTION_SECURITY_CHECKLIST.md` | §H2 host checks |

**Safety guarantees in code/scripts:**

- UFW `--apply` never runs `ufw reset`; only ensures SSH/80/443 allows + defaults.
- HTTP Fail2Ban jail ships disabled until Cloudflare real-IP is verified.
- SSH jail documents “keep live if stricter” before reload.

**VPS:** pull repo → follow DEPLOYMENT_NOTES Phase C → `wave1_infra_verify.sh`.

---

## 1. Goals

After this area:

1. Fail2Ban SSH protection is **documented as code** (tunable jail), reviewed against the live `sshd` jail.
2. HTTP brute-force gets a **safe, low false-positive** Fail2Ban layer that complements Django `LoginRateLimitMiddleware`.
3. UFW policy is **reproducible** from the repo with apply/rollback notes.
4. Operators have a **verification command set** for SSH, firewall, and service exposure.

---

## 2. Current state (pre-implementation)

| Check | Wave 0 | Repo before this change |
|-------|--------|-------------------------|
| UFW OpenSSH + Nginx | PASS | No script |
| Fail2Ban sshd | PASS | No template |
| HTTP Fail2Ban jail | NEEDS ACTION | Absent |
| `deploy/nginx/cloudflare-realip.conf` | — | Present |

Django failed logins usually return **200/302**, not 401 — HTTP jail uses access-log **POST** matching, not blanket 401 bans.

---

## 3–11. Design summary

See prior sections in git history / Wave 1 production plan §4.2. Key rules unchanged:

- Cloudflare real-IP before enabling HTTP jail.
- Conservative thresholds; `ignoreip` for loopback (+ ops VPN).
- Do not ban health/static/public branding.
- UFW additive; preserve SSH.

---

## Verification (post-deploy)

```bash
bash deploy/scripts/wave1_infra_verify.sh
sudo bash deploy/firewall/ufw-churchhub.sh --check-exposure
```
