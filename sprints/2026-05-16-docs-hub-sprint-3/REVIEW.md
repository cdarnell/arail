# Review: docs-hub-sprint-3 (closure)

**Date:** 2026-05-16
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at d5ea019
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at c095760
**Branch:** qukaizen/arail-docs-hub-sprint-3-bundle
**Commits reviewed:** b44f76d, 33d325a, 90220ba, d41f812 (plus d5ea019 BUILD_LOG, 5df5725 unrelated dashboard TOC)

## Verdict: PASS

All four planned steps shipped. 109 docs tests green in full-suite run (no isolation flakes). Failure modes F1–F10 covered. One non-blocking observation about an off-scope commit on the branch; one INFO about a redundant allowlist entry.

## Spec adherence

- Step 1 (F5 / sys.modules rebind): `_fresh_registry` rewritten exactly per architecture (monkeypatch.setattr on `arail.portal.app._docs_registry`). Builder went further than the spec and also rewrote `test_live_repo_*` (3 tests) to use `importlib.reload()` rather than `del sys.modules` — this is **correct scope expansion**: the architecture explicitly authorises (F5 row) fixing dependent tests in the same commit. New sentinel test `test_fresh_registry_rebinds_app_module_reference` pins the contract.
- Step 2 (F3/F4 cross-link audit): allowlist is 8 entries (≤10 cap). Code-fence stripping uses inline regex (also covers inline backticks — slight scope expansion, harmless). Three real broken links surfaced and fixed by editing the docs, not widening the allowlist — exactly the spec's instruction. F10 perf bound included.
- Step 3 (INDEX.md deletion + redirect): file deleted, dedicated route handler at `app.py:1820` issues 301 to `/docs` without reading the file. F6 sentinel test plus file-gone belt-and-suspenders test. The Sprint 2 `test_viewer_renders_doc_without_registry_entry` had to flip from 200 → 301 (documented in BUILD_LOG); this is a legitimate intent change, not a regression.
- Step 4 (LanceDB docs ingest): `index_all(*, include_docs=True)` matches the spec exactly. `_build_docs_rows` caps body at 4 KB (F1), returns `[]` and logs a warning on registry failure (F8 isolation contract honoured). Return dict gains `indexed_docs` key; pre-existing zero-arg callers unaffected.

Spec drift: none material. The builder respected the scope ceiling everywhere except test LOC (see below).

## Code quality findings

- [INFO] `tests/test_docs_ingest.py` repeats `sys.path.insert(0, ...)` + `from arail.vector_index import available` + skip-guard block in 7 tests (~12 LOC × 7 = ~84 LOC of repetition). Pulling this into a module-level `pytestmark = pytest.mark.skipif(not _lance_available(), ...)` would have collapsed the file to ~200 LOC and cleared the cap. Not blocking; tests are correct as written.
- [INFO] `_REPO_ROOT_ALLOWLIST` in `tests/test_docs_cross_links.py` contains both `design.md` and `docs/portal-design.md`-via-resolve-or-not. Since Sprint 2 renamed `design.md` → `docs/portal-design.md`, the bare `design.md` entry is dead weight unless someone is linking to a repo-root `design.md` that does not exist. Recommend dropping it in a follow-up to keep the allowlist truly minimal.
- [INFO] `_build_docs_rows`'s `source_root` access assumes the `Doc` dataclass exposes that field. Confirmed it does (registry sets it from category); no risk, but a unit-level type hint at the call site would help future readers.
- [INFO] An unrelated commit `5df5725 feat(dashboard): sticky TOC strip` landed on this branch. It is not described in BUILD_LOG.md and is not part of the closure sprint scope. Recommend either calling it out in BUILD_LOG or splitting it to a separate branch before merge so the sprint diff stays focused. Non-blocking — the change is self-contained and benign.

## Security findings

- [INFO] Docs ingest reads `doc.path` from the registry, which already enforces containment via `resolved.relative_to(root)` (verified in `test_symlink_escape_via_root_allowlist_is_blocked`). F9 delegated to registry; no new attack surface.
- [INFO] Cross-link audit is read-only and walks only paths derived from the registry. No user input.
- [INFO] `/docs/INDEX.md` redirect handler does not read the filesystem — pure 301. No path-traversal risk.
- [INFO] LAB_MODE airgap default unaffected; no network I/O introduced.

## Test coverage assessment

109 tests pass across the five docs test modules:
- F1: `test_index_all_perf_under_2s` — asserts <2.0s; 0.70s on dev (BUILD_LOG).
- F2: `test_index_all_stale_doc_removed_on_reingest`.
- F3: `test_cross_link_audit_all_internal_links_resolve` + `test_cross_link_audit_allowlist_is_minimal`.
- F4: `test_cross_link_audit_code_fence_false_negative_is_blocked` + positive-case complement.
- F5: `test_fresh_registry_rebinds_app_module_reference` + green run of all four files together.
- F6: `test_docs_index_md_redirect_still_works` + `test_index_md_file_does_not_exist`.
- F7: `test_index_all_empty_body_doc_does_not_crash`.
- F8: `test_index_all_handles_registry_failure_gracefully` + `test_index_all_source_kind_docs_does_not_pollute_pkb_source_kind`.
- F9: free (registry containment, already tested).
- F10: `test_cross_link_audit_perf_under_one_second`.

Every architecture failure mode has a corresponding test. Coverage on changed lines of `pkb._build_docs_rows` and `index_all` is exercised by all 7 ingest tests; coverage on the new redirect route is exercised by 2 tests.

## Performance assessment

- `index_all` with 50 PKB + 24 docs: 0.70s wall (builder-reported); spec budget 2.0s; comfortable margin.
- Cross-link audit on live corpus: bounded by `<1.0s`; trivially linear in (#docs × links-per-doc).
- 4 KB body cap honoured per F1 spec; LanceDB write latency unchanged from PKB-only ingest.

## Tech debt delta

Architecture predicted **strongly negative** net debt (closure sprint). Realised net debt is **strongly negative** as predicted, minus the small INFO items:
- Repaid: sys.modules carry-over, LanceDB docs ingest, cross-link audit, INDEX.md deletion, isolation flake.
- Added (vs prediction): test LOC overage (~493 vs 300 cap) due to fixture boilerplate. Acceptable per BUILD_LOG rationale — collapsing would compromise test independence. The architect's 300-LOC estimate undercounted LanceDB setup/teardown per-test cost.
- Added (new, not predicted): off-scope dashboard TOC commit on the same branch. File against a follow-up note.

The test-LOC overage is documented in BUILD_LOG.md with a defensible reason. The cleaner path (a module-level skip + shared `_make_pkb_root` already present) would have fit the cap; recommend that pattern for the next ingest-test sprint.

## Required actions before merge

None blocking. Optional cleanups (file as follow-up tickets, do not gate merge):

1. Refactor `tests/test_docs_ingest.py` to use module-level `pytestmark` skip-guard, dropping ~80 LOC of repetition. Test count and coverage unchanged.
2. Drop the redundant `design.md` entry from `_REPO_ROOT_ALLOWLIST` in `tests/test_docs_cross_links.py` (verify with a re-run of `test_cross_link_audit_all_internal_links_resolve`).
3. Either annotate commit `5df5725` (dashboard TOC) in BUILD_LOG.md or rebase it onto a separate branch so the sprint diff stays scoped.

Ready to hand to /qa.
