# TEST_REPORT — docs-hub-sprint-2

**Verdict:** WEAK_PASS (no FAIL findings; product correctness clean in isolation)
**Date:** 2026-05-16
**QA agent:** ac982f08e1e75e172

## Why WEAK_PASS not PASS

47 new QA tests at `tests/test_docs_routes_qa.py` all pass in isolation
and when run alongside their natural neighbours (`test_docs_routes.py`,
`test_docs_registry.py`). Five of them flake when run in the same
session as `tests/test_docs_registry_qa.py` due to a **pre-existing
test-infra issue** (Sprint 1 `del sys.modules` pattern) that REVIEW.md
already accepted as a Sprint 3 carry-over. Product behaviour is
correct; the noise is in the test scaffolding.

## Test counts

- New: `tests/test_docs_routes_qa.py` — **47/47 passing (in isolation)**
- Combined sprint surface: registry (31) + registry_qa (22) + routes (25) + routes_qa (47) = **125/125 in isolation**
- Cross-suite flake count: 5 tests + 1 pre-existing (`test_hub_empty_registry_renders_fallback`)
- Full suite: 1432 passed, 6 pre-existing unrelated failures + 5 isolation flakes + 1 pre-existing isolation flake = 13 reported failures, all documented non-blockers

## Allocation actually delivered

| Bucket | Tests | Share |
|---|---:|---:|
| Security / edge | 30 | 64% |
| Regression | 9 | 19% |
| Happy | 8 | 17% |

Slightly over-weighted security (target 50%) because templates consume user-controlled frontmatter.

## Coverage highlights

- **XSS (7 payloads × 3 fields):** `<script>`, `<svg/onload=>`, `<img onerror=>`, attribute-breakout `"`, `'`, backtick, `{{7*7}}` SSTI canary — all escaped, SSTI not evaluated.
- **Path traversal:** `../../`, URL-encoded `..%2f`, double-encoded `..%252f`, leading `/`, Windows `..\\` — all blocked by the preserved F4 guard.
- **Tier title-leak:** tier-blocked viewer passes `doc=None`; only the URL slug surfaces, never the title.
- **Markdown HTML injection:** markdown-it `html: False` confirmed.
- **Buddy URL encoding (F9):** `quote_plus` on prompt + slug; 5KB payload, newlines, `&?#<script>` all encoded correctly.
- **Concurrency:** 8 threads × 32 registry reads agree; 8 concurrent `/docs` requests all 200.
- **Unicode/special headings:** `## !@#$` falls back to `"heading"` slug with deterministic uniqueness counter.
- **TOC:** unicode, emoji, code-fence skipping, deep nesting (H4/H5), 5× duplicate dedup.
- **Featured strip filter** (architect's §6.1 test #6 — missed in build, added here): featured docs that fail tier filter are omitted.
- **Buddy voice:** all `buddy_prompt` values reviewed — warm lab-partner voice, no "Pip" leakage.

## Findings

### No FAIL-class findings.

### INFO — pre-existing test-infra hazard (Sprint 3 carry-over)

`tests/test_docs_registry_qa.py:41` calls `del sys.modules['arail.portal.docs_registry']` inside `_fresh_registry`. The reloaded module replaces the entry in `sys.modules`, but `arail.portal.app:50` already holds a binding to the *original* module object (imported as `_docs_registry`). Subsequent `monkeypatch.setattr(docs_registry, ...)` patches no-op against the running app handler.

**Suggested Sprint 3 fix:** rebind `arail.portal.app._docs_registry` explicitly (via `monkeypatch.setattr`), or use `importlib.reload` and re-bind.

## Carry-overs for Sprint 3

1. Fix the `del sys.modules` pattern in `tests/test_docs_registry_qa.py` (above).
2. Convert TOC injection from sequential `body_html.replace(..., 1)` to a proper token-walking renderer if exotic markdown lands (architect-flagged, currently defensive).
3. LanceDB ingest of `docs/`, full cross-link audit, deletion of `docs/INDEX.md` (out-of-scope items from master plan).

## Conclusion

WEAK_PASS. Product behaviour clean. Ships with REVIEW.md PASS + this WEAK_PASS (acceptable per `/sprint` gate rules).
