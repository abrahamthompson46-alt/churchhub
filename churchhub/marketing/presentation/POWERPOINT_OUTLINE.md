# ChurchHub Enterprise — PowerPoint Outline

**Deck:** `ChurchHub_Enterprise_Pitch.pptx` (generated)  
**Duration:** ~10 minutes (aligns with demo / teleprompter)  
**Aspect:** Widescreen 16:9  
**Brand:** Navy `#0B1F3A` · Accent blue `#1F6FEB` · Slate `#334155` · Light `#F8FAFC` · White `#FFFFFF`  
**Fonts:** Title Calibri Bold · Body Calibri (swap to brand fonts in PowerPoint Theme if available)

**Related**
- Speaker notes: [`SPEAKER_NOTES.md`](./SPEAKER_NOTES.md)
- Demo script: `../demo-script/DEMO_SCRIPT_10MIN.md`
- Teleprompter: `../demo-script/TELEPROMPTER_10MIN.md`
- Screenshots: `../brochure/SCREENSHOT_CHECKLIST.md` (P1)

---

## Master animation language

| Code | PowerPoint meaning |
|------|-------------------|
| **FA** | Fade |
| **WI** | Wipe (from left) |
| **FL** | Float in (bottom) |
| **AP** | Appear |
| **ZO** | Zoom (subtle, icons only) |
| **Seq** | On click, sequential |
| **With** | With previous |
| **After** | After previous (0.2–0.4s) |

**Global rules**
- Title: FA With previous (0.2s)
- Bullets: FA Seq, 0.15s delay between
- Icons: ZO With accompanying bullet
- Charts: WI After title, then data series FA After
- Screenshot placeholders: FA After bullets
- Never animate more than 5 clicks per slide
- Closing CTA: no busy motion — FA once

---

## Slide 01 — Title

| Field | Content |
|-------|---------|
| **Layout** | Full-bleed navy gradient; large brand left/center |
| **Title** | CHURCHHUB |
| **Subtitle** | Enterprise Church Management System |
| **Tagline** | One platform. Complete hierarchy. Books you can trust. |
| **Footer** | Confidential · Prospect briefing |
| **Icon** | `bi-building` / cathedral + hub node (custom logo preferred) |
| **Chart** | — |
| **Screenshot** | Optional faint Mission Control wash at 12% opacity |
| **Animations** | 1) Logo FA 2) Title FA After 3) Tagline FA After 4) Footer AP After |
| **Time** | 00:00–00:30 |

---

## Slide 02 — Agenda

| Field | Content |
|-------|---------|
| **Title** | Ten minutes. The full arc. |
| **Bullets** | 1 Mission Control · 2 People & visitors · 3 Giving & treasury · 4 Reports · 5 Church life · 6 Platform |
| **Icons** (row of 6) | `bi-speedometer2` `bi-people` `bi-cash-coin` `bi-bar-chart` `bi-calendar-event` `bi-building-gear` |
| **Chart** | — |
| **Animations** | Icons ZO Seq · Labels FA With each icon |
| **Time** | 00:20–00:30 (spoken over intro close) |

---

## Slide 03 — The Challenge

| Field | Content |
|-------|---------|
| **Title** | Church administration is enterprise work |
| **Left bullets** | Spreadsheets break at scale · Tools don’t respect hierarchy · Finance mistakes erode trust · Pastoral follow-ups get lost |
| **Right callout** | “Financial mistakes aren’t IT issues — they’re trust issues.” |
| **Icons** | `bi-file-earmark-excel` `bi-diagram-3` `bi-shield-exclamation` `bi-heart` |
| **Chart** | Simple before/after bar: “Systems in use today” (demo data) — Spreadsheets 4 · Point tools 3 · Unified ChMS 1 |
| **Animations** | Left bullets FA Seq · Quote WI After · Chart FA After |
| **Time** | Optional if live demo starts immediately; use in pitch-only mode |

---

## Slide 04 — Product Overview

| Field | Content |
|-------|---------|
| **Title** | Built for your structure — not a flat single-site toy |
| **Hierarchy visual** | GC → Union → Conference → Zone → District → Church |
| **Capability chips** | Membership · Treasury · Remittance · Church Life · Reports · Portal · Platform |
| **Icons** | `bi-diagram-3` (hero) · chip icons as on agenda |
| **Chart** | Horizontal hierarchy flowchart (SmartArt Organization Chart or 6 stacked chevrons) |
| **Animations** | Hierarchy levels WI Seq top→bottom · Chips FA After |
| **Screenshot** | Org tree (shot `03-organization-hierarchy.png`) |
| **Time** | Bridge before live login |

---

## Slide 05 — Mission Control

| Field | Content |
|-------|---------|
| **Title** | Mission Control — pulse for every role |
| **Bullets** | Role-aware KPIs · Action Queue · Teller console & business date · This Week Pulse |
| **Icons** | `bi-speedometer2` `bi-list-check` `bi-calculator` `bi-lightning` |
| **Chart** | **Column chart** “Income vs Expense (6 months)” — demo series Income / Expense |
| **Screenshot** | `01-mission-control.png` + `11-finance-trend.png` |
| **Animations** | Bullets FA Seq · Chart WI After · Screenshot FA After chart |
| **Time** | 01:00–02:00 (live demo preferred; slide as backup) |

**Demo chart data (illustrative — label as sample)**

| Month | Income | Expense |
|-------|--------|---------|
| Feb | 42 | 28 |
| Mar | 45 | 30 |
| Apr | 48 | 29 |
| May | 51 | 33 |
| Jun | 49 | 31 |
| Jul | 55 | 34 |

---

## Slide 06 — People

| Field | Content |
|-------|---------|
| **Title** | Membership & visitors — one living record |
| **Two columns** | **Members:** Directory · Profile · Journey · Families · Transfers · Leadership · **Visitors:** Capture · Follow-up · Convert with history |
| **Icons** | `bi-person-vcard` `bi-people` `bi-arrow-left-right` `bi-person-plus` `bi-heartbeat` |
| **Chart** | **Donut** “Membership status mix” (sample): Baptized 62% · Profession 18% · Visitor track 12% · Other 8% |
| **Screenshot** | `05-members-directory.png` · `visitors-directory.png` |
| **Animations** | Column headers FA · Bullets FA Seq per column · Donut ZO After |
| **Time** | 02:00–04:00 |

---

## Slide 07 — Stewardship & Treasury

| Field | Content |
|-------|---------|
| **Title** | Giving you can counsel. Books you can trust. |
| **Bullets** | Permissioned giving statements · Record receipt → printable confirmation · Maker-checker approvals · Business date & periods · Remittance / cut-off |
| **Icons** | `bi-receipt` `bi-printer` `bi-people-fill` (maker-checker) `bi-calendar3` `bi-bank` |
| **Chart** | **Stacked bar** “Tithe vs Combined Offering (MTD by church)” — Church A/B/C sample |
| **Screenshot** | `04-receipt-confirmation.png` · `giving-statement.png` |
| **Animations** | Bullets FA Seq · Chart WI After · Confirmation screenshot FA |
| **Time** | 04:00–06:00 |

**Demo chart data**

| Church | Tithe | Combined |
|--------|-------|----------|
| Central | 18.2 | 6.4 |
| Eastside | 12.1 | 4.8 |
| Riverside | 9.7 | 3.2 |

*(Values in thousands; mark slide “Sample demo data”)*

---

## Slide 08 — Church Life

| Field | Content |
|-------|---------|
| **Title** | Meetings, calendar, announcements — one pastoral rhythm |
| **Bullets** | Upcoming calendar (meetings · birthdays · comms) · Meeting agenda / minutes / actions · Announcements → member portal |
| **Icons** | `bi-calendar-week` `bi-journal-text` `bi-megaphone` `bi-phone` |
| **Chart** | — (optional timeline graphic: Sabbath → Midweek → Board) |
| **Screenshot** | `07-announcements-calendar.png` · `meetings-detail.png` · `08-portal-mobile.png` |
| **Animations** | Three screenshot cards FL Seq · Captions FA With |
| **Time** | 07:00–08:00 |

---

## Slide 09 — Reports & Integrity

| Field | Content |
|-------|---------|
| **Title** | Reports leaders use. Integrity auditors expect. |
| **Bullets** | Report Center (role-filtered) · Tithe & offering · Membership & attendance · Trial balance / P&L / balance sheet · Export CSV · Excel · PDF |
| **Icons** | `bi-file-earmark-bar-graph` `bi-pie-chart` `bi-balance-scale` `bi-download` |
| **Chart** | **Combo** or two callouts: “Double-entry books of record” + sample **trial balance** mini-table (Debits = Credits) |
| **Screenshot** | `reports-center.png` · `reports-tithe.png` |
| **Animations** | Bullets FA Seq · Mini trial-balance table AP After · Equal-balance badge ZO |
| **Time** | 06:00–07:00 |

**Mini trial balance (sample)**

| Account | Debit | Credit |
|---------|-------|--------|
| Cash | 120,000 | |
| Tithe Income | | 85,000 |
| Offerings | | 25,000 |
| Expenses | 15,000 | |
| **Total** | **135,000** | **135,000** |

---

## Slide 10 — Security, Access & Platform

| Field | Content |
|-------|---------|
| **Title** | Least privilege. Denomination wall. Operator lane. |
| **Three pillars** | **RBAC** — roles, overrides, effective permissions · **Tenancy** — church scope + denomination isolation · **Platform** — subscriptions, features, audit, health |
| **Icons** | `bi-key` `bi-shield-lock` `bi-layers` `bi-toggles` `bi-journal-check` |
| **Chart** | **Simple architecture** 3-box: Institution Workspace → Denomination Wall → Platform Control |
| **Screenshot** | `09-permissions-matrix.png` · `10-platform-tenancy.png` |
| **Animations** | Pillars WI Seq · Architecture boxes FA After · Screenshots FA |
| **Time** | 08:00–09:30 |

---

## Slide 11 — Outcomes by Role

| Field | Content |
|-------|---------|
| **Title** | What each leader walks away with |
| **Matrix** | Executive → visibility & roll-up · Pastor → Action Queue & visitors · Treasurer → receipts, statements, trial balance · Admin/Clerk → directory, transfers, invitations |
| **Icons** | `bi-briefcase` `bi-heart-pulse` `bi-wallet2` `bi-person-gear` |
| **Chart** | 2×2 role cards (no numeric chart) |
| **Animations** | Role cards FL Seq (4 clicks max, or After cascade) |
| **Time** | 09:30 close setup |

---

## Slide 12 — Next Steps

| Field | Content |
|-------|---------|
| **Title** | Recommended next step |
| **Bullets** | Guided pilot · Your conference hierarchy · Your chart of accounts · Two local churches |
| **CTA buttons** (shapes) | Request a Demo · Talk to Sales · Start Pilot |
| **Icon** | `bi-rocket-takeoff` |
| **Chart** | — |
| **Contact** | [Your email / scheduling link] |
| **Animations** | Title FA · Bullets FA Seq · CTAs ZO After (once) |
| **Time** | 09:30–10:00 |

---

## Slide count & modes

| Mode | Slides to show | Notes |
|------|----------------|-------|
| **Live demo** | 01, 02, then app; return 11–12 | Keep 05–10 as backup if app fails |
| **Pitch only** | 01–12 full | Use sample charts; insert P1 screenshots |
| **Board pack PDF** | Export without animations | Embed screenshots |

---

## Icon kit (Bootstrap Icons → PowerPoint)

Prefer SVG import from [Bootstrap Icons](https://icons.getbootstrap.com/) or Office Icons. Recolor to `#1F6FEB` on light slides, white on navy.

| Concept | Bootstrap Icon |
|---------|----------------|
| Brand / org | `building`, `diagram-3` |
| Dashboard | `speedometer2` |
| Members | `people`, `person-vcard` |
| Visitors | `person-plus` |
| Giving | `cash-coin`, `receipt` |
| Treasury | `bank`, `calculator` |
| Reports | `bar-chart-line`, `file-earmark-bar-graph` |
| Meetings | `calendar-event`, `journal-text` |
| Announcements | `megaphone` |
| Portal | `phone` |
| Security | `shield-lock`, `key` |
| Platform | `building-gear`, `layers`, `toggles` |
| Audit | `journal-check` |
| CTA | `rocket-takeoff` |

---

## Chart kit summary

| Slide | Chart type | Purpose |
|-------|------------|---------|
| 03 | Clustered bar | Fragmentation “today” |
| 05 | Clustered column | Income vs expense trend |
| 06 | Donut | Membership status mix |
| 07 | Stacked bar | Tithe vs offering by church |
| 09 | Table + totals | Trial balance equality |
| 10 | Process / 3 boxes | Architecture (not Excel chart) |

All numeric charts: footer **“Sample demo data — not prospect figures.”**

---

## Screenshot drop-in map

| Slide | Files from checklist |
|-------|----------------------|
| 04 | `03-organization-hierarchy.png` |
| 05 | `01-mission-control.png`, `11-finance-trend.png` |
| 06 | `05-members-directory.png`, `visitors-directory.png` |
| 07 | `04-receipt-confirmation.png`, `giving-statement.png` |
| 08 | `07-announcements-calendar.png`, `meetings-detail.png`, `08-portal-mobile.png` |
| 09 | `reports-center.png`, `reports-tithe.png` |
| 10 | `09-permissions-matrix.png`, `10-platform-tenancy.png` |

---

## Regeneration

```bash
pip install python-pptx
python churchhub/marketing/presentation/generate_pitch_pptx.py
```

Output: `churchhub/marketing/presentation/ChurchHub_Enterprise_Pitch.pptx`
