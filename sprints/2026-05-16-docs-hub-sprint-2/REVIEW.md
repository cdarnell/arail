# Review: docs-hub-sprint-2

**Date:** 2026-05-16
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at d8c6c6c
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 9e61dfe
**Branch:** qukaizen/arail-docs-hub-sprint-2-bundle
**Commits reviewed:** 48a6519, 54c7be3, e98e1a9, e826b82

## Verdict: PASS

## Spec adherence

The builder executed the architect's recommended implementation order
verbatim and shipped the four logically-separated commits called for
in BUILD_LOG.md's plan table. Every failure-mode row (F1–F18) maps to
shipped code or a shipped test. One acknowledged deviation: F7's perf
test uses `docs/agents.md` (~24KB) instead of `ROADMAP.md` because
ROADMAP.md is served by the registry hub, not the `/docs/{path:path}`
viewer route — this is a spec wording fix, not a coverage gap.
Architect §9 question (1) on `api-conventions.md` audience was left
unchanged; builder explicitly chose Architect's option (b) ("keep
architect, accept featured strip shows 2 of 3 on min") rather than
silently mutating frontmatter. Acceptable — F3 test passes either way
and the behaviour is documented in BUILD_LOG.md.

## Validation of the five required checks

1. **F3 tier-leak — filter on BOTH surfaces:** Confirmed.
   `app.py:1882` applies `_filter_by_tier(raw_cats, tier)` in the Hub
   handler. `app.py:2098-2113` applies an inline audience-allowed check
   in `serve_local_doc()` for the direct-URL path. Both use the same
   allowed sets (`{beginner, operator}` for `min`, plus `architect`
   for `max`). The blocked viewer path passes `doc: None` to the
   template — title cannot leak.
2. **F4 path-traversal guard preserved verbatim:** Confirmed.
   `app.py:2074-2084` preserves the original `endswith(".md") / ".." /
   startswith("/")` prefilter PLUS the `docs_root in target.parents`
   containment check after `resolve()`. Sprint 2 widened the handler
   downstream of the guard but did not weaken it. Test
   `test_viewer_path_traversal_rejected` is shipped (line 277).
3. **F11 slug-collision rename atomic:** Confirmed. `git show 48a6519`
   shows `docs/{design.md => portal-design.md}`,
   `docs_registry.py` denylist entry removal,
   `app.py` 301 redirect handler, and the
   `test_no_slug_collision_after_rename` test all landed in the same
   commit. No window exists where the registry could raise on collision.
4. **Jinja autoescape on doc.title / doc.description / doc.buddy_prompt:**
   Confirmed. In both templates `doc.title` and `doc.description` are
   rendered as `{{ ... }}` with no `|safe` filter — Jinja's default
   autoescape (FastAPI Jinja2Templates default `autoescape=True`) wraps
   them. `doc.buddy_prompt` is never inserted into the template
   directly; only the precomputed `buddy_prompt_url` is rendered, and
   the prompt value flows through `urllib.parse.quote_plus` before
   embedding. The only `|safe` usage is `doc_html | safe` on the
   markdown-rendered body, which is intentional and is rendered by a
   markdown-it instance configured with `html: False` (raw HTML
   tokens are escaped, see `app.py:1918`). `test_hub_card_title_is_escaped`
   (line 200) shipped as F8 sentinel.
5. **S1 denylist composition (commit e826b82):** Confirmed correct.
   `docs_registry.py:88` performs `_DOCS_DENYLIST = _DOCS_DENYLIST |
   _ROOT_DENYLIST` at module load, so any of `CLAUDE.md`, `AGENTS.md`,
   `README.md`, `CODE_OF_CONDUCT.md` dropped under `docs/` will be
   filtered. The Sprint 1 QA pin test `test_root_denylist_files_in_docs_
   dir_dont_leak` was flipped from "pin current leak" to "assert no leak"
   and passes. Composition is visible-at-source one-liner — easy to
   reason about, matches Sprint 1 QA finding S1 wording.

## Code quality findings

- [INFO] `_render_with_toc` performs sequential `body_html.replace(...,
  1)` calls to inject H2/H3 ids. This is correct because tokens and
  rendered tags emerge in the same document order, but a malformed
  doc where markdown-it re-orders blocks (e.g. inside a definition
  list) could mis-attribute an id. Defensive enough for current scale;
  worth a follow-up if docs grow exotic markdown.
- [INFO] `_recently_updated` imports `time` inside the function. Minor
  style nit; harmless.
- [INFO] F15 returns 200 (not 404) with `tier_blocked=True` — matches
  ARCHITECTURE §4.1/F15 (teaching moment, not error). No leak: title
  withheld by passing `doc=None`.

## Security findings

- [INFO] Path-traversal guard intact (F4). Both the lexical prefilter
  (`".." in path`) and the post-`resolve()` containment check
  (`docs_root in target.parents`) survive.
- [INFO] No new dependencies introduced (markdown-it-py, frontmatter
  already pinned from Sprint 1).
- [INFO] `buddy_prompt_url` is URL-encoded via `quote_plus` server-side;
  template uses it only as `href`. F9 closed.
- [INFO] Markdown rendering keeps `html: False` — raw HTML in user docs
  is escaped. XSS surface bounded to frontmatter fields, which are all
  rendered through Jinja autoescape.
- [INFO] No secrets logged, no `lab/data/secrets.env` touched, no
  authentication surface changed.

## Test coverage assessment

- 21 new tests in `tests/test_docs_routes.py` covering every numbered
  test in ARCHITECTURE §6.1 (1–21). 78/78 docs-related tests pass
  in isolation (`tests/test_docs_routes.py` + `tests/test_docs_registry.py`
  + `tests/test_docs_registry_qa.py`).
- One known cross-suite isolation issue noted in BUILD_LOG.md
  (`test_hub_empty_registry_renders_fallback` flakes only when full
  suite ordering corrupts module-level state). Pre-existing test infra
  problem, not a sprint-2 regression. Acceptable — file as follow-up
  in Sprint 3.
- Coverage on changed lines is well above 80% — every helper has at
  least one direct test, and the route handlers are end-to-end tested.

## Performance assessment

Not benchmarked under load in this review. `_render_with_toc`'s extra
markdown pass adds <30ms for the largest viewer-served doc on the dev
machine per Architect §6.4. Sprint 2 perf test budget of <250ms wall
time (test 20) is the regression sentinel. Acceptable.

## Tech debt delta

Matches ARCHITECTURE §7 predictions exactly. No surprise debt was
added. Repaid:
- Sprint 1 debt #2 (`docs/design.md` slug collision) — closed by
  rename.
- Sprint 1 debt #4 (registry unconsumed) — closed by both Hub and
  viewer wiring.
- Sprint 1 QA finding S1 (denylist parity) — closed.

Net debt change is marginally positive (the `/chat?seed=` stub and
the legacy `/design` handler), and both are scheduled for Sprint 3
with named owners.

## Required actions before merge

None. Ship it. Follow-ups for Sprint 3 (already tracked in
ARCHITECTURE §7):

1. Chat-side consumption of `?seed=` query param to make the Ask
   Buddy CTA non-stub.
2. Remove the `GET /docs/design.md` → 301 redirect once one release
   has shipped.
3. Collapse legacy single-doc handlers (`/design`,
   `/blueprints-overview`, etc.) into the registry-aware route.
4. Address `test_hub_empty_registry_renders_fallback` cross-suite
   isolation flake.
