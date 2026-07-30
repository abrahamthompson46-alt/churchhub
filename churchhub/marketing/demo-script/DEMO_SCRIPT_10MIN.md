# ChurchHub — 10-Minute Executive Demonstration Script

**Audience:** Church executives, pastors, treasurers, administrators  
**Duration:** 10:00  
**Environment:** Seeded demo tenant — mid-size conference, 2–3 churches, realistic members/finance data  
**Presenter roles in demo:** Overseer / Conference Admin (primary), switch briefly to Treasurer lens via Action Queue / Finance tabs  
**Do not show:** Real PII, live production data, stack traces, Django admin

---

## Pre-demo setup (5 minutes before)

| Check | Detail |
|-------|--------|
| Browser | Chrome/Edge, zoom 100%, hide bookmarks bar |
| Window | Full screen; optional presenter notes on second screen |
| Login | Pre-fill username only; password ready (or stay logged in on a hidden tab if policy allows) |
| Context | Active church selected (named demo church, not “All Churches”) |
| Data | Pending approval ≥1, open visitors ≥2, upcoming meeting, recent receipt, unread notification |
| Features | Remittance/welfare and reports available; payroll/assets optional if enabled |
| Backup | Screenshots from `SCREENSHOT_CHECKLIST.md` P1 set if live demo fails |

**Presenter voice:** Confident, pastoral, concrete. Prefer “what this means for Sunday” over feature jargon.

---

## At-a-glance timeline

| Time | Section | Primary screen |
|------|---------|----------------|
| 00:00 | Introduction | Title slide or login (idle) |
| 00:30 | Login | Staff Login → Dashboard |
| 01:00 | Dashboard | Mission Control |
| 02:00 | Membership | Member Directory → Profile |
| 03:00 | Visitors | Visitor Directory → Convert (preview) |
| 04:00 | Giving | Giving Center → Statement |
| 05:00 | Treasury | Record Receipt → Confirmation → Register |
| 06:00 | Reports | Report Center → Tithe report |
| 07:00 | Meetings & Church Life | Calendar → Meeting Detail |
| 08:00 | Platform Administration | Control Room → Tenancy |
| 09:30 | Closing | Dashboard or closing slide |

---

## 00:00 – 00:30 · Introduction (0:30)

**Screen:** Title slide *or* Staff Login idle (no typing yet).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 00:00–00:10 | Hold on brand / product name. Do not click. | “Good morning. In the next ten minutes I’ll show ChurchHub — the church management system built for Adventist (and multi-level) administration: from the local church to conference and beyond.” |
| 00:10–00:20 | Optional: point (don’t click) at audience roles on a slide: Pastor · Treasurer · Clerk · Overseer. | “We’ll walk the path your teams use every week — membership, visitors, giving, treasury, reports, meetings — and close with how the platform is operated safely across many churches.” |
| 00:20–00:30 | Transition: click into Staff Login if not already there. | “Everything you’re about to see respects roles, church scope, and audit — so pastors see pastoral work, treasurers see books, and executives see the roll-up.” |

**Transition cue:** Cursor to username field.

---

## 00:30 – 01:00 · Login (0:30)

**Screen:** Staff Login → Mission Control (load).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 00:30–00:38 | Click username → type demo user. Tab to password → type (or paste). | “Staff sign in through ChurchHub’s secure session login — same discipline you’d expect for financial and membership data.” |
| 00:38–00:45 | Click **Sign in**. Brief pause on load. Skip MFA unless demo policy requires it; if MFA appears: complete quickly, say one line below*. | “No separate apps for clerk vs treasurer — one workspace, permissions decide what appears.” |
| 00:45–00:55 | Land on Dashboard. Hover church switcher (do not change yet). | “We’re in *Demo Central Church* under a conference with multiple congregations — so hierarchy is real, not a flat single-church toy.” |
| 00:55–01:00 | Move cursor to KPI strip. | “This landing page is Mission Control.” |

\*If MFA shows: “High-privilege accounts can require a second factor — policy-controlled, not theater.”

**Transition cue:** Cursor over first KPI card.

---

## 01:00 – 02:00 · Dashboard (1:00)

**Screen:** Mission Control (scroll as needed).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 01:00–01:15 | Slowly pan across KPI strip (Tithe MTD, Combined, Remittance, member counts). Pause on finance KPIs. | “Executives and pastors get the pulse immediately: giving this month, remittance position, membership shape — scoped to the church you’re working in.” |
| 01:15–01:28 | Scroll to **Action Queue**. Hover 2–3 items (pending approvals, visitors, transfers) — click none yet. | “The Action Queue is the pastor and admin ‘to-do’: open visitors, pending transfers, financial approvals waiting for a second pair of eyes.” |
| 01:28–01:40 | Scroll to **teller / finance** section or trend chart. Hover bars. | “Treasurers see business date and teller activity — so Sabbath posting isn’t guesswork. Trends show income versus expense over recent months.” |
| 01:40–01:50 | Hover **This Week Pulse** chips if visible (birthdays, meetings, visitors). | “Pastoral care signals sit in the same place — birthdays, meetings, follow-ups — without hunting five menus.” |
| 01:50–02:00 | Click top nav **Members** (or Members mega-menu → Directory). | “Let’s start where ministry starts — people.” |

**Transition cue:** Member Directory loading.

---

## 02:00 – 03:00 · Membership (1:00)

**Screen:** Member Directory → Member Profile → (optional) Journey.

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 02:00–02:12 | On directory: click search box, type 2–3 letters of a demo surname. Show filtered results. | “Clerks and pastors search a living directory — filter by status, church, and more — always limited to churches you’re authorized to see.” |
| 02:12–02:25 | Click a well-populated member row. Open **Member Profile**. Slow scroll: personal, membership, family. | “A member profile is the single record: identity, membership status, family, church placement — not a spreadsheet tab per department.” |
| 02:25–02:40 | Click **Journey** / timeline if available; else scroll to history/roles section. Hover baptism or transfer event. | “The journey timeline preserves history — baptism, transfer, leadership — so we never ‘overwrite’ someone’s story.” |
| 02:40–02:50 | Hover nav: Families / Leadership / Transfers (don’t deep-dive). | “Same module covers families, leadership assignments, baptisms, and transfers with audit trail.” |
| 02:50–03:00 | Mega-menu or Members → **Visitors**. | “Guests become discipleship opportunities — Visitors.” |

**Transition cue:** Visitor Directory.

---

## 03:00 – 04:00 · Visitors (1:00)

**Screen:** Visitor Directory → Add Visitor (or open existing) → Conversion entry (stop before save).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 03:00–03:15 | On visitor list: point at open follow-ups / status column. Click one open visitor. | “Pastors and greeters capture who visited, who invited them, and what’s next — so Sabbath guests don’t disappear by Tuesday.” |
| 03:15–03:30 | Scroll visitor detail / edit fields: interests, follow-up, assigned elder if present. | “Follow-up is assignable and visible in the Action Queue we saw on the dashboard.” |
| 03:30–03:48 | Click **Convert to member** (or equivalent). Show conversion form; **do not submit**. Hover mapped fields. | “When they’re ready, conversion carries visit history into membership — continuity instead of re-typing.” |
| 03:48–04:00 | Cancel/back. Open **Finance** or **Giving** from mega-menu → Giving Center. | “Stewardship next — how we honor giving with privacy and clarity.” |

**Transition cue:** Member Giving Center.

---

## 04:00 – 05:00 · Giving (1:00)

**Screen:** Giving Center → Individual Giving Statement.

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 04:00–04:15 | Giving Center: search/select the same demo member. Show recent giving summary. | “Giving lookup is permission-controlled. Treasurers and authorized stewards see contribution history; casual users don’t.” |
| 04:15–04:35 | Open **Individual Giving Statement**. Scroll totals by fund/category if shown. Hover print/export if available (don’t need to download). | “Members and finance teams get a clear statement — tithe, offerings, period totals — suitable for counseling or year-end conversations.” |
| 04:35–04:50 | Briefly return or point upward to nav: Remittance / Cut-off (hover only). | “At conference level, remittance and monthly cut-off roll local faithfulness into organizational accountability — we’ll touch cut-off from the treasurer path.” |
| 04:50–05:00 | Finance mega-menu → **Record Receipt** (or Treasury → Record Receipt). | “Now the Sabbath desk — recording the offering.” |

**Transition cue:** Record Receipt form.

---

## 05:00 – 06:00 · Treasury (1:00)

**Screen:** Record Receipt → Confirmation → Transaction Register (optional Approvals hover).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 05:00–05:18 | On Record Receipt: select member or anonymous as appropriate; enter a small demo amount; choose tithe/offering category; ensure business date visible. | “Tellers post against the church’s business date — not whatever the laptop clock says. Categories and funds stay consistent with your chart.” |
| 05:18–05:30 | Click **Save / Post** (use a reversible demo amount). Land on **Receipt Confirmation**. | “Every posting lands on a confirmation you can print or file — reference, amount, method, status.” |
| 05:30–05:42 | On confirmation: hover print actions; point at status (approved/pending). | “Sensitive changes use maker-checker where configured — one person records, another approves — so books stay trustworthy.” |
| 05:42–05:52 | Navigate to **Transaction Register**. Filter today’s or this week’s entries. | “The register is the operational ledger UI — searchable, church-scoped, auditable.” |
| 05:52–06:00 | Top nav → **Reports**. | “Leaders don’t live in journals — they live in reports.” |

**If posting is risky in shared demo:** walk a *pre-created* confirmation URL and say “I’ve opened a receipt we posted earlier this morning.”

**Transition cue:** Report Center.

---

## 06:00 – 07:00 · Reports (1:00)

**Screen:** Report Center → Tithe & Offering (or Financial Summary) → mention Trial Balance.

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 06:00–06:15 | Report Center: scroll catalog. Hover Member vs Finance vs Advanced reports. | “One report center — membership, attendance, stewardship, and accounting — filtered by what your role may run.” |
| 06:15–06:35 | Open **Tithe & Offering** (or Financial Summary). Set a clear date range (this month). Click run/view. Pan totals. | “Pastors and executives answer ‘how are we doing in stewardship?’ in seconds — by church, period, and scope you already selected.” |
| 06:35–06:48 | Hover export actions (CSV / Excel / PDF) without long wait. If async export: open status briefly or just point. | “Exports are available for board packs — still permission-aware, still tenant-scoped.” |
| 06:48–06:55 | Back to catalog; point at **Trial Balance** / Income Statement (don’t fully run unless fast). | “For treasurers and auditors: trial balance, income statement, balance sheet — double-entry integrity, not a second set of books.” |
| 06:55–07:00 | Church Life / Meetings → **Calendar** or **Meetings**. | “Ministry rhythm — calendar and meetings.” |

**Transition cue:** Upcoming Calendar or Meetings list.

---

## 07:00 – 08:00 · Meetings & Church Life (1:00)

**Screen:** Upcoming Calendar → Meeting Detail → (optional) Announcements list.

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 07:00–07:15 | Calendar: point at meetings, birthdays, announcements in the upcoming view. | “Church Life pulls the week together — meetings, birthdays, communications — so the pastoral team shares one calendar truth.” |
| 07:15–07:35 | Click an upcoming **Meeting**. On detail: scroll agenda, minutes, decisions/actions. Hover attendance if present. | “Board and committee work isn’t email archaeology: agenda, minutes, decisions, and attendance live on the meeting record — with approval flow for minutes when you need governance.” |
| 07:35–07:48 | Navigate to **Announcements** list; open one published item. | “Announcements publish to the church — and the member portal can surface the same message to members on their phones.” |
| 07:48–08:00 | Optional 5s: resize or cut to Portal Home bookmark (mobile width) — then return *or* say “Portal demo available after.” Navigate to Platform (or announce switch). | “Finally — how ChurchHub itself is run for many denominations and churches.” |

**Transition cue:** Platform Control Room (platform operator login/tab).

**Tip:** Keep Platform in a second browser profile already logged in as platform operator to avoid burning clock on re-auth.

---

## 08:00 – 09:30 · Platform Administration (1:30)

**Screen:** Control Room → Denominations/Subscriptions → Tenant or Applications → Feature Registry (hover).

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 08:00–08:15 | Platform **Control Room**. Pan operator dashboard widgets. | “Platform Administration is a separate lane from the church workspace — ChurchHub operators manage the SaaS wall: denominations, tenants, health.” |
| 08:15–08:35 | Open **Denominations** or **Subscriptions** (tenancy shot). Hover plans/subscriptions. | “Each denomination is isolated. Subscriptions and plans control what a tenant may use — payroll, assets, advanced ledger — without mixing data across the wall.” |
| 08:35–08:55 | Open **Applications** or **All Churches / Tenant Detail**. Hover status, provision actions (don’t destroy data). | “Public church registration can feed an application queue. Operators provision tenants and hierarchy instead of hand-building databases.” |
| 08:55–09:10 | Open **Feature Registry**. Toggle nothing; point at feature flags. | “Features are switched deliberately per church — so a pilot congregation can gain assets or payroll when ready.” |
| 09:10–09:25 | Open **Audit Log** or **Operations Health** briefly. | “Platform actions are audited. Operations health keeps the runbook honest — because church finance can’t afford silent failure.” |
| 09:25–09:30 | Switch back to institution Dashboard (or closing slide). | “That’s the full arc — congregation to conference to platform.” |

**Transition cue:** Closing.

---

## 09:30 – 10:00 · Closing (0:30)

**Screen:** Mission Control *or* closing slide with contact / next steps.

| Time | Mouse / screen | Narration |
|------|----------------|-----------|
| 09:30–09:42 | Hold Dashboard KPIs + Action Queue in frame (or slide: three bullets). | “ChurchHub gives executives visibility, pastors a pastoral queue, treasurers accountable books, and administrators clean membership and access control — in one secure system.” |
| 09:42–09:52 | Stop moving mouse. Optional: show QR/link slide. | “Recommended next step: a guided pilot on your conference hierarchy with your chart of accounts and two local churches.” |
| 09:52–10:00 | Smile; open for questions. | “I’m happy to go deeper on remittance, permissions, or the member portal — what matters most to your team?” |

---

## Role call-outs (use if someone asks mid-demo)

| Role | Re-emphasize |
|------|----------------|
| **Executive / Overseer** | Dashboard KPIs, hierarchy, reports roll-up, remittance cut-off, platform tenancy |
| **Pastor** | Action Queue, visitors, meetings/minutes, calendar, announcements, portal praise/prayer |
| **Treasurer** | Business date, receipt → confirmation, approvals, register, giving statements, trial balance |
| **Administrator / Clerk** | Member directory, transfers, families, permissions matrix, invitations |

---

## Timing recovery cheats

| If behind by… | Cut |
|---------------|-----|
| 30–45s | Skip visitor conversion form; skip announcement detail |
| ~1 min | Skip ledger mention; skip portal flash; shorten platform to Control Room + Subscriptions only |
| >1 min | Jump from Treasury confirmation → one report → Closing; offer portal/platform as “appendix” |

| If ahead by… | Add |
|--------------|-----|
| 20–30s | Permissions **Role Matrix** (Administration) — one sentence on least privilege |
| 30–45s | Member **Portal Home** at mobile width — prayer/giving cards |
| 45–60s | **Bank reconciliation** list or **Pending financial approvals** queue |

---

## Demo data wishlist (seed before recording)

- [ ] Conference + 2 churches; active church selected  
- [ ] 20+ members; 1 family; 1 leadership role; 1 transfer pending  
- [ ] 3+ visitors (at least 1 open follow-up)  
- [ ] 1 meeting this week with agenda/minutes draft  
- [ ] 1 published announcement; calendar shows birthday  
- [ ] 1 pending financial approval *or* fresh receipt to post  
- [ ] Giving history on demo member for statement  
- [ ] Platform operator login with denominations + 1 subscription visible  

---

## Related assets

- Screenshot checklist: `churchhub/marketing/brochure/SCREENSHOT_CHECKLIST.md`  
- Brochure PDF: `churchhub/marketing/brochure/ChurchHub_Enterprise_Brochure.pdf`  
- Capture folder: `churchhub/marketing/screenshots/`
