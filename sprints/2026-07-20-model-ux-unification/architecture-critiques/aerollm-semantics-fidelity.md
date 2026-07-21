# Pre-build critique — lens: aerollm-semantics-fidelity

**Target:** `sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md`
**Ground truth:** `PROMPT.md §3` (two-regime distinction) and `§6` (guardrails)
**Question asked:** Does the architecture's treatment of aeroLLM load/unload/streaming
badges match §3 — the "resident-because-it-fits today" vs "true frontier layer-streaming"
split, and the fact that `AERO_MOE_SELECT` is opt-in / default-off / never set — or is it
still conflating the two, or overselling a capability that is not turned on?

**Verdict: it is BETTER than the current code but the fidelity floor it claims to reach has
concrete holes.** It correctly names the two regimes in prose (Decision 2 in VISION, C4 in
ARCH) and correctly refuses to build streaming UI. But the *enumerated fixes* miss most of
the places where the old code oversells `AERO_MOE_SELECT`, and the honest badge it
substitutes introduces two *new* false-residency claims of exactly the class this sprint
exists to kill. These are cheap to fix now and expensive to discover in QA. Findings below,
ranked, each with a section/line reference and a code receipt.

---

## BLOCK-class findings (a lie survives, or a new one is introduced)

### 1. The overselling fix is scoped to 1 of ~13 sites; the test demands all 13 → the plan cannot pass its own test.

- **ARCH refs:** F-OVERSELL detection (line 137), T-COPY, and implementation-order **step 4**
  (line 246): `"selective expert-streaming" / "streaming" → "resident (aeroLLM)"` — but step 4
  only lists **`models_catalog.yaml:126-127` and `chat.html:3722`** (the deepEntries verdict).
- **Ground truth:** §3 says the catalog claim that gpt-oss-20b uses "AeroLLM's native
  selective expert-streaming backend" **overstates current reality** — it runs the resident
  whole-layer path, `AERO_MOE_SELECT` off.
- **Receipt — the overselling is systemic, not a single string.** In `chat.html` alone:
  - `1736` / `2187`: the deep column **section header** literally reads `Local · SSD (streamed)`.
  - `1740`: subtitle `30B+ models streamed from disk via AeroLLM.`
  - `2076` / `3306`: a `streamed-badge` rendered on rows: `Layer-streamed via AirLLM…`.
  - `3320`: `deep layer-streaming backend (AirLLM/AeroLLM)`.
  - `1817`: References note `ARAIL's Rust runtime for 30B+ via layer-streaming`.
  - `3733`: `Layer-streaming for 70B+ local models on modest VRAM`.
  - `3803`: `The deep model adds a few GB resident even when streamed` (already
    self-contradictory copy).
  - In `models_catalog.yaml`: `93` (`AirLLM/AeroLLM layer-streaming frontier lane`),
    `111-115` (comment asserting `native selective (active-only) expert streaming … 32 experts
    / 4 active, bit-exact`), and `127` (visible description).
- **Why it matters for this lens:** ARCH step 4 changes the *verdict string* and *one catalog
  line* and leaves the **entire visual scaffolding** (section header, subtitle, per-row badge,
  tooltip, references) still claiming layer-streaming. F-OVERSELL (line 137) asserts "grep
  rendered payload + `models_catalog.yaml` for '…streaming' on aerollm rows → 0", which these
  sites fail. **The architecture is internally inconsistent: the test is stricter than the
  fix.** A builder following step 4 literally ships a still-overselling screen that fails
  T-COPY.
- **Fix:** enumerate all sites in the implementation order (or state "grep-and-replace all
  layer-streaming copy on deep rows" as the unit of work), and explicitly reconcile the
  `streamed-badge` (`chat.html:918, 2076, 3306`) and the `streamed` boolean (finding 6).

### 2. The "≤ 8B" header lie is killed; its symmetric twin "Local · SSD (streamed)" is left standing.

- **ARCH refs:** F-HEADER / T-HEADER kill `Local · GPU (≤ 8B)` (`chat.html:1731, 2175`). The
  deep column header `Local · SSD (streamed)` (`chat.html:1736, 2187`) is **not** in scope.
- **Why it matters:** these are the *same class of false section header* — one asserts a size
  bucket that is wrong, the other asserts a streaming mode that is off. The sprint's thesis is
  "one visible lie taxes every true thing next to it." Killing the GPU-column header lie while
  leaving the SSD-column header lie directly under it is asymmetric fidelity and re-opens the
  exact "header oversells" bug on the deep half of the same list.
- **Fix:** treat `Local · SSD (streamed)` as a fifth header lie; retitle to something like
  `Local · aeroLLM (resident)` and add it to F-HEADER's assertion.

### 3. The honest badge `"resident (aeroLLM)"` is keyed off `installed`, not warmth → it lies when the singleton is cold.

- **ARCH refs:** C4 (line 100) "deep entries render badge/verdict **`"resident (aeroLLM)"`**";
  C2 bad-input (line 93) "A deep entry with no fit → verdict copy `"resident (aeroLLM)"`
  (static, not computed)".
- **Receipt:** `chat.html:3722` computes the verdict as
  `o.installed ? 'streaming' : 'not installed'`. ARCH changes the `'streaming'` arm to
  `'resident (aeroLLM)'` — but the predicate is still **`installed`**, which is not the same as
  **resident/warm**. Meanwhile `model_warmth.py` only preloads the singleton *when it is safe*
  (`background_safe()` gated on `metal_memory_pressure() < 0.60`, `_preload.py` header lines
  5-10, 66). On a fresh portal before the first preload tick, or on a 32 GB Mac under memory
  pressure where preload is deliberately skipped, the model is **installed but not resident** —
  and the badge would assert `resident (aeroLLM)`.
- **Why it matters for this lens:** this is the identical failure mode to the fake `good` chip
  and the lying eject — a badge asserting a memory state that isn't true. The sprint cannot
  simultaneously ban false-residency for Ollama rows and hard-code it for aeroLLM rows. §3
  bullet 1 is explicit that residency here is *conditional* on the preload loop.
- **Fix:** compute the deep badge from actual warmth (`AeroLLMBackend._shared` populated / the
  preload status the warmth loop already emits — `_preload.py:92-101` emits
  `preload_ok`/`preload_failed` events), rendering `resident (aeroLLM)` vs `cold (aeroLLM) ·
  warms on first deep call`. A static badge here is a designed-in lie.

### 4. "Frees on next portal restart" is undercut by the auto-preload loop; T-RESTART may race it and the copy becomes a new lie.

- **ARCH refs:** C4/C5 honest copy `"resident (aeroLLM) · frees on next portal restart"`;
  T-RESTART (line 160) asserts "RSS returns toward baseline" after restart; A3 (line 23)
  *acknowledges* the re-warming loop but never reconciles it with the promise.
- **Receipt:** `model_warmth.py` runs `aerollm_preload_loop()` every
  `ARAIL_AEROLLM_PRELOAD_INTERVAL_SEC` (default 300 s, floor 30 s) and, when a safe window
  exists, re-warms the singleton on startup (`_preload_once()` → "Tier 1 is resident and
  ready", lines 56-94). So after a restart the memory frees momentarily and is then **re-pinned
  within one tick** (immediately, if the startup window is safe).
- **Why it matters:** "frees on next portal restart" is thus only transiently true. An operator
  who restarts specifically to reclaim memory watches it climb back — the same
  "button/affordance reports an effect that doesn't hold" pattern §6 bullet 3 forbids.
  T-RESTART as written ("returns toward baseline") can pass or fail depending purely on whether
  the assertion samples RSS before or after the first preload tick — a flaky test guarding a
  copy that is itself imprecise.
- **Fix:** either (a) make the copy honest about the loop — "frees on restart until the deep
  preloader re-warms it (~5 min, or immediately if memory is free)"; or (b) have the restart
  path set `ARAIL_AEROLLM_PRELOAD=0` / skip the first warm so the freed state actually holds;
  and pin T-RESTART to sample RSS deterministically relative to the preload tick.

---

## ASK-class findings (mislabels, under-specified, mechanism won't deliver the promised contract)

### 5. AirLLM is mislabeled as aeroLLM in the honest eject note and the deep badge.

- **ARCH refs:** C5 (line 106) groups **`airllm | aerollm`** and returns
  `notes:["resident (aeroLLM) · frees on next portal restart"]`; data-flow line 61 folds
  `optional_backends` into deep entries with verdict `"resident (aeroLLM)"`.
- **Receipt:** AirLLM is a *distinct* backend (the legacy CUDA fallback — ARAIL CLAUDE.md: "CUDA
  hosts fall back to AirLLM"), opt-in via `ARAIL_INSTALL_AIRLLM=1`. The existing honest branch
  (`app.py`, the `elif runtime in ("mlx","cpu","cuda","airllm","aerollm")`) already uses
  correct **backend-neutral** copy: *"{runtime} in-process backend cannot hot-eject; restart
  the portal to drop it."* ARCH proposes to *replace* that already-correct neutral copy with
  aeroLLM-specific copy that is **wrong for an airllm-runtime row** — the badge on an
  AirLLM-served model would read `resident (aeroLLM)`.
- **Why it matters for this lens:** it re-introduces the exact conflation §3 warns against, just
  in the other direction (labeling AirLLM as aeroLLM). And `chat.html:2076/3306` already carries
  the opposite conflation (`Layer-streamed via AirLLM` on an aeroLLM deep row) — so the two
  brands are already smeared together and ARCH does not disentangle them.
- **Fix:** template the note per-runtime (`resident ({runtime})`), or keep the existing neutral
  "in-process backend" wording. Do not hard-code "aeroLLM" for the airllm arm.

### 6. C5's stated mechanism ("remove the false-success interception so the honest note wins") does not actually produce `ok:false`.

- **ARCH ref:** C5 (line 106) promises the shape `{ok:false, freed:[], requires_restart:true,
  notes:[…]}` and says to "resolve by removing the false-success `if runtime in
  ("airllm","aerollm")` interception so the honest note wins."
- **Receipt:** the eject endpoint's **terminal return is unconditional
  `return {"ok": True, "freed": freed, "notes": notes}`**. Removing the `if` block drops flow
  into the `elif …("mlx","cpu","cuda","airllm","aerollm")` arm, which appends the honest *note*
  — but the function **still returns `ok:True`**, and nothing sets `requires_restart`.
- **Why it matters:** the promised contract (`ok:false`, `requires_restart:true`, tested by
  T-EJECT-AERO which asserts `ok==false` and `requires_restart==true`) is *not delivered by the
  described change*. The mechanism is under-specified: the terminal return and a
  `requires_restart` field must be edited explicitly. As written, a builder who does exactly
  what C5 says ships an endpoint that still reports `ok:true` and fails T-EJECT-AERO.
- **Fix:** state that the honest branch returns `{"ok": False, "requires_restart": True, …}`
  explicitly, not merely that the note "wins."

### 7. C4 removes the **Load** affordance for aeroLLM, contradicting §3/VISION that Load is a real event for the resident regime.

- **ARCH ref:** C4 (line 100): "**No Load/Unload/Eject button** on the aeroLLM row." Data-flow
  line 64 still renders a `WARM/cold` dot for every row.
- **Ground truth:** §3 bullet 1 and VISION Decision 2 both say for aeroLLM-resident: "Load is a
  real, one-time, heavy event — the operator's cold→WARM mental model basically holds here …
  The *only* thing broken is Unload." Neither asked to remove Load; only Unload.
- **Why it matters:** ARCH over-removes. A row that shows a `cold` dot (line 64) but offers **no
  Load button** and simultaneously asserts the static verdict `resident (aeroLLM)` (finding 3)
  is internally incoherent — cold dot + "resident" text + no way to warm it. This under-
  represents the resident regime §3 tells the sprint to design *for*.
- **Fix:** decide explicitly whether the aeroLLM deep model is operator-loadable (keep a Load
  button, cold→WARM per §3) or purely auto-preloaded (then suppress the `cold` dot and never
  show it as loadable). Do not ship the half-state (cold dot, no Load, "resident" text).

### 8. The "one reserved hook" for true frontier streaming is named 3× but never specified — a §6 dormant-lane risk.

- **ARCH refs:** Tech-debt (line 193), Non-goals (line 232), Restatement — each mentions "one
  scoped, explicitly-labeled non-goal hook … reserved (not built)" for true layer-streaming.
- **Why it matters:** §6 bullet 1 forbids "a new 'dormant lane' … without a committed date to
  either activate or delete it." The hook's trigger is "`AERO_MOE_SELECT` actually enabled" (an
  external event, acceptable as an activation trigger) but there is **no deletion date and no
  definition of what the hook physically is** (a code stub? a comment? a catalog field?). An
  undated, undefined "reserved hook" is precisely the kind of artifact that becomes the seventh
  unread field this sprint is chartered to prevent.
- **Fix:** either specify the hook concretely (what file, what label, what deletes it and when)
  or drop it — "name the concept in a doc" is sufficient to honestly acknowledge the
  frontier-streaming case without reserving un-dated code.

---

## What the architecture gets right (so the builder does not "fix" these)

- It does **not** conflate the Gemma-4-26B MoE (an *Ollama* model — all experts resident, fit
  computed off disk weights per A6/F-MOEBASIS) with `AERO_MOE_SELECT` (aeroLLM *selective
  expert-streaming*). Both carry "MoE/expert" language and conflating them would be the easy
  mistake; ARCH keeps Gemma on the Ollama resident path (data-flow line 70) and treats
  AERO_MOE_SELECT strictly as the off-by-default aeroLLM flag. This is the single most important
  thing to get right for this lens, and it is right.
- The core §3 decision — "design for the resident case now, badge says `resident (aeroLLM)` not
  `streaming`, build no UI for true streaming" — is faithfully carried into VISION Decision 2
  and C4, matching §3's recommended resolution.
- A3 correctly enumerates why the singleton can't be hot-freed (three caches + preload loop +
  unverified Rust Drop→Metal-free), which is the honest basis for removing Eject.

---

## Bottom line

The architecture correctly *states* the two-regime distinction and refuses streaming UI — the
prose fidelity is good. But at the level of concrete, buildable steps it (1) under-scopes the
overselling cleanup to ~1 of 13 sites while its own T-COPY test demands all of them, (2) leaves
the symmetric `Local · SSD (streamed)` header lie standing next to the `≤ 8B` header it kills,
(3) substitutes a *static* `resident (aeroLLM)` badge that itself lies when the singleton is
cold, and (4) promises "frees on next portal restart" without reconciling the auto-preload loop
that re-pins it. Findings 5-8 are mislabels and mechanism gaps that will fail the sprint's own
named tests (T-COPY, T-EJECT-AERO). None require redesign — all are enumeration/specification
fixes to make the honest-floor claim actually hold. Recommend the builder not start the aeroLLM
row work until findings 1-4 are folded into the implementation order.
