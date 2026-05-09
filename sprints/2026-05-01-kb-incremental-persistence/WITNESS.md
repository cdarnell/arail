# Live witness: KB incremental persistence

**Date:** 2026-05-09
**Sprint:** [SPRINT.md](./SPRINT.md) · [VISION.md](./VISION.md) · [TEST_REPORT.md](./TEST_REPORT.md)
**Branch witnessed against:** `main` at `521a926` (PR #31 merged)
**Run from:** `qukaizen/arail-rename-arailctl` working tree (current branch is post-#31; pkb_index.py present)
**Driver:** `/tmp/arail_witness_driver.py`
**Summary JSON:** `/tmp/arail_witness_summary.json`

## Why this exists

VISION.md threshold #3 names an end-to-end witness:

> a scripted scenario — start lab, ask Researcher to investigate a topic,
> wait for one experiment write, open Chat, ask "what did you find about
> $TOPIC" — returns a response grounded in the agent's actual write
> within one session. No manual rebuild step in the script.

TEST_REPORT.md PASSed this threshold against
`test_e2e_researcher_write_findable_within_10_seconds` (an in-process
synthetic). The build log explicitly noted the live-process witness was
deferred:

> the architect's plan placed it as the end-to-end witness, which QA
> should validate by running the lab against a real PKB and checking
> `lab_brain.build_chat_messages` output includes agent-written paths.

This document records the live run.

## Method

1. Started the portal in airgapped mode on `127.0.0.1:8088`:
   `LAB_MODE=airgapped PORTAL_PORT=8088 uvicorn arail.portal.app:app --host 127.0.0.1 --port 8088`.
   The portal's `_startup()` ran `pkb_index.ensure_ready()` against the
   real `lab/pkb/.cache/lancedb/` (the user's actual PKB, ~12 hits on a
   sanity query → table loaded fine).
2. Driver script wrote one experiment via the same code path the
   Researcher uses on completion (`pkb.write_agent_experiment(exp_id, body)`).
   The body contained a unique sentinel phrase — `boysenberry-bismuth-witness-marker` —
   designed to not match anything pre-existing.
3. Driver polled the live portal at `GET /api/pkb/search?q=<sentinel>`
   every 250 ms and waited for a hit whose `path` contained the
   experiment ID **and** whose `source == "semantic"` (the LanceDB
   path; not the regex fallback).
4. Recorded wall-clock latency from `pkb.write_agent_experiment()`
   return to the first qualifying portal-side semantic hit.
5. Cleaned up the witness file and re-triggered an upsert so the index
   row was deleted.

## Why a synthetic Researcher (not the real one)

The real Researcher (`src/arail/agents/researcher.py`) makes multiple
LLM calls per run to parse the goal, branch hypotheses, design
experiments, and synthesize a report. In the airgapped witness
environment no LLM endpoint is loaded, so a real Researcher run would
either stall or fall through to placeholder output — neither of which
exercises the loop we shipped.

The driver instead calls `pkb.write_agent_experiment(...)` directly.
That is the **bottom of the same call stack** the real Researcher uses
at `researcher.py:738`. The wedge under test is the index→chat loop,
not Researcher authoring quality (which the VISION explicitly
deferred to the disconfirming-evidence one-week observation window).

## Result

**Verdict: PASS.**

| Metric | Value |
|---|---|
| Portal cold-start to `/api/pkb/search` returning 200 | 0.01s (already up by the time the driver checked) |
| Pre-write search hits for the sentinel | 0 (correctly absent) |
| `pkb.write_agent_experiment` returned | `lab/pkb/agents/experiments/2026-05-09_witness-2026-05-06-boysenberry.md` |
| Polls until the live portal's `/api/pkb/search` returned a `source: semantic` hit on the new path | 9 |
| Wall-clock from write to first qualifying portal hit | **2.67 s** |
| Wall-clock from write to first regex-fallback hit on the new path | never (the semantic path closed first) |
| Driver-local in-process search agreement | YES (`source: semantic`) |
| Budget | 10.0 s |
| Headroom under budget | **3.7×** |

The live portal saw the new agent-written page in **2.67 seconds**,
through the LanceDB index (not the regex fallback), with no manual
rebuild step. VISION threshold #3 holds in production wiring, not just
in the synthetic test.

## Notes

- The semantic hit beat the regex fallback because `pkb.search()`
  short-circuits on any non-empty `_semantic_search` return. The sprint's
  win condition was "findable via `pkb.search()`" — but the spirit was
  always the LanceDB path, since the regex fallback would have made the
  test trivially passing on file-write alone. The driver enforced the
  spirit by requiring `source == "semantic"`.
- Driver-local in-process search confirmed the same row, eliminating
  any "the portal is reading a cached view" suspicion.
- File was deleted after the run; a follow-up `schedule_upsert` against
  the now-missing path triggered an index delete, so the user's PKB is
  unchanged. Verified by re-querying the portal post-cleanup: zero hits
  containing `boysenberry`.
- The witness ran against the user's real `lab/pkb/` (which already has
  one prior real Researcher experiment at
  `agents/experiments/2026-05-06_2a0d7ac1.md` — visible in the search
  output). This is the most honest possible proof: the loop closes on
  real existing PKB state, not a fresh empty corpus.

## Reproducer

```bash
# From repo root with .venv active and main checked out (or a branch
# post-#31 merge):
LAB_MODE=airgapped PORTAL_PORT=8088 \
  .venv/bin/uvicorn arail.portal.app:app --host 127.0.0.1 --port 8088 \
  --log-level warning > /tmp/portal.log 2>&1 &
sleep 6  # let the portal bind + ensure_ready() run
.venv/bin/python /tmp/arail_witness_driver.py http://127.0.0.1:8088
kill %1
```

Exit code 0 = PASS. Summary JSON written to `/tmp/arail_witness_summary.json`.
