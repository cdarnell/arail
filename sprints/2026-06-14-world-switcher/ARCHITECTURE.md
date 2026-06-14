# ARCHITECTURE — World switcher (catalog + UI)

Sprint: `2026-06-14-world-switcher` · Repo: `arail-verify` · Branch: `qukaizen/arail-world-switcher`
Persona: architect (DESIGN mode). Builder implements this with **zero new decisions**.

> Thesis: ARAIL loads **Worlds** like aerollm loads LLMs. The loader primitives
> (`world_mount.mount`/`unmount`/`current_mount`/`swap`) are merged and stable.
> This sprint adds the **catalog** (scan `lab/worlds/`) + the **UI** (nav dropdown)
> so a user loads/unloads a World from the portal — no CLI.

Every seam below is grounded in the merged code. Line references are to the tree at design time.

---

## 0. Findings (read these before building)

### F1 — `WORLDS_DIR` (config)
`src/arail/config.py` resolves runtime paths with `_resolve(env_key, default_rel)`
(lines 42–46) and assigns `MODELS_DIR = _resolve("ARAIL_MODELS_DIR", str(LAB_ROOT / "models"))`
(line 71). **Add `WORLDS_DIR` the identical way:**

```python
WORLDS_DIR = _resolve("ARAIL_WORLDS_DIR", str(LAB_ROOT / "worlds"))
```

Place it immediately after `MODELS_DIR` (line 71). Default `lab/worlds/`. No directory is
created at import time (mirrors `MODELS_DIR` — none of the `_resolve` paths are `mkdir`'d at import).

### F2 — swap vs unmount+mount (THE switch-semantics decision)
`mount()` (world_mount.py:697) and `swap()` (world_mount.py:804) are **functionally
identical for the switch case**: both (1) `load_bundle` → `verify_seal` → `check_compat`
→ `check_categories` and **refuse before touching disk** on any failure, (2) `_stage_files`
(atomic `.staging-<slug>/` → `world-<slug>/` rename), (3) index best-effort, (4) `_write_record`
LAST via atomic temp+`os.replace` (world_mount.py:521–531), overwriting any prior record,
(5) resolve capabilities sidecar best-effort. `swap`'s only extra is a docstring promise
("old world stays on failure"), which `mount` **also** satisfies because the seal/compat/category
checks run before `_stage_files` and before `_write_record`.

**DECISION: the switcher calls `world_mount.mount(bundle_dir, ...)` for every World
selection (A→B included), and `world_mount.unmount(...)` for "default".**
- Rationale: `mount` is the documented public switch; it overwrites the record atomically,
  re-stages the new World's KB into `pkb/sources/world-<slug>/`, and re-resolves the
  capabilities sidecar — exactly the staged-KB + sidecar + capabilities update the brief
  requires. Using `mount` (not `swap`) keeps one code path for both first-mount and
  switch; there is no behavioral gap. **Do not call `swap`** — it adds nothing here and
  is a second path to test.
- A→B leaves no stale stage: B's terms live in `pkb/sources/world-B/`. A's `pkb/sources/world-A/`
  dir is **not** removed by `mount(B)` (mount never touches other worlds' staged dirs), but A is
  no longer the current mount, so identity/dictionary/curator all read B. That residual `world-A/`
  dir is inert staged DATA, indexed but not "current". This matches existing `swap` behavior and
  is acceptable (the brief's "no stale stage" = the *current* lab is fully B; confirmed). We do
  **not** add cleanup of the prior world's stage in this sprint (ROADMAP note below).
- Failure atomicity: a seal/partial/schema/category failure in `mount(B)` raises **before**
  `_write_record`, so the current World (A, or default) is unchanged. Confirmed atomic.

### F3 — discovery does NOT exist yet
`world_mount.py`'s CLI `list` (`_cmd_list`, line 935) only prints the **currently mounted**
record via `current_mount` — it does **not** scan a folder. There is **no** `lab/worlds/`
scanner. **We add a new `list_available_worlds(worlds_dir)`** (§1).

### F4 — identity flips per request; post-switch UX = full page reload
`effective_identity()` (identity.py:90) reads `current_mount(data_dir)` with **no cache** and
re-derives name/logo/theme/intent/framing every call. `_identity_ctx()` (app.py:585) spreads
`brand`/`ui_theme`/`ui_theme_css`/`identity` into every page's template context per request.
The recolor middleware + World badge + dictionary all re-resolve on the next request.
**DECISION: after a successful `POST /api/worlds/select`, the nav JS does
`window.location.reload()`.** Simplest and correct — the next GET re-runs `_identity_ctx()`,
recolors, and rebuilds the badge + dropdown active marker. No live DOM patching (ROADMAP).

### F5 — framework + endpoint idiom
The portal is **FastAPI/Starlette** (not Flask), `@app.get`/`@app.post` with `async def`,
`request: Request`, returning dicts (auto-JSON) or `JSONResponse(status_code=…, content=…)`.
Mirror `post_airgap_toggle` (app.py:8510) for the POST: bind-loopback gate, `Sec-Fetch-Site`
+ Origin CSRF checks, `_err(code, body)` helper, body parsed via `await request.json()`.

### F6 — slug path-jail primitive already exists
`world_mount._SLUG_RE = ^[a-z0-9][a-z0-9-]*$` (world_mount.py:96) — no dots, no slashes, no
`..`. `load_bundle` re-validates `manifest.world` against it (lines 200–209) and raises
`SlugInvalid`. We reuse `_SLUG_RE` for the select endpoint's slug→dir jail (§2).

### F7 — test wiring
Autouse `_no_ambient_world_mount` (conftest.py:67) monkeypatches `world_mount._default_data_dir`
to a clean tmp dir so no ambient mount leaks. Tests that mount re-`monkeypatch.setattr(wm,
"_default_data_dir", lambda: data_dir)` (test_world_identity_flip.py:45) and build
`TestClient(portal_app.app)`. Fixtures live at `tests/fixtures/world-bundles/{physics,tampered,
hostile,world-caps-both,world-caps-stt,world-no-caps}/`, each a full 7-file bundle. `physics` is
a valid sealed bundle; `tampered` has a broken seal.

---

## 1. Catalog discovery — `list_available_worlds`

**Location:** new function in `src/arail/world_mount.py` (keeps World logic in one module;
reuses `load_bundle`, `_SLUG_RE`, `current_mount`, `MountRecord`). Add a `WorldInfo` dataclass
beside `MountRecord`.

```python
@dataclass
class WorldInfo:
    slug: str            # manifest.world (validated) or dir name if unreadable
    display_name: str    # manifest.display_name, else slug
    path: str            # absolute path to the bundle dir
    valid: bool          # passed light validation (see below)
    mounted: bool        # this slug == current_mount().world
    reason: str = ""     # when valid is False: short operator-facing why

    def to_dict(self) -> Dict[str, Any]:
        return {"slug": self.slug, "display_name": self.display_name,
                "path": self.path, "valid": self.valid,
                "mounted": self.mounted, "reason": self.reason}
```

```python
def list_available_worlds(
    worlds_dir: Path | None = None,
    *,
    data_dir: Path | None = None,
) -> List[WorldInfo]:
    ...
```

**Behavior (exact):**
1. Resolve `wd = worlds_dir or _default_worlds_dir()` where `_default_worlds_dir()` imports
   `from arail.config import WORLDS_DIR` and returns it (mirror `_default_data_dir`,
   world_mount.py:486–488). Add `_default_worlds_dir()` next to it.
2. If `wd` does not exist or is not a directory → return discovery of just the current mount
   (step 6) — i.e. an empty scan, **no crash, no mkdir**.
3. `current = current_mount(data_dir)` once, up front. `current_slug = current.world if current else None`.
4. For each **immediate subdirectory** `d` of `wd` (sorted by name; ignore files and dotdirs):
   - **Light validation** (NOT a full seal): call `load_bundle(d)` inside try/except.
     - `load_bundle` already parses `manifest.json`, validates the slug against `_SLUG_RE`,
       reads all 6 siblings, and runs cross-file slug consistency. This is "well-formed bundle"
       without a sha256 verify of every file → cheap enough for a list call. The full
       `verify_seal` runs only at mount (§2). **Do NOT call `verify_seal` here.**
     - Success → `WorldInfo(slug=bundle.slug, display_name=bundle.manifest.get("display_name",
       bundle.slug), path=str(d.resolve()), valid=True, mounted=(bundle.slug==current_slug))`.
     - `load_bundle` raised `PartialBundle`/`SlugInvalid`/`Exception` → `WorldInfo(slug=d.name,
       display_name=d.name, path=str(d.resolve()), valid=False, mounted=False,
       reason=getattr(e, "user_message", str(e))[:200])`. **List it disabled, do not skip.**
5. **De-dupe by slug:** if two valid dirs share a slug, keep the first (sorted order) and mark
   the rest `valid=False, reason="duplicate slug <slug>"`.
6. **Include the currently-mounted World even if not in `lab/worlds/`** (e.g. CLI-mounted by
   absolute path): if `current_slug` is set and no `WorldInfo` in the list has
   `mounted=True`, append `WorldInfo(slug=current.world, display_name=<manifest display_name
   from current.bundle_dir if readable else current.world>, path=current.bundle_dir, valid=True,
   mounted=True, reason="")`. Resolve its display_name best-effort by reading
   `Path(current.bundle_dir)/"manifest.json"` (same idiom as identity.py:115–123); on any error
   fall back to `current.world`.
7. Return the list. Order: scanned worlds (sorted by display_name, case-insensitive), then the
   appended out-of-folder current (if any).

**Never raises.** Wrap the per-dir work; a single bad dir cannot abort the scan. A failure to
resolve `WORLDS_DIR` or read the dir returns the current-only / empty list.

---

## 2. Endpoints (in `src/arail/portal/app.py`)

Place both near the World/dictionary endpoints (after the `_world_mounted_dict_response`
block, ~line 2667) so World code is co-located. Both are **async**, airgap-safe (local files
only, no network).

### 2a. `GET /api/worlds`
```python
@app.get("/api/worlds")
async def api_worlds_list():
    from arail.world_mount import list_available_worlds, current_mount
    worlds = [w.to_dict() for w in list_available_worlds()]
    rec = current_mount()
    return {"worlds": worlds, "current": rec.world if rec else None}
```
- Shape: `{"worlds": [WorldInfo.to_dict(), ...], "current": "<slug>"|null}`.
- `current` is `null` when the default lab is active (no mount).
- Uses default `WORLDS_DIR`/`data_dir` so tests' `_default_data_dir`/`_default_worlds_dir`
  monkeypatches apply (see §7).

### 2b. `POST /api/worlds/select`
Mirror `post_airgap_toggle` (app.py:8510) for the security envelope. Body:
`{"slug": "<slug>"}` OR `{"path": "<abs path>"}` OR `{"slug": "default"}` (or `{"default": true}`).

```python
@app.post("/api/worlds/select")
async def api_worlds_select(request: Request):
    from fastapi.responses import JSONResponse
    from arail.world_mount import (
        mount, unmount, current_mount, _SLUG_RE, _default_worlds_dir,
        SealMismatch, PartialBundle, SchemaSkew, GateViolation, SlugInvalid,
    )
    def _err(code, body): return JSONResponse(status_code=code, content=body)

    # ── CSRF envelope (same order as airgap toggle) ──
    _sfs = request.headers.get("sec-fetch-site", "").strip().lower()
    if _sfs in ("cross-site", "none"):
        return _err(403, {"error": "cross_site"})
    origin = request.headers.get("origin", "")
    host = request.headers.get("host", "")
    if origin:
        from urllib.parse import urlparse
        if urlparse(origin).netloc and urlparse(origin).netloc != host:
            return _err(403, {"error": "cross_origin"})

    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}

    slug = str(body.get("slug", "")).strip()
    raw_path = str(body.get("path", "")).strip()

    # ── "default" → unmount ──
    if slug == "default" or body.get("default") is True:
        unmount()  # never raises; returns bool
        return {"ok": True, "current": None}

    # ── Resolve a bundle dir, path-jailed ──
    bundle_dir = _resolve_world_dir(slug, raw_path)   # helper below
    if bundle_dir is None:
        return _err(400, {"error": "bad_request",
                          "message": "Provide a known slug or a path under WORLDS_DIR, or 'default'."})

    # ── Mount (atomic; refuses before touching disk on any error) ──
    try:
        rec = mount(bundle_dir)
    except (SealMismatch, PartialBundle, SchemaSkew, GateViolation, SlugInvalid) as e:
        return _err(409, {"error": "mount_refused",
                          "message": getattr(e, "user_message", str(e))})
    except Exception as e:  # noqa: BLE001
        _log.warning("world select: unexpected mount error: %s", e)
        return _err(500, {"error": "mount_failed", "message": str(e)})

    return {"ok": True, "current": rec.world}
```

**`_resolve_world_dir(slug, raw_path)` — module-level helper in app.py, the path-jail:**
- If `slug` is given (and not "default"):
  - reject if `not _SLUG_RE.match(slug)` → return `None` (rejects `../`, dots, slashes, uppercase).
  - `candidate = (_default_worlds_dir() / slug).resolve()`.
  - **Jail:** require `candidate` is a real dir AND `_default_worlds_dir().resolve()` is a parent
    of `candidate` (`candidate.is_relative_to(worlds_root)` on 3.9+: use
    `str(candidate).startswith(str(worlds_root) + os.sep)` for portability, or
    `os.path.commonpath`). If not jailed or not a dir → `None`.
  - return `candidate`.
- Else if `raw_path` is given:
  - `candidate = Path(raw_path).expanduser().resolve()`.
  - **Accept only if** it is an existing dir AND it is **inside `_default_worlds_dir()`** (same
    jail as above). A path outside `WORLDS_DIR` → `None`. (The currently-mounted out-of-folder
    World is selected by its **slug** via the include in §1.6 only if it is also droppable; to
    re-select a CLI-mounted-by-absolute-path World we still require it inside WORLDS_DIR — the UI
    never sends an arbitrary path. `path` exists purely so the UI can pass the discovered
    `WorldInfo.path` back; that path is always under WORLDS_DIR for scanned worlds.)
  - return `candidate`.
- Else → `None`.

> **No traversal, no arbitrary FS read, no code execution.** The slug is regex-jailed; the path
> is resolved-then-jailed under `WORLDS_DIR`. `mount` itself re-validates the manifest slug and
> the seal. Bundles are DATA: the seal + the existing DATA-not-instructions boundary
> (world_mount.py:11–16) hold; nothing from a bundle is executed.

**Error surface (no 500s for expected failures):**
- tampered/broken seal → `409 {"error":"mount_refused", "message": <SealMismatch.user_message>}`.
- partial/schema/category/slug → `409 mount_refused` with the bundle error's `user_message`.
- unknown slug / bad path / traversal → `400 bad_request`.
- truly unexpected → `500 mount_failed` (logged). The current World is unchanged in every
  failure path because `mount` is atomic (F2).

---

## 3. UI — nav dropdown in `_nav.html`

**One edit to the shared partial** (`src/arail/portal/templates/_nav.html`) → appears on every
page. Render the dropdown **server-side** from `_identity_ctx()` data already in context, plus a
lazy fetch of the catalog on open (keeps the nav render cheap; the catalog can be a folder scan).

### 3a. Markup — replace the badge block (lines 21–25) with badge + `<details>` popover
Keep the existing badge styling language (the `◆ <World> World` pill colors/border). Use a
native `<details>`/`<summary>` popover (no framework, no FOUC, closes on outside click via JS):

```html
{# World switcher: badge doubles as the dropdown trigger. Rendered on every page. #}
<details class="world-switcher" id="world-switcher" style="position:relative;display:inline-block;margin-left:.55rem;vertical-align:middle;">
  <summary class="world-badge" style="list-style:none;cursor:pointer;
        padding:.12em .58em;border-radius:999px;font-size:.72rem;font-weight:600;
        letter-spacing:.02em;white-space:nowrap;
        color:var(--purple,var(--blue,var(--green,#9e8cff)));border:1px solid currentColor;"
        title="Load or unload a World — swaps the lab's theme & knowledge.">
    {% if identity is defined and identity.mounted %}◆ {{ (identity.world or 'world')|capitalize }} World{% else %}◇ AI Lab{% endif %}
    <span aria-hidden="true" style="opacity:.7;">▾</span>
  </summary>
  <div class="world-menu" id="world-menu" role="menu"
       style="position:absolute;top:115%;left:0;z-index:1200;min-width:220px;
              background:rgba(10,14,20,.98);border:1px solid currentColor;border-radius:10px;
              padding:.35rem;box-shadow:0 8px 28px rgba(0,0,0,.45);">
    <div class="world-menu-empty" style="padding:.4rem .6rem;font-size:.72rem;opacity:.7;">Loading…</div>
  </div>
</details>
```
- When unmounted, the summary reads `◇ AI Lab ▾`; when mounted, `◆ <World> World ▾` (preserves
  the existing badge text/behavior, now clickable).
- Items are injected by JS on first open from `GET /api/worlds` (3b).

### 3b. JS — append a `world-switcher` IIFE to `static/nav.js`
Follow the existing fetch+POST idiom (the airgap toggle block, nav.js:255–370). Add at the end of
nav.js (it's already loaded on every page; `_nav.html` references `/static/nav.js`).

Behavior (exact):
1. On `toggle` of `#world-switcher` (first open only, cache the result): `fetch('/api/worlds')`
   → render `#world-menu`:
   - Row 0 always: **"AI Lab (default)"**, `data-action="default"`. Active (✓ + bold) when
     `json.current === null`.
   - Then one row per `world` in `json.worlds`:
     - `valid:true` → clickable row, `data-slug=w.slug`, `data-path=w.path`, label =
       `w.display_name`. Active (✓ + bold) when `w.mounted`.
     - `valid:false` → **disabled** row (greyed, `pointer-events:none`), label =
       `w.display_name`, with a small `(unavailable)` tag and `title=w.reason`.
   - Empty folder → only the "AI Lab (default)" row (+ any out-of-folder current from §1.6).
2. On click of a clickable row: optimistic UI not needed (we reload). Disable the menu, POST:
   ```js
   fetch('/api/worlds/select', {
     method:'POST', credentials:'same-origin',
     headers:{'Content-Type':'application/json'},
     body: JSON.stringify(action==='default' ? {slug:'default'} : {slug: slug, path: path})
   })
   ```
   - `r.ok` → `window.location.reload()` (F4: next GET re-resolves identity/theme/badge).
   - non-ok → parse body, show `window.ARAIL.whisper.show({text: body.message || 'World load
     failed', tone:'amber'})` (the whisper toast API already exists, nav.js:373–453) and
     re-enable the menu. **Current World unchanged** (server is atomic).
3. Outside-click / Escape closes the `<details>` (native for Escape on summary focus; add an
   outside-click listener that does `details.open=false`, mirroring the airgap close wiring
   nav.js:233–253).

No new CSS file; inline styles + existing CSS vars (`--purple/--blue/--green`) match the badge.
No new heavy deps. Pure vanilla, airgap-safe.

---

## 4. Switch semantics (restate, builder-facing)
- Select World B (valid) → `mount(B)`. Atomic: stages B's KB, overwrites the record, re-resolves
  capabilities sidecar, identity flips on reload. (F2)
- Select "AI Lab (default)" → `unmount()`. Removes the record + capabilities sidecar (first),
  identity reverts to operator brand + AI/ML defaults on reload. (`unmount` never raises;
  returns bool.)
- Select B while A mounted → `mount(B)` overwrites A's record. The lab is fully B. A's staged
  `pkb/sources/world-A/` remains on disk (inert, not current). Acceptable; cleanup is ROADMAP.
- Any mount failure (seal/partial/schema/category) → 409, current World unchanged. (F2 atomicity.)

---

## 5. Failure modes / grace
| Condition | Behavior |
|---|---|
| `WORLDS_DIR` absent / not a dir | `list_available_worlds` returns current-only/empty; no mkdir, no crash (§1.2). UI shows just "AI Lab (default)". |
| Empty `lab/worlds/` | Only "AI Lab (default)" (+ out-of-folder current if CLI-mounted). |
| Broken/partial bundle dir in folder | Listed `valid:false` with `reason`; **disabled** in UI; never mountable from UI. (§1.4) |
| Tampered bundle selected (seal fail) | `mount` raises `SealMismatch` → `409 mount_refused` → amber whisper; current World unchanged. |
| Two dirs, same slug | First wins; rest `valid:false reason="duplicate slug …"`. |
| CLI-mounted World not in folder | Appended to catalog, `mounted:true`, marked active. |
| Mount mid-fail | Atomic — never half-switched (F2). |
| Corrupt mount record | `current_mount` already returns `None` on parse error (world_mount.py:516) → treated as default. |

---

## 6. Security checklist (builder must satisfy)
- **Path jail:** slug via `_SLUG_RE`; path resolved + confined under `WORLDS_DIR` (§2b
  `_resolve_world_dir`). No `..`, no absolute escape, no symlink-out (resolve() then prefix-check).
- **No code execution** from bundles — they are DATA; only `load_bundle`/`verify_seal`/staging run.
- **Seal enforced at mount** (not at list) — tampered bundles refused at select.
- **CSRF/Origin envelope** on the POST, identical to `post_airgap_toggle` (Sec-Fetch-Site +
  Origin/Host). `GET /api/worlds` is read-only, no gate needed.
- **Airgapped-safe:** local filesystem only, zero network. Do not regress `LAB_MODE=airgapped`.
- **No secrets**: World selection never touches `secrets.env`; never logs bundle contents.

---

## 7. Tests (arail weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression)
New file `tests/test_world_switcher.py`. Point `WORLDS_DIR` at a tmp dir populated from
`tests/fixtures/world-bundles/`. Use the `_default_worlds_dir`/`_default_data_dir`/`_default_pkb_root`
monkeypatch idiom (test_world_identity_flip.py:45; conftest.py:67). Build
`TestClient(portal_app.app)`.

**Fixture wiring helper (per test):**
```python
import shutil
from arail import world_mount as wm
def _worlds(tmp_path, monkeypatch, *names):
    wd = tmp_path / "worlds"; wd.mkdir()
    for n in names:
        shutil.copytree(f"tests/fixtures/world-bundles/{n}", wd / n)
    data = tmp_path / "data"; pkb = tmp_path / "pkb"
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: wd)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    return wd
```

**Discovery (setup, ~30%):**
1. scan finds valid bundle: `list_available_worlds` over `{physics}` → one `valid=True`,
   `slug=="physics"`, `display_name` from manifest, `mounted=False`.
2. invalid dir: drop a junk dir (e.g. empty dir, or copy `tampered` which is partial/seal-bad at
   *mount* but `load_bundle`-valid — instead make a dir with only `manifest.json` removed) →
   `valid=False` with a `reason`.
3. empty dir → `[]` (or current-only). missing dir (don't create `worlds/`) → no crash, `[]`.
4. de-dupe: copy `physics` twice under different dir names → one valid, one
   `valid=False reason~="duplicate"`.
5. out-of-folder current: `mount(physics from fixtures path)` then list an *empty* worlds dir →
   physics appears, `mounted=True`.

**`GET /api/worlds` (happy/regression):**
6. shape: `{worlds:[...], current:null}` with default lab.
7. with physics mounted → `current=="physics"`, the physics row `mounted:true`.

**`POST /api/worlds/select` (happy + Buddy/identity, ~30%):**
8. select physics by slug → `200 {ok,current:"physics"}`; **follow-up** `GET /` (or `/api/brand`)
   render shows the physics identity flipped (assert name/theme — reuse assertions from
   test_world_identity_flip.py). Asserts the staged dir exists.
9. select "default" after physics → `200 {current:null}`; follow-up render reverts to default lab
   (regression: default identity unchanged).
10. switch A→B (mount physics, then select a second valid world e.g. `world-caps-stt`) → current
    is B; B's staged dir present; identity reflects B (no stale A in the current surfaces).

**Security (~20%):**
11. tampered bundle: copy `tampered` into worlds dir, select by slug → `409 mount_refused`,
    message non-empty; `current_mount()` still the prior (or None). Current World unchanged.
12. path traversal: `POST {"slug":"../../etc"}` → `400` (regex reject); `POST {"path":"/etc"}`
    → `400` (outside WORLDS_DIR jail). No mount occurs.
13. (optional) `GET /api/worlds` over a folder containing `hostile` fixture lists it without
    executing anything (DATA boundary).

**Nav render (regression):**
14. `GET /` HTML contains the `world-switcher`/`world-menu` element and, when physics mounted,
    the `◆ Physics World` active text in the summary. When unmounted, `◇ AI Lab`.

Note the autouse `_no_ambient_world_mount` (conftest.py:67) already isolates ambient state; the
per-test monkeypatches above (same `monkeypatch` instance) override it.

---

## 8. Build order (numbered, done-conditions)

1. **config: `WORLDS_DIR`** — add the `_resolve("ARAIL_WORLDS_DIR", str(LAB_ROOT/"worlds"))` line
   after `MODELS_DIR` (config.py:71).
   *Done:* `from arail.config import WORLDS_DIR` resolves to `lab/worlds` by default; env override works.

2. **world_mount: `WorldInfo` + `_default_worlds_dir()` + `list_available_worlds()`** per §1.
   *Done:* discovery tests 1–5 pass; function never raises on missing/empty/junk dirs.

3. **app.py: `GET /api/worlds`** per §2a.
   *Done:* tests 6–7 pass; shape `{worlds,current}`.

4. **app.py: `_resolve_world_dir` helper + `POST /api/worlds/select`** per §2b, mirroring the
   airgap CSRF envelope.
   *Done:* tests 8–12 pass; tampered→409, traversal→400, default→unmount, slug→mount; no 500 on
   expected failures.

5. **_nav.html: badge→`<details>` switcher markup** per §3a.
   *Done:* every page renders the `world-switcher`; summary text matches mount state (test 14).

6. **nav.js: `world-switcher` IIFE** per §3b — fetch catalog on open, render rows (default + valid
   + disabled-invalid + active marker), POST select → reload on ok / amber whisper on error,
   outside-click/Escape close.
   *Done:* manual smoke (drop `physics` into `lab/worlds/`, open dropdown, select it → page reloads
   recolored; select "AI Lab (default)" → reverts). Test 14 asserts the markup.

7. **tests: `tests/test_world_switcher.py`** per §7. *Done:* full file green; `pytest -k world_switcher` passes.

---

## 9. BUILT vs ROADMAP
**BUILT this sprint:** `WORLDS_DIR` config; `WorldInfo` + `list_available_worlds`; `GET /api/worlds`;
`POST /api/worlds/select` (mount/unmount, path-jailed, CSRF-guarded, clean error surface); nav
`<details>` dropdown + nav.js wiring; full test suite.

**ROADMAP (explicitly out of scope — do not build):**
- Live identity update without page reload (we reload; F4).
- Cleanup of a prior World's staged `pkb/sources/world-<slug>/` on switch (inert residue tolerated).
- World *install/import* UI (drag-drop a bundle into `lab/worlds/`); for now the user drops the
  directory in manually, mirroring `lab/models/`.
- Per-World metadata preview (terms count, source editions) in the dropdown.
- Re-selecting an out-of-folder CLI-mounted World by absolute path from the UI (the UI only sends
  paths under `WORLDS_DIR`).
