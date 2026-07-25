# EXPERIENCE_SPEC — ARAIL's first-impression experience

> Phase 0 (discover) + Phase 1 (design) for
> `docs/briefs/first-impression-experience.md`. Companion: `VISION.md` in
> this directory. **This is a design artifact. No code, template, or
> script in the repo has been changed to produce it.** Every factual claim
> below carries a `file:line` reference verified against the working tree
> at commit `581d161` (branch `qukaizen/arail-workbench-into-admin`) during
> this session — three independent read-only exploration passes plus
> first-hand re-reads of the load-bearing lines.

---

## Phase 0 — Discovery: the map, as it exists today

### 0.1 The two onboarding paths, side by side

| | Browser (`/welcome`) | CLI (`./arailctl setup`) |
|---|---|---|
| Passphrase | Step 1, server-rendered (`welcome.html:181-241`) → `POST /api/welcome/setup` | `capture_password()` (`scripts/setup.sh:1359-1447`) |
| Network mode | Step 2, client JS `showModeStep()` (`welcome.html:322-416`) → `POST /api/airgap/toggle` | `capture_mode()` (`setup.sh:1300-1345`) — copy near-duplicates Step 2 |
| World | Step 3, client JS `showWorldStep()` (`welcome.html:420-533`) → `POST /api/worlds/select`, a **real mount** | **Never asked.** No World picker in `setup.sh` at all. |
| Competing question | none | `capture_goal()` (`setup.sh:1882+`): 9-option `LAB_INTENT` taxonomy + free-text research goal + work-window hours → `.env` + `lab/data/goals/bootstrap_goal.json` |
| End state | Lands on `/` with a World mounted (or explicitly skipped) | Lands on `/` **World-less**, with a bootstrap goal already set |

`welcome.html:238-239` tells the CLI user "Either path lands at the same
place." This is false today — confirmed by reading both code paths. The
two flows ask disjoint questions and produce different final states.

### 0.2 The critical gap — `welcome_page()` redirect

`src/arail/portal/app.py:1211-1222`:

```python
@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request):
    """First-run onboarding form. Allowed by the middleware regardless
    of password state, so a fresh lab can land here on first open."""
    # If they're already onboarded, send them home — nothing to do here.
    if _lab_password_set():
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "welcome.html", {
        **_identity_ctx(),
        "current_lab_name": effective_identity().name,
    })
```

Confirmed: any request to `/welcome` from an onboarded browser — including
one a CLI-onboarded user might type manually — 302s to `/` unconditionally.
There is **no `?step=` query param anywhere in this handler or in
`app.py`** (grep-confirmed). Steps 2 and 3 are pure client-side JavaScript,
reachable only by falling through from the Step-1 success handler
(`welcome.html:282-284`). They have no URL of their own. A CLI-onboarded
user cannot reach the World picker by any means short of editing `.env` by
hand or running `./arailctl world mount <dir>` from a terminal.

`onboarding_gate` (`app.py:282-329`) is the middleware that makes `/welcome`
reachable pre-onboarding at all; it is the innermost of six
`@app.middleware("http")` registrations (the docstring at `app.py:344-349`
claiming it's "second-outermost" is stale — `local_trust_boundary`,
registered last at `app.py:563`, is actually outermost). "Onboarded" means
exactly `_lab_password_set()` (`app.py:250-276`): `ARAIL_PASSWORD` present
in `.env` (or live env) and not in `{"", "change-me", "__needs_setup__"}`.
There are no cookies, no sessions — this one file-backed check is the
entire authorization model, so it is also the entire "has this person been
through onboarding" signal available to any redesign.

### 0.3 What happens to a CLI-onboarded user today

1. `./arailctl setup` sets a real passphrase, asks network mode, asks a
   goal — never mentions Worlds.
2. `./arailctl start`, open `http://127.0.0.1:8080/` → dashboard.
3. `effective_identity()` (`src/arail/identity.py:90-206`) resolves via
   `_unmounted_identity()` (`identity.py:70-87`) since `current_mount()`
   (`src/arail/world_mount.py:634-645`) returns `None` — no
   `lab/data/world-mount.json` exists. Brand defaults to "Autoresearch AI
   Lab", `lab_theme` defaults to "Making SSD-hosted model inference
   faster…", `intent_name` defaults to "AI Engineer".
4. Nav badge reads `◇ AI Lab ▾` (`templates/_nav.html:33`).
5. The one built-in nudge — `dashboard.html:1980-1987`, "Your lab studies
   nothing yet — mount or forge a World →" — **only renders when the
   mission card is empty** (`#mission-empty` visible). Because CLI setup
   already wrote a bootstrap goal (`setup.sh:1889-1993` →
   `lab/data/goals/bootstrap_goal.json`), the mission card is *not* empty.
   **The one nudge that exists is suppressed for exactly the users who
   most need it** — a chain confirmed end-to-end by reading
   `dashboard.html`'s conditional, `world_mount.py`'s mount check, and
   `setup.sh`'s goal-capture step.
6. The only remaining discovery surfaces are the nav World switcher
   dropdown (present on every page but easy to miss — a small `◇ AI Lab ▾`
   with no call-out) and `/dac`'s "Mount a World" empty state, neither of
   which is surfaced proactively.

This is the gap the brief is built around, and discovery confirms it in
full.

### 0.4 The Worlds subsystem — what a mount actually does

`mount()` (`src/arail/world_mount.py:1370-1449`), in order:

1. **Verify-first gate**: `load_bundle` → `verify_seal` → `check_compat` →
   `check_categories` (:1395-1400). Nothing on disk changes if any step
   fails.
2. **Stage**: copies the bundle's 6 sealed files + `SKILL.md` into
   `lab/pkb/sources/.staging-<slug>/`, generates one wiki-ready markdown
   page per term (`_write_term_pages`, :1124 — 339 pages for the `ai`
   bundle today) plus an index page, then an atomic two-rename swap into
   `lab/pkb/sources/world-<slug>/`.
3. **Sweep**: `_sweep_other_worlds` (:1280-1309) **deletes every other
   `sources/world-*/` directory.** This is deliberate design ("A World IS
   the lab's dataset… not an accumulation of every World ever mounted",
   module docstring) — but it happens with **zero confirmation** anywhere
   in the current call chain: not in the CLI (`world mount`/`world swap`
   have no confirm prompt), not in the nav switcher, not in `/worlds`
   (only Delete has a `confirm()`, `worlds.js:692`), not in welcome Step 3.
4. **Index**: LanceDB upsert of the staged pages.
5. **Write the pointer last**: `lab/data/world-mount.json`, atomically
   (:1426, `_write_record` :648-658). This file's presence/absence is the
   sole "is a World mounted" signal (`current_mount()`, :634-645).
6. Catalog adopt, KB refresh (wiki rebuild), capability + model-hint
   sidecars — all best-effort, none block the mount.

**Theming is not part of the mount.** `face.json.theme`
(`dac.world-theme/v1`) is validated fail-closed by
`src/arail/world_theme.py` (12 hex slots, WCAG contrast floors, a closed
`personality` enum) and resolved **per request** by `effective_identity()`
— every page recolors live once a World is mounted, via the
`inject_ui_theme` middleware (`app.py:444-508`) splicing a `<style>` block
into every HTML response.

**What a mount really changes** (verified against every consumer of
`current_mount()`/`effective_identity()`):

| Real | Cosmetic / inert |
|---|---|
| Knowledge Base re-stocked: N term pages + wiki graph edges + vector index; previous World's pages swept | `roster.json`, `agenda.json`, `drift-report.json` — sealed, staged, never read by any consumer |
| AI Dictionary fully replaced; generation disabled; theme-switch endpoint 409s | `arail-plugin.json` — descriptive only, zero code references |
| Buddy + Researcher system prompts gain a `domain_framing`/`vocabulary_register` block plus the full `SKILL.md` glossary | Declared `knowledge.ground.*` capabilities — no consumer reads them |
| Researcher's `intent` forced to `"other"`; its base prompt is rebuilt from `face.name`/`face.domain_framing` | The agent roster itself — unchanged by any mount |
| Curator's trusted-domain list gains the World's `knowledge_sources` | `terms.json` contents never enter a prompt (by design — treated as data) |
| Full page recolor + brand/logo/tagline swap on every page | Chat mic/OCR capability gating — currently always `declared_unavailable` (no shipped bundle's adapter resolves) |

This table is the honest source for any "here's what a World changes" copy
— it replaces guessing with what the code actually does.

**Bundles that exist on a genuinely fresh clone**: only `ai` (339 terms,
`mixed` provenance tier, `hacker` theme) and `qukaizen` (32 terms, `hacker`
theme) are git-tracked. `photography` (223 terms) and `physics` (42 terms)
exist in this checkout but are **untracked** (`git status` confirms `??`)
— they will not be present after `git clone`. Any onboarding copy that
lists them as pickable options must not assume they ship; the spec below
treats them as **illustrative examples in copy**, consistent with the
brief's honesty rule, and only surfaces them as pickable cards when
`GET /api/worlds` actually returns them (which it already does, filtered
to `valid`).

**Existing portal surfaces for Worlds**: the nav switcher (`_nav.html:22-44`,
`nav.js:631-890`, on every page already), `/worlds` (forge + catalog, not
linked from the nav), `/dac`'s empty-state buttons, and welcome Step 3
itself, which — confirmed by reading `welcome.html:501-509` and
`app.py:3082-3149` — **already performs a real mount**, not a preference
write. Its failure handling is the gap: `POST /api/worlds/select` can
return 409 `mount_refused` on a seal failure, but Step 3's client code
swallows every error (`catch (e) { /* fall through — never trap */ }`,
:507) and calls `goHome()` regardless, so a refused mount looks identical
to a successful one to the user.

### 0.5 Reset — CLI-only, and inconsistent with the World model

`scripts/reset.sh` (11 modes: `models|data|pkb|pkb-seeds|program|skills|
plugins|env|full|destroy|stop`) has **no portal surface at all** — the only
mention of reset in any template is a copy-paste command snippet in
`admin.html:854`. Confirmed against the World pointer and staged KB:

- `reset data` deletes all of `lab/data/` — including
  `world-mount.json` — but **not** `lab/pkb/sources/world-<slug>/`. The
  pointer is gone; the staged term pages are orphaned in the KB, silently.
- `reset pkb` deletes `lab/pkb/` — the staged World content is gone — but
  **not** `world-mount.json`. The lab now reports a World mounted whose
  knowledge base has been erased: a dangling pointer.
- Neither scope, nor any other, mentions Worlds. Nothing re-stages or
  reconciles at boot (`app.py:864-877` only verifies bundle seals;
  `app.py:896-910` only announces the current mount).

This is the mechanism the loop-safety guardrail in §1.3 below has to
account for: whatever first-load marker this spec introduces must not
survive a reset scope in a way that produces a stale/broken state.

### 0.6 The credible first win

`src/arail/research/mini_experiments.py` (`ENGINE_ID =
"mini_experiments/v1"`) is real: three deterministic archetypes
(`model_throughput`, `prompt_variant`, `retrieval_quality`), each producing
either genuinely measured metrics or an honest `cannot_run`/`unmeasured`
outcome — verified by reading the module docstring (:1-22) and the
`_cannot_run()` call sites (:151-157, :221, :241-242, :292, :326-328,
:357-358, :361-366). `setup.sh:1957`'s default goal — "Find the best small
model for my laptop — measure the speed and responsiveness of the model(s)
I have installed" — was deliberately chosen (per
`sprints/2026-07-23-clean-experience/BUILD_LOG.md:324-329`) so that pressing
Enter at setup, then **▶ Run** in Autoresearch, produces a real
`model_throughput` result: median `decode_tok_per_sec` / `ttft_ms` over
three runs.

Two honest caveats a first-win screen must respect:

- **Timing**: the Researcher plans up to 5 experiments
  (`researcher.py:1110`), each budgeted 60s (`LAB_EXP_RUNTIME_SEC`), and
  the plan step itself makes LLM calls — a full run can exceed 5 minutes.
  The single fastest real measured signal today is actually **sending one
  chat message** — the reply's provenance popover shows code-measured
  `throughput <n> tok/s`, `latency <n> ms` (`chat.html:3107-3109`) in
  seconds, not minutes.
- **retrieval_quality requires approved KB docs first** — a fresh lab with
  nothing approved hits the honest, teaching `cannot_run` at
  `mini_experiments.py:361-366` ("no approved knowledge — approve
  documents on the Knowledge (DaC) page first, then this experiment can
  measure retrieval quality"). A first-win screen should not point here
  first.

---

## Phase 1 — Design

### 1.1 Core decision: one World moment, three doors

Rather than inventing a new World-picking UI, the design **promotes welcome
Step 3 to a single, addressable, reusable component**, because discovery
found it already does the real work (seal-gated mount, path-jailed,
audited) — the only things missing are an address, honest failure display,
and a place for CLI-onboarded and returning users to reach it.

**New route contract**: `GET /welcome?step=world`.

- When `?step=world` is present **and** the requester is onboarded
  (`_lab_password_set()` true), `welcome_page()` renders `welcome.html`
  directly into the World-step state — server sets a flag the page's JS
  reads on load to call `showWorldStep()` immediately instead of showing
  Step 1 — rather than 302ing to `/`. This is the **only** new branch in
  `welcome_page()`; every other combination keeps today's behavior exactly
  (see the truth table in §1.2).
- When `?step=world` is present and the requester is **not** onboarded,
  the existing `onboarding_gate` already routes them through `/welcome`
  from scratch (§0.2) — the param is simply ignored until they reach Step
  3 normally. No new precedence conflict.

This one route serves all three entry doors:

1. **Cold start, browser.** Step 3 of the existing linear flow — unchanged
   in position, upgraded in content (§1.4).
2. **Cold start, CLI-onboarded** — the gap in §0.2/§0.3. A **strictly
   one-shot** nudge (mechanism in §1.3) redirects such a user from `/` to
   `/welcome?step=world` exactly once.
3. **Swap / reset-into-a-new-World.** New "Change World" entry points (nav
   switcher's existing top item, `/dac`'s empty-state button, the
   dashboard nudge when it *does* fire) all link to
   `/welcome?step=world`, rendering a **mounted variant** (§1.5) that
   states honestly what a swap changes and asks one confirmation before
   doing it — closing the zero-confirmation gap in §0.4.

One component, three doors, means the second and tenth time a user
chooses or swaps a World, it looks and behaves like the first — the
brief's explicit ask ("reuses the cold-start components and tone so the
2nd/10th time feels like the same trustworthy place").

### 1.2 Loop-safety — the full truth table

The brief's guardrail is direct: `welcome_page()` must special-case
`?step=world` (a), the nudge must be strictly one-shot with a marker
persisted **before** the redirect (b), `reset.sh` must re-arm it (c), and
it must never fire when a World is mounted or for a non-onboarded user
(d). Design:

**New marker file**: `lab/data/.world-prompt-seen` — an empty sentinel
file, written the same way other one-shot markers in this codebase are
(`lab/data/goals/bootstrap_goal.json` is the existing precedent for
"presence = already handled"). Chosen location: `lab/data/` specifically
*because* `reset data` and `reset full` already delete that entire
directory (§0.5) — the marker re-arms for free on those two scopes with no
new code. `reset pkb` needs an explicit line (below) because it does not
touch `lab/data/`.

**The one new branch, precisely** — a check added to the dashboard route
(`app.py:1382-1401`), evaluated only on `GET /`, only after
`onboarding_gate` has already let the request through (so it never runs
for a non-onboarded user — guardrail d, first half):

```
if onboarded
   and current_mount() is None                    # guardrail (d), second half
   and not (DATA_DIR / ".world-prompt-seen").exists():
       (DATA_DIR / ".world-prompt-seen").touch()   # write marker FIRST — guardrail (b)
       return RedirectResponse("/welcome?step=world", 302)
# otherwise render the dashboard exactly as today
```

Truth table over every reachable state:

| Onboarded? | World mounted? | Marker present? | Result |
|---|---|---|---|
| No | — | — | `onboarding_gate` already sends to `/welcome` (existing behavior, untouched) |
| Yes | Yes (any World) | any | Dashboard renders normally — guardrail (d) |
| Yes | No | Yes | Dashboard renders normally — already nudged once, never traps them again |
| Yes | No | No | Marker written, then **one** 302 to `/welcome?step=world` — the only new path |

Because the marker write happens synchronously before the redirect
response is constructed, a user who force-quits the browser mid-redirect
and reloads sees the dashboard, not a repeat redirect — there is no window
where the nudge can loop. "Skip for now" and the "AI Lab (default)"
choice inside the World step both count as resolving the moment (they
already land the user back on `/`, where the marker — already written on
entry — prevents any further redirect).

**`scripts/reset.sh` re-arm wiring**:

- `reset data` / `reset full` — no code change needed; both already
  `rm -rf $DATA_DIR` (§0.5), which removes the marker along with
  everything else in `lab/data/`.
- `reset pkb` — gets one new line: also remove
  `lab/data/.world-prompt-seen` **and** `lab/data/world-mount.json` (the
  dangling-pointer bug from §0.5). This is the one reset-side code change
  this spec calls for; it is a bug fix (dangling mount after `reset pkb`)
  that the loop-safety design surfaces as a prerequisite — without it, a
  user who runs `reset pkb` would see `current_mount()` still return a
  (now-broken) World and the nudge would correctly, but unhelpfully, stay
  silent while the World picker in the nav shows a phantom active World.
- Every other scope (`models`, `pkb-seeds`, `program`, `skills`, `plugins`,
  `env`, `destroy`, `stop`) is unaffected — none of them touch
  `world-mount.json` or the marker, so behavior is unchanged.

**Quiet boot**: every check above is a local file `.exists()`/`.touch()`
call inside an already-firing request handler — no new probe, timer, or
background loop, and `ARAIL_AUTOCHECKS` is untouched. This satisfies the
guardrail as written.

### 1.3 Screen-by-screen: what/why/how

Each screen below states the one decision it asks for, the plain-language
what/why/how, and the primary action plus its always-available "skip / do
this later" — per the brief's progressive-disclosure requirement.

#### Step 1 — Passphrase (unchanged position; copy retained)

- **What**: pick a passphrase.
- **Why**: it protects the code-server IDE and Open Notebook's encryption
  — not the dashboard itself, which the existing warn box
  (`welcome.html:200-210`) already discloses honestly ("anyone who can
  open this browser on this machine is treated as you"). That box is the
  single strongest piece of security copy in the product and today only
  browser users ever see it — this spec does not touch it, but notes it as
  a candidate the CLI's closing banner could point at as further reading.
- **How**: type it, confirm it, continue.
- No design changes to Step 1 in this pass beyond what's needed for the
  `?step=world` boot flag (§1.1) to coexist with it.

#### Step 2 — Network mode (unchanged position; one naming fix)

- **What**: airgapped (default) or hybrid.
- **Why, reframed around the user's data** (already mostly true in
  existing copy — `welcome.html:307-310`, :316-318 — kept, tightened):
  "Airgapped: your data never leaves this machine — the lab studies what
  you give it and the sealed Worlds it ships with. Hybrid: cloud providers
  become reachable and agents may fetch from the web, per-domain, with
  your consent, and every call is logged for you to review."
- **How**: pick one, continue — reversible anytime from the mode badge.
- **Fix**: existing copy calls the toggle "the shield badge in the nav"
  (`welcome.html:375`, :409-410; `setup.sh:1322`) but the actual element
  is a filled circle glyph `⬤ Airgapped`/`⬤ Hybrid` (`_nav.html:91-92`) —
  no shield exists anywhere in the UI. Rename the copy to "the mode badge
  in the nav" everywhere it appears (welcome, setup banner). Small, but
  it's the kind of small mismatch that makes a non-expert doubt they're
  looking at the right thing.

#### Step 3 — World picker (upgraded; the heart of this spec)

**What/why/how, stated plainly**, added above the existing card list:

> A World is what your lab studies — not just a theme, but the whole
> lab re-oriented: its knowledge base, what its agents pay attention to,
> its vocabulary, its look. **AI & Machine Learning is the recommended
> default** — mount it and you both *use* AI (run models, run real
> experiments) and *learn* AI, because the World's own knowledge base
> teaches the concepts as you work. You can change this anytime.

**Concept-teaching strip** (new — the brief's explicit ask: "teach the
concept with relatable examples"), placed below the explainer and above the
card grid, three short illustrative lines, each labeled as an example:

> *What a World of X could mean —*
> **Photography**: agents and the knowledge base reorient around lenses,
> lighting, and editing workflows; autoresearch could compare develop
> settings or gear tradeoffs.
> **Advanced Biology**: the lab orients around a research domain — papers,
> terms, and methods — with agents summarizing and connecting findings.
> **Video Games** *(vivid, and honestly bounded)*: mount a Video Games
> World pointed at a driving sim, and the lab's agents read the game's
> manual, learn your hardware, and run real, measured experiments to find
> *your* optimal settings — the same measure-don't-guess loop the
> Researcher already runs today (`mini_experiments.py`), applied to a new
> domain. In hybrid mode, opt-in only, agents could also watch for new
> driver releases worth installing or flag a newly released sim for your
> review.

Each of these three lines is explicitly labeled *"an example of the
pattern"* — per the brief's non-negotiable honesty rule — unless the
corresponding bundle is actually present in `GET /api/worlds`'s response,
in which case it renders as a real, clickable card instead of prose (see
next paragraph). This means the copy is correct whether run against a
clean clone (photography/physics absent → prose examples only) or this dev
checkout (present → real cards, and the prose line for that one is
dropped so nothing is said twice).

**Card content, upgraded from today's swatch+name+tagline**
(`welcome.html:462-495`) to include, sourced entirely from data the bundle
already exposes (`face.json`, `manifest.json`, `spec.json` — no new
backend fields required):

- theme swatch (existing)
- display name + tagline (existing)
- **new**: term count + provenance tier chip (e.g. "339 terms · mixed
  provenance" or "223 terms · sourced") — sourced from
  `manifest.provenance_counts`/`provenance_tier`, giving the "previews what
  the lab becomes" the brief asks for
- **new**: 2-3 example category names from `spec.categories` (e.g.
  "Fundamentals · Training · Inference") so the choice feels concrete
  before committing

**Honest failure states** (closing the two swallowed-failure gaps from
§0.4):

- If `GET /api/worlds` errors or returns zero valid worlds, render an
  explanatory empty state — "Couldn't load the World catalog right now —
  you can still start with AI & ML (the default) or skip for now" — instead
  of today's silent `goHome()`.
- If `POST /api/worlds/select` returns 409 `mount_refused` (a seal or
  schema failure), show it on screen — "That World's bundle didn't pass
  its integrity check, so nothing was mounted. Try a different one, or
  skip for now" — instead of swallowing the error and calling `goHome()`
  as if it had worked. The user must never be told (implicitly, by silent
  success) that something happened that didn't.

**Primary action / skip, unchanged pattern**: click a card to mount it
(disables the grid, shows real progress, then a genuine success/failure
state per above); "✦ Forge your own…" to `/worlds`; "Skip for now" always
available, always lands on `/` with the marker already resolved — never
traps.

#### First-win landing (new — the brief's explicit ending requirement)

After any successful mount or explicit skip, from **any** of the three
doors, the dashboard shows a one-time card (dismissible, using the same
`localStorage`-dismiss pattern already used for the runbook banner at
`dashboard.html:393-411`, so it doesn't need a new backend flag):

> **Your lab is set. Here's a real first thing to try.**
> Your lab's opening research goal — *"Find the best small model for my
> laptop — measure the speed and responsiveness of the model(s) I have
> installed"* — is already staged in Autoresearch. Press **▶ Run** to
> start a real, measured experiment (this can take a few minutes).
> Want something faster? Send one message in Chat — the reply shows real
> measured speed in seconds.
> And the honest hook: your lab's agents keep working on your research
> goals while you're away, and report back what they actually found —
> never a guess, never a canned result.

Every claim in this card is grounded in verified code behavior (§0.6): the
staged goal, the ▶ Run action, the chat provenance popover, and what the
agents genuinely do. No fabricated numbers, no invented urgency.

#### Swap variant (the World step, when a World is already mounted)

When `/welcome?step=world` is reached with `current_mount()` not `None`
(i.e., via the new "Change World" doors, never via the one-shot nudge —
guardrail (d) already prevents that path), the same component renders with
two differences:

1. A header stating the current World by name, with a **single
   confirmation** before any card click proceeds to mount — replacing
   today's zero-confirmation destructive sweep (§0.4):
   > "Switching Worlds re-stocks the lab's knowledge base, changes what
   > your agents focus on, and updates the look — **your current World's
   > added knowledge base pages will be removed** (the sealed World bundle
   > itself is never deleted and can always be re-mounted). Continue?"
   This sentence is built entirely from the "what a mount really changes"
   table in §0.4 — no aspirational claims.
2. On completion, instead of the first-win card, a **"what changed"**
   summary drawn from the same table — theme, vocabulary/agent focus, and
   knowledge base — so a returning operator can verify the swap did what
   they expected.

### 1.4 Component reuse across cold-start and swap

| Component | Cold-start (browser) | Cold-start (CLI, one-shot) | Swap |
|---|---|---|---|
| Route | `/welcome` → Step 3 in sequence | `/welcome?step=world` (redirected) | `/welcome?step=world` (linked) |
| World card grid + copy | shared | shared | shared, plus the confirm banner (§1.3, swap variant) |
| Concept-teaching strip | shown | shown | shown (useful for "what else could I mount") |
| Failure handling | shared honest states | shared | shared |
| Ending | first-win landing | first-win landing | "what changed" summary |

This is the "reuses the cold-start components and tone" requirement made
concrete: one Jinja template state, one JS module, three entry conditions.

### 1.5 Scope discipline — what this spec does not touch

- `setup.sh`'s `LAB_INTENT` taxonomy and the World model remain
  unreconciled; flagged in the gap list below as a named follow-up, not
  fixed here (the brief's scope note excludes new-World-bundle and
  broader setup work).
- The stale "331 sourced terms" tagline on the `ai` bundle, the untracked
  `photography`/`physics` bundles, and the CLI setup banner's Worlds
  silence are all named in the gap list; none require a code change to
  *this* spec's mechanism (the honesty rules above already handle the
  untracked-bundle case by design), but a follow-up pass should update the
  authored `face.json` copy after any growth-engine run.
- `reset.sh`'s missing `ARAIL_EXPERIMENTS_DIR` handling and its 4
  argv-only modes are pre-existing bugs unrelated to this effort — noted,
  not fixed.
- Research's empty-state copy conflating the `mini_experiments` engine
  with the separate `/tuning` git-branch loop is a distinct truth-in-UI
  bug outside this experience's surface area — noted, not fixed.

---

## Full gap list (Phase-0 output, consolidated)

1. **CLI-onboarded users never see the World step** — `welcome_page()`
   302s unconditionally; no `?step=` param exists. *(Fixed by §1.1/§1.2.)*
2. **CLI vs. browser onboarding ask disjoint questions**;
   "Either path lands at the same place" (`welcome.html:238`) is false.
   *(Named as a follow-up; not resolved by adding the World door alone —
   the CLI's own banner should gain a closing line pointing at
   `/welcome?step=world`, which this spec's route makes possible for a
   future small patch.)*
3. **The one existing World nudge is suppressed for exactly the users who
   need it** — CLI's bootstrap goal fills the mission card, hiding
   `dashboard.html:1980-1987`. *(Superseded by the new one-shot redirect,
   which does not depend on the mission card's state.)*
4. **Welcome Step 3 swallows mount failures** and silently skips entirely
   on `/api/worlds` errors. *(Fixed by §1.3's honest failure states.)*
5. **No guided in-portal swap/reset flow; zero-confirmation destructive
   sweep.** *(Fixed by §1.3's swap variant + confirmation.)*
6. **`reset pkb` leaves a dangling World mount pointer**; `reset data`
   orphans staged World content. *(Partially fixed — `reset pkb`'s
   dangling-pointer case is fixed as a loop-safety prerequisite in §1.2;
   `reset data`'s orphaned-staging case is a separate, smaller bug left as
   a follow-up since it doesn't affect the marker/redirect correctness.)*
7. **Three existing pickers (welcome, nav switcher, `/worlds`) show three
   different amounts of information**; `/worlds` has no nav link.
   *(Partially addressed — welcome's card gets richer per §1.3; making the
   switcher and `/worlds` match, and adding a nav link, is a natural
   follow-up using the same data, not required for this spec's mechanism.)*
8. **No first-win ending; the first real action has many names across
   surfaces.** *(Fixed by §1.3's first-win landing card.)*
9. **Assorted truth-in-UI dents**: stale `face.tagline` term counts;
   photography's placeholder tagline; untracked bundles that vanish on
   clean clone; "shield badge" copy for a badge that isn't a shield; mode
   badge's hardcoded-then-corrected first paint; research's empty state
   promising the wrong loop's git branches; all 15 declared World
   capabilities showing `declared_unavailable`. *(The "shield badge"
   naming is fixed in §1.3 Step 2; the untracked-bundle honesty concern is
   handled by design (§1.1); the rest are named here as follow-ups outside
   this pass's scope.)*
10. **World-concept teaching was previously two sentences on Step 3 only;
    no dual-promise framing; no gaming example anywhere.** *(Fixed by
    §1.3's explainer + concept-teaching strip.)*

---

## What Phase 2 (build, pending approval) would touch

Named here for the operator's review before any code is written — not
executed in this pass:

- `src/arail/portal/app.py`: one new conditional branch in `welcome_page()`
  (render World-step state on `?step=world` for onboarded users, per
  §1.2's truth table); one new conditional in the dashboard route
  (marker-write-then-redirect, same section).
- `src/arail/portal/templates/welcome.html`: server-side boot flag to jump
  straight to `showWorldStep()`; richer card markup (term count,
  provenance chip, example categories); concept-teaching strip; honest
  failure-state rendering in place of silent `goHome()`; swap-variant
  confirmation banner and "what changed" summary; "shield badge" → "mode
  badge" copy fix.
- `src/arail/portal/templates/dashboard.html`: new dismissible first-win
  card (reusing the existing `localStorage`-dismiss pattern).
- `scripts/reset.sh`: one new line in the `pkb` scope removing the marker
  and the dangling `world-mount.json`.
- New entry points to the swap door: nav switcher's existing "AI Lab
  (default)"/World rows already link correctly; `/dac`'s empty-state
  buttons and the dashboard nudge (when it fires) point at
  `/welcome?step=world` instead of `/worlds`.
- Tests: `TestClient` coverage for every row of the §1.2 truth table, plus
  the `reset pkb` marker/pointer cleanup; live screenshot verification of
  cold-start (both doors) and swap on fresh local state, per the brief's
  Phase 3.

Atomic commits, reviewable slices, each verified locally — no GitHub
Actions, per repo convention.
