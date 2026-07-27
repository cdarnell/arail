# Build log: World of Debt Finance

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Plan:** `.claude/plans/snappy-zooming-volcano.md`
**Started:** 2026-07-26

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| A | `scripts/worlds_src/debt-finance/{spec,terms,face}.json`, `compliance/DISCLAIMER.md`, `src/arail/skill_seed.py`, `scripts/forge_debt_finance_world.py` | Author + seal the `debt-finance` World bundle into `examples/worlds/debt-finance/` (opt-in example, not a catalog default) | `tests/test_world_forge_debt_finance_seal.py` | see below |
| B | `src/arail/agents/loader.py`, `src/arail/agents/builtin_seed.py` | Make both agents git-trackable shipped agents (`_SHIPPED` + `ensure_*_folder`) | `tests/test_debt_finance_agents_seed.py` | see below |
| C | `src/arail/agents/debt_finance_compliance.py`, `_builtin_debt_advisor.py`, `_builtin_consolidation_analyzer.py` | Agent bodies: guardrail, disclaimer precondition, arithmetic, tick loops | `tests/test_debt_finance_compliance.py`, `tests/test_debt_finance_agents.py` | see below |
| D | `.gitignore`, `lab/data/user-import/debt-finance/balances.json` (test-only) | Input staging tree + explicit gitignore line | covered by C/F tests | see below |
| E | `src/arail/portal/app.py`, `src/arail/portal/static/js/worlds.js`, `CLAUDE.md` | Generic `user_data` reveal slot + one button on mounted World cards | `tests/test_debt_finance_reveal_slot.py` | see below |
| F | `tests/` | Full Phase F test suite per ARCHITECTURE.md §11 | — | see below |

## Execution

### Phase A — World bundle
- Authored 24 terms across 6 categories (5 base + `retirement-and-secured-credit`
  for ARM/HELOC/401(k)-loan per the plan's decision), sourced to CFPB/NCUA/IRS/
  PenFed/Chase/Ramsey/Clark Howard pages, all real URLs.
- Institution chosen: **PenFed Credit Union** (Pentagon Federal Credit Union),
  NCUA-insured, open membership, public personal-loan rate page — first 3
  `knowledge_sources[]` are URL-kind (CFPB, NCUA, PenFed) so all 3 make it into
  live scouting watches; position 4 (Chase balance-transfer offers page) is a
  citation-only source per the ordering-cap rule, confirmed by the seal-time
  `assert_agenda_ordering` check.
- Added the four skill constants (`debt-strategy-summary`,
  `cite-approved-findings`, `blended-apr-calc`, `breakeven-calc`) to
  `skill_seed.py`, mirroring `observe-lab`.
- **Deviation from the plan's literal path**: the plan says
  `examples/worlds/debt-finance/`, matching `ARCHITECTURE.md`'s bundle location
  language, but also names `forge_video_games_world.py` as the structural
  template — that script seals to `lab/worlds/video-games/` (a catalog
  default). Verified against `examples/worlds/README.md` and
  `lab/worlds/README.md`: catalog defaults auto-mount-visible to every fresh
  lab; `examples/worlds/` bundles are opt-in via "+ Add a World…" /
  `/api/worlds/import`. Followed the plan's literal path
  (`examples/worlds/debt-finance/`) — a personal-finance World should not be a
  forced-default the way `video-games` is. `forge_video_games_world.py` was
  still used as the structural template for `preflight()`/seal/verify shape;
  the two Phase-A-specific checks (`_EVALUATIVE_RE` scan, `assert_agenda_ordering`)
  are new, per the plan.
- Fixed two bugs found only by running the sealer against real content (not
  assumed from the template): `GateResult` has no `.violations` attribute
  (it's `.unsourced` / `.undeclared_category` / `.dangling_edges` — the
  video-games script has the same latent bug, never triggered because its
  gate always passes; left untouched, out of scope); `slug`/`term` fields in
  `terms.json` are (unique-id, display-name), not (world-slug, unique-id) —
  the architecture's illustrative example uses `"slug": "debt-finance"` for
  every term, which is a docs bug, not the real contract (confirmed against
  `dac_world.assert_closed_sourced_graph`, which treats `slug` as the graph's
  node identity).
- **Local dev environment note**: `dac_world` is an unpublished git-ssh
  dependency (`pyproject.toml`). Verification in this sandbox used
  `pip install -e ~/ProJects/qukaizen-dac` into a throwaway Python 3.11 venv
  at `/tmp/arail-venv` (system Python was 3.9, below the `>=3.10` floor) — not
  committed, not part of this repo's tree.
- `PYTHONPATH=src python scripts/forge_debt_finance_world.py` seals cleanly;
  `examples/worlds/debt-finance/agenda.json` contains exactly the 3 intended
  feed URLs.

### Phase B — Agents made durable
(filled in after Phase B lands)

### Phase C — Agent bodies
(filled in after Phase C lands)

### Phase D — Input/output staging tree
(filled in after Phase D lands)

### Phase E — Reveal button
(filled in after Phase E lands)

### Phase F — Tests
(filled in after Phase F lands)

## Architect feedback required

(none yet)

## Final state
(filled in at the end)
