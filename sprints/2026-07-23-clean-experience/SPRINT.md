# SPRINT — 2026-07-23-clean-experience

**Product:** arail
**Branch:** `qukaizen/arail-platform-review-48ba04` (worktree)
**Scope:** One coherent cleanup pass making ARAIL match its own promise — "educate the
user and be an intuitive, inviting playground to explore the powers of AI" — across four
streams: intuitive model building (truth-in-UI), KB/DaC/agent data-flow button-up,
no-auto-checks frictionless boot, and inviting onboarding, plus security quick wins.

## Owner decisions (2026-07-23, Charlie — binding)

1. **Model path:** Honest UX + distill-now. This sprint does truth-in-UI only; the real
   bake→seal→compact build path remains `sprints/2026-07-22-distill-now/` (separate).
2. **Researcher:** build a **real mini experiment engine** — label-only rejected. The
   fabricated-metrics path is deleted, replaced with genuinely measured on-device
   experiments (three archetypes; see ARCHITECTURE.md Part A).
3. **Execution:** one cleanup pass in one session, P0s first (not staged per-stream sprints).
4. **Security:** quick wins included (tier guards, plugin confirm, secret perms, Marimo
   URL, hand-off card); full dashboard auth **deferred**.
5. **Hard constraint:** no package/version/model auto-checks at boot or runtime unless
   explicitly invoked. `ARAIL_AUTOCHECKS` defaults **off**; `arailctl doctor` is the
   explicit checkup surface. Airgap/egress guard untouched.

## Artifacts

- `ASSESSMENT.md` — the platform critique (think phase). Raw sweeps in `reports/`.
- `ARCHITECTURE.md` — the build spec (plan phase): Part A mini-engine design, Part B
  no-auto-checks design, Part C the 8 ordered work packages with verification gates.
- `PROMPT.md` — reusable "cleaner experience" master prompt (deliverable).
- `BUILD_LOG.md` — appended per work package during build (pending).
- `REVIEW.md` / `TEST_REPORT.md` — architect review + QA (pending).

## Ledger

| Phase | Status | Notes |
|---|---|---|
| think (assessment) | DONE | 9-dimension multi-agent sweep + verified synthesis (`ASSESSMENT.md`) |
| plan (architecture) | DONE | Design pass re-verified all anchors on disk (`ARCHITECTURE.md`); plan approved by owner |
| build WP0 — sprint artifacts | DONE | this commit |
| build WP1 — quiet boot | DONE | ARAIL_AUTOCHECKS master gate, parse_offline, doctor; tests green (see BUILD_LOG.md) |
| build WP2 — egress honesty | DONE | Buddy HF consent-gated + local correlation, browser consent, chmod 0600; tests green |
| build WP3 — security quick wins | DONE | tier guards on 11 routes, plugin confirm, chmod 0600, Marimo URL, hand-off + bind warnings; tests green |
| build WP4 — model-surface truth | DONE | /build explainer + actionable nucleus state, docs/models-on-disk.md, /tuning banner, unbuilt-plan banners, adapter stub relabel |
| build WP5 — mini experiment engine | PENDING | the new subsystem; fabrication deleted |
| build WP6 — KB/DaC button-up | PENDING | index leak, wipe contract, classifiers, banners |
| build WP7 — onboarding truth | PENDING | default goal, one action name, wizard for CLI users |
| build WP8 — docs drift & pruning | PENDING | CLAUDE.md refresh, legacy names, dead surfaces |
| review (architect) | PENDING | over cumulative diff |
| test (qa) | PENDING | arail gating: 30% setup / 30% Buddy / 20% security / 10% happy / 10% regression |

## QA gating (arail, per workspace CLAUDE.md)

Shippable when: setup-on-clean-machine holds (quiet boot < 5 s to first byte, no probes),
Buddy quality (no unconsented egress, honest outputs), security (guards + perms verified),
onboarding clarity (one action name, truthful copy), failure-mode grace (cannot-run states
teach). Verification gates per WP are in ARCHITECTURE.md Part C.
