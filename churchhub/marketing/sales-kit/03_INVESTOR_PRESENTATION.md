# ChurchHub — Investor Presentation Outline

**Audience:** Investors, strategic partners, enterprise buyers  
**Length:** 10–12 slides (~12 minutes)  
**Companion deck:** Adapt `../presentation/ChurchHub_Enterprise_Pitch.pptx` or build from this outline  
**Tone:** Institutional software thesis — not consumer church app hype

---

## Slide 01 — Title

**ChurchHub Enterprise**  
Church management infrastructure for hierarchical networks  

*One platform. Complete hierarchy. Books you can trust.*

---

## Slide 02 — Problem

- Church admin is **enterprise work** (fiduciary + pastoral + multi-site)
- Status quo: spreadsheets, flat ChMS, accounting tools with no pastoral ops
- Result: weak remittance accountability, permission sprawl, lost visitor follow-up, audit pain

**Sound bite:** Financial mistakes aren’t IT issues — they’re trust issues.

---

## Slide 03 — Solution

ChurchHub = **operating system for ministry networks**

Membership + Treasury + Remittance + Church Life + Reports + Platform control  
…scoped by hierarchy and role.

---

## Slide 04 — Market / ICP

| Segment | Need |
|---------|------|
| Mid/large conferences | Multi-church roll-up + remittance |
| Unions / denominations | Multi-tenant isolation + provisioning |
| SaaS operators | Subscriptions, features, operator audit |
| Single large churches | Path into Conference tier |

*(Insert TAM/SAM/SOM only with finance-approved numbers.)*

---

## Slide 05 — Product proof

Live / screenshot mosaic:

1. Mission Control  
2. Hierarchy tree  
3. Receipt confirmation  
4. Permissions matrix  
5. Platform tenancy  

---

## Slide 06 — Moat / differentiation

| Differentiator | Why it sticks |
|----------------|---------------|
| Hierarchy-native data model | Not bolted onto single-site CRM |
| Books of record (double-entry) | Auditors and treasurers align |
| Denomination wall + dual lanes | True SaaS without data bleed |
| Action Queue UX | Adoption by pastors, not only IT |
| Self-host *or* cloud | Institutional procurement flexibility |

---

## Slide 07 — Business model (placeholder)

- Subscription tiers: Parish · Conference · Network/Enterprise  
- Professional services: migration, training, hypercare  
- Expansion: more churches, payroll/assets features, managed hosting  

*Replace $___ with board-approved pricing.*

---

## Slide 08 — Go-to-market

1. Guided demos (executive 10-min script)  
2. 30–60 day pilots (1–3 churches)  
3. Conference land-and-expand  
4. Denomination / platform deals  

Assets: brochure, website, sales kit, teleprompter demo.

---

## Slide 09 — Technology

- Django monolith, PostgreSQL, Redis, Celery  
- Gunicorn + Nginx; Docker / Render / private DC  
- Session auth, RBAC, CSRF; health endpoints  
- **No** invented public REST `/api/v1/` product surface today  

---

## Slide 10 — Traction / milestones

*(Fill with real metrics only.)*

- Product completeness: membership, finance, remittance, portal, platform  
- Docs / ops: production settings, runbooks, CI  
- Pipeline: ___ pilots · ___ conferences in discussion  

---

## Slide 11 — Ask

| If fundraising | If partnering |
|----------------|---------------|
| Use of funds: GTM, CS, infra, compliance | Pilot seats / design-partner status |
| Round size / instrument TBD | Co-marketing + migration services |

---

## Slide 12 — Close

ChurchHub turns fragmented church administration into **auditable, hierarchical operations software**.

**Next:** Mission Control demo · pilot scoping · enterprise security review  

sales@churchhub.example

---

### Speaker notes (global)

Stay Current vs Planned. Do not claim universal MFA enforcement, soft-delete, or public DRF APIs unless code confirms. Charts = sample until live metrics approved.
