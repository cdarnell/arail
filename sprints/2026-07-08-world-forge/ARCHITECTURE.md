# World Forge — dream any world, study it, let agents curate it

## Context

Worlds shouldn't be a fixed set of 3–5 shipped bundles. The user wants **selective world creation**: name any subject — "5th grade mathematics", "Differential equations", "Botany", "Indoor plants & their care" — pick a size, and the lab's local model drafts the initial knowledge base (efficient core definitions: terms + categories + related-term associations, e.g. Snake Plant → category `indoor-plants`, related `succulents`, `low-light-plants`). That world mounts (theme + identity + agent context), the user refines it in the Knowledge tab (edit / update / associate), and agents curate and experiment **for** the user — who is the student, learning the world through terms, explanations, and experiments.

Everything rests on proven seams: DaC's `forge-world.mts` is a working 7-stage draft pipeline (CLI, TS); ARAIL's `docs/world-forge.md` already designs the "draft cheap, curate forever" loop; DaC's VISION mandates *"World generation is an ARAIL capability"* with no cross-repo runtime imports — so the pipeline gets **ported to Python inside ARAIL**. The seal is plain sha256; ARAIL's `verify_seal`/`mount`/`swap` machinery consumes the output unchanged.

**User decisions (locked):**
1. **Full `/worlds` page** — first-class catalog surface (all worlds w/ swatches + provenance badges, mount/unmount/delete/import) with "Forge a World" as the hero action; switcher gets a "✦ Forge a World…" entry.
2. **Curator review ships in v1** — on-demand "Ask the Curator to review this world": model judges terms, flags render as badges in the term editor.
3. **All three size presets**: 25 Sketch / 50 Field guide / 100 Compendium, honest ETAs + Cancel.
4. **Tier philosophy (corrected)**: minimalist vs maximus is about breadth of functionality and STARTING MODEL SIZE (1B vs 3–7B) — BOTH tiers get knowledge base, world creation, Curator review, autoresearch, and chat in full. Minimalist concedes only non-critical tabs (notebooks, admin extras). Nothing in World Forge is tier-gated; the Curator simply judges better on a bigger model (`complete_preferring_deep` picks the best available on either tier). Update `docs/world-forge.md`'s tier table accordingly (its "maximus = + curation" framing is wrong).
5. **World-first lab flow**: the World is the lab's STARTING POINT and starting data set — an objective subject foundation. A GOAL is subjective and comes second, set *within* the mounted world, and autoresearch/agent curation/Buddy all gear to *goal-within-world*. Flow: **World → Goal → Autoresearch → agents curate → Buddy tutors toward the goal.** Current world building is poorly integrated; this plan makes it the front door.

**Decisions made (not user-facing):** hand-edited terms get `source: "operator:<lab-slug>"` (UI chip "edited by you"); tier machinery stays honest (rollup flips `model-asserted → mixed`). Shipped sourced worlds (ai/art-history) are editable with a one-time warning ("re-seals locally, flips provenance to mixed; re-import restores"). Draft loop uses the default local router (deep model enters only in Curator review via `complete_preferring_deep`). Multi-categorization (Snake Plant = indoor + succulent) is modeled v1 as primary category + `related` edges + `aka` — a `tags[]` schema bump is a named DaC follow-up.

## Architecture (one paragraph)

New framework-free module **`src/arail/world_forge.py`** ports DaC's draft pipeline (SPEC → SEED → DISCOVER BFS → LINK → DEFINE → CLOSE → GATE, verbatim prompts/temperatures from `~/ProJects/qukaizen-dac/scripts/forge-world.mts:103-184`), the gate (`src/gate.ts` three laws), provenance recognizer (`src/provenance.ts`, `model:` regex), sealer (`export-bundle.mts`: 6 sealed siblings + manifest sha256s), SKILL.md renderer (`src/arail-export/skill.ts` with F1/F2 injection sanitizers), and the reconcile judge prompt (`reconcile-world.mts`). A **forge job** runs via the dictionary-generation async pattern (202 + 2s polling, `scheduler.inference_slot`, `asyncio.to_thread`, one-at-a-time lock, cancel event). Preview held in memory; **confirm** writes the bundle to `WORLDS_DIR/<slug>/` and `mount()`s (or `swap()`s). The **term editor** edits the catalog bundle: every write validates (caps, category ∈ spec, related ⊆ roster) → gate → `reseal_bundle` (re-derive SKILL.md/face counts/drift/manifest hashes; atomic dir replace) → `wm.swap()` — the mounted world is never seal-inconsistent, wiki restages automatically. Provenance is always **derived, never asserted**.

## Phase 1 — `src/arail/world_forge.py` (the port; no UI)

- `loose_json()` + `first_array()`: local tolerant JSON digger (repair ladder from `dictionary.parse_entries` steps 1–4, WITHOUT its glossary coercion — stage outputs have varied shapes). `parse_entries` untouched.
- `assert_closed_sourced_graph(terms, declared) -> GateResult` + `tier_of_source` / `compute_provenance_tier` (regex `^model:[a-z0-9][a-z0-9._:/-]*$`, rollup all-model→model-asserted / none→sourced / mix→mixed).
- `forge_world(ForgeParams, *, router=None, progress_cb, cancel) -> ForgeResult` — sync, injectable router (`ModelRouter(billing_source="agent").complete(...)`, max_tokens≈700, temps 0.3/0.1(LINK)/0.2(DEFINE)); source tag from `ModelResponse.model` (lowercase, strip `:latest`, `:`→`/`); cancel checked before every call; pure in-memory (no disk until seal). Knob mapping: 25→4 cats/3 seeds, 50→5/4, 100→6/5. `estimate_skill_chars` warns >150 terms / >48K (56K body cap in `skills_loader.py`).
- `render_world_skill(spec, face, terms, world_sha)` — exact SKILL.md contract (frontmatter title/id `world-<slug>`/name/domain/version/tags/when_to_use/when_not_to_use; body framing + honesty-rail line + `### <Category>` sections + `- **Term** (\`slug\`) — short` + `  - Source:` sub-bullets + `<!-- dac:world_sha256 … -->`), with F1 (frontmatter scalar sanitize/quote) and F2 (body newline-collapse + ZWNJ before leading `#`/`-`/`>`/backtick).
- `write_bundle(out_dir, spec, terms, *, face_overrides, created_at)` — gate refusal → derive tier/counts → write 6 sealed siblings (`json.dumps(o, indent=2, ensure_ascii=False)+"\n"`, hash exact bytes) → seal-exempt SKILL.md + minimal capabilities.json + arail-plugin.json → manifest (`dac.world-bundle/v1`, compat {1,1}). Invariant: round-trips ARAIL's own `load_bundle`+`verify_seal`+`check_compat`+`check_categories`. Byte-parity with DaC's sealer is a NON-goal (state in docstring) — only the round-trip matters. `face_overrides.theme` built from a chosen ui_theme preset and validated via `world_theme.parse_world_theme` before sealing.
- `reseal_bundle(bundle_dir, terms=None)` — re-derive everything downstream of terms.json; temp-dir + atomic replace (the `_adopt_into_catalog` pattern).
- `reconcile_terms(spec, terms, *, router, limit) -> list[Flag]` — the judge prompt port (accept/correct/reject + better_category + bad_edges + ≤12-word note).

## Phase 2 — Worlds page + forge API

Endpoints in `portal/app.py` (new section after worlds block ~L3010; ALL writes use the **Sec-Fetch-Site/Origin-Host CSRF envelope** from `api_worlds_select` L2764-2774):
- `POST /api/worlds/forge` `{subject, slug?, max_terms, palette_hint?, personality?, overwrite?}` → validate (subject 1–120; slug auto-`slugify`, `_SLUG_RE`, ≤48; 409 forge_busy / slug_exists) → 202 `{started, slug, eta_minutes}`; background `_run_forge` mirrors `_dict_run_generation` (app.py:3085): `inference_slot("world-forge")` + `to_thread`; activity_log events.
- `GET /api/worlds/forge/status` (state/stage/terms_found/elapsed — 2s poll) · `POST …/cancel` · `GET …/preview` (in-memory result: categories tree, full terms, tier, avg_edges, warnings) · `POST …/confirm` (write_bundle → mount/swap → `{suggested_goal: "Study <subject>: verify and deepen the glossary…"}` → one tap into existing `/api/goal/preview→confirm`) · `POST …/discard`.
- `DELETE /api/worlds/<slug>` for catalog management (unmount-if-mounted guard; never delete shipped? — allow, with confirm; they're re-importable).

UI — new route `/worlds` + `templates/worlds.html` + `static/js/worlds.js` + `static/worlds.css` (Warm Observatory tokens only — the token-compliance ratchet applies):
- **Catalog**: card per world — swatch gradient (existing `theme_preview`), display name, term count, provenance chip (`dreamed`/`mixed`/`sourced`), mounted state, actions (Mount/Unmount · Open terms · Delete), plus Import bundle/zip (existing endpoints).
- **Forge hero**: subject input + example chips (`5th grade mathematics · Differential equations · Botany · Indoor plants & their care · Espresso brewing`); size segmented control (25/50/100 + honest ETA line + "your local model will be busy while forging"); collapsed Look picker (palette swatches + personality); honesty banner ("*dreamed by your local model — labeled model-asserted, unverified until curated*"); single amber **Forge** button (duotone rule).
- **Progress**: six stage rows, active row cyan, mono `terms 34/50` counter, elapsed, Cancel.
- **Preview**: tier badge, category tree with term rows, warnings, **Accept & Mount** (amber) / Regenerate / Discard. On accept: live theme flip + study-goal toast.
- `nav.js` switcher: add "✦ Forge a World…" row → `/worlds`.

## Phase 3 — structured term editor (Knowledge tab)

Endpoints (CSRF envelope; 409 when unmounted; module `_reseal_lock`; edits land on the canonical catalog copy `WORLDS_DIR/<slug>/`):
- `GET /api/worlds/terms` (mounted world's full structured terms + tier + editability)
- `PUT /api/worlds/terms/{slug}` (fields: term/short/definition/example/category/related/aka; validate caps ≤200/600/300, category ∈ spec, related ⊆ known ∧ ≠self → 400 field errors; source → `operator:<lab-slug>`) → gate → reseal → `wm.swap()` → `{term, tier, counts}`
- `POST /api/worlds/terms` (manual add; slug collision 409) · `POST /api/worlds/terms/draft` (single-term model proposal via DEFINE+LINK prompts under `inference_slot`, returned unpersisted for review) · `DELETE /api/worlds/terms/{slug}` (auto-close inbound `related` edges — delete always succeeds)

UI in `knowledge.html` + `static/js/world-terms.js`: when a world is mounted, tab header **Files / World Terms** (Terms default). Search + category sections; term rows (term · short · provenance chip: `dreamed` warn-tint / `edited by you` / `sourced` positive); row → edit drawer (char-counter fields, category select, searchable related slug-picker chips, Save amber / Delete danger); "＋ Add term" with "Draft with model" helper; live tier badge ("mixed · 3 edited / 47 dreamed"); one-time warning banner on shipped sourced worlds. All term text via `textContent` (dictionary.js F8 discipline).

## Phase 4 — World-first lab flow (the integration the user called out)

Make the World the lab's front door and the goal's frame (all seams verified to exist):

- **Welcome step 2 — "Pick your lab's World."** `welcome.html` is currently "Step 1 of 1" (passphrase). Add a second step after setup succeeds: shipped-world cards (swatch + name + term count from `/api/worlds`), a "Forge your own…" card linking to `/worlds` (post-login), and "Start with the AI Lab default" (mounts the shipped `ai` world — the pre-curated default; its terminal-hacker theme flips the lab on first entry). Skippable, never blocking. POST target: existing `/api/worlds/select`.
- **Dashboard mission card becomes world-framed.** Today the mission/goal UI floats free ("goals are too subjective" standalone). When a world is mounted: the card header reads "Studying: <World name>" with the provenance chip; the goal input carries world-derived **suggested goals** (from spec categories, e.g. "Verify the dreamed terms in <category>", "Deepen <category> with sourced examples", plus the generic "Study <subject>: verify and deepen the glossary"). New tiny endpoint `GET /api/worlds/goal-suggestions` (pure function over the mounted spec — no model call). When NO world is mounted: the empty state points to `/worlds` ("Your lab studies nothing yet — mount or forge a World"), and the goal form is framed as secondary.
- **Autoresearch grounding**: nothing new to build — `mount()` already stages terms into the PKB and LanceDB (`_index_staged`), so the world IS the starting data set the Researcher retrieves against; the suggested goal makes it the loop's target.
- **Buddy gearing**: verified — Buddy already composes the world SKILL.md into its prompt AND is goal-driven (`get_current_goal`, goal-aware suggesters, goal-staleness watcher). Add only a framing line to its composed context when both exist: "The lab's World is <name>; the user's goal is <goal>. Teach toward the goal using the World's terms." (one seam in `_builtin_buddy._compose_prompt`, failsoft like the existing world-skill block).
- **Docs**: rewrite `docs/world-forge.md` tiers section (both tiers create + curate; model size differs); README "getting started" leads with World selection.

## Phase 5 — Curator review (visible agent curation)

- `POST /api/worlds/review` (one at a time, `inference_slot("world-review")`, `complete_preferring_deep` — on minimalist this is the 1B, on maximus the 3–7B/deep; NEVER tier-gated, limit N terms/run — default 16) → judge each term → write flags to **seal-exempt** `review.json` sidecar in the bundle dir `{schema:"arail.world-review/v1", world, reviewed_at, model, flags:[{slug, verdict: accept|correct|reject, better_category?, bad_edges?, note}]}`. `GET /api/worlds/review` returns current flags + running state.
- Editor UI: ⚑ badge on flagged rows with the Curator's note; "Apply suggestion" (one tap: fixes category / strips bad edges via the existing PUT). Worlds page + editor both get "Ask the Curator to review" (cyan action — it's a data/agent task, not a primary mutation).
- Activity events ("Curator reviewed 16 terms in 'Indoor Plants' — 3 flags") so the dashboard narrates agents working for the student.

## Phase 6 — tests, docs, verification

Tests (new: `tests/test_world_forge_gate.py`, `_pipeline.py`, `_seal.py`, `_api.py`, `tests/test_world_terms_editor.py`; reuse `tests/world_bundle_builder.py` + FakeRouter with canned `ModelResponse` scripts):
- Gate/provenance parity tables (empty corpus vacuous-ok; self-edge; dict-shaped edges; `model:qwen2.5:7b` recognized; mixed rollup).
- Pipeline vs 1B-garbage responses (non-JSON, wrapped arrays, `"short":"A"`) — survives, gate passes; cancellation; empty → GateRefused.
- Sealer round-trip through ARAIL's `verify_seal`+`check_*`; reseal-after-edit keeps seal + flips tier; SKILL.md parses via `skills_loader.parse_frontmatter`, adversarial term fields (`\n---\n`, `\n## pwned`) neutralized (mirror `test_world_skill_qa_adversarial.py`).
- API integration: 202→status→preview→confirm→mounted→`load_world_skill` composes→theme applies; 409s (busy/slug/unmounted); CSRF rejections on every write; editor loop (PUT→fresh `verify_seal` on disk→staged md updated; DELETE auto-close; hostile PUT fields contained); review flags round-trip.
- UI smoke + token-compliance ratchet stays green.

Docs: update `docs/world-forge.md` status (design → shipped v1 scope), README surfaces list, `docs/world-theme-contract.md` note that ARAIL is now a second producer of `dac.world-bundle/v1` (schema unchanged — flag to DaC per ADR-0004).

**Manual verification (single uvicorn via `.claude/launch.json`, OOM-safe):** forge **"Indoor plants & their care" / 25 terms** on the real local model → watch stage progress → preview shows plant categories → Accept & Mount → theme flips, dashboard reads "Studying: Indoor Plants & Their Care" with world-derived suggested goals → accept the suggested study goal → autoresearch starts against the staged terms → Buddy answers a Snake Plant question from the glossary and references the goal → open Knowledge → World Terms → edit Snake Plant's short definition + add `related: succulents` → tier flips to mixed → Ask the Curator to review → a flag appears → apply suggestion → unmount/remount survives (seal valid). Also: fresh-lab welcome flow shows the "Pick your World" step.

## Non-goals (named)

- **Leveled worlds axis** (5th-grade vs graduate as levels of one world) — different subject strings v1; follow-up = DaC's proposed leveled-worlds ADR.
- **Full promotion pipeline** (model-asserted → sourced with retrieved sources) — Curator flags only in v1; promotion belongs to the autoresearch/AeroLLM epic.
- **Multi-category `tags[]` schema bump** — coordinate with DaC as `terms_schema: 2` later.
- **Curriculum/Reader assembly** — the study experience v1 is glossary + Buddy + study goal.

## Critical files

- NEW `src/arail/world_forge.py` (~600 lines; do NOT touch `src/arail/agents/forge.py` — that's the Agent forge)
- `src/arail/portal/app.py` (forge/terms/review endpoints + `/worlds` route; clone the CSRF envelope L2764-74 and the async-generation pattern L3085-3120)
- NEW `templates/worlds.html`, `static/js/worlds.js`, `static/worlds.css`, `static/js/world-terms.js`; MOD `knowledge.html`, `static/nav.js`
- Reference (read-only): `~/ProJects/qukaizen-dac/scripts/{forge-world,export-bundle,reconcile-world}.mts`, `src/{gate,provenance}.ts`, `src/arail-export/skill.ts`
- Reuse as-is: `src/arail/world_mount.py` (`mount`/`swap`/`verify_seal`/`_SLUG_RE`), `src/arail/world_theme.py` (`parse_world_theme`), `src/arail/router/core.py` + `deep_policy.py`, `src/arail/dictionary.py` (pattern reference), `src/arail/portal/scheduler.py` (`inference_slot`), `tests/world_bundle_builder.py`
