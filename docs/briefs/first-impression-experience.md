# Brief: ARAIL's first-impression experience — cold start AND reset-into-a-new-World

> **Hand-off brief for Fable.** This is an input spec, not a finished design.
> Follow the Phases: discover, then produce a design artifact and STOP for the
> operator's approval before building. Companion brief:
> [`video-games-world-build.md`](./video-games-world-build.md).

## Who you are working for
ARAIL — Autoresearch AI Labs — a local-first, airgapped-by-default AI research
lab that people CLONE and adapt (a blueprint, not a product). Repo:
`~/ProJects/qukaizen-arail`. READ FIRST, in order: `CLAUDE.md`,
`sprints/2026-07-23-clean-experience/PROMPT.md` (the master prompt — binding),
`README.md`, `design.md`, `docs/agents-explained.md`. Verify every claim against
the actual code before writing anything. Run all verification LOCALLY — this
operator does NOT use GitHub Actions.

## The vision (this is the point — read twice)
The first time someone opens ARAIL — and every time they RESET INTO A NEW WORLD —
must feel clean, calm, and inviting. In five minutes, with no cloud account and
no jargon, a non-expert friend should come away understanding:
  • WHAT ARAIL is (a private lab that runs on their own machine),
  • WHY it works the way it does (local-first / airgapped = their data never
    leaves; a "World" re-themes and re-stocks the whole lab around a domain they
    care about),
  • HOW to take their first real action and see a real result.
And they should WANT TO COME BACK. The success test is emotional as much as
functional: confidence, understanding, and a reason to return — not a form they
endure. If a screen makes a novice hesitate, it has failed. This is a large,
design-led undertaking — treat it like a mini-sprint. Produce a design artifact
and STOP for the operator's approval before building (see Phases).

## The World concept — the heart of ARAIL, and how to teach it
A "World" is not just a theme; it re-orients the entire lab around a domain — its
knowledge base, its agents' focus, its vocabulary, and its look. Onboarding must
make this concept click with relatable examples.

- DEFAULT / INITIAL WORLD = **AI & Machine Learning** (it already ships as the
  default identity when nothing else is mounted — `lab/worlds/ai`, and the
  dashboard's "operator / AI-ML default when unmounted"). Frame its dual promise
  explicitly: in the AI & ML World the user both LEVERAGES AI (runs models,
  autoresearch) AND is EDUCATED about AI/ML — the World's knowledge base teaches
  the concepts as they work. "Use the power of AI, and understand it."

- Teach "what an ARAIL World of X means" with concrete, relatable examples so the
  idea generalizes. Illustrations to use in the copy:
  • Photography — the lab becomes a photography studio-of-knowledge: agents and
    the KB oriented around lenses, lighting, editing workflows; autoresearch
    could compare, e.g., develop settings or gear tradeoffs.
  • Advanced Biology — the lab oriented around a research domain: papers, terms,
    and methods for that field, with agents summarizing and connecting findings.
  • **Video Games (flagship worked example — make this vivid):** you mount a
    "Video Games" World and point it at, say, a driving-simulation game. The
    agents read the game's manual so they know its tunables/toggles, they know
    your hardware specs, and autoresearch kicks off EXPERIMENTS to find YOUR
    optimal configuration on YOUR machine — measured, not guessed. In hybrid
    mode (opt-in), agents can also watch for new NVIDIA drivers and research
    whether a given release is worth installing, or notice a newly released
    driving sim and pull it into the knowledge base for your review. This is the
    "your lab works while you're away, then reports what it found" promise made
    tangible.

- WHY the gaming example is credible (use it, don't overclaim it): the
  "find the optimal config by measuring options on this machine" loop is exactly
  what the real autoresearch engine already does
  (`src/arail/research/mini_experiments.py` — measured metrics, honest
  "cannot run"). So present it as a real application of an existing capability,
  not a promise of unbuilt magic. The actual Video Games World build is specified
  in the companion brief `video-games-world-build.md`.

## Honesty rule for the examples (non-negotiable)
Truth-in-UI applies to the sell, too. The AI & ML World exists today; other
Worlds (photography, biology, video games) are ILLUSTRATIONS of the same
pattern — label them as examples/possibilities, not shipping features, unless a
bundle actually exists on disk. Anything that reaches the internet (driver
watching, scouting new releases, pulling in new content) is an OPTIONAL,
CONSENT-GATED, HYBRID-MODE capability — never on by default, and the copy must
say so plainly. Never imply cloud/egress is the default or required.

## The two entry points it must serve
1. COLD FIRST LOAD.
   - Browser onboarding today = `templates/welcome.html`, a 3-step flow
     (Step 1 passphrase → Step 2 network mode → Step 3 "pick your lab's World";
     kicker `#wc-kicker`, JS `showModeStep()` / `showWorldStep()`).
   - CRITICAL GAP: users onboarded via `./arailctl setup` already have
     `ARAIL_PASSWORD` set, so `welcome_page()` (app.py ~1212) redirects them
     straight to `/` — they NEVER see the mode or World steps and land on a
     dashboard with no World mounted and no guidance. The cold-start experience
     must cover BOTH browser- and CLI-onboarded users.
2. RESET / SWAP INTO A NEW WORLD.
   - Worlds re-theme + re-stock the lab (`src/arail/world_mount.py`,
     `world_theme.py`, `world_forge.py`; bundles in `lab/worlds/`). Ops exist at
     `arailctl world list|mount|swap|unmount` and `arailctl reset [pkb|data|
     full|...]` (`scripts/reset.sh`). Today swapping/resetting is a CLI action
     with no guided in-portal experience — the user is dropped into a re-themed
     lab with little explanation of what changed or why.
   - The same clean, confidence-building flow should wrap choosing / forging /
     swapping a World from inside the portal, so "start fresh in a new World"
     feels intentional and understood, and reuses the cold-start components and
     tone so the 2nd/10th time feels like the same trustworthy place.

## What "inviting and clear" concretely means (design targets)
- Progressive disclosure: one decision per screen, plain language, an obvious
  primary action, an always-available "skip / do this later" that never traps.
- Every screen answers what/why/how in a sentence a non-expert gets. Explain
  airgapped-vs-hybrid in terms of THEIR data, not our architecture.
- The World picker names AI & ML as the recommended default AND teaches the
  concept with at least the gaming example, and PREVIEWS what the lab becomes
  (theme + example terms/capabilities from the bundle's `face.json`) so the
  choice feels real.
- End on a concrete first win + a reason to return — e.g. "your lab is set;
  here's the first thing to try," pointing at a real, MEASURED action (the
  autoresearch throughput goal, or the gaming-config idea), and the honest
  "your agents keep working while you're away" hook. No fabricated results.

## Hard guardrails (from CLAUDE.md + the master prompt)
- QUIET BOOT: add NO boot-time/runtime probe/network/LLM/version check.
  `ARAIL_AUTOCHECKS` stays default-off and untouched. This flow is navigation +
  local reads only.
- AIRGAPPED default is sacred. Present hybrid/cloud only as an optional,
  clearly-explained choice, never the default.
- TRUTH-IN-UI / NEVER FABRICATE: every number is measured on-device or absent.
  "Not set up yet" / "no World mounted" are honest, teachable states.
- KNOWLEDGE CONTRACT: don't weaken the compiled-KB gate or the `onboarding_gate`
  middleware (app.py ~283); don't reorder it.
- Routes stay stable (rename labels, not endpoints). Package stays `arail`.
  Secrets stay in the existing 0600 files, never logged.
- LOOP-SAFETY (the trap that deferred this): `welcome_page()` ALREADY bounces
  onboarded users (password set) back to `/`, so a naive dashboard→World-step
  redirect loops. Requirements: (a) `welcome_page()` must special-case
  `?step=world` and RENDER the World step for onboarded users instead of
  bouncing; (b) any first-load nudge is strictly ONE-SHOT — persist a marker
  (e.g. `lab/data/.world-prompt-seen`) BEFORE issuing the redirect; (c) wire
  that marker into `scripts/reset.sh` so a reset re-arms it; (d) never fire when
  a World is already mounted (`world_mount.current_mount()` not None) or for a
  non-onboarded user.

## Phases — design FIRST, then STOP for approval
Phase 0 — DISCOVER (read-only): map cold-start + World-swap/reset end to end
  (welcome.html steps, the CLI-skip path, world_mount/theme/forge, reset.sh, the
  dashboard first impression, and how a mounted World's identity/theme/example
  content is sourced — `face.json`, `current_capabilities()`). List every gap
  against the vision.
Phase 1 — DESIGN: write `sprints/<date>-first-impression/EXPERIENCE_SPEC.md` —
  screen-by-screen flow for BOTH entry points, the what/why/how copy for each
  moment (including the World-concept explainer with AI&ML-as-default and the
  gaming worked example), the components reused across cold-start and
  World-swap, the one-shot/loop-safety model, and the "first real win + reason
  to return" ending. Plus a short VISION.md (win condition, who it's for, what
  "wanting to come back" looks like, explicit non-goals for this pass). THEN STOP
  and hand the spec back for operator approval before building.
Phase 2 — BUILD (only after approval, in reviewable slices): shared
  World-experience components; loop-safe CLI-user cold-start coverage; the
  in-portal reset/swap-into-a-new-World flow. Atomic commits; tests per slice.
Phase 3 — VERIFY: TestClient tests for every branch of the loop-safety + marker
  + reset-rearm logic; PLUS live verification — boot the portal locally and
  screenshot the actual cold-start and World-swap screens on fresh state,
  because "inviting" can only be judged by looking.

## Scope note
Building NEW World bundles (photography, advanced biology, video games) is a
separate track. THIS effort ships the EXPERIENCE around the existing AI & ML
default and uses the other Worlds as explanatory examples. Flag the Video Games
World as a high-value FUTURE build that would showcase the already-built measured
autoresearch engine (the "optimal game config on your hardware" loop) — note it
in VISION.md as the recommended next World to forge, and see
`video-games-world-build.md`.

## Definition of done
A non-expert, on a fresh clone with no cloud account, reaches a real measured
first result in ~5 minutes and can say in their own words what ARAIL is, why it's
private, and what a World does — including that AI & ML is the default where they
both use and learn AI — for both a cold start and a reset into a new World, with
no dead ends, no fabricated numbers, no boot-time probes, and no redirect loops.
Delivered as focused PRs on `qukaizen/arail-<slug>` branches, each verified
locally, with EXPERIENCE_SPEC.md committed as the record of intent.
