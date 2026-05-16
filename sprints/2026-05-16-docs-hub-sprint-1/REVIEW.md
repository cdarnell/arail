# Review: Docs Hub Sprint 1 (Phase F + Phase A)

**Date:** 2026-05-16
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 714c5fd (sprint commits a011185, 8c5b625, 0229f79, 714c5fd)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5fb1929
**Mode:** review (post-merge — PR #56 already merged to main)

---

## Verdict: PASS

No BLOCK findings. The implementation matches the architecture contract closely;
all failure modes from §7 have corresponding tests; the tier-leak and
path-traversal attack surfaces are structurally closed; the regression sentinels
are in place. One INFO-level follow-up (docs/design.md rename) is documented
below as a Sprint 2 carry-over, not a merge blocker.

---

## Spec adherence

| Contract element | Status | Notes |
|---|---|---|
| `'docs'` added to `_TIER_SURFACES["min"]` (app.py:99) | DONE | Verified — `{"dashboard","chat","research","knowledge","agents","docs"}`. |
| Docs nav link between Knowledge and Agents in `_nav.html` | DONE | Lines 39-42; gated on `'docs' in _ts`; `active == 'docs'` highlight; tooltip matches spec. |
| Stale nav comment updated | DONE | `_nav.html` lines 11-14 now reflect the real min surface set. |
| `pyproject.toml` mirror update for min surfaces | DONE | Confirmed in commit a011185. |
| `docs_registry.py` per §5.1 / §5.2 contract | DONE | Frozen `Doc` dataclass with all 13 fields; five accessors with documented signatures; categories closed enum; coercion philosophy honored. |
| `python-frontmatter>=1.1.0` in base deps | DONE | commit 0229f79. |
| 24-doc frontmatter rollout | DONE (23 in catalog) | One doc (`docs/design.md`) excluded via denylist due to slug collision with root `design.md` — handled defensively, see Tech Debt Delta. |
| Sprint 1 registry unconsumed in production | HONORED | `app.py` does not import `docs_registry`. No template reads it. Tests are the only callers. |
| `_render_markdown_page` untouched | HONORED | No diff on that function. |
| Knowledge tab cross-link banner (mid-sprint scope add) | DONE | `knowledge.html` lines 89-103; gated on `'docs' in tier_surfaces`; styled in `knowledge.css`. |

Scope discipline was strong — no Hub template, no viewer rewrite, no LanceDB
ingest, no `docs_hub.html`. Builder resisted the pull toward Sprint 2 work.

---

## Code quality findings

- [INFO] `docs_registry.py` is ~310 LOC vs the architecture's ~120 LOC estimate.
  The growth is justified — the explicit defensive parsing (per-field type
  coercion, symlink resolution, double-checked locking) accounts for the
  delta. No function exceeds ~50 lines. Cyclomatic complexity stays low.
- [INFO] `_parse_doc()` is ~100 lines (lines 214-314) — long but linear. Each
  field is parsed in an isolated block. Refactoring into per-field helpers is
  possible but would not improve readability. Acceptable.
- [INFO] `siblings()` and `related()` both call `all_docs()` and iterate.
  O(n) per call. At n=23 this is fine; revisit if Sprint 2 calls these on a
  hot path.
- [INFO] `_BUILD_CALLS` module global is exposed for tests but not actually
  used by the shipped test suite (the concurrency test installs its own
  counter). Harmless; consider removing in Sprint 2.

---

## Security findings

The paranoid pass — what was specifically checked:

- [INFO] **Path traversal via `related:` (F9):** structurally impossible.
  `related()` only looks up slugs through the `other` dict built from
  `all_docs()`. It never opens a file path derived from frontmatter.
  `test_related_drops_path_traversal_slug` asserts this with three traversal
  variants (`../../etc/passwd`, `/etc/passwd`, `..\\windows\\system32`).
- [INFO] **Symlink escape (F10):** `_register()` calls `path.resolve()` and
  then `resolved.relative_to(root.resolve())` — escapes raise `ValueError`
  and are skipped with a WARNING. `test_symlink_to_outside_root_is_skipped`
  exercises this end-to-end with a real symlink. The check is correctly
  placed *after* symlink resolution, not before.
- [INFO] **Malformed YAML (F1):** `_parse_doc()` catches a bare `Exception`
  inside the `frontmatter.loads` block — broader than the spec's
  `yaml.YAMLError` but safer (covers `frontmatter`-internal exceptions too).
  Doc still registers with defaults.
- [INFO] **Denylist enforcement:** `_DOCS_DENYLIST` and `_ROOT_ALLOWLIST` are
  `frozenset`s — cannot be mutated at runtime. CLAUDE.md / AGENTS.md /
  README.md correctly excluded from the user-facing catalog (no leak of
  Claude-onboarding or porting-manifest content into the lab UI).
- [INFO] **Tier-leak (the explicit review concern):** verified — the
  registry walks both `docs/` and the curated repo-root allowlist *with no
  tier awareness*. The same set of 23 docs is returned regardless of
  `LAB_TIER`. **This is correct for Sprint 1** because the registry is
  unconsumed; no template or route renders it; the only tier-gated surface
  is the nav link itself, which is correctly gated. There is no tier-leak
  attack surface in shipped code. **Sprint 2 must add tier-awareness when
  the registry becomes a render source** — flagged in carry-over below.
- [INFO] **Secret leak via doc content:** `docs/` is checked-in content,
  not user-uploaded. No new untrusted-input surface introduced. The
  `lab/data/secrets.env` invariant is untouched.
- [INFO] **No new HTTP routes, no new auth surface, no new dependency
  beyond `python-frontmatter`** (pure Python, 50KB, actively maintained,
  no known CVEs as of cutoff).

---

## Test coverage assessment

- `tests/test_docs_registry.py`: 31 tests, covers F1–F17. Behavior-focused
  (asserts on `Doc` fields and accessor outputs, not internal state).
- `tests/test_docs_routes.py`: 5 tests, covers F18 (`docs` in min surfaces),
  F19 (nav link renders in min HTML), max-tier render, and the Knowledge→Docs
  cross-link banner.
- Combined: **36/36 pass locally** (verified during this review).
- Failure-mode-to-test mapping: every row F1–F19 in ARCHITECTURE.md §7 maps
  to at least one test. F20 (WIP-branch hygiene) is process, not testable.
- Changed-line coverage on `docs_registry.py` is effectively complete (all
  five accessors, all coercion branches, all error paths exercised).
- **Gap (INFO):** no test asserts that no `app.py` import statement imports
  `docs_registry`. The Sprint 1 promise of "unconsumed" is enforced by code
  review, not by test. A future grep-test could harden this, but it would
  fail by design in Sprint 2.

---

## Performance assessment

Not on a hot path in Sprint 1 (no caller). `test_large_doc_parses_under_threshold`
asserts <100ms for a 40KB doc; the full 23-doc build measured in 2.29s test
suite time (including all 36 tests) is well within budget. No regression risk.

---

## Tech debt delta

Versus ARCHITECTURE.md §9 prediction:

- **Predicted debt added:** dual tier-surface declarations, two frontmatter
  parsers, INDEX.md redirect still present, unconsumed registry, per-worker
  cache, no author-side schema validator. **All present as predicted.**
- **New, unpredicted debt:**
  1. **`docs/design.md` is denylisted** to resolve the slug collision with
     root `design.md`. The denylist entry is correct as a defensive measure
     but means a real user-facing doc is invisible to the eventual Hub.
     **Owner: Sprint 2** — rename `docs/design.md` → `docs/portal-design.md`
     (content change requires user/author judgment), then remove the
     denylist entry. Documented in BUILD_LOG open question #1.
  2. **MD025 linter warnings** on docs with both `title:` frontmatter and a
     `# H1` body. Cosmetic; the registry prefers frontmatter title and
     correctly falls back to H1. Owner: doc-style follow-up.
- **Pre-existing failing test** `tests/portal/test_opencode_config_lifecycle.py::TestStartEnvVars::test_start_sets_OPENCODE_CONFIG_DIR_env`
  fails on `main` independent of this sprint — confirmed not caused here.
  Out of scope but worth a separate ticket.

**Net debt: slightly positive, as predicted, with one new item (design.md
rename) that is bounded and has a clear owner in Sprint 2.**

---

## Required actions before merge

None — the PR is already merged. Carry-over items for Sprint 2:

1. **Rename `docs/design.md` → `docs/portal-design.md`** (or merge it into
   the root `design.md`), then remove `"design.md"` from `_DOCS_DENYLIST`
   in `docs_registry.py:72`. Tracked from BUILD_LOG open question #1.
2. **Add tier-awareness to the registry** when it becomes a render source.
   Today every doc is returned regardless of tier; once the Hub renders
   from the registry, `max`-only docs (if any are added) must be filtered
   when `LAB_TIER=min`. Sprint 2 should add an `audience` or
   `min_tier` field check at the render boundary, not in the registry
   itself (keeping the registry tier-agnostic is a deliberate design
   choice — the *consumer* enforces visibility).
3. **Optional CI grep-test** that asserts `docs_registry` is not yet
   imported by `app.py` — useful only until Sprint 2 wires it in, so
   probably skip.
4. **Pre-existing OPENCODE_CONFIG test failure** — separate sprint.

---

## Closing note

The architect's design contract was followed with discipline. The builder
made one judgment call (the `design.md` collision workaround) and surfaced
it clearly in BUILD_LOG for review — that is exactly the right escalation
pattern. The Phase F regression fix plus the Knowledge cross-link banner
together resolve the immediate UX miss; the Phase A foundation is locked
and tested before any UI depends on it, which was the strategic point of
the sprint split. Sprint 2 can build on a stable base.
