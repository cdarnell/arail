# ARAIL Portal Simplification — Review & Proposal

**Date:** 2026-05-08
**Status:** Pre-sprint exploration. Decisions still needed before `/sprint` can fire.
**Owner:** Charles
**Trigger:** "users feel overwhelmed; want progressive disclosure with double-clicks for advanced; keep core surfaces front and center; an Expand All escape hatch for power users."

---

## 1. Win condition (the one sentence)

> **A returning user can land on any surface, see only the 3–5 things that matter
> right now, and reach every advanced control in ≤2 clicks.**

That single sentence drives every decision below. If a proposal doesn't move us
toward it, drop the proposal. If it does, we keep it even when it costs effort.

The opposite — and what we have today on chat/admin — is: every dial visible
all the time, on the theory that hiding things hides power. That's wrong. Hiding
isn't lossy if recovery is cheap. The cost is the always-on cognitive load.

---

## 2. Five disclosure patterns to apply consistently

Not a list of one-off tweaks. These are the named patterns we use everywhere so
the portal feels coherent.

### Pattern A — **Hero pair + "More ▾"**
For meter strips and stat rows: show 2 hero metrics, hide the rest behind one
disclosure. The hero pair is *prescriptive* — it's the lab's editorial choice
about what matters most.

> Dashboard cost meter: today 6 stats are always on. Hero pair = (Net saved
> this month, Lifetime tokens). Behind ▾: cloud equiv, energy, inferences,
> active backend.

### Pattern B — **Preset row + ⚙ drawer**
For tunables: keep curated preset buttons always visible (one click = good
defaults), hide raw sliders/inputs behind a gear icon that opens a side drawer.

> Chat tab: Factual / Code / Creative / Custom buttons stay on the composer.
> Temp, top_p, top_k, freq penalty, max_tokens — all behind ⚙. The drawer
> appears as a slide-in from the right, not an inline expansion that pushes
> the chat window down.

### Pattern C — **Active-only cards**
For agent / service / experiment grids: show only items that did something
recently. Idle items collapse to a single "3 idle (Buddy, Browser, …)" chip
that expands on click.

> Agents tab: today shows 4 cards × 4 buttons × ~10 trail items each. With
> active-only: if Researcher ran in last hour, show its full card; Buddy
> idle 3h → collapsed into a chip.

### Pattern D — **Per-card disclosure + page-level "Expand all"**
Every collapsible block uses native `<details>` so a single button at the top
of the page can fire `document.querySelectorAll('details').forEach(d => d.open = true)`.
Power users get the full shebang in one click. Default is collapsed.

> The "Expand all" affordance is small (text link or 16px icon, not a button)
> placed top-right of each page. Sticky so it's always reachable while
> scrolling. Toggles to "Collapse all" when most details are open.

### Pattern E — **Drawer-based advanced surfaces**
Advanced/admin pages become slide-in drawers from the right edge, NOT
nav destinations. The user stays anchored on their current task; the drawer
overlays without losing context.

> Plugins, Tuning, Admin diagnostics — all become drawers triggered from a ⚙
> in the nav. The user keeps the chat or dashboard in view behind the drawer.
> Closing returns them where they were.

---

## 3. Surface-by-surface proposals

Each below has BEFORE / AFTER ASCII wireframe + a numbered list of changes
ranked by impact. Symbols: `▾` disclosure trigger, `⚙` advanced, `[…]` chip /
button, `═` always-on / hero, `┄` collapsed / dimmed.

### 3.1 Chat (highest impact — currently the densest surface)

**BEFORE** (chat.html: 3,258 lines, "Advanced Tunables" open by default):
```
┌──────────────────────────────────────────────────────────────────┐
│ NAV  Dashboard · Chat · Autoresearch · KB · Agents · Skills      │
├──────────────────────────────────────────────────────────────────┤
│ [Model: Qwen-8B ▼]  [Temp: 0.7]  [☐ Stream]  [Compare]           │
├──────────────────────────────────────────────────────────────────┤
│ ╔════ ACTIVE MODELS RAIL (always visible) ════╗                  │
│ ║  Qwen-8B • mlx • 12 tok/s • 1.2GB           ║                  │
│ ╚══════════════════════════════════════════════╝                  │
│                                                                   │
│      [chat transcript area — actual conversation goes here]       │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│ Composer: [_________________________________] [Send]             │
├──────────────────────────────────────────────────────────────────┤
│ ▼ Advanced Tunables (OPEN by default — 6 cards, ~40% viewport)   │
│   ┌─Sampling─────┐ ┌─Length──────┐ ┌─Penalties───┐               │
│   │ temp [0.7]   │ │ max_tok 512 │ │ freq_pen 0  │               │
│   │ top_p [0.9]  │ │ ctx 4096    │ │ pres_pen 0  │               │
│   │ top_k [40]   │ │ memory ☑    │ │             │               │
│   └──────────────┘ └─────────────┘ └─────────────┘               │
│   ┌─Format────┐ ┌─Repro──┐ ┌─Runtime────┐                        │
│   │ stop […]  │ │ seed - │ │ backend mlx│                        │
│   └───────────┘ └────────┘ └────────────┘                        │
├──────────────────────────────────────────────────────────────────┤
│ ┌─System Prompt──────────┐ ┌─Model Browser──────────┐             │
│ │ [4-row textarea]       │ │ [10 model cards w/      │             │
│ │ help text…             │ │  inline stats + badges] │             │
│ └────────────────────────┘ └─────────────────────────┘             │
└──────────────────────────────────────────────────────────────────┘
```

**AFTER** (chat dominant, presets always visible, raw tunables in drawer):
```
┌──────────────────────────────────────────────────────────────────┐
│ NAV  Dashboard · Chat · Autoresearch · KB · Agents       Expand▾ │
├──────────────────────────────────────────────────────────────────┤
│ Qwen-8B • mlx • 12 tok/s              ⚙ Tune    System ▾   Models▾│
├──────────────────────────────────────────────────────────────────┤
│                                                                   │
│      [chat transcript — fills 70%+ of viewport]                   │
│                                                                   │
│      … assistant: streaming reply tokens here …                   │
│                                                                   │
│                                                                   │
├──────────────────────────────────────────────────────────────────┤
│ [Factual] [Code] [Creative] [Custom]  ←presets always visible    │
│ Composer: [_________________________________] [Send]  ☐ Stream   │
└──────────────────────────────────────────────────────────────────┘

  ⚙ Tune (slide-in drawer from right when clicked):
   ┌────────────────────────┐
   │ Sampling               │
   │  temp     [0.7]        │
   │  top_p    [0.9]        │
   │  top_k    [40]         │
   ├────────────────────────┤
   │ Length & memory   ▾    │
   │ Penalties         ▾    │
   │ Format & stop     ▾    │
   │ Repro             ▾    │
   │ Runtime           ▾    │
   ├────────────────────────┤
   │ Save as preset…        │
   └────────────────────────┘
```

**Changes (ranked by impact):**
1. **Remove `open` from Advanced Tunables `<details>`.** Single line. Massive payoff.
2. **Add preset row above composer**: `Factual` (temp 0.3, top_p 0.9), `Code`
   (temp 0.2, stop tokens), `Creative` (temp 0.95, top_p 0.95), `Custom` (opens
   ⚙). Click = applies preset to current model + flashes the new values briefly.
3. **Move tunables grid into right-side ⚙ drawer.** Sliding overlay; doesn't push
   chat down. Sub-sections (Length, Penalties, Format, Repro, Runtime) are
   `<details>` collapsed inside the drawer.
4. **System Prompt collapses to summary.** Default: "System prompt: 'You are a
   helpful research assistant…' (40 chars) — Edit ▾". Click to expand the
   textarea inline.
5. **Model browser → "Models ▾" in header.** Click pops a dropdown with the
   model list; current selection is the chip in the header. No more permanent
   right-side pane.
6. **"Active models" rail moves to a small pill** in the header next to the
   model name. Frees the entire row above the chat window.

### 3.2 Dashboard (landing page — moderate density, big wins available)

**BEFORE:**
```
┌──────────────────────────────────────────────────────────────────┐
│ NAV ················                                              │
├──────────────────────────────────────────────────────────────────┤
│ ╔ COST METERS (always-on, 6 wide) ════════════════════════════╗  │
│ ║ Cloud  $0.24 │ Energy $0.001 │ Saved $0.24 │ Calls 109     ║  │
│ ║         │ Tokens 371k  │ Backend MLX                       ║  │
│ ╚════════════════════════════════════════════════════════════╝  │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Quick Actions (6 buttons)────────────────────────────────────┐ │
│ │ [Chat][Health][Graph][Updates][Plugins][Restart]             │ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Service Status (chips: portal, knowledge-canvas, …)─────────┐ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Lab Shortcuts (4 link buttons)──────────────────────────────┐ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Mission card (~250 lines: goal input, swarm plan,           │ │
│ │  worker lanes, phases, checklist when expanded)─────────────│ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Mission Status: progress ring + experiment table───────────┐  │
│ └────────────────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Activity Feed (live SSE stream)─────────────────────────────┐ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Knowledge Base hero (5 type tiles + recent + wiki)──────────┐ │
│ └─────────────────────────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────┤
│ ┌─Agent Consent (unbounded list of pending requests)──────────┐ │
│ └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

**AFTER** (mission front and center, meters compressed, secondary collapsed):
```
┌──────────────────────────────────────────────────────────────────┐
│ NAV ················                                Expand all ▾ │
├──────────────────────────────────────────────────────────────────┤
│ ═ Net saved $0.24 ═ ═ 371k tokens ═      [More metrics ▾]        │
├──────────────────────────────────────────────────────────────────┤
│ ╔══ MISSION ═══════════════════════════════════════════════════╗ │
│ ║ ◎ Investigate speculative decoding tradeoffs                ║ │
│ ║   Started 2h ago · 3 of 5 experiments done · ETA ~40m       ║ │
│ ║   ▾ swarm plan  ▾ activity  ▾ report                        ║ │
│ ╚══════════════════════════════════════════════════════════════╝ │
├──────────────────────────────────────────────────────────────────┤
│ ▾ Activity feed (last 5 events visible; click for full)          │
│ ▾ Knowledge — 14 docs, wiki rebuilt 8m ago    [Open KB →]        │
│ ▾ Agent consent — 0 pending                                      │
├──────────────────────────────────────────────────────────────────┤
│ Quick: [Chat]  [Health]  [Graph]  ⚙ More                         │
│ Status: ● portal  ● knowledge-canvas  (3 idle)                   │
└──────────────────────────────────────────────────────────────────┘
```

**Changes (ranked by impact):**
1. **Mission card promotes to top, becomes the visual anchor.** Below the meter,
   above everything else. The lab's purpose is the operator's current goal —
   show it.
2. **Cost meter strip → 2-up hero pair.** Net saved + lifetime tokens. "More
   metrics ▾" reveals the other 4. Same numbers, 1/3 the screen real estate.
3. **Quick Actions → 3 visible + ⚙ More.** Chat / Health / Graph stay (the
   common verbs). Updates / Plugins / Restart go behind ⚙.
4. **Service Status → single status line with idle collapsed.** "● portal ●
   knowledge-canvas (3 idle)" — click "(3 idle)" to expand.
5. **Activity Feed / KB hero / Agent Consent → all collapsed by default**,
   each shows a 1-line summary that expands.
6. **Lab Shortcuts card removed.** Already covered by nav.
7. **Add page-level "Expand all ▾"** top-right of the page (pattern D).

### 3.3 Agents (moderate density)

**BEFORE:** 4 cards always full-size, each with stats + 5–10 trail items + 4 buttons (~36 buttons total visible).

**AFTER** (active-only):
```
┌─ Researcher ── 3.4k tok · 5 captures · 87% ──────────────────────┐
│ Working on: speculative decoding tradeoffs                       │
│ Last 3 moves:                                                    │
│  · Read paper "Med-Spec-2 (2024)" 4m ago                         │
│  · Drafted experiment plan 6m ago                                │
│  · Loaded baseline model 12m ago                                 │
│  ▾ full history (47 events)    [Pause] [Inspect] [Talk]          │
└──────────────────────────────────────────────────────────────────┘

3 idle agents: Curator · Browser · Buddy   [show ▾]
```

**Changes:**
1. **Auto-collapse idle agents** (no activity in last 30 min). Header chip
   shows them as a row.
2. **Trim activity trail to last 3 events**, expand for full history.
3. **Default to one card visible** (the active one). Idle cards expand on
   click without re-rendering the whole grid.

### 3.4 Knowledge Base (moderate density)

**Changes:**
1. **Ingest tiles → single "Add content ▾" button** in toolbar that pops a
   menu (Docs, Images, Video, Audio, URL, Starter pack). Saves ~80 lines of
   always-on tile chrome.
2. **Welcome pane** (graph mini + agent + recent + tags) → 4 collapsed sections;
   first-time users see hints to open them; returning users see content state.
3. **Toolbar power-user buttons (Process inbox, Rebuild) → ⚙ menu.** They
   shouldn't be at the same prominence as Search and Open.

### 3.5 Autoresearch (moderate, mostly fine)

**Changes (light touch):**
1. **Cockpit strip** (6 step circles + progress bar) → compact "Step 3/6 ●
   running" pill when not interactive.
2. **Inside swarm review modal**, sub-sections (Worker Lanes, Phases,
   Checklist) start collapsed.

### 3.6 Tuning (max-tier, density expected but trimmable)

**Changes:**
1. **Two architecture diagrams** (MLX, AeroLLM) → single "Architecture ▾"
   accordion. Casual user doesn't see them.
2. **Tech explanation cards** (4 of them) → "Where the gains come from ▾".

### 3.7 Admin (max-tier — structural overhaul candidate)

This is the densest page after chat. Trying to do too much. Recommend
splitting:

**BEFORE:** Quick Actions + Status + Production Readiness + Models + Terminal +
Health Checks + Components & Graph + Activity + Help (9 sections, ~1500 lines).

**AFTER:** tab-internal layout + drawer for terminal + dedicated /docs/admin.
```
Admin
├ [Status]  [Models]  [Diagnostics]  [Activity]
│
├ Status pane:
│  Production readiness summary (3 hero numbers)
│  Service health (compact list, click for details)
│
├ Models pane:
│  Model search/filter
│  Paginated grid (10 per page)
│
├ Diagnostics pane:
│  Health check button → modal (already exists)
│  Components table (paginated)
│  Graph preview thumbnail → click to open /graph full page
│
└ Activity pane:
   Activity log (scrolling)
```
- **Remove duplicate Quick Actions** (already on dashboard).
- **Move Terminal** to `/terminal` only (it has its own page already; the
  embedded iframe is duplicate weight).
- **Move Help & Reference** to dedicated `/docs/admin` page with sidebar nav.
- **Tabs** instead of vertical stack reduces 1500 lines to 400 visible at a time.

### 3.8 Notebooks — already spartan. No changes.
### 3.9 Nav — already clean. Add Expand-all link top-right pattern.

---

## 4. Bolder ideas worth piloting (not safe tweaks — structural)

These go beyond "hide the dial". Pick one if you want to swing.

### 4.1 Lab Quiet Mode toggle
A nav-level switch: **Lab Mode** (everything visible, current behavior with
disclosure) vs **Quiet Mode** (only the Mission card + Chat + the 2-up meter).
Persists per-user. Quiet mode is the default for first-time visitors; Lab mode
is opt-in for daily operators. Like browser reader mode but for your lab.

### 4.2 "Now Playing" persistent strip
A 24-pixel strip at the bottom of every page showing: current goal title +
active backend + current token rate + halt button. Replaces the per-page
status duplication. Operator always knows the lab's state without looking up.

### 4.3 Today-bounded dashboard
Default dashboard shows last-24h activity, today's experiments, current session
costs. "All time ▾" reveals lifetime totals. Reduces cognitive load of staring
at "lifetime tokens 371k" when the question is "what did I do today?".

### 4.4 Buddy-narrated landing
Instead of a 9-section dashboard, the landing is Pip (the buddy agent) showing
3 sentences:
> "You ran 3 experiments today. Researcher is currently deep on
> spec-decode tradeoffs (~40m left). I noticed 2 papers worth reading —
> want me to summarize?"
With links: [resume mission] [read summaries] [open dashboard]. The
9-section dashboard is one click away — but most days you don't need it.

### 4.5 Drawer-everything for advanced
Plugins, Tuning, Admin all become slide-in drawers from the right edge of
the dashboard or chat. You never lose your current task to "navigate to
admin". This is the most invasive change but the strongest reduction in
context switching.

---

## 5. Recommended phased plan

### Phase 1 — small wins (1 sprint, ~1-2 days)
The "free" changes — defaults flipped, no new components.

- [ ] Chat: remove `open` from Advanced Tunables `<details>`
- [ ] Dashboard: 2-up hero meter pair, "More metrics ▾" reveals the other 4
- [ ] Dashboard: Quick Actions trimmed to 3 + ⚙ More
- [ ] Dashboard: Service Status idle services collapsed into "(N idle)" chip
- [ ] Knowledge: ingest tiles → single "Add content ▾" button
- [ ] Agents: trim trails to last 3 events, "show full history" toggle
- [ ] Tuning: collapse architecture diagrams + tech cards behind accordions
- [ ] Admin: remove duplicate Quick Actions card

These are surgical and cumulative. Each is a 5–30 line diff. Together they
materially reduce density on every surface.

### Phase 2 — preset row + drawer (1 sprint, ~3-4 days)
The chat tab gets the preset bar + ⚙ slide-in drawer (Pattern B). New
component: side drawer overlay (reusable for Phase 4).

- [ ] Build `<arail-drawer>` reusable web component or template partial
- [ ] Chat: preset row (Factual / Code / Creative / Custom)
- [ ] Chat: tunables grid moves into ⚙ drawer
- [ ] Chat: System Prompt collapses to summary line
- [ ] Page-level "Expand all ▾" affordance (top-right, sticky), reusable
      across surfaces

### Phase 3 — active-only patterns (1 sprint, ~2-3 days)
Server already knows which agents/services are idle; surface uses that.

- [ ] Agents: idle agents auto-collapse to chip
- [ ] Dashboard: Activity / KB / Consent → 1-line summaries with disclosure
- [ ] Mission card promotion to dashboard top anchor

### Phase 4 — admin restructure (1 sprint, ~3-5 days)
The biggest single page. Tabs + drawer + dedicated docs page.

- [ ] Admin tab structure (Status / Models / Diagnostics / Activity)
- [ ] Move embedded terminal out of admin
- [ ] Move Help & Reference to `/docs/admin` with sidebar nav
- [ ] Models grid pagination
- [ ] Maybe: Plugins/Tuning move to drawer (Pattern E) — defer to Phase 5

### Phase 5 — optional bolder bets
Discuss separately. Quiet Mode, Now Playing strip, Buddy-narrated landing,
Drawer-everything. These are worth piloting but each is its own sprint with
its own win condition. Don't bundle.

---

## 6. Open questions for the owner

Things I can't decide for you:

1. **Quiet Mode vs always-Lab Mode (4.1):** worth piloting, or feels like
   feature bloat?
2. **Now Playing strip (4.2):** the persistent goal/backend/tok-rate strip —
   useful constant context, or visual noise?
3. **Buddy-narrated landing (4.4):** is this *the* product (lab buddy is the
   front door) or a side experiment?
4. **Tier max-only complexity:** admin and tuning are already gated to max
   tier. Does "users overwhelmed" include max-tier users, or only min-tier?
   (If only min-tier — Phase 4 deprioritizes.)
5. **Telemetry to validate:** before Phase 1 ships, do you have ANY signal
   on what users actually click vs ignore? If not, even rough click logging
   on the dashboard would tell us within a week which sections are dead
   weight and which are load-bearing.
6. **Mobile/tablet:** is this a desktop-only target, or do you need the
   simplification to also work at narrow widths? (Affects drawer widths, the
   2-up meter pair, and tab vs vertical stack on admin.)

---

## 7. What this review does NOT change

To be clear about scope:

- **No functionality removed.** Every dial/button still reachable.
- **No backend changes.** Pure template/CSS/JS edits, except the page-level
  "Expand all" affordance which is one new ~30-line JS helper.
- **No API contracts touched.** All endpoints stay; we just collapse what they
  feed.
- **No tier changes.** Min vs max stays as is.

This is a UX surface re-prioritization, not a re-architecture. The
infrastructure to do it (`<details>`, modals, drawer modals) is already in
place — what's missing is consistent application of the patterns and the
courage to set most defaults to closed.

---

## Next step

If this resonates: I'd suggest committing this file, then spinning a
proper `/sprint` for **Phase 1 only**. Phase 1 is small enough to ship as
one cohesive change, will materially reduce density on every surface, and
gives us real-world feedback before committing to the bigger Phase 2-4 work.

If anything in here is wrong (especially §1 win condition, §6 open questions),
push back — those are the levers that change the rest.
