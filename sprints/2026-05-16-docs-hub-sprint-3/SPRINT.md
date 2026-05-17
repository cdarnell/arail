# Sprint: 2026-05-16-docs-hub-sprint-3

**Branch:** qukaizen/arail-docs-hub-sprint-3-bundle
**Master plan:** `~/.claude/plans/huge-miss-the-docs-elegant-gem.md` (Phase D + E + cleanup)
**Predecessors:**
- `sprints/2026-05-16-docs-hub-sprint-1/` (foundation: frontmatter + registry)
- `sprints/2026-05-16-docs-hub-sprint-2/` (Hub + viewer overhaul)

## Closure scope

This is the closure sprint of the Docs Hub effort. Visionary phase
skipped — the master plan covers the why; this sprint just lands the
remaining items.

### In scope

1. **LanceDB ingest of `docs/`** — extend `pkb.index_all` so the 24
   frontmatter-annotated docs are searchable in the KB alongside
   user notes. Reuse `pkb.py` ingest plumbing; do not duplicate.
2. **Cross-link audit** — every internal `[label](path.md)` in a doc
   must resolve to a real registered (or whitelisted) file. Enforced
   by a test that walks the corpus.
3. **Delete `docs/INDEX.md`** — denylisted since Sprint 1; `/docs`
   already lands on the Hub. Removal is mechanical.
4. **Fix test-infra hazard** at `tests/test_docs_registry_qa.py:41`
   — the `del sys.modules[...]` pattern leaves `arail.portal.app`
   bound to the stale module; rebind explicitly via
   `monkeypatch.setattr(arail.portal.app, '_docs_registry', mod)`.

### Out of scope

- Buddy CTA wiring beyond the URL-encoded stub already shipped.
- Doc deletions other than `INDEX.md`.
- Model swaps for the LanceDB embedding (still the hash-embedding
  stub from `arail.vector_index`).
- TOC token-walking renderer (architect carry-over INFO, defensive
  only).

## Phases

- [x] design (architect) — produced `ARCHITECTURE.md`
- [x] build (builder) — 6 atomic commits, 140 docs tests, 3 broken links fixed
- [x] review (architect) — **PASS**
- [x] qa — **PASS** (18 new tests, 158/158 docs-domain green, 0 FAIL)
- [x] ship — bundled with sticky-TOC ride-along + sprint-1/2 carry-overs in PR
