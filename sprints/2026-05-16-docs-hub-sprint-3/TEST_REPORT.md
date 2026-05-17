# TEST_REPORT — docs-hub-sprint-3

**Verdict:** PASS
**Date:** 2026-05-16
**QA agent:** a804aad6cf388723c

## Test counts

- New: `tests/test_docs_sprint3_qa.py` — **18/18 passing**
- Docs-domain suite (registry + registry_qa + routes + routes_qa + links + ingest + sprint3_qa): **158/158** when run together
- Full suite: 13 pre-existing failures (all reproducible on parent state via `git stash`), 0 regressions

## Allocation actually delivered

| Bucket | Tests | Share |
|---|---:|---:|
| Security / edge | 8 | 44% |
| Perf / concurrency | 4 | 22% |
| Regression | 4 | 22% |
| Happy | 2 | 12% |

## Coverage map

| Hunt item | Test |
|---|---|
| LanceDB re-ingest duplicates | `test_index_all_idempotent_no_duplicates_on_double_call` |
| Stale entries after delete | `test_index_all_stale_doc_removed_on_reingest` (existing) |
| Body > 4 KB embedding cap | `test_index_all_handles_doc_larger_than_4kb` |
| Empty `docs/` dir | `test_index_all_empty_docs_dir_does_not_crash` |
| Doc without frontmatter | `test_index_all_doc_without_frontmatter_does_not_crash` |
| Path namespacing | `test_index_all_docs_and_root_namespacing` |
| Anchor-only links | `test_cross_link_regex_handles_anchor_only_link` + audit |
| Query-string links | `test_cross_link_regex_handles_query_string_link` |
| Mixed-case `.MD` | `test_cross_link_regex_does_not_match_mixed_case_md_extension` (LOW pin) |
| Inline backticks | `test_cross_link_audit_skips_link_inside_inline_backticks` |
| INDEX.md → /docs 301 | `test_index_md_redirect_returns_301` |
| INDEX.md w/ query string | `test_index_md_redirect_with_query_string` |
| INDEX.md lowercase | `test_index_md_lowercase_variant_is_not_redirected` |
| Concurrent index_all | `test_index_all_concurrent_calls_do_not_corrupt_index` |
| sys.modules rebind hermeticity | `test_fresh_registry_rebind_is_hermetic_over_repeated_calls` |
| Empty `all_docs()` | `test_index_all_with_empty_registry` |
| Missing on-disk doc | `test_build_docs_rows_tolerates_unreadable_path` |
| Live corpus regression | `test_live_cross_link_audit_clean` |

## Findings

### No FAIL-class findings.

### LOW — `_MD_LINK_RE` mixed-case

`tests/test_docs_cross_links.py:30` only matches lowercase `.md`. A link to `foo.MD` would silently pass audit. Pin test added; recommend `re.IGNORECASE` follow-up.

### LOW — F5 cross-domain contamination remains

Sprint's claim that the rebind closes test-isolation flakes is true *within* the docs cluster, but full-suite ordering still surfaces `tests/test_docs_routes_qa.py` failures plus `test_hub_empty_registry_renders_fallback`. Reproducer:

```
pytest tests/                              # ❌ 6 docs_routes_qa fail
pytest tests/test_docs*.py                 # ✅ 158 pass
pytest tests/test_docs_routes.py tests/test_docs_routes_qa.py  # ✅ 74 pass
```

Not introduced by this sprint (`git stash` of sprint changes leaves the failures identical). Some upstream non-docs test mutates `arail.portal.app._docs_registry`. Recommended follow-up: session-scoped autouse fixture restoring `app._docs_registry` to its import-time value after every test.

## Pre-existing failures (not regressions)

13 full-suite failures total, all reproducible on parent state:
- 6 docs_routes_qa isolation flakes (documented above)
- 2 swarm_goal_surfaces
- 1 system_metrics
- 2 opencode lifecycle
- 2 airgap_happy

## Security review

- F9 path containment: delegated to registry (already tested)
- INDEX.md redirect: pure 301, no filesystem read — no traversal surface
- Cross-link audit: read-only over registry-derived paths
- LAB_MODE airgap default unaffected
- 3-way concurrent `index_all`: no deadlock, no corruption

## Performance

`test_index_all_perf_under_2s`: 0.70s on dev (budget 2.0s).
Concurrent-ingest test confirms LanceDB write-lock under contention.

## Conclusion

PASS. Sprint-3 ships and closes the Docs Hub effort.
