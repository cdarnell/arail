# Brief: build the "Video Games" ARAIL World — a themed, grounded lab that finds each gamer their optimal setup

> **Hand-off brief for Fable.** Companion to
> [`first-impression-experience.md`](./first-impression-experience.md). Layer A
> is a shippable World on its own; build it first.

## Context & why this exists
ARAIL re-themes and re-stocks itself around a "World." AI & ML is the default.
This task builds a second first-class World — **Video Games** — because it's the
World that best showcases ARAIL's measured autoresearch loop to a public,
non-enterprise audience: a gamer mounts it, and their lab starts finding the
optimal game configuration for THEIR hardware, watching for driver updates worth
installing, and surfacing newly released games for review. Repo:
`~/ProJects/qukaizen-arail`. READ FIRST: `CLAUDE.md`, the master prompt
(`sprints/2026-07-23-clean-experience/PROMPT.md`),
`docs/adr/0002-chat-memory-and-the-dac-boundary.md`, and study the existing
`lab/worlds/ai/` bundle as the reference implementation. Verify against disk;
verify LOCALLY (no GitHub Actions).

## The World-bundle contract you must follow (from lab/worlds/ai/)
A World is a SEALED `dac.world-bundle/v1` bundle, forged via the shared
`dac_world` package (ARAIL's `src/arail/world_forge.py` re-exports it;
`src/arail/portal/world_routes.py` injects the theme validator). Files, all
sha256-sealed in `manifest.json`:
  • `manifest.json` (dac.world-bundle/v1) — world slug, display_name,
    world_sha256, per-file hashes, provenance counts.
  • `face.json` (dac.world-face/v1) — name, tagline, palette_hint,
    domain_framing, vocabulary_register, and the dark/light `theme` palette
    (`dac.world-theme/v1`, validated by `arail.world_theme.parse_world_theme`).
  • `spec.json` — slug, display_name, `categories[]`, `knowledge_sources[]`.
  • `terms.json` — the grounded glossary; every term carries provenance
    (sourced vs model), a definition within the forge's length budgets.
  • `capabilities.json` (dac.world-capabilities/v1) — declared capabilities.
  • `SKILL.md` — the World's research persona/skill.
  • `arail-plugin.json` (dac.arail-plugin/v1) — the mountable plugin wrapper.

## CRITICAL boundary — what goes in the SEALED bundle vs runtime input
- IN the bundle (general, shareable, sealed): the gaming glossary (graphics
  settings, GPU/CPU/RAM concepts, sim-racing terms, driver concepts), the theme,
  the categories, the SKILL persona, the DECLARED capabilities.
- NOT in the bundle (per-user, runtime, never sealed): the user's actual
  hardware specs, a specific installed game's chosen settings, driver versions
  on their machine. These are runtime inputs the autoresearch archetype consumes
  — the same way chat memory stays out of DaC. Do not bake user data into a
  World bundle; that would violate the DaC boundary (ADR-0002).

## Layered scope — Layer A is a shippable World on its own
### Layer A — author & forge the Video Games World bundle (deliverable alone)
Produce a sealed, mountable Video Games World that re-themes the lab and grounds
gaming knowledge:
  • `terms.json`: a real, SOURCED glossary — graphics settings (resolution
    scaling, anti-aliasing types, shadow/texture/LOD, frame-gen, ray tracing,
    VRR/G-Sync/FreeSync, frame pacing, 1%-lows), hardware (GPU/VRAM, CPU bottleneck,
    RAM/timings, thermals), and sim-racing specifics (FFB, tire model, wheel/pedal
    calibration). Cite sources; respect the forge's length budgets and provenance
    gate (sourced > model). Use the same forge path that produced the AI World.
  • `face.json`: a distinct gaming theme (e.g. an arcade/neon or "performance
    HUD" palette, dark + light), a tagline, and a `domain_framing` that says what
    this World studies and that every claim is source-grounded.
  • `spec.json`: sensible `categories[]` (Graphics Settings, Hardware, Sim Racing,
    Drivers, Performance Metrics) and `knowledge_sources[]`.
  • `SKILL.md`: the gaming-research persona — how it reasons about a config search
    (change one variable, measure, keep the win), reads a game's tunables, and
    respects the user's hardware envelope.
  • `capabilities.json`: declare knowledge-grounding per category (works today),
    PLUS declare the Layer-B dynamic capabilities as `desired` (see below) so the
    World advertises its ambition; ARAIL will honestly show them "available" only
    when the runtime implements them.
  • Seal it, wrap it in `arail-plugin.json`, confirm it mounts:
    `./arailctl world mount lab/worlds/video-games` re-themes the lab and grounds
    gaming Q&A. Add a `verify-shipped` check like the other bundles.
DONE for Layer A = the World mounts, re-themes, and answers gaming questions from
its own gated glossary with citations — a complete, honest product on its own.

### Layer B — the flagship: measured game-config autoresearch (runtime feature)
This is real engineering in `src/arail/research/mini_experiments.py` + agents,
NOT bundle authoring. Add a new experiment archetype, e.g.
`game_config_optimization`:
  • INPUTS (runtime, user-provided, never sealed): a hardware profile
    (GPU/CPU/RAM — captured via a simple form or a local, CONSENT-GATED read) and
    a game's tunables (the "manual": the set of settings + allowed values, entered
    or imported per game).
  • WHAT IT MEASURES: it runs a real, on-device search over configurations and
    measures an honest objective (e.g. a benchmark's avg FPS AND 1%-lows, or a
    frame-time-stability score) — following the existing engine's discipline:
    measured or it does not exist; "cannot_run" when it can't measure; success is
    computed, never defaulted True. Do NOT fabricate FPS numbers. If ARAIL can't
    execute the game/benchmark, it must say so and degrade to a
    knowledge-grounded RECOMMENDATION clearly labeled as advice, not measurement.
  • OUTPUT: the optimal config found for THIS hardware, with the measured
    tradeoffs, written to the experiment tracker with provenance — the "your lab
    worked while you were away and here's what it found" payoff.

### Layer C — optional, HYBRID-ONLY, consent-gated scouting (do last, clearly bounded)
Only in `LAB_MODE=hybrid`, only behind the existing consent store, never on by
default, never with user data in third-party URLs:
  • driver-watch: notice new NVIDIA/GPU drivers and research whether a given
    release is worth installing for the user's setup — surfaced as a reviewable
    finding, never auto-installed.
  • release-scout: notice a newly released (e.g. driving) game and bring it into
    the knowledge base FOR HUMAN REVIEW via the compiled-KB gate — never
    auto-approved.
These are the vivid "agents on the lookout" features from the vision — build them
honestly as opt-in, gated, and airgapped-off-by-default, or leave them declared
(capabilities.json) but unimplemented (shown as unavailable) until a later pass.

## Hard guardrails
- TRUTH-IN-UI: measured numbers only; declared-but-unimplemented capabilities
  show honestly as unavailable; recommendations are labeled as advice, not
  measurement. No fabricated FPS/benchmark values, ever.
- AIRGAPPED default sacred; all of Layer C is opt-in + consent-gated; no user
  data (hardware, game, drivers) in any third-party URL.
- DaC boundary: user/runtime data never enters a sealed bundle (ADR-0002).
- QUIET BOOT: mounting/using this World adds no boot-time probe; `ARAIL_AUTOCHECKS`
  untouched. Any benchmark/experiment runs only when the user starts it.
- Reuse the existing forge, mount, capabilities, and experiment-tracker
  primitives — don't rebuild them.

## Verify
- Layer A: `./arailctl world verify-shipped` passes for video-games; mount it and
  screenshot the re-themed lab + a grounded, cited gaming answer (live, local).
- Layer B: unit tests for the archetype's measured/cannot_run/never-default-True
  paths (mirror `tests/test_mini_experiments.py`); a live run on a real game or
  benchmark if one is available, else the honest "cannot_run" path demonstrated.
- Layer C: tests proving it is inert in airgapped mode and gated on consent in
  hybrid; no user data in any outbound URL.

## Deliverable & sequencing
Separate PRs on `qukaizen/arail-<slug>` branches, in order: (A) the World bundle,
(B) the config-optimization archetype, (C) optional gated scouting. Layer A ships
value immediately; B is the showcase; C is the flourish. Commit an
EXPERIENCE-facing note so the onboarding's "what a Video Games World means" copy
can point at what actually works today.
