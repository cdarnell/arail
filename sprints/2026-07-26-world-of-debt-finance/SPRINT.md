# Sprint: World of Debt Finance

**Sprint ID:** `2026-07-26-world-of-debt-finance`
**Product:** arail
**Status:** design complete (visionary + architect phases, run via ultracode multi-agent workflow) — awaiting operator sign-off on open questions before `/builder`

## What this sprint is

A new DaC-governed World (`debt-finance`) plus two agents — Debt Advisor and
Consolidation Analyzer — that read a user's manually-staged debt/loan numbers
and surface sourced, named comparisons (credit unions, non-profit lenders,
balance-transfer offers) against the user's current terms. First wedge of a
larger "Modern Finance" world; investing is explicitly deferred.

## Artifacts

- [VISION.md](VISION.md) — six-question framing, win conditions, wedge scope, disconfirming evidence, displacement cost.
- [ARCHITECTURE.md](ARCHITECTURE.md) — full design: World bundle spec, scouting reuse (zero new code), agent tick-loop design, sensitive-data storage resolution, compliance/disclaimer layer, interface contracts, failure modes, test strategy, tech debt.
- [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) — 7 items needing explicit operator decision before build starts.

## How this was produced

Run via a 14-agent `Workflow` orchestration (ultracode) rather than the
standard single-pass visionary→architect handoff, given the sensitivity of
the domain (real financial data, compliance exposure):

1. **Understand** (4 parallel) — explored World declare/gate/seal/mount
   mechanics, the generic `scouting.py` precedent and the operator's standing
   "scouting must be generic, never per-World" rule, portal surface/tier-gate
   patterns, and agent-loader + sensitive-data-handling conventions.
2. **Frame** (4 parallel) — formalized VISION.md while independently drafting
   3 competing architecture angles (MVP-first, compliance-and-trust-first,
   world/agent-architecture-first).
3. **Synthesize** — merged the 3 angles into one ARCHITECTURE.md, grafting
   the best of each.
4. **Verify** (4 parallel adversarial reviews) — regulatory/compliance
   (WEAK_PASS), data privacy/security (**BLOCK**), World/DaC contract
   conformance (PASS), technical feasibility (WEAK_PASS).
5. **Finalize** — the BLOCK (agent output would have been written to
   `decisions.md`, which this repo's own `/api/pkb/search` returns ungated to
   anyone with portal access) was resolved by verifying `_iter_pkb_files` and
   `/api/pkb/search` directly against source, then re-routing all sensitive
   agent output to a new non-PKB location (`lab/data/user-import/debt-finance/`)
   that is structurally outside the PKB walk — not merely policy-excluded.

## Key design decisions

- **No new portal UI in v1.** A loan-comparison table is a domain-specific
  form; the operator's standing rule (post–Video Games World) holds unless a
  genuinely World-generic comparison surface is designed. Held, not built.
- **Zero new code in `scouting.py`/`agenda_watch.py`.** The World's
  `knowledge_sources[]` feeds the existing generic scouting/consent/airgap
  mechanism unchanged — this is the concrete proof the operator's "scouting
  must be generic" rule survives contact with a real domain.
- **Sensitive data lives entirely outside `lab/pkb/`.** Input staging
  (`lab/data/user-import/debt-finance/`) and agent findings
  (`lab/data/user-import/debt-finance/findings/`) are both structurally
  unreachable by the wiki indexer and `/api/pkb/search` — verified against
  `_iter_pkb_files`, not assumed.
- **Numbers are code-inserted, never LLM-paraphrased**, and a code-level
  disclaimer + institutional-claim guardrail runs on every write — closing
  the review finding that prompt-only compliance language is an insufficient
  safeguard.
- **Investing stays out structurally**: no `investing` category is declared
  in `spec.json`, so the gate's category law rejects it by construction, not
  by convention.
- **Autoresearch integration rejected**, not deferred — `/research`'s own
  honesty contract requires every number come from an actual on-machine run;
  a debt hypothesis has none.

## Next step

Operator reviews [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) (disclaimer wording,
which real institutions to name, real-vs-stand-in test data, airgapped vs.
hybrid intent, reveal-affordance fast-follow, two cross-repo `qukaizen-dac`
proposals, and a possible CLAUDE.md policy addition). Once resolved, proceed
to `/builder` against ARCHITECTURE.md.
