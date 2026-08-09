# Build log: Compiled-KB bootstrap (QA-6)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 6bef72c
**Started:** 2026-08-09

## Plan

Given the size of ARCHITECTURE.md's scope, this build targets the
"recommended implementation order" §1-5 and §8 (the mechanism that actually
fixes QA-6: the empty-gate bug and its mount-time bootstrap), plus the unit
and integration tests the architect assigned to the builder. Caller UX
updates (§6: doctor/lab_brief/goal-drafter/researcher wiring;
§7: promote_bulk + /dac UI) are large, independent surfaces; deferred and
called out below rather than half-built under time pressure. This is a scope
note, not a design disagreement — no architect gap found.

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/compiled_kb.py` | `manifest_present`, `gate_state` | unit (`tests/test_compiled_kb.py`) | pending |
| 2 | `src/arail/pkb.py` | `retrieve_for_agents`; `search_for_agents` becomes `["hits"]` | unit + regression (`tests/test_pkb_gate.py` untouched) | pending |
| 3 | `src/arail/compiled_kb.py`, `world_mount.py` (revoke callers) | `auto_approve_world_terms`, sticky `unapproved.json` | S1-S3-style unit tests in `test_compiled_kb.py` | pending |
| 4 | `src/arail/compiled_kb.py`, `arailctl` | `bootstrap()` + CLI + `./arailctl pkb bootstrap` | unit + I2-style | pending |
| 5 | `src/arail/world_mount.py` | mount() step 3.5 hook | integration (I1/I3-style) | pending |
| 6 | `arailctl` (install verb) | call bootstrap once, non-fatal | manual/CLI smoke | pending |
| 7 | `docs/conversation-memory.md` sibling doc | document sentinel + verb | n/a | pending |

Deferred (documented, not implemented this pass — flagged to orchestrator):
- Caller updates: `lab_brain.py`, `agents/researcher.py`, `portal/app.py`
  goal drafter, `lab_brief.py`, `doctor.py` gate_state wiring.
- `promote_bulk` endpoint + `/dac` empty-state/bulk-select UI +
  `ARAIL_APPROVED_ONLY=off` persistent banner.

## Execution

(filled in per commit)

## Architect feedback required

(none yet)

## Final state

(filled in at the end)
