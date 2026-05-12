# VISION — Surface autoresearch git branches in the Research tab

**Sprint ID:** 2026-05-11-experiment-branches
**Date:** 2026-05-11
**Branch:** qukaizen/arail-experiment-branches

## The win condition

A user opens the Research tab and immediately sees:
1. **The brand thesis** — "ARAIL is A-rail for experiments. If you can measure it, we can improve it."
2. **Their experiment branches** — a live list of `autoresearch/*` git branches with win/loss status, headline metric deltas, and click-to-expand commit logs.

The user can answer the question "where are my experiments?" in one click, with no terminal commands.

## The wedge

The git plumbing **already exists and works**. `src/arail/experiments/autoresearch.py` creates `autoresearch/<exp_id>` branches per knob variant, commits winners, leaves losing branches as inspection points. The whole loop is wired through `git_ops.py` with a small safe-commit allowlist. But none of this is visible in the lab UI — it's only shown on the sibling `/tuning` page that most users never find.

We are not building a new capability. We are **making visible what the lab already does**, and rebranding around it.

## The user

A friend/family member running ARAIL on their laptop. They started a tuning sweep an hour ago. They want to:
- See which variants the agent tried.
- See which won and by how much (tok/s delta).
- Click into a winning branch and read its commit message.
- Trust that "if you can measure it, we can improve it" is not marketing — it's actually rendering on screen, sourced from git.

## Disconfirming evidence we considered

- *Risk: The bench JSONL may not have a `git_branch` column.* — Flagged in the architecture as a conditional change to `bench.append_run`. Verifies first, adds field if missing. Safe.
- *Risk: Many `autoresearch/*` branches accumulate over time.* — UI defaults to `--count=100` newest, sorted by committer date. Cleanup remains a terminal operation (`git branch -D autoresearch/*`) for now.
- *Risk: Doing too much.* — Scope was deliberately locked: tuning loop only (not the Researcher agent's 6-step loop), read-only (no delete/checkout/archive), rebrand limited to research.html tagline + empty-state copy. Researcher-to-git wiring deferred to a follow-up.

## Why now

User feedback: "Help tie in the GIT commits, like where are they in our lab? Make that easy and fun for the user to see the different experiment branches." The infrastructure for the thesis is built and untested in front of users because it's invisible. Surfacing it costs ~7 files of mostly read-only code, and immediately validates whether the framing resonates.

## Recommendation

**Proceed.** Scope is tight. The risk surface is small (read-only endpoints, regex-validated branch names, no new mutation paths). The brand payoff is large: the Research tab finally embodies the product thesis.
