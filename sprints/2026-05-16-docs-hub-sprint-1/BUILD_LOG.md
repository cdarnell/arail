# Build log: Docs Hub Sprint 1 (Phase F + Phase A)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5fb1929
**Started:** 2026-05-16

---

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/portal/app.py`, `pyproject.toml`, `_nav.html`, `knowledge.html` | Phase F: promote docs to min tier, restore nav link, update stale comment, add Knowledge→Docs banner | `tests/test_docs_routes.py` (F18, F19, F34 + knowledge banner regression) | — |
| 2 | `src/arail/portal/docs_registry.py` | Phase A: frontmatter-driven registry, 5 accessors, mtime cache, threading.Lock, CATEGORIES enum | `tests/test_docs_registry.py` (31 tests) | — |
| 3 | `docs/*.md` (19 files) + root `design.md`, `BLUEPRINTS.md`, `ROADMAP.md`, `SECURITY.md`, `CONTRIBUTING.md` | Add YAML frontmatter to 24 user-facing docs | verified by `all_docs()` count ≥ 20 | — |
| 4 | `pyproject.toml` | Add `python-frontmatter>=1.1.0` to base deps | `test_setup_extras.py` not modified — manual clean-venv check | — |

---

## Execution

### Step 1 — Phase F: nav link, tier promotion, Knowledge cross-link

_Pending_

### Step 2 — Phase A: docs_registry

_Pending_

### Step 3 — Phase A content: frontmatter to 24 docs

_Pending_

### Step 4 — build: python-frontmatter dep

_Pending_

---

## Architect feedback required

_None so far._

---

## Final state

_Pending._
