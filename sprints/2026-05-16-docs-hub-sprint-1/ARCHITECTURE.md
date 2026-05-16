# Architecture — Docs Hub Sprint 1 (Phase F + Phase A)

**Date:** 2026-05-16
**Spec:** [SPRINT.md](./SPRINT.md) and the approved plan at
`~/.claude/plans/huge-miss-the-docs-elegant-gem.md`
**Mode:** design

---

## 1. Goal

Restore a broken nav link (regression fix) and lay the *foundation* for a
real Docs Hub by introducing a frontmatter-backed registry module.
Concretely Sprint 1 delivers:

- **Phase F:** promote `'docs'` from max-only to the **min** tier in
  `_TIER_SURFACES` (`src/arail/portal/app.py:98-102`); restore the
  `Docs` `<a>` element in `src/arail/portal/templates/_nav.html` between
  `Knowledge` and `Agents`, gated on `'docs' in _ts`.
- **Phase A:** add YAML frontmatter to 24 user-facing markdown files
  (`docs/*.md` minus 5 internal plus the curated repo-root five); build
  `src/arail/portal/docs_registry.py` (~120 lines) that walks both
  source roots, parses frontmatter, computes derived defaults, caches
  in-process keyed by directory mtime, and exposes the five accessors
  (`all_docs`, `by_category`, `get`, `siblings`, `related`); add tests
  in `tests/test_docs_registry.py`; add `python-frontmatter` to
  `pyproject.toml`.

The Sprint 1 registry is **importable but unconsumed**. No template or
route reads it yet. Sprint 2 wires it into the Hub landing and viewer.
The justification for shipping it now: the frontmatter contract is the
*hardest* thing to change once docs author against it, so we lock it
first, ship it independently, and prove it parses cleanly before any UI
depends on it.

---

## 2. Out of scope (explicit)

These are Sprint 2/3 work the architect is *resisting*:

- New `docs_hub.html` landing template. Sprint 2.
- Rewrite of `doc_viewer.html` (3-column layout, sidebar, TOC,
  prev/next, "Ask Buddy" CTA). Sprint 2.
- Anything that changes the existing `_render_markdown_page` function
  signature. Sprint 2 will extend it; Sprint 1 must not touch it.
- Deletion of `docs/INDEX.md`. The legacy redirect at
  `app.py:1812-1814` still points to `/docs/INDEX.md` and continues to
  resolve. Sprint 2 replaces the redirect with the Hub handler and
  Sprint 2 will decide whether to delete `INDEX.md` or keep it as a
  fallback.
- Extending wiki/PKB ingest to include `docs/`. Sprint 3.
- In-text linkification of canonical terms across docs. Sprint 3.
- Cross-link audit for orphan docs. Sprint 3 (the `related:`
  frontmatter values authored in Sprint 1 *enable* Sprint 3's audit but
  do not perform it).
- A registry-driven sitemap or sitemap-shaped JSON endpoint. Not
  needed in Sprint 1 because no consumer exists.

If the builder finds themselves writing template code, importing
`docs_registry` from `app.py`, or modifying `_render_markdown_page`,
they have drifted out of scope and should stop.

---

## 3. Assumptions

What this design trusts (and could be wrong about):

1. **`python-frontmatter==1.1.0` is already importable in dev** — it is
   (verified in `.venv` via `pip show`) but it is *not* declared in
   `pyproject.toml` today. It is reaching `.venv` as a transitive dep
   of something. Treat it as missing for the install contract and
   declare it explicitly.
2. **`_TIER_SURFACES` is the runtime source of truth** for nav gating.
   `pyproject.toml`'s `[tool.arail.tiers]` block (line 96-99) declares
   the same data but `app.py` does not read it. Updating the Python
   set is sufficient for nav behaviour; updating the TOML keeps the
   declarative copy in sync (architects considered authoritative).
   This duplication is pre-existing tech debt — flagged below, not
   resolved here.
3. **Tier gating in `_nav.html` is the only place** the `'docs'` key
   needs to appear for the link to render. Confirmed by reading
   `_nav.html` — every nav item is wrapped in `{% if '<key>' in _ts %}`.
4. **The existing `/docs/{path:path}` route at `app.py:1909-1933`
   continues to work** for every user-facing doc. Sprint 1 does not
   touch this route. Sprint 2 will replace `/docs` (the redirect) and
   may extend `_render_markdown_page` to pass registry context, but
   the per-doc URL pattern stays the same.
5. **Frontmatter parsing is restricted to a well-known YAML
   subset.** Doc authors will not invent custom tags, multi-line
   strings, anchors/aliases, or directives. The schema in §6 defines
   the allowed surface.
6. **The portal is not reachable from outside the user's machine.**
   This is the ARAIL local-first invariant. The registry returns
   string slugs and `Path` objects — it does not return rendered HTML
   and does not perform fetches.
7. **`docs/` is read-only at runtime** in the normal lab. The user
   *can* edit docs (it is their lab) but edits are infrequent. We
   accept O(seconds) cache staleness when docs are edited live.
8. **`python-frontmatter` parses YAML defensively when given malformed
   input.** Verified by reading the library source — it raises
   `yaml.YAMLError` (subclass of `Exception`) on bad YAML and the
   registry must catch it.
9. **The codebase already has a homegrown `wiki.parse_frontmatter`**
   (in `src/arail/wiki.py:127`) used by the wiki page index. The
   architect deliberately chose `python-frontmatter` for the docs
   registry rather than reusing `wiki.parse_frontmatter` because:
   the wiki parser only supports a tiny subset (`key: value` and
   single-line `[a, b]` lists), while the docs schema needs multi-word
   string values and nested-ish keys (`buddy_prompt:` may contain
   colons in the seed message). Justified divergence; documented as
   tech debt §9.

---

## 4. Data flow

```
                   ┌────────────────────────────────┐
                   │  src/arail/portal/app.py       │
                   │   • _TIER_SURFACES adds 'docs' │
                   │     to the "min" set           │
                   │   • templates.env.globals      │
                   │     ["tier_surfaces"] picks    │
                   │     it up at module import     │
                   └─────────────┬──────────────────┘
                                 │
                                 ▼
              ┌─────────────────────────────────────┐
              │ _nav.html (rendered per request)    │
              │   {% if 'docs' in _ts %}            │
              │     <a href="/docs">Docs</a>        │
              │   {% endif %}                       │
              └─────────────────────────────────────┘
                                 │
                                 ▼  (link target — unchanged Sprint 1)
              ┌─────────────────────────────────────┐
              │ /docs  → redirect to /docs/INDEX.md │
              │ /docs/{path}  → _render_markdown..  │
              │                 (existing route)    │
              └─────────────────────────────────────┘

────────────────────────────────────────────────────────────────
Phase A registry — independent data path, no consumer yet
────────────────────────────────────────────────────────────────

  repo_root/
   ├─ docs/*.md  ─────────────┐
   │                          │
   ├─ design.md               │   ┌──────────────────────────────┐
   ├─ BLUEPRINTS.md           ├──▶│ docs_registry.load()         │
   ├─ ROADMAP.md              │   │  1. walk curated roots       │
   ├─ SECURITY.md             │   │  2. skip denylist + internal │
   ├─ CONTRIBUTING.md         │   │  3. python-frontmatter parse │
   └──────────────────────────┘   │  4. fill defaults (word-count│
                                  │     read_minutes, H1 title,  │
                                  │     audience=beginner)       │
                                  │  5. build category index     │
                                  │  6. build related-by-tag idx │
                                  │  7. cache keyed by max(mtime │
                                  │     across both roots)       │
                                  └─────────┬────────────────────┘
                                            │
                                            ▼
                                  ┌──────────────────────────┐
                                  │ in-process module cache  │
                                  │ {_cache_key, _cache_data}│
                                  │   threading.Lock for     │
                                  │   concurrent rebuilds    │
                                  └─────────┬────────────────┘
                                            │
            ┌───────────────────────────────┼──────────────────────────┐
            ▼               ▼               ▼              ▼            ▼
       all_docs()    by_category()      get(slug)    siblings(slug) related(slug)
       → list[Doc]   → dict[cat,list]   → Doc|None    → (Doc?,Doc?)   → list[Doc]

  (no caller in Sprint 1 — only tests import these)
```

The two flows are independent. Phase F changes do not depend on Phase
A; Phase A changes do not depend on Phase F. They are bundled in one
sprint because they are both small and ship together to unblock Sprint
2.

---

## 5. Interface contracts

### 5.1 `docs_registry.Doc` (return type)

```python
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class Doc:
    slug: str                       # e.g. "agents-explained" or "design"
    path: Path                      # absolute path on disk, resolved
    title: str                      # never empty; falls back to H1, then stem
    description: str = ""           # may be empty
    category: str = "Reference"     # one of CATEGORIES; defaults to "Reference"
    order: int = 100                # sort key within category; lower first
    tags: tuple[str, ...] = ()      # immutable; lowercased; deduped
    read_minutes: int = 1           # >= 1; computed from word count if absent
    audience: str = "beginner"      # one of {"beginner","operator","architect"}
    related: tuple[str, ...] = ()   # raw slugs from frontmatter (validated)
    buddy_prompt: str = ""          # may be empty; opaque to registry
    source_root: str = "docs"       # "docs" or "root" (for routing in Sprint 2)
    mtime: float = 0.0              # file mtime, for "recently updated" UI
```

`Doc` is **frozen** so callers cannot mutate cached state. The
`related` field stores raw slugs as authored; resolution to actual
`Doc` objects happens in `related(slug, ...)` so a typo in
frontmatter does not crash construction.

### 5.2 Module-level accessors

| Function | Signature | Postcondition |
|---|---|---|
| `all_docs()` | `() -> tuple[Doc, ...]` | All registered docs, ordered by `(category_order, order, slug)`. Never raises. Empty tuple if registry could not be built. |
| `by_category()` | `() -> dict[str, tuple[Doc, ...]]` | Mapping of category → ordered docs in that category. Insertion order follows `CATEGORIES` declaration. Categories with zero docs are omitted. |
| `get(slug)` | `(str) -> Doc \| None` | `None` if no doc matches the slug. Case-sensitive match. |
| `siblings(slug)` | `(str) -> tuple[Doc \| None, Doc \| None]` | `(prev, next)` within the same category ordered list. `(None, None)` if the slug is unknown. Either side may be `None` at the boundaries. |
| `related(slug, limit=3)` | `(str, int) -> tuple[Doc, ...]` | Up to `limit` docs related to `slug`. Resolution rule below. |

Behavioural rules for `related()`:

1. Resolve any explicit `related:` slugs from the doc's frontmatter
   (in order). Skip slugs the registry does not know (silently drop;
   log at DEBUG).
2. If fewer than `limit` collected, fall back to tag-overlap
   candidates: docs in the same category that share ≥1 tag, scored
   by `len(shared_tags)` descending, then by `order` ascending, then
   by `slug` ascending.
3. Never include the doc itself.
4. Cap at `limit`. If `limit < 0`, treat as `0`. If `limit > total`,
   silently cap at total.

### 5.3 Preconditions for the module

- `python-frontmatter` is importable. If not, the module logs a single
  warning at module import and `all_docs()` returns `()`. The portal
  does not crash. The Sprint 2 Hub will see an empty registry and
  must degrade gracefully — out of scope here, but flagged.
- `pyyaml>=6.0` is already in `pyproject.toml` (`python-frontmatter`
  pulls it transitively, but it is also direct). Verified.

### 5.4 Slug scheme

Slugs are the path basename with `.md` removed, lowercased preserved
exactly as on disk. Examples:

- `docs/agents-explained.md` → slug `agents-explained`
- `docs/INSTALL.md` → slug `INSTALL`
- `design.md` (repo root) → slug `design`
- `BLUEPRINTS.md` (repo root) → slug `BLUEPRINTS`

**Open question:** the plan's `related:` example uses `agents.md` (with
extension). The registry must accept *both* `agents` and `agents.md`
in `related:` lists for author ergonomics. Resolution rule: strip
trailing `.md` before lookup. (Builder: implement this normalisation
in `related()` and in the frontmatter parser.)

**Collision risk:** because slugs are case-sensitive basenames,
`docs/INDEX.md` and a hypothetical root `INDEX.md` would collide. There
is no root `INDEX.md` today, but Sprint 1 should add an assertion in
`load()` that raises `RuntimeError` on collision (so the failure is
loud, not silent). Tested in §8.

### 5.5 Categories (closed enum)

```python
CATEGORIES: tuple[str, ...] = (
    "Getting Started",
    "Concepts",
    "Operating",
    "Reference",
    "Design",
)
```

Any frontmatter `category:` value outside this set is **coerced to
`Reference`** and a warning is logged. The set is closed and
authoritative; adding a category is a code change, not a doc change.
This is deliberate — it prevents docs drifting into orphaned
categories like `category: Misc`.

### 5.6 Phase F interface contract

In `_nav.html`, between the `knowledge` block (current line 33-36)
and the `agents` block (current line 38-41), insert:

```jinja
{% if 'docs' in _ts %}
<a href="/docs"{% if active == 'docs' %} class="active"{% endif %}
   title="Docs — learn the lab.">Docs</a>
{% endif %}
```

In `app.py` line 99 (the `"min"` set), append `"docs"`:

```python
"min": {"dashboard", "chat", "research", "knowledge", "agents", "docs"},
```

The `"max"` set already contains `"docs"` (line 101); no change there.
Also update `pyproject.toml`'s `[tool.arail.tiers].min.surfaces` array
to mirror — the declarative file is documentation, not runtime, but
keeping it in sync prevents future confusion.

The nav-partial header comment (lines 4-9) lists `active` values; it
already says `docs` is a valid `active`, so the comment is correct.
The header comment also reads "Default tier (min) shows only
dashboard + chat + research" which is now stale; update the line to
include `docs`.

---

## 6. Frontmatter schema

The canonical schema, locked for Sprint 1. Frontmatter is **optional**
— a doc with no `---` block still appears in the registry with
defaults. Frontmatter is **partial** — every field has a default; only
the fields the author cares about need be present.

| Key | Type | Required? | Default | Validation |
|---|---|---|---|---|
| `title` | string | no | first H1 in body; else stem (`Title Case`) | non-empty string after fallback chain |
| `description` | string | no | `""` | string |
| `category` | string | no | `"Reference"` | must be in `CATEGORIES` else coerced to `"Reference"` + warn |
| `order` | int | no | `100` | int; non-int coerced to `100` + warn |
| `tags` | list[str] | no | `[]` | normalised: strip, lowercase, dedupe, drop empty |
| `read_minutes` | int | no | computed from word count (`max(1, round(words/200))`) | int ≥ 1; non-int → recompute |
| `audience` | string | no | `"beginner"` | must be one of `{"beginner","operator","architect"}` else coerced to `"beginner"` + warn |
| `related` | list[str] | no | `[]` | normalised: strip, strip trailing `.md`, dedupe, drop empty, drop self-references |
| `buddy_prompt` | string | no | `""` | string; opaque to registry (Sprint 2 consumes) |

**Coercion philosophy:** the registry never refuses to register a doc
because of bad frontmatter. Bad fields are logged at WARNING level
(not ERROR — they are user input, not bugs) and replaced with
defaults. The reader's experience always wins over the author's
typo. This matches the ARAIL "fail gracefully on user input" principle
in the product CLAUDE.md.

**Buddy voice rule:** `buddy_prompt:` values written in Sprint 1 must
sound like Buddy (per `project_buddy_identity` memory: not "Pip", not
generic "AI assistant"; warm, collaborative, lab-partner voice). The
registry does not enforce this — it is a content-review item for the
QA pass.

**Internal exclusion list** (denylist; never appear in the registry):

In `docs/`:
- `BLUEPRINT_PROMPT.md` (prompt-engineering scratch)
- `DEBUG_QWEN25_7B_CASE_STUDY.md` (debugging case study)
- `maximus.plan.md` (planning doc)
- `chat-studio.spec.md` (legacy spec)
- `standards-compliance.md` (per plan: "either link or move to
  internal/ and exclude" — Sprint 1 excludes; Sprint 3 may rehome)

In repo root (denylist):
- `CLAUDE.md` (Claude onboarding, not user docs)
- `AGENTS.md` (external-agent porting manifest, not user docs)
- `README.md` (the project home page, not part of the in-app catalog)
- `CODE_OF_CONDUCT.md` (governance — out of catalog by author choice;
  can be added in Sprint 2 if desired)

**Curated allowlist for repo-root docs:**
- `design.md` → category `"Design"`
- `BLUEPRINTS.md` → category `"Design"`
- `ROADMAP.md` → category `"Design"` (or `"Reference"` — open
  question; default to `"Reference"` if author has no frontmatter
  preference)
- `SECURITY.md` → category `"Operating"`
- `CONTRIBUTING.md` → category `"Reference"`

**Special case — `docs/INDEX.md`:** the legacy hub. Sprint 1
**excludes** it from `all_docs()` because (a) it is the hub itself,
not a content page; (b) it has no frontmatter; (c) Sprint 2 will
delete or repurpose it. Excluded by name match in the denylist. The
registry must continue to function whether or not `INDEX.md` exists.

---

## 7. Failure modes

This is the most important section. Every row has a corresponding
test in §8.

| # | Failure | Detection | Recovery |
|---|---|---|---|
| F1 | Malformed YAML in a doc's frontmatter (e.g. unclosed bracket, bad escape) | `yaml.YAMLError` raised inside `python-frontmatter.loads` | Log WARNING with the file path and exception message; register the doc with defaults; do not crash the registry |
| F2 | Doc has no frontmatter (no leading `---` block) | `python-frontmatter.loads` returns empty metadata dict | Register with derived defaults: title from first H1 or stem; `read_minutes` from word count; `audience=beginner`; `category=Reference` |
| F3 | Frontmatter present but unknown key (e.g. `auther: ...` typo) | Key not in schema | Silently ignore the key (forward-compat for Sprint 2 additions); do not warn (would be noisy) |
| F4 | `category:` value not in the closed `CATEGORIES` enum | String comparison fails | Coerce to `Reference`; log WARNING once per doc |
| F5 | `audience:` value not in `{beginner, operator, architect}` | String comparison fails | Coerce to `beginner`; log WARNING once per doc |
| F6 | `tags:` is a string (not a list) — e.g. `tags: agents, buddy` | `isinstance(meta["tags"], str)` | Split on `,` and normalise (mirrors `wiki.build_page_index` behaviour); not an error |
| F7 | `related:` contains a slug that is not in the registry (typo or future doc) | Lookup miss in `related()` | Silently drop from results; log at DEBUG level (not warn — common during authoring) |
| F8 | `related:` contains a slug that resolves to the doc itself | Self-reference detected in `related()` | Drop silently — never include `self` |
| F9 | Path traversal via `related: ["../../etc/passwd"]` or `related: ["/etc/passwd"]` | `related()` only looks up slugs through `self._docs` dict; never reads files based on related values | The registry never opens a file path derived from frontmatter — it only walks the two curated roots at boot. F9 is structurally impossible by the design of §5, but the test in §8 asserts this anyway as a regression sentinel |
| F10 | File outside curated roots reachable via symlink (e.g. `docs/secret -> ../../../tmp/secret.md`) | `Path.resolve()` followed by `is_relative_to(root)` check | Skip the file; log WARNING. Each walked path must be resolved and verified to be inside one of the two curated roots after symlink resolution |
| F11 | Doc edited at runtime; cache returns stale data | Cache key includes `max(mtime)` over both root directories' immediate listings (not recursive — directory mtime changes when a child is added/removed/renamed; for in-place edits, fall back to per-file mtime in the cache key) | When `current_cache_key != _cache_key`, rebuild on next access. See concurrency note F12 |
| F12 | Concurrent rebuild — two uvicorn workers (or two threads in one worker) hit a stale cache simultaneously | Two threads detect stale cache, both enter the rebuild path | Hold a single `threading.Lock` around the rebuild. The losing thread waits, re-checks the cache, and uses the freshly built value. **Note:** under uvicorn's multi-worker mode each worker has its own cache — the lock only protects within a single worker. Cross-worker staleness is bounded by the cache key TTL (which is `mtime`-driven, not time-driven). Acceptable for Sprint 1 because nothing reads the cache yet; revisit in Sprint 2 |
| F13 | `python-frontmatter` not installed (regressed from `pyproject.toml`) | `ImportError` at module top | Log a single WARNING at module import; expose accessors that return empty / `None`; do not crash the portal. The Sprint 2 Hub will need to handle empty registry gracefully (out of scope here, but called out) |
| F14 | A registry collision — two docs produce the same slug (e.g. hypothetical root `INDEX.md` and `docs/INDEX.md`) | Duplicate-slug check during `load()` | Raise `RuntimeError("docs_registry: slug collision: <slug> from <pathA> and <pathB>")` — this is a developer error, not user input, so loud failure is correct. Caught in tests |
| F15 | `docs/` directory missing entirely (e.g. test running against a stripped repo) | `Path.exists()` check before walk | Skip that root; register repo-root docs only; do not crash. If both roots are missing, `all_docs()` returns `()` |
| F16 | Frontmatter parses but `title:` is whitespace or empty string | Truthiness check on resolved title | Fall back to first H1, then to filename stem with `Title Case` (matches `wiki.build_page_index`'s convention) |
| F17 | Doc has thousands of words (e.g. `chat-studio.spec.md` — 38K bytes; excluded but architectures should handle ingestion of similarly large docs) | Word count is O(n) on body; bounded | Acceptable: at 20 docs × 40KB each, total registry build is < 50ms even with full parses. No optimisation needed. Tested at the upper bound in §8 |
| F18 | Phase F regression: `'docs'` is removed from `_TIER_SURFACES["min"]` again in a future change | Direct assertion test on `_visible_surfaces()` with `LAB_TIER=min` | Sprint 1 adds the regression test (§8) so a future trim breaks CI |
| F19 | Phase F regression: the `Docs` link is removed from `_nav.html` again | Render `_nav.html` with a min-tier context and assert the link is in the HTML | Sprint 1 adds the regression test (§8) |
| F20 | WIP branch state (`lab/pkb/compiled/docs/guides/README.md` modified, `docs/decks/` untracked) bleeds into Sprint 1 PR | Builder must branch from a clean commit on `main`; pre-commit + `git status` review before push | Builder phase explicitly checks `git status` is clean of those paths before commit; the test branch starts from `main` |

---

## 8. Test strategy

ARAIL's stock QA weighting is 30% setup / 30% Buddy / 20% security /
10% happy / 10% regression. Sprint 1 has **no Buddy code changes** and
**no setup code changes** beyond a `pyproject.toml` line addition.
Re-weighting for this sprint:

| Bucket | Sprint 1 weight | Why |
|---|---|---|
| Setup | 15% | One pyproject line — `python-frontmatter` install verified on a clean venv |
| Security | 30% | Path traversal (F9), symlink escape (F10), denylist enforcement, malformed YAML (F1) — the lab runs on others' machines and this is the only Phase A surface a hostile doc could touch |
| Regression | 25% | Phase F is *itself* a regression fix and must not be re-regressed (F18, F19); the registry must not crash the portal on unusual frontmatter (F1, F11, F13) |
| Happy | 20% | The five accessors work for typical docs |
| Buddy | 10% | `buddy_prompt:` voice review (content-only, no code) |

Justification recorded in the sprint ledger.

### 8.1 Unit tests — `tests/test_docs_registry.py` (NEW)

A single test file per the plan. Each test gets its own fixture
directory written under `tmp_path` to isolate from the real repo
contents. Tests:

1. `test_loads_doc_with_full_frontmatter` — happy path; verify all
   `Doc` fields populate from a complete frontmatter block.
2. `test_loads_doc_with_no_frontmatter` — title falls back to first
   H1; `read_minutes` computed from word count; defaults apply
   (F2, F16).
3. `test_loads_doc_with_partial_frontmatter` — only `title:` and
   `category:` set; other defaults apply.
4. `test_malformed_yaml_logs_and_continues` — frontmatter block with
   `tags: [unclosed` does not crash; doc still registered with
   defaults; WARNING logged (F1). Use `caplog`.
5. `test_unknown_category_coerces_to_reference` — `category: Misc`
   → `Reference` (F4); WARNING logged.
6. `test_unknown_audience_coerces_to_beginner` — `audience: wizard`
   → `beginner` (F5); WARNING logged.
7. `test_tags_string_form_splits_correctly` — `tags: agents, buddy`
   → `("agents", "buddy")` (F6).
8. `test_unknown_frontmatter_keys_silently_ignored` — `auther: x`
   does not appear in `Doc` and does not warn (F3).
9. `test_all_docs_ordering` — sorted by category position, then
   `order`, then slug.
10. `test_by_category_omits_empty_categories` — only categories with
    ≥1 doc appear.
11. `test_get_returns_none_for_unknown_slug` — `get("does-not-exist")
    is None`.
12. `test_siblings_returns_prev_next_within_category` — middle doc
    has both; first has `None, next`; last has `prev, None`.
13. `test_siblings_unknown_slug_returns_none_pair` — `(None, None)`.
14. `test_related_resolves_explicit_frontmatter_first` — three docs
    in the same category, doc A has `related: [b, c]`, result is
    `(b, c)` in that order.
15. `test_related_falls_back_to_tag_overlap` — doc A has no
    `related:`; docs B and C share two tags with A and doc D shares
    one; result orders B/C above D.
16. `test_related_drops_self_reference` — `related: [self_slug]`
    → empty (F8).
17. `test_related_drops_unknown_slug` — `related: [ghost]`
    → empty + no exception (F7).
18. `test_related_drops_path_traversal_slug` — `related:
    ["../../etc/passwd", "/etc/passwd", "..\\windows\\system32"]`
    → empty; registry **never** opens these as files (F9).
19. `test_related_handles_extension_stripping` — `related:
    [agents.md]` resolves the same as `related: [agents]`.
20. `test_related_respects_limit_zero_and_negative` — `limit=0` →
    `()`; `limit=-1` → `()`.
21. `test_cache_invalidates_on_directory_mtime_change` — touch a
    file in the fixture root, `all_docs()` rebuilds (F11).
22. `test_concurrent_load_under_lock` — two threads call
    `all_docs()` simultaneously after invalidating; verify only one
    rebuild runs (count via a spy on the internal `_build` fn) (F12).
23. `test_python_frontmatter_missing_falls_back_to_empty_registry`
    — monkeypatch the import to raise `ImportError`; module loads;
    `all_docs()` returns `()`; WARNING logged (F13).
24. `test_slug_collision_raises_runtime_error` — fixture with two
    files resolving to the same slug → `RuntimeError` from `load()`
    (F14).
25. `test_missing_docs_dir_does_not_crash` — fixture root with no
    `docs/` subdir; registry returns only repo-root docs (F15).
26. `test_symlink_to_outside_root_is_skipped` — fixture has `docs/
    leak.md -> ../../outside.md`; the leaked doc is **not**
    registered and a WARNING is logged (F10). Skip on Windows
    (symlink permissions).
27. `test_internal_docs_excluded` — fixture contains a file named
    `DEBUG_QWEN25_7B_CASE_STUDY.md`; not in `all_docs()`.
28. `test_index_md_excluded` — fixture contains `docs/INDEX.md`;
    not in `all_docs()`.
29. `test_root_docs_use_root_source` — `design.md` at repo root
    appears with `source_root="root"`.
30. `test_word_count_read_minutes_floor_at_one` — a 5-word doc has
    `read_minutes == 1`, not 0.
31. `test_large_doc_parses_under_threshold` — a generated doc of 40KB
    parses in <100ms (F17). Marked `perf`.

### 8.2 Phase F regression tests — `tests/test_docs_nav_tier.py` (NEW)

32. `test_docs_in_min_tier_surfaces` — directly assert
    `'docs' in arail.portal.app._TIER_SURFACES['min']` (F18). This
    is the canary test: if a future PR trims it again, CI breaks.
33. `test_docs_link_renders_in_min_nav` — using the FastAPI TestClient
    with `LAB_TIER=min`, GET `/` (or any tier-min page), assert the
    response HTML contains `href="/docs"` (F19). This catches both
    the tier-set and the template wiring.
34. `test_docs_link_renders_in_max_nav` — same assertion for `max`.

### 8.3 No new integration/e2e tests for Sprint 1

The registry has no caller in Sprint 1. Integration tests for the
Hub render and viewer sidebar are Sprint 2's responsibility.

### 8.4 Manual verification (sprint exit checklist)

- `./arailctl start` → nav shows **Docs** on the default (min) tier.
- `LAB_TIER=max ./arailctl start` → nav still shows **Docs**.
- Click **Docs** → land on `/docs/INDEX.md` (unchanged Sprint 1 — the
  visible Hub lands in Sprint 2).
- `pytest tests/test_docs_registry.py tests/test_docs_nav_tier.py` →
  all green.
- `python -c "from arail.portal.docs_registry import all_docs;
  print(len(all_docs()))"` → returns ≥ 20.
- `pip install -e .` on a clean venv succeeds and pulls
  `python-frontmatter` (no manual `pip install` needed).

---

## 9. Tech debt assessment

### Debt added by Sprint 1

1. **Dual tier-surface declarations** — `_TIER_SURFACES` in
   `app.py:98-102` and `[tool.arail.tiers]` in `pyproject.toml`
   declare the same surfaces. Sprint 1 must keep both in sync (we
   add `docs` to both). The duplication itself is pre-existing debt;
   Sprint 1 does not remove it. **Owner:** future infra sprint —
   either have app.py read TOML, or delete the TOML copy.
2. **Two frontmatter parsers in the codebase** — `wiki.parse_frontmatter`
   (homegrown, minimal) and `docs_registry` (uses `python-frontmatter`).
   Justified by schema differences (§3.9), but reconciling later
   would simplify. **Owner:** Sprint 2 or later, when wiki ingest
   includes docs (Sprint 3 of the plan).
3. **`docs/INDEX.md` is still the redirect target** at `app.py:1814`
   even though the registry doesn't include it. Sprint 2 replaces
   this redirect. Sprint 1 deliberately leaves it intact so the nav
   link works the same as before. **Owner:** Sprint 2.
4. **Registry is unconsumed** — code that compiles, has tests, and
   is imported by nothing in production paths. This is intentional
   foundation work but it is debt in the sense that it is unverified
   in real use until Sprint 2 wires it up. **Owner:** Sprint 2.
5. **Per-worker cache under uvicorn** (F12 note) — each worker
   rebuilds independently. Cheap enough at 20 docs; revisit if the
   doc count grows past ~200 or if Sprint 2 puts the registry on a
   hot request path. **Owner:** Sprint 2.
6. **No author-side schema validator** — if a contributor writes
   `category: Misc`, the registry coerces silently. Sprint 2 should
   add a `pytest`-time validator that fails CI on unknown categories
   so authoring errors are caught at PR time rather than at runtime
   (where they degrade to "Reference"). **Owner:** Sprint 2.

### Debt repaid

1. **The Phase F regression** — accidentally trimmed in commit
   `732dc8e`. After Sprint 1, the regression cannot reappear silently
   because `test_docs_in_min_tier_surfaces` and `test_docs_link_renders
   _in_min_nav` are sentinels.
2. **`docs` was max-only** — newcomers on the default tier could not
   reach the docs they most needed. Promoted to min.

### Net assessment

**Net debt: slightly positive but bounded.** The biggest single piece
is the unconsumed registry, which is by design — the alternative is
to fold Sprint 2 in and ship a much bigger PR with all the rendering
churn. The split is the right call.

---

## 10. Open questions for the builder (and possibly the user)

The builder must resolve these before coding, or escalate to the user
session:

1. **`ROADMAP.md` category** — Sprint 1 categorises it as
   `Reference`. The plan groups it loosely under "Design and layout"
   and the existing `INDEX.md` lists it under "Design and layout".
   **Recommendation:** keep it under `Reference` for Sprint 1; the
   author can change `category:` in frontmatter later without
   touching code. Builder may overrule with a one-line note in the
   build log.
2. **Default `description` for the 24 docs** — many existing docs
   lack a single-line summary. Builder may either (a) author a
   one-line description for each as part of the frontmatter
   addition, or (b) leave `description: ""` and let the registry's
   consumer (Sprint 2) display the first paragraph instead.
   **Recommendation:** author one-line descriptions for the five
   featured docs (`agents-explained.md`, `BUDDY.md`,
   `api-conventions.md`, `INSTALL.md`, `design.md`) and leave the
   rest empty. Sprint 2 will tighten this.
3. **`buddy_prompt` strings** — the plan shows one example
   (`"Walk me through what an agent loop does, using the lab I'm in
   as the example."`). Sprint 1 does not consume these — the
   "Ask Buddy" CTA is Sprint 2. **Recommendation:** include a
   `buddy_prompt:` only for the three featured docs (`agents-
   explained.md`, `BUDDY.md`, `api-conventions.md`) in Sprint 1;
   leave the rest blank so Sprint 2 authors them when the CTA UX is
   designed. Builder may overrule.
4. **`pyproject.toml` placement of `python-frontmatter`** — base
   `dependencies` or a new `[project.optional-dependencies]` group?
   **Recommendation:** base `dependencies`. The docs surface ships
   on `min`; the registry is core. `python-frontmatter` is a 50KB
   pure-Python package — no install-time cost concern.
5. **Should `CONTRIBUTING.md` be in the registry?** It is repo-root
   developer-facing, not lab-user-facing. The plan lists it under
   curated roots. **Recommendation:** include it (audience
   `architect`, category `Reference`). A friend forking the repo to
   build their own lab is a user and should see contribution norms.
6. **What does the Phase F nav comment update look like?** The
   header comment on `_nav.html` lines 12-13 currently says
   "Default tier (min) shows only dashboard + chat + research."
   That is already stale (knowledge, agents are also in min).
   **Recommendation:** rewrite line 12-13 to "Default tier (min)
   shows: dashboard, chat, research, knowledge, agents, docs.
   Upgrade with `./arailctl upgrade max`."
7. **Branching discipline** — the WIP changes
   (`M lab/pkb/compiled/docs/guides/README.md` and `?? docs/decks/`)
   must not enter this PR. **Required:** start the build branch from
   the current `main` (`git checkout main && git pull && git
   checkout -b qukaizen/arail-docs-hub-sprint-1`); the WIP changes
   stay on `qukaizen/arail-warmup-overlay`. Confirm with `git status`
   before the first commit.

---

## 11. Recommended implementation order

For the builder. Each step is independently verifiable.

1. **Branch off `main`** — `git checkout main && git pull && git
   checkout -b qukaizen/arail-docs-hub-sprint-1`. Verify `git status`
   is clean of `lab/pkb/compiled/docs/guides/README.md` and
   `docs/decks/`.
2. **Phase F first** (5-minute change, immediate user-visible value):
   - Update `_TIER_SURFACES["min"]` in `app.py:99` to add `"docs"`.
   - Update `[tool.arail.tiers].min.surfaces` in `pyproject.toml:98`
     to mirror.
   - Insert the `{% if 'docs' in _ts %}` block in `_nav.html` between
     the knowledge block and the agents block.
   - Update the stale nav comment on `_nav.html:12-13`.
   - Write `tests/test_docs_nav_tier.py` covering the three
     regression tests (F18, F19, plus max-tier render).
   - Run the new tests; commit: `fix(portal): restore docs nav link
     + promote to min tier`.
3. **Phase A scaffold**:
   - Add `python-frontmatter>=1.1.0` to `pyproject.toml` base
     `dependencies`.
   - Create `src/arail/portal/docs_registry.py` per §5 contract.
   - Write `tests/test_docs_registry.py` with the 31 tests in §8.1.
   - Run tests; iterate until green.
   - Commit: `feat(portal): docs_registry — frontmatter-driven docs
     foundation`.
4. **Phase A content** (the slowest step — 24 files):
   - Add frontmatter to the 19 user-facing `docs/*.md` files
     (excluding INDEX + 5 internal) and the 5 repo-root files
     (`design.md`, `BLUEPRINTS.md`, `ROADMAP.md`, `SECURITY.md`,
     `CONTRIBUTING.md`). Use the defaults table in §6.
   - For each, populate `title`, `category`, `audience`. Optional
     `tags`, `order`, `description` per the §10.2 recommendation.
   - Run `python -c "from arail.portal.docs_registry import
     all_docs; [print(d.slug, d.category) for d in all_docs()]"` and
     verify the count is ≥ 20 and categories distribute roughly
     evenly.
   - Commit (single content commit): `docs: add YAML frontmatter to
     user-facing docs (Sprint 1 of Docs Hub)`.
5. **Final pass**:
   - Run the full test suite (`pytest -x`) to ensure nothing
     unrelated broke.
   - Write `BUILD_LOG.md` per the sprint pipeline.
   - Hand off to architect (review mode).
