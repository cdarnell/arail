# ARCHITECTURE-recolor.md — World mount visibly recolors the whole lab

> Addendum to the "World Identity Flip" sprint (`ARCHITECTURE.md`). DESIGN mode.
> Scope: **UI-only**. Make mounting a World recolor **every** portal page, not
> just `welcome.html`. Reuses `effective_identity()` / `_identity_ctx()` /
> `theme_css()` unchanged — does not touch identity, world-mount, or capability
> logic.
>
> Label key: **[BUILT]** = exists on branch `qukaizen/arail-world-identity-flip`
> today. **[ROADMAP]** = this addendum proposes it.

---

## 0. Problem, grounded in the real code

The prior sprint made identity flip live per-request: `effective_identity()`
resolves `Identity.ui_theme` from the mount sidecar, and `_identity_ctx()`
(`src/arail/portal/app.py:498`) exposes `ui_theme_css = theme_css(ident.ui_theme)`
to templates. **[BUILT]**

But only ONE template consumes it. `welcome.html:7`:

```html
<link rel="stylesheet" href="/static/style.css">
<style id="ui-theme-vars">{{ ui_theme_css|safe }}</style>
```

`theme_css()` emits a `:root { … }` block that, because it comes *after* the
static stylesheet, overrides `style.css`'s `:root` tokens → recolors the page.

The other **22 page templates** (`dashboard.html`, `chat.html`, `admin.html`,
`graph.html`, `agents.html`, `knowledge.html`, `tuning.html`, `docs_hub.html`,
`mission.html`, `plugins.html`, `research.html`, …) link `/static/style.css`
but never inject `ui_theme_css`. They render the static palette regardless of
the mounted World. Verified: `grep -rl ui-theme-vars templates/` → only
`welcome.html`; `grep -rl "</head>" templates/*.html` → 22 files.

**Two independent gaps make "include it in each head" fragile:**

1. Several HTML page routes pass **no** `_identity_ctx()` at all, so even the
   markup wouldn't have a value to inject. Audited handler bodies:

   | Route | `_identity_ctx()` in handler? |
   |---|---|
   | `/skills` (app.py:1965) | **NO** |
   | `/design` (2178) | **NO** |
   | `/blueprints-overview` (2196) | **NO** |
   | `/blueprints-guide` (2211) | **NO** |
   | `/porting-manifest` (2226) | **NO** |
   | `/docs/design.md` (1975), `/docs/INDEX.md` (1982) | **NO** |
   | `/` , `/mission`, `/chat`, `/terminal`, `/notebook`, `/opencode`, `/open-notebook`, `/notebooks`, `/marimo`, `/plugins`, `/integrations/knowledge-canvas`, `/docs`, `/docs/dictionary`, `/autoresearch`+`/research`, `/graph`, `/admin`, `/agents`, `/agents/skills`, `/agents/skills/{id}`, `/knowledge`, `/tuning`, `/docs/{path}` | yes |

2. A newly added page is one forgotten `{% include %}` away from rendering the
   wrong palette, with no failing test to catch it.

---

## 1. Injection mechanism — DECISION: **(b) Starlette/FastAPI middleware**

**Chosen: an `@app.middleware("http")` that injects `<style id="ui-theme-vars">…</style>`
immediately before `</head>` on `text/html` responses.** [ROADMAP]

### Why middleware, not the include partial or the dynamic CSS route

The bar set by the prompt is: *"a newly added page recolors automatically, or
it's a one-line obvious add."* Only the middleware clears it without relying on
author discipline:

- **(a) `{% include "_ui_theme_head.html" %}`** — one markup source of truth,
  but still ~22 edits now AND every future page must remember the include AND
  every page route must remember to spread `_identity_ctx()`. The audit above
  shows 7 routes already forget the context — the same class of omission will
  recur. Rejected: "can be forgotten" is exactly the failure we're removing.
- **(c) dynamic `/static/ui-theme.css` route, linked per template** — same ~22
  link edits and same per-page-forgettable problem; *plus* a caching trap: the
  palette is per-request (flips on mount) but `<link>`'d CSS is cached by the
  browser, so a mount wouldn't recolor an already-open tab without cache-busting
  gymnastics. The prior sprint's whole point was **instant** flip. Rejected.
- **(b) middleware** — **ONE** place, **zero** template edits, **zero** route
  edits. Works on pages that don't pass `_identity_ctx()` because the middleware
  calls `effective_identity()` itself. A new page recolors with no action at
  all. The repo **already has this exact pattern** (`fast_path_meter` app.py:~306,
  `presence_meter` app.py:341) so it is idiomatic here, not exotic.

### The HTML-rewrite fragility, assessed and contained

HTML string-rewriting is the legitimate concern with (b). Containment rules
(all cheap, all in the middleware):

1. **Content-type gate.** Only rewrite when the response
   `Content-Type` starts with `text/html`. JSON, SSE (`text/event-stream`),
   CSS/JS static, file downloads, redirects → untouched.
2. **`</head>` presence gate.** Only rewrite if a `</head>` (case-insensitive)
   exists in the body. Partials/fragments without a head (e.g. `_nav.html`,
   `_graph_canvas.html` rendered as HTMX fragments, the `?preview` graph body)
   are returned unchanged → no double-injection, no broken markup.
3. **Idempotency gate.** Skip if `id="ui-theme-vars"` already present
   (so `welcome.html`, which injects inline, is not double-styled). This lets
   us *optionally* later strip the inline block from `welcome.html`, but we are
   NOT required to — the gate makes the two coexist safely.
4. **First-occurrence only.** Inject before the **first** `</head>` (`str.replace(…, 1)`).
5. **Empty/no-op.** If `ui_theme_css` is empty/falsy, inject nothing (inert).
6. **Streaming responses.** Starlette `StreamingResponse` / `FileResponse` have
   no materialized `.body`; the middleware must read the body iterator. Simplest
   correct approach: gate on content-type first and only buffer `text/html`
   responses (portal HTML pages are small, already fully rendered by Jinja —
   `TemplateResponse` is a plain `Response` with a complete body, not streamed).
   For any response without a readable in-memory body, pass through untouched.

**Perf:** `effective_identity()` + `theme_css()` is the same tiny work the
welcome route already does per request (dict build + a sidecar stat + a ~20-line
string join). `theme_css()` is pure string formatting over a frozen dict — no
I/O, no model calls. One `bytes.decode`/`encode` + one `.replace` on a small
HTML doc per page load. Negligible; the inference scheduler is untouched. Apply
only on the HTML page surface (the content-type gate already excludes the hot
`/api/*` and `/static/*` paths).

### Implementation sketch [ROADMAP]

```python
# app.py — register AFTER presence_meter so it runs in the chain on HTML pages.
_UI_THEME_MARK = 'id="ui-theme-vars"'

@app.middleware("http")
async def inject_ui_theme(request, call_next):
    response = await call_next(request)
    ctype = response.headers.get("content-type", "")
    if not ctype.startswith("text/html"):
        return response
    body = getattr(response, "body", None)
    if not body:                       # streaming / empty → leave alone
        return response
    html = body.decode("utf-8", "ignore")
    low = html.lower()
    if "</head>" not in low or _UI_THEME_MARK in html:
        return response
    css = theme_css(effective_identity().ui_theme)  # reuse [BUILT] resolver
    if not css.strip():
        return response
    block = f'<style id="ui-theme-vars">{css}</style></head>'
    idx = low.index("</head>")
    new = html[:idx] + block + html[idx + len("</head>"):]
    data = new.encode("utf-8")
    response.headers["content-length"] = str(len(data))
    return Response(content=data, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.media_type)
```

(Builder: confirm `Response` import; reset `content-length` as shown — stale
length on a rewritten body is the one correctness trap. Drop `content-encoding`
handling is unnecessary because we sit above any compression that isn't enabled
here; if a compression middleware is later added, register this one inside it.)

> Note: middleware injection makes per-route `_identity_ctx()` **redundant for
> recolor** (the page still needs `brand`/`identity` for its text, so existing
> spreads stay — do NOT remove them). The recolor no longer depends on them.

---

## 2. CSS-variable contract — coverage finding (a real gap)

`style.css :root` (lines 8–72) declares two groups:

- **Base tokens** `theme_css()` DOES emit (the 20 keys in every preset's
  `tokens`): `--bg --surface --surface2 --border --border-hi --text --text-hi
  --muted --green --green-dim --blue --amber --red --purple` + the 4 `--glow-*`.
  These override cleanly. ✅
- **Tokens `theme_css()` does NOT emit:**
  - **Alpha tiers** `--green-a08 … --purple-a28` (15 tokens, lines 34–48).
    **Finding: these are already broken in the static CSS** — each is declared
    self-referentially, e.g. `--green-a08: var(--green-a08);`, which is an
    invalid/cyclic declaration resolving to the guaranteed-invalid value
    (effectively unset). They're consumed widely (`var(--green-a08)` etc.). So
    they don't carry color in the static theme *or* under override — this is a
    **pre-existing bug, not a recolor regression**, and recoloring doesn't make
    it worse. **Out of scope to fix here** (it's not identity work); flag it for
    a separate sprint.
  - **Non-token-driven colors:** many components hard-code `rgba(0,212,255,…)`,
    `rgba(0,255,65,…)`, `rgba(255,176,0,…)` literally (e.g. lines 203–243,
    304, 412, 789, 1043–1047, 1326–1366, …). These are the cyan/green/amber of
    the **default** palette baked in as literals. **They will NOT recolor** —
    they're not `var()`-driven.

**Honest limit to document:** the recolor changes the *structural* palette
(backgrounds, surfaces, borders, text, the primary accent vars, link color,
nav active state — everything driven by the base `var(--…)` tokens). It will
**not** repaint the hard-coded `rgba()` accent glows/decorations. The page will
read as a different World (deep navy → e.g. slate-violet base, different accent
text/links/nav), but stray default-cyan/green glints remain in a few decorated
components.

**Recommendation (sized for the builder, optional polish — ROADMAP):**
- **Required for "visibly recolors":** nothing beyond the middleware — the base
  tokens already cover bg/surface/text/border/primary accent, which is the bulk
  of the visible surface.
- **Optional follow-up (separate sprint, not this one):** sweep `style.css` to
  replace literal `rgba(0,212,255,…)/rgba(0,255,65,…)/rgba(255,176,0,…)` with
  `var(--blue)/var(--green)/var(--amber)` (or fixed the alpha tiers and use
  them). Do NOT do this inside the identity sprint — it's a design-system
  refactor with its own regression surface.

Do **not** extend `theme_css()` to emit the broken alpha tiers — emitting
`--green-a08: <something>` would change the *unmounted* default look (regression
risk against §4) and is the wrong layer to fix the design-system bug.

---

## 3. Visible contrast — DECISION (this is what makes the flip obvious)

**Confirmed problem.** `default_ui_theme()` is `_THEMES[0]` =
`blue-cyan-lab` (`ui_theme.py:149`). The physics fixture's
`face.json:6` has `"palette_hint": "blue-cyan-lab"`. `effective_identity()`
(identity.py:166–171) honors `palette_hint` only when it matches a preset id —
it matches, resolving to… **the same `blue-cyan-lab` as the unmounted default.**

⇒ **Mounting physics today produces a palette identical to unmounted.** Even
with the middleware shipping, "mount physics → colors change" would be visibly
**false**. This must be fixed for the sprint's win condition.

**Chosen fix: give the demo/physics World a contrasting `palette_hint`.**
Change `tests/fixtures/world-bundles/physics/face.json` `palette_hint`
from `"blue-cyan-lab"` to **`"slate-violet"`** (a preset that already exists,
`ui_theme.py:113` — slate base `#0d1018`, violet accent `#9e8cff`, visibly
distinct from the default navy/cyan). [ROADMAP]

Why this over alternatives:
- **vs. changing the default preset** — rejected: §4 forbids regressing the
  unmounted look; `blue-cyan-lab` IS "the default Arail look" (its own
  description). Don't move it.
- **vs. adding a new preset** — unnecessary; `slate-violet`/`emerald-terminal`/
  `night-amber` already give three clearly-distinct contrasts. Reuse.
- This is a **data/fixture change**, not logic — it doesn't touch the resolver
  contract. The resolver already does the right thing once the hint differs.

**State of the world after the fix:**
- **Unmounted (default):** `blue-cyan-lab` — deep navy `#0a0a0f` bg, cyan
  `#00d4ff` accent. **Unchanged from today.** No regression.
- **Mount physics:** `slate-violet` — slate `#0d1018` bg, violet `#9e8cff`
  accent. **Obviously different** background tint + accent/link/nav color across
  every page. That is the demonstrable "mount → whole lab recolors."

> If a real (non-fixture) physics World bundle ships elsewhere, apply the same
> `palette_hint` there. Within this worktree the fixture is the demo surface the
> tests assert against.

---

## 4. Unmounted / fallbacks (regression-safe by construction)

- **Unmounted** → `effective_identity()` returns `_unmounted_identity()` with
  `ui_theme=load_ui_theme()` = `blue-cyan-lab` = today's look. The middleware
  injects the default `:root` block, which equals the static stylesheet's
  values → visually identical to no injection. **No regression.** **[BUILT
  resolver, ROADMAP injection]**
- **Unknown `palette_hint`** → resolver already falls back: `load_ui_theme`
  returns `default_ui_theme()` and the id-match guard (identity.py:170) keeps
  `ui_theme = default` when the hint doesn't resolve. Graceful. **[BUILT]**
- **Empty `ui_theme_css`** → middleware §1 rule 5 injects nothing. Inert. The
  resolver never returns an empty theme (always a full preset), but the guard
  is defense-in-depth for future callers.

---

## 5. Scope / safety

- UI-only. No change to `identity.py`, `world_mount.py`, capability logic, or
  the instant-flip path. The middleware **reuses** `effective_identity()` and
  `theme_css()` verbatim.
- Instant-flip preserved: middleware resolves identity per-request, so a
  mount/unmount between requests recolors the next page load — same liveness the
  welcome route already had, now on all pages.
- Existing per-route `_identity_ctx()` spreads stay (templates still need
  `brand`/`identity` text). Recolor no longer depends on them.
- Perf: see §1 — negligible, off the inference path, content-type-gated away
  from `/api/*` and `/static/*`.

---

## 6. Tests (arail weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression)

All via `TestClient`, autouse `_no_ambient_world_mount` (conftest.py:66) hides
ambient mounts; tests that mount re-`monkeypatch.setattr(world_mount,
"_default_data_dir", …)` in-body (same monkeypatch instance wins). New tests in
`tests/test_ui_theme_recolor.py`. [ROADMAP]

1. **Happy / setup (rendered page carries the palette):** GET `/` (dashboard),
   unmounted → body contains `<style id="ui-theme-vars">` AND the default
   `--bg: #0a0a0f;` / `--blue: #00d4ff;`. Asserts injection fires on a page that
   does NOT inline the block.
2. **Representative page coverage (not just one):** parametrize over a spread of
   the 23 pages crossing the "passes `_identity_ctx()`" boundary —
   `/` , `/chat`, `/admin`, `/graph`, `/agents`, `/knowledge`, `/tuning`,
   **and crucially `/skills`, `/design`, `/blueprints-overview`** (the routes
   that pass NO context) — each must contain the injected `<style id="ui-theme-vars">`.
   This is the test that would have failed under the include-partial approach
   and proves the "can't be forgotten" property.
3. **Mount → recolor (setup/Buddy weight, core win condition):** mount the
   physics fixture (palette_hint now `slate-violet`); GET `/` → body contains
   `--bg: #0d1018;` and `--purple: #9e8cff;` (slate-violet), and does NOT
   contain the default `--bg: #0a0a0f;` inside the injected block.
4. **Unmount → revert (regression):** after unmount, GET `/` → back to default
   `--bg: #0a0a0f;`. Proves liveness + no sticky state.
5. **Idempotency on welcome (regression):** GET `/welcome` → exactly ONE
   `id="ui-theme-vars"` occurrence (middleware's idempotency gate respected the
   inline block). `assert body.count('id="ui-theme-vars"') == 1`.
6. **Non-HTML untouched (regression):** GET a JSON endpoint (`/api/ready`) and a
   static asset → response body unchanged, no `<style` injected, content-type
   preserved.
7. **Security / XSS-safety (security weight):** assert by construction. The
   injected CSS is `theme_css(ui_theme)`, and `ui_theme` is selected from the
   **closed frozen `_THEMES` map** in `ui_theme.py` via `palette_hint`, which
   only *selects a preset id* (identity.py:167–171 requires an exact id/env
   match against the preset table) — raw `face.json` text NEVER flows into the
   emitted CSS. Token values are hardcoded hex/rgba/box-shadow literals authored
   in-repo. Test: build an Identity from a **hostile face** (use
   `tests/fixtures/world-bundles/hostile/`, or a face with
   `palette_hint: "</style><script>alert(1)</script>"`) → mount → GET `/` → the
   injected block contains a real preset's `:root` and contains **no** `<script`
   / no attacker substring; the hostile hint resolved to the default preset.
   Document the conclusion: **the injection is XSS-safe by construction** — a
   `palette_hint` can only pick a preset id; it can never carry markup into the
   page.

Note: do not weaken `_no_ambient_world_mount` — tests 3/4 set their own mount
dir explicitly.

---

## 7. Build order (numbered, done-conditions — zero new decisions)

1. **Fix the contrast (data).** Edit
   `tests/fixtures/world-bundles/physics/face.json`: `palette_hint`
   `"blue-cyan-lab"` → `"slate-violet"`.
   *Done when:* `effective_identity()` on a mounted physics World returns
   `ui_theme.id == "slate-violet"`. **Check existing `test_world_face.py:61`** —
   it asserts physics resolves to `blue-cyan-lab`; update that assertion to
   `slate-violet` in the same commit (it documents the demo palette, not a
   contract). *Don't change any other test's expectation.*

2. **Add the middleware.** In `app.py`, after `presence_meter`, add
   `inject_ui_theme` per §1 sketch. Reuse `effective_identity` + `theme_css`
   (already imported for `_identity_ctx`). Confirm `Response` is importable.
   *Done when:* GET `/` unmounted contains `<style id="ui-theme-vars">` with the
   default `:root`; `content-length` matches the rewritten body; `/api/*` and
   `/static/*` responses are byte-identical to before.

3. **Tests.** Add `tests/test_ui_theme_recolor.py` covering §6 cases 1–7.
   *Done when:* all pass, and the full prior suite (`test_world_identity_flip.py`,
   `test_brand.py`, `test_world_face.py`) stays green.

4. **Manual smoke (optional, no code):** `./arailctl start`, mount physics,
   load `/`, `/chat`, `/admin` → slate-violet base; unmount → default navy.

**Explicitly NOT in this sprint (ROADMAP, separate work):** fixing the broken
self-referential alpha tiers in `style.css`; replacing hard-coded `rgba()`
accent literals with `var()`; stripping the now-redundant inline block from
`welcome.html` (the idempotency gate makes it harmless to leave).

---

## Report summary

- **Mechanism:** FastAPI `@app.middleware("http")` that injects
  `<style id="ui-theme-vars">{theme_css}</style>` before the first `</head>` on
  `text/html` responses. ONE place, zero template/route edits, can't be
  forgotten on a new page; gated by content-type + `</head>`-present +
  idempotency; reuses `effective_identity()`/`theme_css()`. Chosen over the
  include-partial and dynamic-CSS-route options because 7 HTML routes pass no
  identity context and any per-page approach is forgettable + breaks instant
  flip via caching.
- **Surfaces to touch:** exactly two code files — `app.py` (one middleware) and
  `tests/fixtures/world-bundles/physics/face.json` (one field), plus
  `test_world_face.py:61` assertion + a new test file. No template edits.
- **CSS coverage:** base tokens (bg/surface/text/border/4 accents/4 glows)
  override correctly. Two gaps, both **pre-existing, out of scope:** the 15
  alpha-tier vars are self-referentially broken in `style.css`; many accent
  decorations use hard-coded `rgba()` literals. Recolor changes the structural
  palette honestly; stray default-accent glints remain → documented limit.
- **Contrast decision:** default (unmounted) = `blue-cyan-lab` (navy/cyan,
  unchanged). Physics fixture's `palette_hint` currently equals the default ⇒
  invisible flip. Fix = retarget physics `palette_hint` to `slate-violet`
  (slate/violet) — data-only, makes "mount physics → whole lab recolors"
  visibly true without regressing the default look.
- **Build order:** (1) fix fixture palette_hint + its test assertion, (2) add
  middleware, (3) add recolor/XSS tests, (4) optional smoke.
