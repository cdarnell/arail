# Build log: docs-hub-sprint-3 (closure)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at c095760
**Started:** 2026-05-16

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `tests/test_docs_registry_qa.py` | Fix `_fresh_registry` — replace `del sys.modules[...]` with `monkeypatch.setattr(arail.portal.app, '_docs_registry', mod)` | F5: run all 4 test files together, assert no flakes | — |
| 2 | `tests/test_docs_cross_links.py` (NEW) | Cross-link audit: walk docs corpus, assert all internal `.md` links resolve; allowlist for repo-root assets; strip code fences | F3, F4: allowlist false-positive; code-fence false-negative | — |
| 3 | `docs/INDEX.md` (DELETE) + `tests/test_docs_routes.py` | Delete the legacy placeholder; add F6 redirect regression test | F6: GET /docs/INDEX.md → 301 even after file gone | — |
| 4 | `src/arail/pkb.py` + `tests/test_docs_ingest.py` (NEW) | Extend `index_all(include_docs=True)` — build docs rows from registry; returns `indexed_docs` key | F1 perf, F2 stale, F7 empty body, F8 source_kind boundary | — |

## Execution

### Step 1 — Test-infra fix: `_fresh_registry` rebind
_pending_

### Step 2 — Cross-link audit test
_pending_

### Step 3 — Delete docs/INDEX.md + redirect regression
_pending_

### Step 4 — LanceDB docs ingest
_pending_

## Architect feedback required

_none at this time_

## Final state

_pending_
