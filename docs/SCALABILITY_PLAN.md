# ChurchHub — Scalability Plan

**Audience:** Engineering + ops planning growth  
**Date:** 21 July 2026  
**Companions:** `PERFORMANCE_REPORT.md`, `CACHE_STRATEGY.md`, `PRODUCTION_READINESS_REPORT.md`

---

## Current architecture (scale posture)

| Layer | Current | Scale lever |
|-------|---------|-------------|
| App | Django monolith, Gunicorn | Horizontal web replicas (stateless + Redis) |
| DB | PostgreSQL | Indexes, pooling, read replicas (later) |
| Cache / sessions | Redis (`cached_db` sessions) | Shared across workers |
| Async | Celery worker + Beat | Scale workers for exports/backups |
| Static | WhiteNoise / Nginx | CDN later |
| Media | Disk or S3 | Object storage for multi-instance |

---

## Growth stages

### Stage A — Limited production (now)

- ≤ 100 churches, ≤ 20k members, ≤ 500k journal lines  
- 1–2 Gunicorn workers + Redis + Postgres  
- Phase 4 indexes + caches applied  
- Sync reports OK for small scopes  

### Stage B — Regional conference (next)

- ≤ 500 churches, ≤ 50k members, ≤ 2M lines  
- 4+ Gunicorn workers, PgBouncer, Celery concurrency ≥ 4  
- Async-default for trial balance / BS / IS / directory exports  
- Monitoring: p95 latency, DB CPU, Redis hit rate  
- Optional read replica for report builders only (never for posting)  

### Stage C — Multi-union / SaaS density

- Partition hot tables by church or year (Planned design)  
- CDN + object storage mandatory  
- Separate report worker queue from email/depreciation  
- Consider materialized MTD KPI tables refreshed by Beat  

---

## Bottleneck map (500 churches / 50k members / 2M lines / 500 users)

| Bottleneck | Symptom | Mitigation |
|------------|---------|------------|
| Unscoped financial statements | Slow TB/BS, timeouts | Force church/date filters; async export |
| Member full-text `icontains` | Slow search | `pg_trgm`, limit scope to manageable churches |
| Org hierarchy without prefetch | N+1 on tree pages | Always use hierarchy selectors |
| LocMem without Redis | Uneven rate limits / cache | **Forbidden in multi-worker prod** |
| Sync large Excel/PDF | Worker blocked | Celery + job UI (already wired) |
| Connection storms | `too many connections` | PgBouncer transaction pooling |
| Beat backup on primary | I/O spikes | Off-peak schedule; provider snapshots |

---

## Multi-tenancy scale rules (enforce)

1. Every church-owned query remains `filter_by_church` / manageable-scope filtered.  
2. Never cache cross-tenant aggregates under a single global key.  
3. Platform operators use denomination-scoped admin helpers — do not widen for speed.  
4. Dashboard executive KPIs are scoped to `get_manageable_churches` — keep that contract.

---

## Load-test plan (Recommended)

Tools: k6 or Locust against staging with anonymized seed.

| Scenario | Target |
|----------|--------|
| Login + dashboard home | p95 < 1.5s @ 100 VUs |
| Member directory page | p95 < 800ms @ 100 VUs |
| Transaction list (church) | p95 < 1s @ 100 VUs |
| Async report queue | 95% jobs complete < 60s for 50k-row export |
| Notification poll | p95 < 200ms @ 200 VUs |

Seed approximate volumes before test: 500 churches, 50k members, 2M lines (synthetic).

---

## Roadmap (no business-logic changes)

| Priority | Item | Effort |
|----------|------|--------|
| P0 | Apply Phase 4 migrations; Redis everywhere | S |
| P1 | PgBouncer + EXPLAIN on top reports | M |
| P1 | UI default async for heavy finance exports | S |
| P2 | Trigram member search | M |
| P2 | Materialized MTD KPI table + Beat refresh | L |
| P3 | Read replica for reports | L |

---

## Success criteria for “enterprise-scale ready”

- [ ] Indexes applied in production  
- [ ] Redis required and healthy (`/health/ready/`)  
- [ ] p95 dashboard < 2s under Stage B load test  
- [ ] No cross-tenant cache leakage in review  
- [ ] Heavy reports async by default  
- [ ] DB connections stable under 500 VU soak (30 min)
