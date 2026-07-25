# The Video Games World — what it means today

> EXPERIENCE-facing note for onboarding copy. Covers Layer A
> (`lab/worlds/video-games/`, forged by `scripts/forge_video_games_world.py`),
> the Layer B measurement engine (`arail.research.mini_experiments`, archetype
> `game_config_optimization`), and the Layer C gating scaffold
> (`arail.research.scouting`). See
> [`docs/briefs/video-games-world-build.md`](../briefs/video-games-world-build.md)
> for the full build brief.

## What mounting it means today

Mounting the Video Games World re-themes the lab to an arcade/performance-HUD
palette and loads a 69-term, fully sourced glossary spanning graphics settings
(DLSS/FSR/XeSS, ray tracing, anti-aliasing, VRR, and more), hardware (GPU/CPU/
RAM behavior, thermal throttling, Resizable BAR), sim racing (force feedback,
tire model, pedal/wheel calibration), drivers (Game Ready vs WHQL, clean
installs, shader compilation), and performance metrics (FPS, frame time, 1%
lows, input latency). Every term cites a real source — Wikipedia, PC Gaming
Wiki, or vendor documentation — the same gated-glossary contract as the AI &
Machine Learning default World.

Like every World, its terms land in the Knowledge Base behind the
Compiled-KB approval gate. Once approved (one tap on `/dac`), chat, the wiki,
and the dictionary answer gaming questions with citations — "Grounded in N
sources" chips pointing at the exact glossary entries used.

## What's built, and what still isn't

The measurement engine for the brief's flagship feature exists:
`arail.research.mini_experiments`'s `game_config_optimization` archetype runs
a real, one-variable-at-a-time search — change a setting, run your benchmark
command, compare avg FPS and 1% lows against baseline, keep the value only if
both improve. It never fabricates: with no benchmark configured, or one that
fails, it reports `cannot_run` and zero metrics, exactly like every other
archetype in this engine.

The wiring around it now exists too, and both pieces are world-generic by
design — nothing in them is gaming-specific:

- **Design an experiment** (`/research`, "＋ design"): enter a hypothesis,
  pick any real archetype, and supply its runtime inputs as variables — for
  this World, a `benchmark_command` and `game_tunables`. The Researcher
  picks the experiment up on its next pass. Inputs are per-user runtime
  data and never enter a World bundle (ADR-0002).
- **Horizon watch** (`docs/horizon-watch.md`): the Librarian acts on the
  agenda this World sealed — its Wikipedia and PC Gaming Wiki feeds are
  checked in hybrid mode, per-feed consent-gated, and a change surfaces as
  a reviewable finding in the `/dac` queue. The same loop watches arxiv.org
  when the AI World is mounted. Free-text agenda entries (like "vendor
  documentation (NVIDIA, AMD, …)") are honestly skipped, never guessed
  into URLs; adding a real driver-page URL to the World's
  `knowledge_sources` and re-forging is all it takes to watch it.

`capabilities.json` declares `research.game-config-optimization`,
`scout.driver-watch`, and `scout.release-watch` as desired. They still
resolve `declared_unavailable` in the capability panel — not because the
code is missing, but because no capability adapter is registered for
research archetypes yet. Nothing here claims more than what's actually
wired.

## What it will never do

This World never states an FPS or benchmark number that wasn't measured.
Definitional facts are fine ("a 144 Hz display refreshes 144 times per
second"); a claim like "GPU X gets N FPS in game Y" is not — and never will
be, in this bundle or in the runtime that eventually builds on it. Any
future recommendation is labeled advice unless it comes from an actual
measurement on the user's own machine.

## 60-second tour

1. Mount the Video Games World (welcome picker, or the Worlds page).
2. On `/dac`, click "✦ Approve all 69 world terms" — the freshly staged
   terms are pending until approved.
3. Ask chat: "What are 1% lows, and why do they matter more than average
   FPS?"
4. See the answer grounded in cited glossary entries — `one-percent-lows`,
   `frame-time`, `frame-pacing` — with source chips you can click through to
   the wiki page or the dictionary entry.
