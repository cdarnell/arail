# Build log: Docs Hub Sprint 1 (Phase F + Phase A)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5fb1929
**Started:** 2026-05-16

---

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `app.py`, `pyproject.toml`, `_nav.html`, `knowledge.html`, `knowledge.css` | Phase F: promote docs to min tier, restore nav link, update stale comment, add Knowledge→Docs banner + CSS | `tests/test_docs_routes.py` (5 tests: F18/F19 sentinels + knowledge cross-link) | a011185 |
| 2 | `src/arail/portal/docs_registry.py`, `tests/test_docs_registry.py` | Phase A: frontmatter-driven registry (31 tests) | `tests/test_docs_registry.py` | 8c5b625 |
| 3 | `pyproject.toml` | Add `python-frontmatter>=1.1.0` to base deps | — | 0229f79 |
| 4 | 19 `docs/*.md` + 5 root `.md` + `docs_registry.py` | Add YAML frontmatter to 24 user-facing docs; fix docs/design.md slug collision | verified by `all_docs()` count = 23 | 714c5fd |

---

## Execution

### Step 1 — Phase F (commit a011185)

Modified:
- `src/arail/portal/app.py` line 98: added `"docs"` to `_TIER_SURFACES["min"]`
- `pyproject.toml` line 98: mirrored change in `[tool.arail.tiers].min.surfaces`
- `src/arail/portal/templates/_nav.html`: inserted `{% if 'docs' in _ts %}` block between Knowledge and Agents; updated stale header comment from "Default tier (min) shows only dashboard + chat + research" to the accurate list
- `src/arail/portal/templates/knowledge.html`: added `📖 Official Docs` banner (tier-gated on `'docs' in tier_surfaces`), placed between folder-row and "Add content" disclosure section
- `src/arail/portal/static/knowledge.css`: added `.kb-docs-banner*` CSS (45 lines, consistent with existing folder button style)

Created:
- `tests/test_docs_routes.py` (5 tests: F18 canary, max-tier sanity, F19 nav link renders in min HTML, max HTML, knowledge cross-link)

All 5 tests pass.

### Step 2 — Phase A: docs_registry (commit 8c5b625)

Created `src/arail/portal/docs_registry.py` (~310 lines):
- Frozen `Doc` dataclass with all 13 fields per §5.1
- `CATEGORIES` tuple + `_CATEGORY_ORDER` dict
- `_DOCS_DENYLIST` (6 entries) and `_ROOT_ALLOWLIST` (5 entries)
- `_build()`: walks docs/ and root, skips denylist, resolves symlinks and validates against curated root via `is_relative_to()`, raises `RuntimeError` on slug collision
- `_load()`: double-checked locking with `threading.Lock`; cache keyed by per-file mtime tuples
- Five public accessors: `all_docs`, `by_category`, `get`, `siblings`, `related`
- Graceful `ImportError` degradation if `python-frontmatter` absent

Created `tests/test_docs_registry.py` (31 tests covering F1–F17).

All 31 tests pass.

### Step 3 — build dep (commit 0229f79)

Added `"python-frontmatter>=1.1.0"` to `[project].dependencies` in `pyproject.toml`.

### Step 4 — frontmatter content (commit 714c5fd)

Added YAML frontmatter to 24 files:

**`docs/` (19 files):**
agents-explained.md, agents.md, api-conventions.md, BUDDY.md, build-and-finetune-plan.md,
CERTIFIED_MODELS.md, design.md, INSTALL.md, LINUX.md, MACOS.md, missions.md, PRIVACY.md,
PUBLISH.md, REPOSITORY_LAYOUT.md, TROUBLESHOOTING.md, tunables.md, tuning-loop.md,
vibe-integrate.md, WSL.md

**Root (5 files):**
BLUEPRINTS.md, CONTRIBUTING.md, design.md, ROADMAP.md, SECURITY.md

Also updated `docs_registry.py` to add `design.md` to `_DOCS_DENYLIST` to resolve the slug
collision between `docs/design.md` and root `design.md` (see Open Questions below).

---

## Open questions surfaced (judgment calls made without stopping)

1. **docs/design.md vs root design.md slug collision.** Both files exist with basename `design.md` → slug `design`. The registry raises `RuntimeError` on collision as per §5.4. Resolution: excluded `docs/design.md` from the registry by adding it to `_DOCS_DENYLIST`. Rationale: root `design.md` is the top-level design philosophy; `docs/design.md` is a portal-surface design spec. The root file is more canonical for the curated catalog. The `docs/design.md` file still has frontmatter added (it is a valid user doc), but it does not appear in `all_docs()` until the collision is resolved by a future rename. **This should be surfaced to the architect in the REVIEW phase**: the cleanest fix would be renaming one file (e.g. `docs/design.md` → `docs/portal-design.md`), which is a content change the builder should not make unilaterally.

2. **ROADMAP.md category.** Chose `Reference` per ARCHITECTURE.md §10.1 recommendation.

3. **description fields.** Populated for the five featured docs (agents-explained, BUDDY, api-conventions, INSTALL, design.md root) per §10.2 recommendation. All others left as `""`.

4. **buddy_prompt strings.** Populated for agents-explained, BUDDY, api-conventions only — the three specifically called out in §10.3. Buddy voice used throughout (warm, collaborative, lab-partner tone, not generic "AI assistant").

5. **MD025 linter warning.** Every file that has a `title:` frontmatter field AND a `# H1` body heading triggers an MD025 "Multiple top-level headings" warning from the markdown linter. This is a linter style preference, not a spec violation — the registry uses frontmatter title preferentially and falls back to H1. No action taken; the warning is cosmetic.

---

## Architect feedback required

**One item for review:**

The `docs/design.md` slug collision (see Open Questions #1 above) was resolved by excluding `docs/design.md` from the registry. The cleanest resolution is to rename `docs/design.md` to `docs/portal-design.md` so both design documents can coexist in the catalog. This is a content change that requires the architect's sign-off before the builder acts on it. The current workaround (denylist) is correct and non-breaking, but leaves a user-facing doc outside the catalog.

---

## Final state

| Metric | Value |
|---|---|
| Commits in sprint | 6 (skeleton + Phase F + registry + build dep + content + sprint artifacts) |
| Tests passing | 36/36 (`test_docs_registry.py`: 31, `test_docs_routes.py`: 5) |
| Pre-existing failing test | `tests/portal/test_opencode_config_lifecycle.py::TestStartEnvVars::test_start_sets_OPENCODE_CONFIG_DIR_env` — fails on `main` before this branch; not caused by this sprint |
| Registry doc count | 23 (≥ 20 required) |
| Files modified | 31 |
| Files created | 3 (`docs_registry.py`, `test_docs_registry.py`, `test_docs_routes.py`) |
| Scope drift | None — no `docs_hub.html`, no `_render_markdown_page` changes, no LanceDB integration |

### Verification outputs

```
$ python -c "from arail.portal.docs_registry import all_docs; print(len(all_docs()), 'docs')"
23 docs

$ python -m pytest tests/test_docs_registry.py tests/test_docs_routes.py -v
======================== 36 passed, 6 warnings in 2.29s ========================
```

### What was NOT done (deferred to Sprint 2/3)

- `docs_hub.html` landing template
- `doc_viewer.html` sidebar/TOC/prev-next rewrite
- "Ask Buddy about this" CTA (Sprint 2 — requires buddy_prompt consumer)
- LanceDB ingest of `docs/` (Sprint 3)
- Cross-link audit for orphan docs (Sprint 3)
- Deletion of `docs/INDEX.md` (Sprint 2)
- `_render_markdown_page` signature changes (Sprint 2)
- Registry-driven sitemap or JSON endpoint
- Any import of `docs_registry` from `app.py` (registry is unconsumed in production until Sprint 2)
- Resolving the `docs/design.md` rename (pending architect review)
