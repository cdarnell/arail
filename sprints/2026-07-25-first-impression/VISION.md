# VISION — ARAIL's first-impression experience

> Output of the visionary pass for `sprints/2026-07-25-first-impression/`.
> Source brief: `docs/briefs/first-impression-experience.md` (branch
> `qukaizen/arail-fable-briefs`). Companion: `EXPERIENCE_SPEC.md` in this
> directory. This is a design artifact — Phase 0 (discover) and Phase 1
> (design) only. **No code changes accompany this document.**

## Who this is for

Two people, not one:

1. **The handed-a-laptop friend.** A non-expert, no cloud account, who just
   ran `git clone` and either double-clicked through the browser welcome
   flow or ran `./arailctl setup` in a terminal because a friend told them
   to. They don't know what "airgapped" means and shouldn't have to. They
   will bounce off anything that reads as a form to endure.
2. **The returning operator.** Someone who already trusts the lab and wants
   to point it at a new domain — swap Worlds the way you'd load a new save
   file — without CLI archaeology or accidentally nuking work they meant to
   keep.

Today's product serves neither well: the friend who used the CLI (the
*documented* quickstart path — `README.md`'s three keystrokes) never sees a
World, and the returning operator has no portal path to swap at all —
`arailctl world swap` from a terminal is the only door, with zero
confirmation before it deletes the previous World's knowledge base.

## The win condition

A non-expert, on a fresh clone with no cloud account, reaches a **real
measured result** in about five minutes and can say, in their own words:

- what ARAIL is (a private lab that runs on their own machine),
- why it's private (their data doesn't leave — stated in terms of *their*
  data, not our architecture),
- what a World does (it re-orients the whole lab — knowledge, agents,
  vocabulary, look — around something they care about; AI & ML is the
  default and teaches AI while using it).

This must hold for **both** entry points — cold browser start and
CLI-onboarded cold start — and for **reset-into-a-new-World**, with no dead
ends, no fabricated numbers, no boot-time probes, and no redirect loops.
Success is emotional as much as functional: confidence, understanding, and
a reason to come back — not a form endured.

## What "wanting to come back" looks like

Not a notification, not a streak counter — those would be fabricated
engagement, which the product's own truth-in-UI rule forbids. The honest
hook that already exists in the codebase: **the lab keeps working while
you're away and has something real to report.** Concretely:

- The Researcher's autoresearch loop runs real, code-measured experiments
  (`src/arail/research/mini_experiments.py`) and writes an honest report —
  a genuine "here's what I found" moment, not a canned congratulation.
- The dashboard's activity stream and goal-suggestion chips are populated
  from the mounted World's own spec, so returning to a different World
  feels like a different lab, not a reskinned form.
- Swapping Worlds is cheap and safe enough to feel exploratory — "what if I
  pointed this at photography instead" — rather than a one-way decision you
  have to research first.

If a future pass wants a stronger "come back" signal (a digest, a
scheduled report), it must be built the same way the rest of ARAIL is:
measured, opt-in, and never fabricated. Not scoped here.

## Explicit non-goals for this pass

- **No new World bundles.** Photography, biology, and video games stay
  illustrations in copy unless a bundle already exists on disk (it does,
  locally, for photography/physics — but those are untracked and must not
  be assumed present on a clean clone).
- **No `setup.sh` intent-taxonomy redesign.** The CLI's competing
  `LAB_INTENT` question (9-option taxonomy + goal + hours) is a real
  divergence from the Worlds model, flagged in `EXPERIENCE_SPEC.md` as a
  follow-up, not resolved here.
- **No auth/session changes.** The "no login, loopback + Host-allowlist is
  the perimeter" model is out of scope; the honest disclosure of it in
  Step 1's warn box is preserved, not touched.
- **No new `reset.sh` portal surface, no scopes added.** The spec asks for
  one marker-file addition and one existing-scope fix (`reset pkb` leaving
  a dangling mount); it does not design a reset UI.
- **No theming/token rework.** `design.md`'s theme system is reused as-is.
- **No changes to the compiled-KB gate, `onboarding_gate` ordering, or any
  route.** Labels can move; endpoints and gates do not.

## Recommendation: build the Video Games World next

Of the illustrative Worlds this experience will *name* (photography,
biology, video games), **Video Games is the one worth actually building
next**, and a companion brief already exists for it:
`docs/briefs/video-games-world-build.md` (Layer A — the sealed bundle
itself — is already in progress on `qukaizen/video-games-world-layer-a-91739b`).

The reasoning, carried over from the brief and confirmed by this session's
discovery of `mini_experiments.py`: it is the World that most directly
*demonstrates* ARAIL's one genuinely distinctive, already-built capability
— a real, measured, on-device search loop — to a broad, non-enterprise
audience. "Mount a World, point it at your driving sim, and your lab finds
your optimal settings by actually measuring them on your hardware" is a
sales pitch that requires no engine work to become true; `mini_experiments`
already does the measure-don't-guess loop, it just needs a
`game_config_optimization` archetype and a sealed gaming glossary. Nothing
else in the illustrative-Worlds list has an existing engine this ready to
back it up — photography and biology would need net-new autoresearch
archetypes with less obvious "gamer's own hardware" payoff.

This is a recommendation for the *next* sprint, not scope here: this pass
only asks that the onboarding copy be honest that Video Games is an
illustration today, not a shipped World, and that it not overclaim Layer
B/C (the measured optimization loop, the opt-in hybrid scouting) as already
built.

## Recommendation to proceed

Proceed to Phase 2 (build) after operator approval of `EXPERIENCE_SPEC.md`.
The core mechanism — treating welcome Step 3 as a single reusable,
addressable component reached from three doors — is a small, well-bounded
change relative to the size of the gap it closes (the CLI-onboarded path,
today's largest and most-verified first-impression failure).
