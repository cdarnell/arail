# Architecture: First-impression experience — one World moment, three doors

**Date:** 2026-07-25
**Spec:** [`EXPERIENCE_SPEC.md`](./EXPERIENCE_SPEC.md) + [`VISION.md`](./VISION.md) (this directory)
**Working tree verified at:** `581d161` (`Move Workbench tab under Admin`), branch `qukaizen/first-impression-spec-404014`
**Mode:** design. No code, template, or script was modified to produce this document.

> Every `file:line` below was re-read first-hand during this design pass, not
> carried over from EXPERIENCE_SPEC.md. Where the spec's anchors were stale or
> wrong, this document says so explicitly and the corrected anchor is binding.

---

## Ground-truth re-verification (read this before trusting EXPERIENCE_SPEC.md)

| EXPERIENCE_SPEC claim | Status | Corrected ground truth |
|---|---|---|
| `welcome_page()` at `app.py:1211-1222`, unconditional 302 when onboarded | ✅ confirmed | verbatim match |
| `onboarding_gate` at `app.py:282-329`; `_lab_password_set()` at `:250-276` | ✅ confirmed | verbatim match; six `@app.middleware("http")` registrations at `:282, :332, :379, :409, :443, :563` |
| Dashboard route at `app.py:1382-1401` | ✅ confirmed | `async def dashboard(request)` at `:1383`, returns `TemplateResponse` at `:1389-1401` |
| `current_mount()` at `world_mount.py:634-645` | ✅ confirmed | `MOUNT_RECORD_NAME = "world-mount.json"` at `:46`; `_write_record` `:648`; `_remove_record` `:660` |
| `reset pkb` leaves `world-mount.json` dangling | ✅ confirmed | `reset_pkb()` at `scripts/reset.sh:187-213` touches `$PKB_DIR` + `$ARAIL_CONVERSATIONS_DIR` only; `reset_data()` `rm -rf "$DATA_DIR"` at `:169`; `reset_full` includes `$DATA_DIR` at `:412` |
| Step 3 swallows every failure and calls `goHome()` | ✅ confirmed | `welcome.html:418-427` (`goHome()` on `!r.ok`, on throw, on empty list) and `:504-509` (`catch (e) { /* fall through */ }` then `goHome()`) |
| Card markup at `welcome.html:462-495` | ✅ confirmed (approx.) | card builder spans `welcome.html:453-512`; swatch/name/tagline only |
| Runbook `localStorage`-dismiss pattern at `dashboard.html:393-411` | ✅ confirmed | `arailRunbookDismissed` key; `dismissRunbookBanner()` at `:406-410` |
| Dashboard World nudge is mission-card-gated | ✅ confirmed | `dashboard.html:1970-1990`; guard `if (!holder || !empty || empty.hidden) return;` at `:1974`; link target `/worlds` at `:1985` |
| **"no new backend fields required" for term count / provenance / categories** | ❌ **WRONG** | The *data* exists on disk (`manifest.provenance_counts` / `provenance_tier`, `spec.categories`) but `WorldInfo` (`world_mount.py:226-256`) exposes only `slug, display_name, path, valid, mounted, reason, theme_preview, tagline`, and `GET /api/worlds` (`app.py:3069-3079`) is a straight `to_dict()` passthrough. **Backend change is required** — see C2. |
| **"nav switcher's existing rows already link correctly" to the swap door** | ❌ **WRONG** | `nav.js:631-890` rows `POST /api/worlds/select` **directly**, with zero confirmation — they *are* the destructive-sweep gap of §0.4, not a fix for it. A new "Change World…" row is required — see C7. |
| "`/dac`'s empty-state buttons" | ⚠️ imprecise | The buttons live in `templates/knowledge/_world_hero.html:58-59` (included by `dac.html:34`), not in `dac.html` |
| `photography` / `physics` untracked on a clean clone | ✅ confirmed | `lab/worlds/` holds `ai, photography, physics, qukaizen`; only `ai` + `qukaizen` are git-tracked |
| `ai` bundle: 339 terms, `mixed` provenance | ✅ confirmed | `provenance_counts = {model: 8, sourced: 331, total: 339}`; `qukaizen` = `{model: 0, sourced: 32, total: 32}`, tier `sourced` |

Two further facts discovered in this pass that the spec did not account for:

- **`DATA_DIR` is bound at import time** in `app.py:31` (`from arail.config import DATA_DIR`). A marker check written as `DATA_DIR / ".world-prompt-seen"` at module scope is **not monkeypatchable** by tests. The codebase already has the correct pattern — re-import inside the handler (`app.py:924-925` does exactly this for `bootstrap_goal.json`). C3 mandates a named helper for the same reason.
- **`inject_ui_theme` (`app.py:443-449`) short-circuits on non-`text/html` content types**, so a 302 from `/` passes through all six middlewares untouched. The redirect is safe; no theme-splice interaction.

---

## Restatement

Today a user who onboards through the CLI (`./arailctl setup` — the *documented* quickstart) never sees the World picker, because the only World-picking UI in the product is Step 3 of the browser welcome flow, which has no URL of its own and sits behind an unconditional `302 → /` for anyone already onboarded. A user who *does* pick a World has their choice silently discarded if the mount is refused, and a returning operator who wants to swap Worlds has no portal path that warns them the swap deletes the previous World's knowledge-base pages. This sprint gives welcome Step 3 an address — `GET /welcome?step=world` — reachable from three doors (in-sequence cold start, a strictly one-shot redirect for CLI-onboarded users gated on a new `lab/data/.world-prompt-seen` marker, and new in-portal "Change World" entry points that render a confirming swap variant), upgrades the step's copy and cards with data the bundles already carry, replaces its swallowed failures with honest on-screen states, ends every path on a dismissible first-win card that points at real measured actions, and fixes the `reset pkb` dangling-mount bug that the marker's re-arm logic depends on.

---

## Assumptions

Numbered so the builder can flag one as false rather than silently working around it.

- **A1 — `_lab_password_set()` is the entire "has this person onboarded" signal.** There are no cookies or sessions. Both the `?step=world` branch and the dashboard nudge key off it and nothing else. If a session model is ever added, both branches must be revisited.
- **A2 — the marker is presence-only.** `lab/data/.world-prompt-seen` is an empty sentinel; nothing reads its contents, mtime, or size. Precedent: `lab/data/goals/bootstrap_goal.json`.
- **A3 — `lab/data/` is writable at request time.** `_write_record` (`world_mount.py:648-650`) already does `data_dir.mkdir(parents=True, exist_ok=True)`; the marker helper does the same. If the write raises, F4 governs.
- **A4 — the marker helper resolves `DATA_DIR` lazily, per call.** Required for testability (see the import-time binding note above) and for `ARAIL_DATA_DIR` overrides.
- **A5 — the server→client boot-flag channel is a Jinja context variable, not a query-string re-read in JS.** `welcome_page()` puts `world_step: true` into the template context; `welcome.html` emits it as a single `<script>window.__ARAIL_BOOT_STEP = "world";</script>` literal (or omits the script entirely). Client JS never parses `location.search` — this keeps the server the sole arbiter of which step renders and avoids a second, divergent precedence rule.
- **A6 — the Step-1 static markup is Jinja-suppressed on the world-step boot path**, not merely overwritten by JS. `showWorldStep()` clears the card with `card.textContent = ''` (`welcome.html:431-432`), which would produce a visible passphrase-form flash if Step 1 rendered first. The template wraps `welcome.html:171-241` in `{% if not world_step %}` and renders a neutral placeholder otherwise.
- **A7 — `showWorldStep()` gains an options object, not more positional params.** Its current signature is `showWorldStep(chosenMode)` (`welcome.html:420`), and on the boot-flag path there is no chosen mode in scope. C4 pins the new signature.
- **A8 — the swap variant learns "a World is mounted" from `GET /api/worlds`'s existing `current` field** (`app.py:3078`), not from a new context variable. One source of truth, already fetched by the step.
- **A9 — one-shot means one *redirect*, not one *view*.** The marker is written before the redirect is constructed; re-visiting `/welcome?step=world` by hand afterwards always works and is never re-marked.
- **A10 — the first-win card's claims stay true only while the CLI keeps staging a default goal.** The card's copy is grounded in `setup.sh`'s default goal + `mini_experiments.py`'s `model_throughput` archetype. If the goal text changes, the card's quoted text must change with it — the builder quotes the *live* `current_goal` where one exists rather than hardcoding the string.
- **A11 — no new dependency, no new endpoint, no route removed.** `GET /welcome` gains a query param; `GET /api/worlds` gains response *fields* (additive, existing consumers unaffected: `nav.js` and `worlds.js` read by key).
- **A12 — quiet boot holds trivially.** Every new check is a local `Path.exists()` / `touch()` inside an already-firing request handler. No probe, no timer, no background task, `ARAIL_AUTOCHECKS` untouched.

---

## Data flow

### Door 1 — cold start, browser (unchanged position, upgraded content)

```
GET /  (no password set)
  └─ onboarding_gate (app.py:282)  → 302 /welcome
GET /welcome
  └─ onboarding_gate: "/welcome" in allowed_prefixes (app.py:305) → pass
  └─ welcome_page (app.py:1212): _lab_password_set() False
       → render welcome.html, world_step = False        [UNCHANGED]
  client: Step 1 form → POST /api/welcome/setup (app.py:1225)
       → showModeStep()   (welcome.html:299)            [copy fix only: "shield badge" → "mode badge"]
       → POST /api/airgap/toggle
       → showWorldStep({mode: chosenMode})              [UPGRADED: C4/C5]
            └─ GET /api/worlds  → cards w/ term count + provenance chip + categories (C2)
            └─ click → POST /api/worlds/select (app.py:3082)
                 200 → goHome()   |   409 mount_refused → honest inline error, grid re-enabled
       → "Skip for now" → GET /
  GET / → dashboard (app.py:1383): marker check (C3) — mounted OR marker present → render
       → first-win card renders (C6), localStorage-gated
```

### Door 2 — cold start, CLI-onboarded (the gap this sprint closes)

```
./arailctl setup   → ARAIL_PASSWORD written, bootstrap goal staged, NO World
GET /
  └─ onboarding_gate: _lab_password_set() True → pass through (app.py:300-301)
  └─ fastpath_meter / … / inject_ui_theme / local_trust_boundary  (untouched)
  └─ dashboard (app.py:1383), FIRST statement in the handler:
        onboarded AND current_mount() is None AND not marker.exists()
          → marker.touch()                          ← write FIRST (guardrail b)
          → RedirectResponse("/welcome?step=world", 302)
        else → existing body from app.py:1384 onward, byte-identical
  └─ inject_ui_theme: content-type is not text/html → passthrough (app.py:447)
GET /welcome?step=world
  └─ onboarding_gate → pass ("/welcome" prefix)
  └─ welcome_page: _lab_password_set() True AND step == "world"
          → render welcome.html with world_step=True, mode=<LAB_MODE>   ← THE NEW BRANCH
        (any other combination → today's 302 to "/", unchanged)
  client: window.__ARAIL_BOOT_STEP == "world" → showWorldStep({mode, boot: true})
        (identical component to Door 1; swap-variant chrome suppressed because
         GET /api/worlds returns current == null)
       → mount 200 → goHome()  |  409 → honest inline error  |  Skip → GET /
GET / → marker now present → dashboard renders → first-win card
```

### Door 3 — swap (new in-portal entry points)

```
nav switcher "◇/◆ … ▾"  → NEW row "Change World…" → href /welcome?step=world   (C7)
/dac empty state         → "Browse Worlds →" retargeted to /welcome?step=world  (C7)
dashboard World nudge    → link retargeted to /welcome?step=world               (C7)
GET /welcome?step=world  → same handler branch as Door 2
  client: GET /api/worlds → current != null
       → swap variant: header names the current World + confirmation banner (C8)
       → card click ⇒ confirm gate ⇒ POST /api/worlds/select
            200 → "what changed" summary, then goHome()
            409 → honest inline error; current World provably unchanged
                  (mount() is verify-first: world_mount.py:1395-1400)
  NOTE: the marker is never written or read on this door — swap is not a nudge.
```

---

## Interface contracts

### C1 — `welcome_page()` — `?step=world` handling (`app.py:1211-1222`)

```python
@app.get("/welcome", response_class=HTMLResponse)
async def welcome_page(request: Request):
    step = (request.query_params.get("step") or "").strip().lower()
    if _lab_password_set():
        if step == "world":
            return templates.TemplateResponse(request, "welcome.html", {
                **_identity_ctx(),
                "current_lab_name": effective_identity().name,
                "world_step": True,
                "lab_mode": <current LAB_MODE string>,
            })
        from fastapi.responses import RedirectResponse       # unchanged path
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "welcome.html", {
        **_identity_ctx(),
        "current_lab_name": effective_identity().name,
        "world_step": False,
        "lab_mode": <current LAB_MODE string>,
    })
```

- **Promises:** 200 + world-step HTML iff (onboarded ∧ `step.strip().lower() == "world"`); 302 → `/` iff (onboarded ∧ that normalized value `!= "world"`); 200 + Step-1 HTML iff not onboarded, **regardless of `step`**.
- **Requires:** nothing new. No middleware ordering change; `onboarding_gate` is untouched.
- **Correction (resolved 2026-07-25, post-build):** an earlier draft of this bullet listed `?step=WORLD` as a "falls through" example, which contradicted the pseudocode above and its own "lowercased" clause in the same sentence — the pseudocode is authoritative and stands as originally written. Casing/whitespace variants of `world` (`WORLD`, `world ` with trailing space, etc.) **do** match and render the World step; this is deliberate (a URL fragment shouldn't be case-sensitively fragile). Genuine bad-input examples that correctly fall through to today's 302: `?step=../`, `?step=mode`, `?step=world&step=x` (repeated param — `query_params.get` returns the *last* value, so this compares `"x" != "world"`). Comparison is never used to index a dict or build a path; `step` is never echoed into the response body. Implemented and tested exactly this way in `tests/test_world_first_impression.py::test_t8_welcome_page_step_matrix`.
- **Non-goal:** `?step=1` / `?step=mode` are **not** implemented. One addressable step only.

### C2 — `WorldInfo` + `GET /api/worlds` — additive fields (`world_mount.py:226-256`, `app.py:3069-3079`)

**This contract exists because EXPERIENCE_SPEC.md's "no new backend fields required" is false.**

```python
@dataclass
class WorldInfo:
    ...                                   # existing fields unchanged
    term_count: Optional[int] = None      # manifest.provenance_counts.total
    provenance_tier: str = ""             # manifest.provenance_tier ("sourced"|"mixed"|...)
    categories: List[str] = field(default_factory=list)  # spec.categories[*].label, first 3
```

- Populated inside the existing `load_bundle` success arm of `list_available_worlds` (`world_mount.py:717-725`) and in the out-of-folder current-mount arm (`:740-752`).
- **Promises:** every field is *optional and best-effort*. Missing/corrupt `spec.json`, absent `provenance_counts`, or a non-int `total` yields `None` / `""` / `[]` — never an exception, never a fabricated number. `list_available_worlds` "never raises" (`:674`) and that stays true.
- **Requires:** `to_dict()` (`:243`) emits the three new keys unconditionally. Existing consumers (`nav.js:631+`, `worlds.js`, `welcome.html`) read by key and are unaffected.
- **Bad input:** `categories` labels are plain strings rendered via `textContent` only — never `innerHTML`, never interpolated into a `style` attribute (`nav.js`'s swatch comment at `:676-678` is the standing precedent for that rule).
- **Truth rule:** the card renders "339 terms · mixed provenance" **only** when `term_count` is a real int; otherwise the chip is omitted entirely. No "—", no "unknown", no guess.

### C3 — marker helper (new, `app.py`, near `_lab_password_set()`)

```python
def _world_prompt_marker() -> Path:
    """Path of the one-shot 'we already offered the World step' sentinel."""
    from arail.config import DATA_DIR          # lazy — matches app.py:924
    return Path(DATA_DIR) / ".world-prompt-seen"

def _world_prompt_pending() -> bool:
    """True iff the one-shot World nudge should fire for this request."""
    # onboarded ∧ no World mounted ∧ marker absent
```

- **Promises:** `_world_prompt_marker()` is pure and side-effect-free; `_world_prompt_pending()` performs at most two `Path.exists()` calls and one `current_mount()` read (itself an `exists()` + small JSON parse, `world_mount.py:634-645`) and **never raises** — any `OSError` is caught and returns `False` (fail-quiet toward "render the dashboard", never toward "redirect").
- **Requires:** module-scope `DATA_DIR` is *not* used. Tests monkeypatch `portal_app._world_prompt_marker`.
- **Bad input:** a `.world-prompt-seen` that exists as a *directory* still satisfies `.exists()` → nudge suppressed. Acceptable and fail-safe (the failure direction is "no nudge", never "redirect loop").

### C4 — dashboard-route conditional (`app.py:1382-1401`)

```python
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    if _world_prompt_pending():
        try:
            _world_prompt_marker().parent.mkdir(parents=True, exist_ok=True)
            _world_prompt_marker().touch(exist_ok=True)     # marker FIRST
        except OSError:
            pass                                            # F4: fall through, render normally
        else:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/welcome?step=world", status_code=302)
    experiments = tracker.list_all()                        # ← existing body, unchanged from here
    ...
```

- **Insertion point is binding:** the very first statement of the handler, *before* `tracker.list_all()` (`:1384`). Placing it later would do the dashboard's full data assembly and then throw it away.
- **Promises:** at most one 302 per lab lifetime per marker generation; the existing render path is byte-identical when the condition is false.
- **Requires:** the handler is only reached post-`onboarding_gate`, so the "onboarded" half of guardrail (d) is structurally guaranteed; `_world_prompt_pending()` re-asserts it anyway (defense in depth, and it keeps the function honest under direct unit test).
- **Bad input / edge:** marker write failing is **not** a reason to redirect (that would be the loop). See F4.
- **Explicitly not done:** no other route gets this check. `/mission`, `/chat`, etc. render normally for an unmounted lab.

### C5 — `showWorldStep()` signature change (`welcome.html:420`)

```js
// was: async function showWorldStep(chosenMode)
async function showWorldStep(opts) {
  // opts = { mode: 'airgapped'|'hybrid'|null, boot: bool }
}
```

- Call sites: `welcome.html:416` (end of Step 2) becomes `showWorldStep({mode: chosenMode, boot: false})`; a new boot block near the bottom of the script does
  `if (window.__ARAIL_BOOT_STEP === 'world') showWorldStep({mode: null, boot: true});`
- The airgapped-flavored intro sentence (`welcome.html:445-447`) renders only when `opts.mode === 'airgapped'`; when the server supplies `lab_mode` on the boot path, the template may seed it — but it is never *guessed*.
- **Bad input:** `opts` undefined → treated as `{}`. No positional-arg back-compat shim is kept; there is exactly one other call site.

### C6 — honest failure states, replacing three `goHome()` calls (`welcome.html:418-427`, `:504-509`)

| Current | Replacement contract |
|---|---|
| `if (!r.ok) { goHome(); return; }` (`:423`) | render catalog-unavailable state: explanatory line + "Skip for now" + a retry link. Never auto-navigates. |
| `catch (e) { goHome(); return; }` (`:426`) | same state, message distinguishes transport failure |
| `if (!worlds.length) { goHome(); return; }` (`:427`) | "no Worlds found in this lab" state + `✦ Forge your own…` + skip |
| `catch (e) { /* fall through */ } goHome();` (`:504-509`) | branch on status: **200** → success path (goHome, or "what changed" on the swap door); **409** → render `message` from the response body verbatim-but-escaped, re-enable the card grid; **4xx/5xx other** → generic honest failure + re-enable; **throw** → transport failure + re-enable. `goHome()` is called **only** on a confirmed 200. |

- **Promise:** the user is never navigated away as if a mount succeeded when it did not.
- **Requires:** the response body's `message` (`app.py:3145-3148`) is rendered with `textContent`, never `innerHTML`.
- **Guarantee under 409:** `mount()` is verify-first (`world_mount.py:1395-1400`) — nothing on disk changed, so "nothing was mounted" is a *true* statement, not a hopeful one.

### C7 — swap-door entry points (three link retargets + one new row)

| Surface | Anchor | Change |
|---|---|---|
| `/dac` empty state | `templates/knowledge/_world_hero.html:58` | `href="/worlds"` → `href="/welcome?step=world"` on the primary button. The `Forge your own` ghost button (`:59`) **stays** pointed at `/worlds`. |
| dashboard nudge | `dashboard.html:1985` | `link.href = '/worlds'` → `'/welcome?step=world'`; link text unchanged |
| nav switcher | `nav.js` `render()` (`:689+`) | **New first row, "Change World…", an `href` navigation to `/welcome?step=world`.** The existing per-World rows keep their direct-`POST` behavior for this sprint (changing them is out of scope and would touch the switcher's whole action dispatch) — but they are now no longer the *only* door, and the new row is the one the empty/default state highlights. This is a deliberate, documented partial fix; see Tech debt D3. |

- **Routes are unchanged.** `/worlds`, `/dac`, `/api/worlds*` all keep their paths and methods. Only `href` targets and one added row.

### C8 — swap-variant confirmation (`welcome.html`, inside `showWorldStep`)

- **Trigger:** `GET /api/worlds` response has `current !== null`.
- **Renders:** header naming the current World (`display_name` of the entry whose `mounted === true`), plus a banner whose text is drawn only from EXPERIENCE_SPEC §0.4's verified "what a mount really changes" table: knowledge-base re-stock, the previous World's staged pages being removed, agent focus/vocabulary, dictionary replacement, and the look. It states explicitly that the sealed bundle itself is never deleted (true: `_sweep_other_worlds`, `world_mount.py:1280-1309`, sweeps `pkb/sources/world-*`, not `lab/worlds/`).
- **Gate:** a card click in this variant does **not** mount. It reveals a Continue / Cancel pair; only Continue issues `POST /api/worlds/select`. Cancel restores the grid. One confirmation, not two.
- **On 200:** a "what changed" summary (theme, agent focus/vocabulary, knowledge base) replaces the first-win card for this door, then the user proceeds home.
- **Contract boundary:** the confirmation is a *client-side* affordance on this surface. It does not, and must not, become a server-side precondition on `POST /api/worlds/select` — the CLI and `/worlds` remain unguarded by it, which is honestly noted in Tech debt D3.

### C9 — first-win card (`dashboard.html`)

- Markup mirrors the runbook banner (`dashboard.html:385-411`) exactly: hidden by default, revealed by an IIFE unless `localStorage['arailFirstWinDismissed'] === '1'`, dismissed by a `✕` that sets the key. `try/catch` around every `localStorage` access, defaulting to *shown* on throw — same as `:398-402`.
- **No backend flag.** No new context variable, no marker read on the dashboard render path.
- **Copy contract:** quotes the live `current_goal` (already in the dashboard context, `app.py:1394`) when present; falls back to a goal-agnostic sentence when absent. Names ▶ Run in Autoresearch as the measured-but-slow path and one chat message as the seconds-scale path (`chat.html:3107-3109` provenance popover). **No numbers appear in this card** — it points at where real numbers will be produced; it never previews them.

### C10 — `scripts/reset.sh` `pkb` scope (`reset_pkb()`, `:187-213`)

Inserted after the conversations-override block (`:211`), before the closing `info` (`:212`):

```sh
    # A World's staged pages live under $PKB_DIR/sources/world-<slug>/ and were
    # just deleted; leaving lab/data/world-mount.json behind would advertise a
    # World whose knowledge base no longer exists. Drop the pointer, and re-arm
    # the one-shot World prompt so the next boot offers the picker again.
    rm -f "${DATA_DIR}/world-mount.json" 2>/dev/null || true
    rm -f "${DATA_DIR}/.world-prompt-seen" 2>/dev/null || true
```

- **Promises:** idempotent; silent when the files are absent; `$DATA_DIR` is the script's already-resolved variable (`:89`, honoring `ARAIL_DATA_DIR` via `_resolve_data_dir` `:73-74`) — no hardcoded path.
- **Requires:** nothing. `reset_pkb`'s early `return` when `$PKB_DIR` is absent (`:194-197`) means these lines don't run for a lab with no PKB — acceptable: with no PKB there is also no staged World content, and a mount pointer without staged content is exactly the state `reset data` handles.
- **Unchanged:** `reset data` (`:165-170`) and `reset full` (`:412`) already `rm -rf "$DATA_DIR"`, which removes both files for free. `models`, `pkb-seeds`, `program`, `skills`, `plugins`, `env`, `destroy`, `stop`: no change, no behavior drift.

---

## Failure modes

Every row has a test in the strategy below; the ID is the cross-reference.

| # | Failure | Detection | Recovery |
|---|---|---|---|
| **F1** | Redirect loop: `/` → `/welcome?step=world` → `/` → … | `TestClient(follow_redirects=False)` asserting exactly one 302 across two consecutive `GET /` calls (T4/T5) | Structural: marker written *before* the redirect response is constructed (C4). The second `GET /` sees the marker and renders. |
| **F2** | Nudge fires for a non-onboarded user | Truth-table test T1 | Structural: `onboarding_gate` (`app.py:300`) redirects before the handler runs; `_world_prompt_pending()` re-checks `_lab_password_set()`. |
| **F3** | Nudge fires while a World is mounted (would look like data loss to a returning operator) | T2 | `current_mount() is None` is a hard conjunct in `_world_prompt_pending()`. |
| **F4** | **Marker write succeeds, redirect never reaches the client** (client aborts, proxy drops) | T5 (marker present after a redirect the client never followed) | By design the user lands on a normal dashboard. They lose the *automatic* nudge but keep three manual doors (nav row, `/dac`, dashboard nudge). Chosen deliberately: a lost nudge is strictly better than a loop. |
| **F5** | **Marker write fails (read-only / full disk), redirect fires anyway** → infinite loop | T6 (monkeypatched `touch` raising `OSError`) | C4's `try/except/else`: the redirect lives in the `else` arm. A failed marker write means **no redirect at all** — dashboard renders normally. |
| **F6** | Concurrent `GET /` requests race on the marker check (browser prefetch, two tabs, duplicate reload) | T7 (two concurrent `TestClient` gets) | `touch(exist_ok=True)` is idempotent; the worst case is two 302s to the same idempotent page, both of which then find the marker. No corruption, no loop, no double-mount — the redirect target performs no writes. |
| **F7** | `GET /api/worlds` errors or returns `[]` exactly when the one-shot redirect just fired — the user is stranded on a page whose whole purpose failed | T12/T13 | C6's catalog-unavailable state: explains, offers retry + "Skip for now" + `/worlds` forge. The marker is already written, so the user is never re-thrown at this page. Explicit non-behavior: the client does **not** auto-`goHome()` and does **not** un-write the marker. |
| **F8** | Mount refused (409 `mount_refused`, seal/schema/category failure) but the UI navigates home as if it worked | T14 | C6: `goHome()` only on 200; 409 renders the server's `message` and re-enables the grid. `mount()`'s verify-first ordering guarantees disk is untouched. |
| **F9** | Partial mount failure *mid-flow* (stage succeeds, index or catalog-adopt fails after the pointer write) | T15 (`monkeypatch` the post-pointer best-effort steps to raise) | Pre-existing `mount()` contract: the pointer is written **last** (`world_mount.py:1426`) and steps 6+ are best-effort by design. The UI reports the 200 it received; the lab is genuinely mounted. This sprint does not change that ordering and must not paper over it — the "what changed" summary (C8) states what was *swapped*, never claims sidecar success it cannot observe. |
| **F10** | Reset scope runs mid-flight (user runs `reset pkb` in a terminal while the World step is open) | T9/T10 (script-level), plus manual step in the live pass | `current_mount()` and the marker are both re-read on the *next* request; there is no cached state. A stale open page's mount click either succeeds (bundle in `lab/worlds/` is untouched by `reset pkb`) or 409s honestly. C10 ensures the pointer/marker are consistent afterwards. |
| **F11** | Dangling mount after `reset pkb` (pointer says mounted; KB is gone) — pre-existing bug this design depends on being fixed | T9 | C10 removes `world-mount.json` and the marker together, so the next boot both reports "no World" *and* re-offers the picker. |
| **F12** | Step-1 passphrase form flashes before the World step paints on the boot path | Visual, caught by the live/screenshot pass (T18) | A6: `{% if not world_step %}` suppresses the Step-1 block server-side. |
| **F13** | XSS via World-supplied strings newly surfaced on the card (`display_name`, `tagline`, category labels, 409 `message`) | T16 (a bundle whose `display_name` contains `<img src=x onerror=…>`) | All new text nodes use `textContent`; no `innerHTML` in the welcome step (today's code at `:465-500` already follows this — the new fields must not break the pattern). `theme_preview` hex values keep the existing `HEX6` regex gate (`welcome.html:294`). |
| **F14** | Path traversal / injection via `?step=` | T3 | Exact string comparison only; never used in a path, a template name, or a redirect target. Never echoed to the page. |
| **F15** | `list_available_worlds` starts raising because of the new manifest/spec reads | T11 (bundle with truncated `spec.json` / missing `provenance_counts`) | C2: per-field `try/except` inside the already-`except`-wrapped per-directory loop; missing data → field omitted, card chip omitted. "Never raises" (`world_mount.py:674`) is preserved. |
| **F16** | Fabricated term counts / provenance shown for a bundle that doesn't declare them | T11 asserts *absence* of the chip, not a placeholder | Truth-in-UI: no `—`, no `0`, no "unknown". Omit. |
| **F17** | Marker file leaks into git or into a user's backup expectations | T17 (`git status --porcelain` clean after `touch`) | `lab/` is git-ignored except contracts; the dotfile name matches the existing ignore posture. Builder verifies rather than assumes. |
| **F18** | Swap confirmation is bypassed (Enter key, double-click, rapid clicks) | T14b | The confirm gate replaces the grid's click handler state; card buttons are disabled the moment the confirm pair renders, and re-enabled only on Cancel or a terminal failure. |

---

## Test strategy

New file: **`tests/test_world_first_impression.py`** (portal `TestClient` cases, T1–T8, T11–T16), extending existing conventions in `tests/test_onboarding.py`, `tests/test_world_switcher.py`, and `tests/test_world_reset.py`. Reset-script cases join **`tests/test_world_reset.py`** (T9/T10). `tests/conftest.py`'s session `.env` isolation is reused as-is; the marker is redirected by monkeypatching `portal_app._world_prompt_marker` to a `tmp_path` (A4/C3), and `current_mount` by monkeypatching the name the dashboard handler resolves.

### Unit / integration — the §1.2 truth table, one test per row

| ID | Onboarded | World mounted | Marker | Expected |
|---|---|---|---|---|
| **T1** | No | — | — | `GET /` → 302 `/welcome`; `GET /welcome?step=world` → **200 Step-1 HTML** (param ignored, not a 302); marker **not** created |
| **T2** | Yes | Yes | absent | `GET /` → 200 dashboard; marker still absent (never written on the mounted path) |
| **T3** | Yes | No | present | `GET /` → 200 dashboard |
| **T4** | Yes | No | absent | `GET /` → 302 `/welcome?step=world`; marker exists afterwards |
| **T5** | Yes | No | absent | **two sequential** `GET /` (no redirect following) → first 302, second **200** — F1/F4 |

Additional handler cases:

- **T6** — `_world_prompt_marker().touch` monkeypatched to raise `OSError` → `GET /` returns **200**, never a 302 (F5).
- **T7** — two concurrent `GET /` from threads with the marker absent → no exception, marker exists once, at most two 302s, and a third sequential `GET /` is 200 (F6).
- **T8** — `welcome_page` matrix: onboarded + `?step=world` → 200 with the world-step boot flag in the body; onboarded + no param → 302 `/`; onboarded + `?step=mode`, `?step=WORLD`, `?step=../../etc/passwd`, `?step=world&step=x` → all 302 `/` except the exact lowercase match; the raw param value never appears in any response body (F14).

### Reset-script tests (shell, `tests/test_world_reset.py` style)

- **T9** — `reset pkb` against a fixture lab with `$PKB_DIR`, `world-mount.json`, and `.world-prompt-seen` present → PKB gone, **both** `lab/data/` files gone, everything else in `lab/data/` untouched (F11, C10).
- **T10** — `reset pkb` with neither file present → exit 0, no error output (idempotence); and `reset models` / `reset plugins` leave both files present (no scope drift).

### World-catalog contract tests

- **T11** — `list_available_worlds` over three fixture bundles: one complete (`term_count == 339`-shaped, tier, ≥1 category), one with `spec.json` truncated, one with `provenance_counts` missing → no exception; missing fields are `None`/`""`/`[]`; `to_dict()` always carries the three keys (F15/F16).
- **T12** — `GET /api/worlds` response shape includes the new keys and the existing keys unchanged (regression guard for `nav.js`/`worlds.js`).

### Client-behavior tests (`tests/js/`, following the existing DOM-harness pattern used by `test_airgap_modal_dom.py`)

- **T13** — catalog fetch returns 500 / `{worlds: []}` → the rendered card contains the explanatory empty state and a skip affordance, and `window.location` is **not** assigned (F7).
- **T14** — select returns 409 with a `message` → the message text appears, the grid is re-enabled, `goHome()` was not called (F8). **T14b** — the swap variant requires an explicit Continue before any `POST` fires, and rapid double-click issues at most one request (F18).
- **T15** — select returns 200 → exactly one navigation to `/`; on the swap door, the "what changed" summary renders first and claims only theme/agent-focus/knowledge-base (F9).
- **T16** — a World whose `display_name`/`tagline`/category label contains `<script>` / `onerror=` markup renders as literal text; no element is created from `innerHTML` (F13).

### Regression

- **T17** — `git status --porcelain` is clean after the marker is touched inside a repo-rooted `lab/data/` (F17).
- Existing suites must stay green untouched: `test_onboarding.py`, `test_world_switcher.py`, `test_world_mount.py`, `test_world_reset.py`, `test_default_worlds_catalog.py`, `test_autochecks_boot.py` (quiet-boot guard — proves no new probe was introduced).

### Security

- Covered above: F13 (T16), F14 (T3/T8), plus an explicit assertion that `POST /api/worlds/select`'s CSRF envelope (`app.py:3110-3121`) is unchanged and still rejects `sec-fetch-site: cross-site` — the new doors add no new mutation endpoint and must not weaken this one.
- No secrets surface is touched; `secrets.env` handling is untouched; no new egress (the entire flow reads local files, consistent with airgapped-default).

### Performance

Not a hot path, but bounded: the dashboard's new pre-check adds at most two `stat()` calls and one small JSON parse per `GET /`, and short-circuits on the first false conjunct. No benchmark required; the acceptance bar is "no new I/O on the mounted-World steady state" — which holds, because `current_mount()` returning non-`None` ends the check.

### Live / screenshot verification (brief's Phase 3)

Run on fresh local state, capturing a screenshot per step:

1. **Cold start, browser** — wipe `.env` password + `lab/data/` → `/` → Step 1 → Step 2 → Step 3 with the new explainer, concept-teaching strip, and enriched cards → mount `ai` → dashboard shows the first-win card once, and not after dismissal + reload.
2. **Cold start, CLI-onboarded** — password set, no mount, no marker → `/` lands directly on the World step with **no Step-1 flash** (F12) → Skip for now → dashboard → reload → **no second redirect**.
3. **Swap** — with `ai` mounted, use each of the three doors (nav "Change World…", `/dac`, dashboard nudge when it fires) → confirmation banner names the current World → Cancel restores the grid → Continue swaps → "what changed" summary is accurate against the mounted state.
4. **Failure honesty** — temporarily corrupt a bundle's seal → the 409 message is visible on screen and the previously-mounted World is provably still mounted.
5. **Reset re-arm** — `./scripts/reset.sh pkb` → confirm both `lab/data/` files gone → next `GET /` re-offers the World step exactly once.

---

## Tech debt

**Repaid**

- R1 — `reset pkb`'s dangling `world-mount.json` (gap #6, first half): fixed (C10).
- R2 — welcome Step 3's three silent `goHome()` failure paths (gap #4): fixed (C6).
- R3 — zero-confirmation destructive World swap, on the portal's *new* primary door (gap #5): fixed for the welcome door (C8); see D3 for the remainder.
- R4 — the CLI-onboarded user's total inability to reach the World picker (gap #1): fixed (C1 + C4).
- R5 — the mission-card-gated nudge that hid itself from exactly the users who needed it (gap #3): superseded by a redirect that does not depend on mission-card state.
- R6 — "shield badge" copy for a badge that is a filled circle (part of gap #9): fixed in welcome copy.
- R7 — `/api/worlds` finally exposing the term-count / provenance / category data the bundles have carried all along (partial gap #7) — reusable by the switcher and `/worlds` later.

**Added**

- D1 — **a new persistent state file** (`lab/data/.world-prompt-seen`) whose lifecycle is now coupled to `reset.sh`. Any future reset scope that removes `world-mount.json` must also consider the marker. Mitigation: the two files are removed adjacently in `reset_pkb` with a comment explaining the coupling.
- D2 — **`?step=world` is a one-off addressing scheme**, not a general step router. If Step 2 ever needs an address, this branch becomes a precedence problem. Deliberate: a general router is unjustified for one step.
- D3 — **the swap confirmation is client-side and door-specific.** `arailctl world swap`, `/worlds`, and the nav switcher's direct per-World rows still mount without confirmation. The destructive sweep is unguarded at the API layer, exactly as today. Follow-up: either a server-side `confirm: true` requirement on `POST /api/worlds/select`, or routing all portal doors through the welcome component.
- D4 — **welcome.html's inline `<script>` grows** with the boot flag, the confirm gate, and the failure states. It is already the largest inline script in the template set. Follow-up: extract to `static/js/welcome-world.js` once it stabilizes — deferred here because extraction mid-change would obscure the diff.
- D5 — **two dismiss keys in `localStorage`** with the same hand-rolled pattern (`arailRunbookDismissed`, `arailFirstWinDismissed`). Third occurrence should become a helper.
- D6 — **the first-win card's copy is coupled to `setup.sh`'s default goal text** (A10). Mitigated by quoting the live goal, but the fallback copy can still drift.

**Net:** negative (debt repaid exceeds debt added). D1 and D3 are the two that will need a home; both are named as follow-ups below rather than left implicit.

**Explicitly deferred, carried forward from EXPERIENCE_SPEC §1.5 and the gap list — not regressions of this sprint:**

- `setup.sh`'s `LAB_INTENT` 9-option taxonomy vs. the Worlds model (gap #2). Unreconciled by design; the `?step=world` route this sprint creates is the prerequisite that makes a future one-line CLI-banner patch possible.
- `reset data` orphaning `pkb/sources/world-*/` staged pages (gap #6, second half) — does not affect marker or redirect correctness.
- `face.json`'s stale "331 sourced terms" tagline on the `ai` bundle; `photography`'s placeholder tagline (gap #9). Note the interaction: this sprint's new chip renders **339** from `provenance_counts.total` while the tagline text may still say 331 — the chip is the truthful number, and the tagline is authored copy. The builder should not "fix" the discrepancy by suppressing the chip.
- `/worlds` having no nav link; the three pickers showing three different amounts of information (gap #7) — C2 makes the richer data available to all three, but only welcome consumes it here.
- All 15 declared World capabilities reporting `declared_unavailable`; the research empty state conflating the two experiment loops; `reset.sh`'s missing `ARAIL_EXPERIMENTS_DIR` handling.
- No new World bundles. Photography / Advanced Biology / Video Games appear **only** as explicitly-labeled examples in the concept-teaching strip, and any of them that *is* present in `GET /api/worlds` renders as a real card with its prose line dropped (no double-telling). Video Games in particular must not be described as shipped, and its Layer B/C measured-optimization story must be framed as the existing `mini_experiments` pattern applied to a new domain — not as built.

---

## Recommended implementation order

Each step is an atomic, locally-verified commit. Steps 1–2 are independently shippable and de-risk the rest.

1. **`reset.sh` `pkb` scope + T9/T10.** Pure bug fix (R1/F11), zero coupling to the rest. Ships alone.
2. **`WorldInfo` + `/api/worlds` additive fields + T11/T12** (C2). Backend-only, additive, no UI consumer yet. This is the step EXPERIENCE_SPEC.md did not know was needed — do it before any card work.
3. **Marker helper + dashboard conditional + T1–T7, T17** (C3/C4). The loop-safety core. Verify the truth table green before any template work.
4. **`welcome_page()` `?step=world` branch + boot flag + Step-1 suppression + T8** (C1/A5/A6). Route now addressable; the page still renders today's Step 3.
5. **Step 3 upgrade: explainer, concept strip, enriched cards, honest failure states + T13/T14/T15/T16** (C5/C6). The largest single slice; split into copy-and-cards vs. failure-states if the diff gets unwieldy.
6. **Swap variant: confirmation banner + "what changed" summary + T14b** (C8).
7. **Swap doors: `_world_hero.html`, dashboard nudge, nav "Change World…" row** (C7). Last, so every door points at a component that is already complete and honest.
8. **First-win card** (C9).
9. **Full live/screenshot pass** (T18 scenarios 1–5), then update `CHANGELOG.md`.

Gate before step 7: steps 3–6 green under `pytest tests/test_world_first_impression.py tests/test_world_reset.py tests/test_onboarding.py tests/test_world_switcher.py`. No door should be opened onto an unfinished room.
