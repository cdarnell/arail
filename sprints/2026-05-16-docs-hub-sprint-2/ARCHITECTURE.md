# Architecture — Docs Hub Sprint 2 (Phase B + Phase C + carryovers)

**Date:** 2026-05-16
**Spec:** [SPRINT.md](./SPRINT.md); approved plan at
`~/.claude/plans/huge-miss-the-docs-elegant-gem.md`; predecessor
[../2026-05-16-docs-hub-sprint-1/ARCHITECTURE.md](../2026-05-16-docs-hub-sprint-1/ARCHITECTURE.md)
**Mode:** design

---

## 1. Restatement

Sprint 1 shipped the Sprint-1 trio (Phase F nav fix, frontmatter on
all user-facing docs, the `docs_registry` module) and intentionally
left the registry **importable but unconsumed**. Sprint 2's job is to
wire the registry into the two surfaces a user actually sees: a real
**Docs Hub** at `/docs` (replacing the 302 redirect to `INDEX.md`) and
a **viewer overhaul** at `/docs/{path}` that turns today's dead-end
markdown page into a navigable learning surface (left rail of category
peers, right TOC, prev/next + related + "Ask Buddy" footer). We also
close two Sprint-1 carry-overs: rename `docs/design.md` to resolve the
slug collision that forced it into the denylist, and add tier-aware
filtering at the render boundary so `architect`-audience docs do not
appear on `min`-tier Hubs.

If the user can click `Docs` from a fresh min-tier lab, land on a Hub
that feels like a library, click into `agents-explained.md`, navigate
sideways to a sibling doc via the left rail, jump within the doc via
the TOC, hit "Ask Buddy about this" and see a sensibly seeded chat —
without ever using the browser back button — this sprint is done.

---

## 2. Assumptions

1. **`docs_registry.all_docs()` returns ≥18 docs** after Sprint 1's
   frontmatter pass. Verified against Sprint 1's exit checklist.
2. **`markdown_it` token stream exposes `heading_open` tokens** with
   `tag in ("h2","h3")` and the following `inline` token's content is
   the heading text. Stable API — confirmed by reading markdown-it-py
   source (used in production already by `_render_markdown_page`).
3. **The existing `/docs/{path:path}` route's path-traversal guard
   (app.py:1924-1932)** is correct as written and the Sprint 2 changes
   only *extend* it — they do not relax `target.parents` check or the
   `docs_root / path` containment check.
4. **The user has not bookmarked `docs/design.md` externally**, or if
   they have, a 301 redirect from the old path is acceptable. We add a
   redirect for one release; Sprint 3 removes it.
5. **TOC extraction at request time is acceptable perf-wise.** The
   largest user-facing doc is ~40KB; markdown-it-py parses that in
   <30ms on the dev machine. We do NOT need to cache rendered HTML for
   Sprint 2. Failure mode F-perf covers regression.
6. **Tier value comes from `os.environ["LAB_TIER"]` via the existing
   `_visible_surfaces()` helper / `tier_surfaces` template global.**
   No new tier plumbing.
7. **Chat tab accepts a `seed=` query param** OR the CTA is a deep-
   link that the chat tab will learn to honor in Sprint 3. If it does
   not consume it today, the CTA is a soft-fail: chat opens to the
   normal initial state. This is the agreed Sprint 2 stub behaviour.
8. **`docs/INDEX.md` continues to render** through the unchanged
   `/docs/{path}` viewer route as a fallback for old links. The Hub
   route owns `/docs` (exact), so there is no route conflict.
9. **No new Python deps.** Everything needed (markdown-it-py,
   python-frontmatter) is already in pyproject from Sprint 1.

---

## 3. Data flow

```
   ┌─────────────────────────────────────────────────────────────┐
   │ Request: GET /docs                                          │
   └─────────────┬───────────────────────────────────────────────┘
                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ docs_hub() handler (app.py, replaces redirect at 1812-1814) │
   │   1. tier = current LAB_TIER                                │
   │   2. cats = docs_registry.by_category()                     │
   │   3. cats = _filter_by_tier(cats, tier)                     │
   │   4. featured = _featured_docs(cats)  # 3 hand-picked slugs │
   │   5. recent  = _recently_updated(cats, days=7)              │
   │   6. render docs_hub.html with {cats, featured, recent}     │
   │   7. degrades gracefully if cats == {} (registry empty)     │
   └─────────────┬───────────────────────────────────────────────┘
                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ docs_hub.html                                               │
   │   ─ Hero (title + tagline + client-side search input)       │
   │   ─ Featured strip (3 cards)                                │
   │   ─ Recently updated chips (≤5)                             │
   │   ─ Category sections × N (each a grid of doc cards)        │
   │   ─ "Add a doc" footer linking to REPOSITORY_LAYOUT         │
   │   ─ Inline JS: filter cards by title/desc/tag substring     │
   └─────────────────────────────────────────────────────────────┘

   ┌─────────────────────────────────────────────────────────────┐
   │ Request: GET /docs/agents-explained.md                      │
   └─────────────┬───────────────────────────────────────────────┘
                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ docs_viewer() (existing route; signature widened)           │
   │   1. existing path-traversal guard (UNCHANGED)              │
   │   2. slug = Path(path).stem                                 │
   │   3. doc  = docs_registry.get(slug)        # may be None    │
   │   4. tier = LAB_TIER                                        │
   │   5. if doc and not _audience_allowed(doc, tier):           │
   │         403 / Not visible on this tier (with upgrade hint)  │
   │   6. body_html + toc = _render_with_toc(target.read_text()) │
   │   7. prev, nxt = docs_registry.siblings(slug) if doc else..│
   │   8. related   = docs_registry.related(slug, limit=3)       │
   │   9. render doc_viewer.html with full context               │
   └─────────────┬───────────────────────────────────────────────┘
                 ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ doc_viewer.html (3-col, collapses <900px)                   │
   │  ┌──────────┬──────────────────────┬────────────────────┐   │
   │  │ Left rail│ Article              │ Right rail (TOC)   │   │
   │  │ Back↩    │ Breadcrumb / H1 ...  │ H2 ...             │   │
   │  │ Cats     │ rendered markdown    │   H3 ...           │   │
   │  │ - peer1  │                      │ H2 ...             │   │
   │  │ * THIS   │                      │                    │   │
   │  │ - peer2  │ Footer: prev | next  │                    │   │
   │  │          │ Related (3 cards)    │                    │   │
   │  │          │ [Ask Buddy ...] btn  │                    │   │
   │  └──────────┴──────────────────────┴────────────────────┘   │
   └─────────────────────────────────────────────────────────────┘
```

The `docs/design.md` → `docs/portal-design.md` rename is a one-time
filesystem change plus:
- remove `"design.md"` from `_DOCS_DENYLIST` in `docs_registry.py`,
- add frontmatter to the renamed file,
- add a one-line redirect handler `GET /docs/design.md → 301
  /docs/portal-design.md` (kept for one release).

---

## 4. Interface contracts

### 4.1 `docs_hub()` handler

- **URL:** `GET /docs` (exact). Replaces the existing redirect.
- **Pre:** none. Works even if registry is empty.
- **Post:** 200 HTML; rendered with `nav_active="docs"`. Never raises.
- **Empty-registry behaviour:** renders a "Docs catalog is unavailable
  right now — try `./arailctl pkb ingest` or read `docs/INDEX.md` directly"
  fallback panel. No 5xx.

### 4.2 `_filter_by_tier(cats, tier) -> dict[str, tuple[Doc, ...]]`

- **Pre:** `cats` is the unfiltered `by_category()` result; `tier` is
  one of `{"min","max"}` (other values treated as `min`).
- **Post:** drops docs whose `audience` is not allowed on `tier`.
  Allowed sets:
  - `min`: `{"beginner","operator"}`
  - `max`: `{"beginner","operator","architect"}`
- Categories that become empty after filtering are omitted.
- Pure function. No I/O. Deterministic.

### 4.3 `_featured_docs(cats) -> tuple[Doc, ...]`

- Hand-picked slugs in priority order: `agents-explained`, `BUDDY`,
  `api-conventions`. Skips any that the tier filter removed. Returns
  up to 3.

### 4.4 `_recently_updated(cats, days=7) -> tuple[Doc, ...]`

- Filters by `mtime > now - days*86400`. Returns up to 5, ordered by
  `mtime` descending.

### 4.5 `_render_with_toc(markdown_text) -> (body_html, toc)`

- **Pre:** UTF-8 string.
- **Post:** `body_html` is the rendered HTML *with H2/H3 headings
  carrying stable `id="<slug>"` attributes* (slug = lowercase, spaces
  → `-`, drop non-`[a-z0-9-]`, ensure uniqueness via numeric suffix).
- `toc` is a list of `{"level": 2|3, "id": str, "text": str}` in
  document order.
- TOC may be empty (single-H1 doc) — viewer hides the right rail when
  empty.

### 4.6 `doc_viewer.html` template contract

Required context: `doc_path`, `doc_html`, `toc`, `doc` (the `Doc` or
`None`), `siblings_prev`, `siblings_next`, `related`, `tier`,
`buddy_prompt_url` (precomputed `/chat?agent=buddy&seed=...&doc=<slug>`
or empty string), `nav_active`. If `doc` is `None` (the registry has
no entry — likely a non-frontmatter fallback case like `INDEX.md`),
the template renders **only** the center article and breadcrumb —
left rail, right rail, and footer strip are all suppressed.

### 4.7 Public registry API

**Unchanged.** Sprint 2 imports `all_docs`, `by_category`, `get`,
`siblings`, `related`, `CATEGORIES`. No new public functions are
required. If a `featured()` helper proves useful, it must live in
`app.py` not in `docs_registry.py` (keep the registry pure catalog).

---

## 5. Failure modes

| # | Failure | Detection | Recovery |
|---|---|---|---|
| F1 | Registry empty (Sprint-1 F13 propagation: `python-frontmatter` not installed, build failed) | `not by_category()` in handler | Render Hub with fallback panel ("Docs catalog unavailable"); link to `/docs/INDEX.md`. No 5xx. |
| F2 | Slug in URL has no registry entry (e.g. `/docs/INDEX.md`, or a file added without frontmatter) | `docs_registry.get(slug) is None` | Render viewer in degraded mode: center article only, no left rail / TOC / footer. Article still works. |
| F3 | Tier leak — an `architect`-audience doc rendered into the Hub on `min` tier | `_filter_by_tier` strips it; test asserts no `architect` slug in min-tier Hub HTML | Filter at handler. If filter is bypassed, the user can still hit the direct URL `/docs/<slug>` — viewer must also apply the filter and return 404-style "Not visible on this tier" page with an upgrade hint. **Don't reveal the title** in the error (mild info leak). |
| F4 | Path traversal via `/docs/../../etc/passwd` | Existing guard `docs_root in target.parents` | Unchanged — Sprint 2 MUST NOT relax this. Test asserts the guard still rejects. |
| F5 | TOC extraction crashes on unusual markdown (raw HTML block, malformed heading, nested headings inside a code fence) | `markdown_it` returns tokens; we iterate defensively (skip tokens missing `tag` or `content`) | Wrap in try/except; on failure, render with `toc=[]` (viewer hides right rail). Log WARNING. |
| F6 | Duplicate heading IDs in TOC (two `## Setup` blocks in one doc) | ID generator must dedupe with numeric suffix | Anchor links remain stable across renders of the same file (counter is per-render and depends only on document order — deterministic). |
| F7 | Large doc render perf regression | Manual measurement: REPOSITORY_LAYOUT.md (~10KB) and ROADMAP.md must render in <100ms p95 | Test in §6.4. If regressed, defer TOC to client-side JS in a follow-up. |
| F8 | Search filter JS leaks (e.g. injecting `<script>` via card title) | All template output goes through Jinja autoescape; the search filter only reads `textContent`, never `innerHTML` | Code review check; test with a fixture doc whose title is `<img onerror=alert(1)>` to confirm it renders as text. |
| F9 | `buddy_prompt` contains characters that break the URL when seeded | `urllib.parse.quote_plus` in the handler, not in the template | Precompute the full `/chat?...` URL server-side and pass as `buddy_prompt_url`; template only inserts it as `href`. |
| F10 | `docs/design.md` rename breaks external bookmarks | Old URL returns 404 | Add `GET /docs/design.md` → 301 `/docs/portal-design.md` redirect for one release. Tracked debt; remove in Sprint 3. |
| F11 | Slug collision reappears (Sprint 1 F14) when `design.md` is un-denylisted | Registry raises `RuntimeError` at load | Builder must verify: rename `docs/design.md` → `docs/portal-design.md` is committed in the **same commit** that removes `"design.md"` from `_DOCS_DENYLIST`. Test in §6.2 asserts the registry loads cleanly. |
| F12 | Empty category section rendered (after tier filter strips all members) | `_filter_by_tier` omits empties; template iterates only the filtered dict | Don't iterate a category with zero visible docs. |
| F13 | Hub or viewer renders successfully but Docs nav link is missing for the current tier (Sprint 1 regression re-occurs) | Sprint 1's `test_docs_link_renders_in_min_nav` is still in CI | If that test breaks, Sprint 2 is blocked from merge. |
| F14 | "Ask Buddy" CTA opens chat but chat ignores `seed=` — user sees a blank chat | Documented stub behaviour per Sprint 2 scope; chat-side wiring is Sprint 3 | Acceptable for Sprint 2. The CTA still navigates to chat (better than nothing). Add a TODO comment in the template referencing Sprint 3. |
| F15 | Viewer is opened on a doc whose audience requires `max` but the user is on `min` | `_audience_allowed(doc, tier)` returns False | Return 200 HTML with a "This doc is for the `max` tier — run `./arailctl upgrade max` to unlock" panel. Do not 404 (gives a teaching moment). Use `nav_active="docs"`. |
| F16 | Per-worker registry cache desync (Sprint 1 F12 carry-over) — two uvicorn workers show different doc lists | Per-Sprint-1 architecture: bounded by file mtime invalidation; acceptable | Document; no code change. Track as debt §9. |
| F17 | WIP from prior session bleeds into the sprint PR | Builder pre-commit `git status` review | The branch starts from current HEAD; unrelated changes (`tests/test_system_health_stream_tier_filter.py`, `lab/pkb/compiled/docs/guides/*`) must be stashed or committed elsewhere before the first Sprint 2 commit. |
| F18 | Markdown-it autolink converts `agents-explained` references inside doc body into `<a href="agents-explained">` but the resolved URL is wrong (relative path issue) | Manual check on a doc that links sibling docs | Existing renderer behaviour unchanged; if regressed, fall back to explicit `[text](slug.md)` in source docs. |

---

## 6. Test strategy

QA weighting for this sprint: 10% setup / 20% Buddy / 15% security /
35% happy / 20% regression.

### 6.1 New unit / integration tests — `tests/test_docs_routes.py`

Use FastAPI TestClient.

1. `test_hub_renders_200_min_tier` — happy path; HTML contains category
   names and at least one doc card.
2. `test_hub_renders_200_max_tier` — same, but `architect`-audience
   docs are present.
3. `test_hub_min_tier_hides_architect_audience_docs` (F3) — assert no
   doc with `audience: architect` appears in HTML; pick a known
   architect-audience slug (e.g. `api-conventions` if architect, else
   author a fixture doc).
4. `test_hub_empty_registry_renders_fallback` (F1) — monkeypatch
   `by_category` to return `{}`; assert 200 + fallback panel text.
5. `test_hub_featured_strip_contains_three_slugs` — when the three
   featured slugs exist.
6. `test_hub_featured_strip_omits_filtered_slugs` — when one of the
   three is filtered out on `min`, only 2 cards render (no broken
   third slot).
7. `test_hub_search_filter_input_present` — Hero has `<input
   type="search">` with the expected JS hook id.
8. `test_hub_card_title_is_escaped` (F8) — fixture doc with a
   `<script>` title renders as text.
9. `test_viewer_renders_with_full_context` — viewer shows left-rail
   sibling, right-rail TOC, prev/next chips, related cards.
10. `test_viewer_renders_doc_without_registry_entry` (F2) — `docs/
    INDEX.md` (no frontmatter — in denylist) renders center-only.
11. `test_viewer_min_tier_blocks_architect_doc` (F15) — direct GET
    on a max-tier-only doc returns 200 with upgrade-hint body; title
    of the blocked doc is **not** in the response (no leak).
12. `test_viewer_path_traversal_rejected` (F4) — `GET /docs/../../etc/
    passwd` returns 404; reuses existing guard.
13. `test_viewer_toc_extracted_for_h2_h3` — fixture doc with two H2
    and one H3 produces a 3-entry TOC with stable IDs.
14. `test_viewer_toc_dedupes_collisions` (F6) — fixture with two
    `## Setup` headings produces `setup` and `setup-2`.
15. `test_viewer_toc_empty_for_single_h1` — viewer template hides
    right rail.
16. `test_viewer_ask_buddy_link_url_encoded` (F9) — `buddy_prompt`
    with `&` and `?` produces a correctly-quoted href.
17. `test_viewer_ask_buddy_omitted_when_prompt_empty` — no Ask Buddy
    button when frontmatter has no `buddy_prompt`.
18. `test_legacy_design_redirect` (F10) — `GET /docs/design.md`
    returns 301 → `/docs/portal-design.md`.
19. `test_no_slug_collision_after_rename` (F11) — `all_docs()` does
    not raise; the renamed slug `portal-design` is present.
20. `test_viewer_renders_largest_doc_under_perf_budget` (F7) — render
    `ROADMAP.md`; assert <250ms wall time (CI-tolerant threshold;
    local target is <100ms).
21. `test_viewer_handles_unusual_markdown_in_toc` (F5) — fixture doc
    with a heading inside a code fence is not in the TOC; raw HTML
    block does not crash extraction.

### 6.2 Regression carry-over (existing tests must still pass)

- `tests/test_docs_registry.py` (Sprint 1) — full suite.
- `tests/test_docs_nav_tier.py` (Sprint 1) — F18/F19 sentinels.
- Any existing `tests/test_docs_*` viewer test — check the rewrite
  did not break older assertions.

### 6.3 Buddy voice review (20% allocation, content-only)

QA inspects every `buddy_prompt` value rendered by the Hub or viewer.
Voice rule: Buddy is the warm lab-partner identity (per
`project_buddy_identity` memory: not Pip, not generic "AI assistant").
Any prompt that sounds robotic or off-voice is filed as a finding.

### 6.4 Performance check (manual; one-shot)

```
time curl -s http://127.0.0.1:8080/docs > /dev/null
time curl -s http://127.0.0.1:8080/docs/ROADMAP.md > /dev/null
```

Acceptance: Hub <120ms p50 with 20 docs; viewer <150ms p50 for the
largest doc. If either fails, defer TOC to client-side.

### 6.5 Manual learning-loop check (exit gate from master plan)

1. Fresh min-tier session → click `Docs` → land on the Hub.
2. Click `Agents, explained` → land on viewer with left rail showing
   the Concepts category and `agents-explained` highlighted.
3. TOC right rail has H2 entries; clicking one scrolls into the doc.
4. Click `Next` chip → adjacent Concepts doc renders.
5. Click `Ask Buddy about this` → chat opens (seed visible in URL,
   even if chat-side consumption is Sprint 3).
6. Return to Hub via the left rail's `← Back to Docs Hub`.

If the loop runs cleanly in <2 minutes without browser back-button
use, this sprint exits.

---

## 7. Tech debt assessment

### Added

1. **`/chat?seed=` is a stub** — the CTA is wired but chat doesn't
   consume it. Sprint 3 closes the loop. Owner: Sprint 3.
2. **`GET /docs/design.md` 301 redirect** — kept for one release. Owner:
   Sprint 3 deletes it.
3. **Per-render TOC extraction** — no caching. Fine at current scale;
   becomes debt if docs grow past 50 or include a 100KB+ doc. Owner:
   open; revisit if `time` numbers regress.
4. **Hub search is client-side substring** — works for 20 docs, will
   not scale to a docs+pkb unified result set. Sprint 3 swaps it for
   the unified `/api/pkb/search?scope=docs|pkb|all`.
5. **Two doc-redirect handlers** for the rename (Sprint 2) + the
   still-existing root-doc handlers (`/design`, `/blueprints-overview`,
   etc. at app.py:1835-1895) that predate the registry. Net: more
   handlers, not fewer. Owner: Sprint 3 collapses these into a single
   registry-aware route.

### Repaid

1. **`docs/design.md` slug collision** — fixed properly by rename, not
   by denylist hack. Sprint 1's debt #2 closed.
2. **Registry was unconsumed** (Sprint 1 debt #4) — now consumed in
   two render paths.
3. **The `/docs` redirect** to `INDEX.md` (a markdown file pretending
   to be a hub) — replaced by a real hub.

### Net

Marginally positive. The `/chat?seed=` stub and the legacy `/design`
handler are the two unpaid items; both are scheduled for Sprint 3.

---

## 8. Recommended implementation order

For the builder. Each step is independently committable.

1. **Branch hygiene.** `git status` must be clean of the untracked
   `tests/test_system_health_stream_tier_filter.py` and the
   `lab/pkb/compiled/docs/guides/*` modifications. Stash or move
   before starting.

2. **Rename `docs/design.md` → `docs/portal-design.md`** in a single
   commit that also:
   - Adds frontmatter to the renamed file (title, category=Design or
     Reference, audience=architect).
   - Removes `"design.md"` from `_DOCS_DENYLIST` in
     `src/arail/portal/docs_registry.py`.
   - Adds the `GET /docs/design.md` → 301 redirect handler in
     `app.py`.
   - Adds a Sprint-1 registry test asserting no collision (`test_no_
     slug_collision_after_rename`).
   - Run `pytest tests/test_docs_registry.py` — Sprint 1 suite still
     green.
   - Commit: `refactor(docs): rename docs/design.md → portal-design.md
     (resolve slug collision)`.

3. **Hub handler + template** (no viewer changes yet).
   - Replace the redirect at `app.py:1812-1814` with `docs_hub()`.
   - Add `_filter_by_tier`, `_featured_docs`, `_recently_updated`
     helpers near the handler.
   - Write `src/arail/portal/templates/docs_hub.html` per §3.
   - Tests 1-8 in §6.1.
   - Commit: `feat(portal): docs_hub landing replaces /docs redirect`.

4. **TOC extractor + viewer rewrite.**
   - Add `_render_with_toc(text)` helper near `_render_markdown_page`.
   - Refactor `_render_markdown_page` to optionally pass the new
     context (toc, doc, siblings, related, buddy_prompt_url, tier).
   - Rewrite `doc_viewer.html` for 3-column layout. Preserve all
     existing `.doc-shell` styles for the center column.
   - Tests 9-17, 20, 21 in §6.1.
   - Commit: `feat(portal): doc_viewer 3-column with TOC + siblings +
     related + Ask Buddy CTA`.

5. **Final pass.**
   - `pytest -x` full suite.
   - Manual learning-loop (§6.5).
   - Write `BUILD_LOG.md`.

---

## 9. Open questions

These are non-blocking but the builder may resolve them inline:

1. **`api-conventions.md` audience** — currently `architect` per the
   Sprint 1 frontmatter pass. Master plan says it should be one of the
   three on-ramps featured for newcomers. Possible options: (a) lower
   to `operator` so it appears on `min`; (b) keep `architect` and
   accept that the third Hub featured card is invisible on min;
   (c) special-case featured docs to bypass tier filter. **Architect
   recommendation:** (a) — lower to `operator`. API conventions belong
   in front of beginners-once-they-start-building. Builder may inline
   this change.
2. **Hub search default behaviour** — empty input shows all docs;
   typed input filters by substring across title+description+tags.
   Confirmed; no question.
3. **Where to put `_featured_docs` and `_filter_by_tier`** — in
   `app.py` near the handler, or in a new `src/arail/portal/docs_view.py`
   module? **Recommendation:** keep in `app.py` for Sprint 2 (small
   functions, fewer files). If they grow past 50 lines combined,
   extract in Sprint 3.

---

## 10. Verdict

**Proceed.** Scope is well-bounded by Sprint 1's deliberate split;
the registry contract is locked; the failure modes are enumerated with
tests. Top three failure modes to watch in review:

- **F3 (tier leak):** an `architect` doc appearing on a `min` Hub.
- **F4 (path traversal):** existing guard must not be weakened.
- **F11 (slug collision regression):** the rename must land before
  the denylist entry is removed in the same commit.
