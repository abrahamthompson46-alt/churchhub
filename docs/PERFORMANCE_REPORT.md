# ChurchHub — Performance Report

**Type:** Phase 4 performance optimization (code + measurement notes)  
**Date:** 21 July 2026  
**Source of truth:** Live Django code after Phase 4 changes  
**Companions:** `SCALABILITY_PLAN.md`, `CACHE_STRATEGY.md`, `PRODUCTION_READINESS_REPORT.md`

| Label | Meaning |
|-------|---------|
| **Current** | Implemented optimizations |
| **Measured** | Verified via tests / static query review (no production load test harness in-repo) |
| **Estimated** | Capacity projections under stated assumptions |

---

## Executive summary

Phase 4 focused on **query reduction**, **missing indexes**, and **targeted Redis caching** without changing financial or tenancy business rules.

| Area | Before (typical) | After |
|------|------------------|-------|
| Giving leaders | Load all tithe/combined lines; Python loop | ORM `Sum(Abs)` + slice + 5 min cache |
| Dashboard MTD KPIs | 4–5 aggregates per KPI block | 1 grouped aggregate |
| Control-center home | Compliance + executive KPIs recomputed 2–3× | Computed once; passed through |
| Working-day issues | N queries (one per church) | 1 `IN` query |
| Cash position | 4 aggregates | 1 grouped query |
| Teller console | Prefetch lines only (N+1 accounts) | `prefetch_related("lines__account")` |
| Async report export | Sync `build_report` then Celery rebuild | Queue only when `async=1` |
| Member directory stats | 3–4 `.count()` queries | 1 conditional `Count` aggregate |
| Notifications unread | Count every poll | 30s cache + invalidate |
| Permission matrix cell | DB hit per uncached codename | Redis/LocMem + request cache |
| Indexes | Gaps on Account type, Notification, txn filters | Additive migrations `0018` / `0003` |

---

## Optimizations completed

### 1. Database / ORM

- **Giving:** `church_giving_leader_totals` — `values(member).annotate(Sum(Abs(amount)))`
- **Giving summary:** one grouped `line_totals_by_account_type` instead of per-type loops
- **Dashboard:** `sum_line_amounts_by_types` for MTD and all-time KPI blocks
- **Dashboard:** batch `open_working_day_church_ids`
- **Dashboard:** `recent_approved_transactions` / member list `select_related` / prefetch
- **Treasury:** cash position single group-by; teller prefetch `lines__account`
- **Members:** directory stats via conditional `Count`
- **Reports:** async export skips synchronous rebuild
- **Calendar home:** counts derived from fetched preview items

### 2. Indexes (migrations)

| App | Migration | Indexes |
|-----|-----------|---------|
| `transactions` | `0018_perf_indexes` | `Account(church, account_type)`; `Transaction(church, approval_status, is_voided, date)`; `(church, member)`; `(church, ledger_category, -date)` |
| `dashboard` | `0003_perf_indexes` | `Notification(user, -created_at)`; `(user, read)` |

### 3. Caching

See `CACHE_STRATEGY.md`. Helpers in `church_system/perf_cache.py`. Invalidation on approve/void, notification read/create, matrix cell update.

### 4. What was deliberately not changed

- Double-entry balance rules, void/reversal, period/working-day gates
- Tenant / denomination scoping semantics
- Permission resolution order (superadmin → override → matrix → implies)
- Trial balance / BS / IS formulas (indexes + async path only)

---

## Performance gains (estimated)

| Path | Query / work reduction (est.) |
|------|-------------------------------|
| Giving leaders (large church, 10k+ lines) | O(n) Python → O(1) SQL top-N; ~10–100× less data to app |
| Dashboard finance KPIs | ~4–6 queries → ~2 aggregates + trend |
| Control center home | Remove duplicate compliance/KPI passes (~30–50% less KPI DB work) |
| Working-day compliance (500 churches) | ~500 queries → 1 |
| Cash position | 4 → 1 |
| Async export | Eliminate 100% of sync report build on async path |
| Notification poll | Cache hit avoids COUNT under burst |

**Note:** Gains are query-count / data-volume estimates from code review. Run `EXPLAIN ANALYZE` on staging Postgres after applying migrations for confirmation.

---

## Remaining bottlenecks

1. **Hierarchy templates** — deep `prefetch` is present for main overview; alternate entry points without prefetch still risk N+1  
2. **Trial balance / BS / IS** — full-scope aggregates; no HTML pagination; large multi-church runs should use async export  
3. **Member search** — `icontains` / `Concat` cannot use B-tree indexes well; consider trigram/GIN later  
4. **Teller daily summary** — still Python loop over day's txns (acceptable for one church-day; annotate further if needed)  
5. **Remittance payable MTD** — still two aggregates when no cutoff row  
6. **Permission implies** — recursive resolution still walks registry (mitigated by request cache)  
7. **No in-repo load test suite** — capacity below is estimated  

---

## Estimated production capacity

Assumptions: Postgres 16, Redis shared cache, Gunicorn 2–4 workers, Celery for async exports, indexes applied, `REDIS_URL` set.

| Scenario | Projection |
|----------|------------|
| **500 churches** | Hierarchy/dashboard control-center: OK with batched working-day + scoped KPIs; org tree pages need prefetch discipline |
| **50,000 members** | Directory (25/page) + stats aggregate: OK; full export may need Celery |
| **2M journal lines** | Church-scoped lists OK with new composites; unscoped TB/BS across many churches: use date filters + async export |
| **500 concurrent users** | Web tier: scale workers behind Redis; DB: connection pooling (`CONN_MAX_AGE`); watch slow query log for report builders |

**Comfortable “launch” band:** ~100–200 active churches, tens of thousands of members, hundreds of concurrent users with Redis + indexes.  
**At 500 churches / 2M lines:** require staging EXPLAIN, connection pooler (PgBouncer), and async-default for heavy reports.

---

## Recommendations before public launch

1. Apply migrations `transactions.0018_perf_indexes`, `dashboard.0003_perf_indexes` in staging/prod  
2. Confirm `REDIS_URL` on all web workers  
3. EXPLAIN ANALYZE top 10 slow endpoints after one week of traffic  
4. Default large financial exports to `async=1` in UI for TB/BS/IS  
5. Add PgBouncer if concurrent DB connections approach Postgres `max_connections`  
6. Optional: PostgreSQL `pg_trgm` for member search  
7. Run soak test (k6/Locust) at target concurrency before marketing launch  

---

## Related files

- `church_system/perf_cache.py`
- `giving/selectors.py`, `giving/services.py`
- `dashboard/services.py`, `dashboard/selectors.py`, `dashboard/repositories.py`
- `transactions/treasury.py`, `transactions/services.py`, `transactions/models.py`
- `reports/views.py`, `members/services.py`, `permissions/services.py`
- `announcements/calendar_services.py`
