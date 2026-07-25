# The Video Games World — what it means today

> EXPERIENCE-facing note for onboarding copy. Written for Layer A
> (`lab/worlds/video-games/`, forged by `scripts/forge_video_games_world.py`).
> See [`docs/briefs/video-games-world-build.md`](../briefs/video-games-world-build.md)
> for the full build brief and Layers B/C.

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

## What it deliberately does not do yet

The brief's flagship feature — a lab that measures your actual hardware and
finds your optimal in-game settings while you're away, and (opt-in) watches
for driver updates or new game releases — is **declared, not implemented**.
`capabilities.json` lists three desired-but-not-yet-built capabilities
(`research.game-config-optimization`, `scout.driver-watch`,
`scout.release-watch`); ARAIL resolves and shows them honestly as
unavailable until Layers B and C ship. Nothing in this World pretends that
work is done.

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
