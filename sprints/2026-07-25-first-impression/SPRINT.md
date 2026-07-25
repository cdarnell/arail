# SPRINT — 2026-07-25-first-impression

**Product**: ARAIL (`~/ProJects/qukaizen-arail`)
**Branch**: none yet — artifacts written uncommitted for operator review
**Scope**: first-impression experience (cold start, both entry points) +
reset-into-a-new-World, per `docs/briefs/first-impression-experience.md`

## Owner decisions

- 2026-07-25 — Fable — Phases 0 (discover) and 1 (design) only per the
  brief and the operator's explicit instruction; STOP for approval before
  any Phase 2 build. — binding

## Artifacts

- `VISION.md` — win condition, who it's for, non-goals, Video Games World
  recommendation.
- `EXPERIENCE_SPEC.md` — full discovery map with file:line evidence, the
  Phase-1 design (one World moment / three doors, loop-safety truth table,
  screen-by-screen copy), the consolidated gap list, and the Phase-2 touch
  list for operator review.

## Ledger

| Phase | Status | Notes |
|---|---|---|
| 0 — Discover | Done | Three parallel read-only exploration passes + first-hand re-reads of `welcome_page`, `onboarding_gate`, dashboard route, `current_mount` |
| 1 — Design | Done | `EXPERIENCE_SPEC.md` + `VISION.md` written |
| 2 — Build | **Not started — awaiting operator approval of the spec** | |
| 3 — Verify | Not started | |

## QA gating

No code changed in this sprint yet — QA does not apply to Phases 0/1.
Phase 2, when approved, follows this repo's standard gates (see CLAUDE.md
/ master prompt: truth-in-UI, quiet boot, airgapped default, loop-safety).
