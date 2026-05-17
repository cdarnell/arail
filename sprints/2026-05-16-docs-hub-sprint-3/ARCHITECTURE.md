# Architecture: docs-hub-sprint-3 (closure)

**Date:** 2026-05-16
**Spec:** `~/.claude/plans/huge-miss-the-docs-elegant-gem.md` Phase D + E + cleanup
**Predecessors:** Sprint 1 REVIEW (PASS), Sprint 2 REVIEW (PASS) / TEST_REPORT (WEAK_PASS)

## Restatement

The Docs Hub effort has shipped its visible surfaces. What remains is
plumbing: make the 24 curated docs searchable through the same
LanceDB index the PKB already uses (so unified KB+docs search becomes
real, not just promised), prove every internal cross-doc link
resolves (so a learner clicking a link in any doc never falls off the
rails), delete the legacy `docs/INDEX.md` placeholder (the registry
replaced it three weeks ago), and fix one carry-over test-infra
hazard that flakes when QA tests run alongside Sprint 1 tests. None
of these change the user-visible UI; all are correctness work that
makes the Hub solid before we stop touching it.

## Assumptions

1. `arail.pkb.index_all` is the single LanceDB ingest entry point;
   no other call site rebuilds the index.
2. The hash-embedding from `arail.vector_index.hash_embedding` is
   acceptable for docs (it's already used for PKB; doc embedding
   quality is not a Sprint 3 goal).
3. `docs/` lives at `<repo_root>/docs/` — same root the registry
   already walks; we will derive it from the same helper to avoid
   two-source drift.
4. The 24 docs are stable enough that adding them to the index
   roughly doubles row count from the current PKB corpus (small
   enough to ignore latency-wise; verified in F1 perf test).
5. `python-frontmatter` is already a runtime dep (Sprint 1).
6. Markdown link regex `[label](target.md[#anchor])` is the only
   internal-link shape we audit — wikilinks and HTML anchors are
   out of scope; the cross-link audit only fails on broken markdown
   links to `.md` files.
7. `monkeypatch.setattr(arail.portal.app, "_docs_registry", mod)` is
   sufficient to rebind — `app.py:50` does
   `from . import docs_registry as _docs_registry`, so the attribute
   lives on the `app` module namespace.
8. Removing `INDEX.md` is safe: the only references in code are the
   denylist entry (kept — defensive) and the legacy redirect tested
   in Sprint 2 (still 301s — points at `/docs`, not at the file).

## Data flow

```
                                       ┌────────────────────────────┐
                                       │ docs_registry.all_docs()   │
                                       │  (already cached, mtime-keyed)
                                       └──────────┬─────────────────┘
                                                  │  Doc.path, Doc.slug,
                                                  │  Doc.title, Doc.tags
                                                  ▼
  ┌──────────────┐    ┌──────────────────────────────────────────┐
  │ pkb._iter_   │    │ pkb.index_all(pkb_root, *, include_docs) │
  │ pkb_files()  │───▶│  rows = pkb_rows + docs_rows             │
  │ (unchanged)  │    │  source_kind="user"|"docs"               │
  └──────────────┘    └──────────────────────┬───────────────────┘
                                              │
                                              ▼
                                  ┌──────────────────────────┐
                                  │ VectorIndex.replace(rows)│
                                  │ lab/pkb/.cache/lancedb   │
                                  └──────────────────────────┘
```

For docs rows:
- `path` = `f"docs/{slug}.md"` (or `root/{slug}.md` for root-allowlist
  entries — namespaced so a future `pkb/docs/foo.md` cannot collide).
- `name` = `Doc.title` (so semantic vector input mixes title +
  filename + body snippet, same as PKB).
- `vector` = `hash_embedding(f"{title} {slug} {body[:4096]}")`.
- `mtime` = `Doc.mtime`.
- `source_kind` = `"docs"` (new value; `_source_kind_for_rel` left
  intact for PKB paths).

The Sprint 3 ingest is **additive** — no PKB schema field is
removed or renamed; consumers reading the existing 5-field schema
keep working.

### Cross-link audit data flow

```
docs_registry.all_docs()  ─┐
                            ├─▶ for each doc:
docs/*.md raw text        ─┘     parse markdown links
                                  │
                                  ▼
                            for each `[label](target.md[#anchor])`:
                              resolve target → absolute path
                              assert exists OR target in allowlist
```

Allowlist (links that resolve outside the registry but are still
legitimate): root-relative references to README.md, AGENTS.md,
CLAUDE.md, scripts/setup.sh, lab/pkb/agents/<id>/AGENT.md, plus
anchor-only links (`#section`) and external URLs (`http(s)://`).

## Interface contracts

### `pkb.index_all(pkb_root=None, *, include_docs=True)`

- **Promises:** rebuilds the LanceDB index with PKB rows + (if
  `include_docs`) one row per registered doc; returns
  `{"ok", "indexed", "indexed_docs", "path"}`.
- **Requires:** `arail.vector_index.available()`; otherwise returns
  `{"ok": False, "indexed": 0, "indexed_docs": 0, "path": None}`.
- **Bad input:** if `docs_registry.all_docs()` raises or returns (),
  log a warning and proceed with PKB-only rows. Docs ingest must
  never block PKB ingest.
- **Backward compat:** `include_docs=True` default. Callers that
  pre-date this change continue to work; the return dict gains one
  key. `index_all()` with no args is unchanged from caller's POV.

### `docs_registry.all_docs()`

Unchanged. Sprint 3 adds no new accessor.

### Test helper: `_fresh_registry(monkeypatch, docs_dir, root_dir)`

- **Promises:** returns a docs_registry module bound to the temp
  roots, AND ensures any reference held by `arail.portal.app` is
  rebound to the same module object.
- **Requires:** `monkeypatch` fixture; caller will not also call
  `del sys.modules[...]` outside the helper.
- **Bad input:** if `arail.portal.app` is not imported yet, the
  rebind is skipped silently (the test isn't exercising the app).

## Failure modes

| # | Failure | Detection | Recovery |
|---|---------|-----------|----------|
| F1 | Re-ingest perf regression (docs ingest doubles index_all wall time) | Perf test: `index_all` with 24 docs + 50 fake PKB rows completes <2.0s | Cap embedding body slice at 4 KB (same as PKB); docs are small so this is generous |
| F2 | Stale doc entry: doc deleted on disk but row persists in LanceDB | `index_all` uses `VectorIndex.replace(rows)` — full-replace semantics already; test asserts deleting a doc and re-ingesting removes its row | Replace-not-append is the recovery; documented in the test |
| F3 | Cross-link audit false positive (link points at a file that exists but is not in the registry — e.g., `scripts/setup.sh`) | Audit consults an explicit allowlist of repo-root assets before failing | Whitelist resolves the false positive without weakening the assertion |
| F4 | Cross-link audit false negative (a broken link is in a fenced code block) | Audit strips fenced code blocks (` ``` ` and `~~~`) before regex sweep — reuse `wiki._strip_code_blocks` if exposed, else inline the same logic | Test exercises a doc with a fake broken link inside a code fence and asserts it does NOT fail |
| F5 | `sys.modules` fix breaks other tests that rely on the old behaviour | Run full `tests/test_docs_registry_qa.py` + `tests/test_docs_routes_qa.py` + `tests/test_docs_routes.py` together; assert no new failures | If a test depends on the broken rebind, fix it in the same commit (scope creep that's worth it — the carry-over flagged 5 such flakes) |
| F6 | Deleting `INDEX.md` breaks the legacy `/docs/INDEX.md` redirect | Sprint 2 viewer redirect on the slug now sees a 404 path; the redirect handler must accept the path even when the file is gone (it never reads the file — it issues a 301 to `/docs`) | Verify with a test: `GET /docs/INDEX.md` → 301 to `/docs` even after the file is deleted |
| F7 | LanceDB ingest crashes when a doc has empty body | `_parse_doc` already tolerates empty body; ingest's `text[:4096]` slice handles `""` cleanly | Confirmed by an empty-body fixture test |
| F8 | Docs ingest pollutes PKB-scoped search results (caller doesn't filter on `source_kind`) | `search()` callers downstream are unchanged; this sprint does NOT auto-expand existing search to return docs. Out-of-scope per master plan (Phase D step 12 is reserved for the next sprint that touches `/api/pkb/search`) | If a downstream test asserts "PKB-only", add `source_kind != 'docs'` filter at the call site. Document this boundary clearly in the build log |
| F9 | Symlink in `docs/` resolves outside docs root and gets indexed | Reuse the registry's containment check — we iterate `docs_registry.all_docs()`, which already enforces `resolved.relative_to(root)` | Free (delegated to registry) |
| F10 | Cross-link audit walks pages quadratically (24 × 24 × N links) | Pre-build a set of valid slugs once; per-doc audit is O(links per doc) | Trivially linear; no test needed beyond the smoke perf bound (full audit <1s) |

## Test strategy

### Unit
- `test_index_all_includes_docs_rows` — when `include_docs=True` (default), the returned `indexed_docs` is ≥1 and each docs row has `source_kind="docs"`.
- `test_index_all_include_docs_false_skips_docs` — opt-out works.
- `test_index_all_handles_registry_failure_gracefully` — monkeypatch `docs_registry.all_docs` to raise; index_all still returns `ok=True` for PKB rows.
- `test_index_all_empty_body_doc_does_not_crash` (F7).

### Integration / regression
- `test_cross_link_audit_all_internal_links_resolve` — the live `docs/*.md` corpus has no broken internal `.md` link (F3, F4).
- `test_cross_link_audit_allowlist_is_minimal` — whitelist constants are pinned (no surprise growth between sprints).
- `test_docs_index_md_redirect_still_works` — `GET /docs/INDEX.md` → 301 to `/docs` after the file is deleted (F6).
- `test_index_md_file_does_not_exist` — the literal `docs/INDEX.md` is gone from the working tree.

### Test-infra fix (the sys.modules carry-over)
- `test_fresh_registry_rebinds_app_module_reference` — after `_fresh_registry`, `arail.portal.app._docs_registry is mod`.
- Re-run the 5 flaky tests identified in TEST_REPORT.md alongside `test_docs_registry_qa.py` and assert clean (F5).

### Performance
- `test_index_all_perf_under_2s` (F1) — synthetic 50-PKB + real-24-docs ingest <2.0s wall.

### Security
- No new attack surface; the registry's containment check covers F9. The cross-link audit is read-only and walks paths derived from `docs_registry` (no user-supplied input).

## Tech debt

**Added:**
- One new kwarg on `index_all` (`include_docs`) — minor surface expansion. Documented; default preserves prior behaviour.
- A small cross-link allowlist (probably 4–6 entries: README.md, AGENTS.md, CLAUDE.md, scripts/setup.sh, plus anchor-only). Will need touching if docs reference new repo-root assets.

**Repaid:**
- Sprint 2 carry-over #1: sys.modules pattern in `tests/test_docs_registry_qa.py` (line 41) — closed.
- Sprint 2 carry-over #3: LanceDB ingest of docs/ — closed.
- Sprint 2 carry-over #3: cross-link audit — closed.
- Sprint 2 carry-over #3: delete `docs/INDEX.md` — closed.
- TEST_REPORT.md WEAK_PASS isolation flake — closed.

**Net:** strongly negative. Sprint 3 is closure.

## Scope ceiling

Hard caps the architect commits to. Builder must stop and report
back if any cap is exceeded.

| Surface | Cap |
|---------|-----|
| Files modified | ≤ 8 |
| Files added | ≤ 2 (one test file at most: `tests/test_docs_ingest.py` and/or `tests/test_docs_cross_links.py` — combinable) |
| Files deleted | exactly 1 (`docs/INDEX.md`) |
| LOC added (excluding tests) | ≤ 120 |
| LOC added (tests) | ≤ 300 |
| New runtime deps | 0 |
| New environment variables | 0 |
| Migrations | 0 (LanceDB index rebuild is automatic on next call) |

Files expected to change:
1. `src/arail/pkb.py` — `index_all` accepts `include_docs`, builds docs rows.
2. `tests/test_docs_registry_qa.py` — fix `_fresh_registry` helper.
3. `tests/test_docs_ingest.py` (NEW) — F1, F2, F7, F8 coverage.
4. `tests/test_docs_cross_links.py` (NEW) — F3, F4, audit allowlist.
5. `docs/INDEX.md` — deleted.
6. Possibly `tests/test_docs_routes.py` — small addition for F6.
7. Possibly 1–2 docs/*.md if the cross-link audit surfaces a real broken link (in which case: fix the link, don't widen the allowlist).
8. `pyproject.toml` — only if a missing dep surfaces (expected: no change).

## Recommended implementation order

1. **Fix the test-infra hazard first.** Rewrite `_fresh_registry`
   in `tests/test_docs_registry_qa.py` to use
   `monkeypatch.setattr(arail.portal.app, "_docs_registry", mod)`
   instead of `del sys.modules`. Confirm the 5 TEST_REPORT.md
   flakes go quiet. **One commit.**
2. **Cross-link audit** as a pure test, no production code. Write
   `tests/test_docs_cross_links.py` with the allowlist baked in.
   Fix any broken links it surfaces by **editing the doc**, not by
   widening the allowlist. **One commit (plus fixup commits for
   any broken doc links it catches).**
3. **Delete `docs/INDEX.md`** and add the redirect-still-works
   regression test. **One commit.**
4. **LanceDB ingest of docs** — extend `pkb.index_all` with
   `include_docs=True` kwarg, build the docs row list from
   `docs_registry.all_docs()`, wire through `replace()`. Add
   `tests/test_docs_ingest.py`. **One commit.**
5. **Stop.** Run full suite. Builder writes BUILD_LOG.md.

Each step is independently revert-able. If step 4 reveals a deeper
LanceDB issue, steps 1–3 still ship value.

## Open questions for the builder

None blocking. If the cross-link audit catches more than ~3 broken
links, pause and report — that suggests a doc-quality issue beyond
this sprint's closure scope.
