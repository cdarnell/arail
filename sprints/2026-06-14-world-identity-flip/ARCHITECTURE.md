# ARCHITECTURE — Complete World Flip (world-identity-flip)

**Repo:** `arail` (isolated worktree `/Users/netsushi/ProJects/arail-verify`, branch `qukaizen/arail-world-identity-flip`, at `origin/main`).
**Mode:** architect / DESIGN. Builder implements this with zero new decisions.
**Scope:** ARAIL only. Additive / refactor. Do NOT break merged World-Mount / STT / OCR / dictionary tests. No qukaizen-dac edits. On-device / airgapped unaffected.

---

## 0. Problem restated (owner decisions, final)

Today, mounting a DaC World flips dictionary/theme/intent/Buddy-framing/UI-palette **only after** `world mount --apply-face` writes `.env` **and** `./arailctl restart` (env read at startup), and it deliberately **keeps** the operator's brand. Three changes:

1. **Brand flips too.** Mounted → `LAB_NAME`/`LAB_LOGO` become the World's identity (e.g. "Physics — Measurement & Units"). Unmounted → operator brand. (Reverses prior "brand stays.")
2. **Instant flip, no restart.** Identity (name, logo, theme, intent name/description, UI palette, dictionary, Buddy framing) resolves from the **mount sidecar at REQUEST time**.
3. **Keep the built-in AI/ML default.** No World mounted → operator `LAB_NAME`/brand + default theme + LLM-generated dictionary. No new default-World bundle.

The dictionary flip **already** resolves from the mount at request time (`_world_mounted_dict_response()` calls `current_mount()` fresh per request — `app.py:2530`). We mirror that pattern for the rest of identity.

---

## 1. Root cause (verified in real code)

| Symptom | Real cause | File:line |
|---|---|---|
| Brand needs restart | `_BRAND = load_brand()` at **module import** | `portal/app.py:52` |
| UI theme needs restart | `_UI_THEME = load_ui_theme()` at **module import**; pushed into Jinja **globals** once | `portal/app.py:53,493,496,498` |
| Intent/theme partially live | `LAB_THEME`, `LAB_INTENT_NAME/DESCRIPTION` already read via `os.getenv` **per request** — but they only have values if `--apply-face` wrote them, so still needs restart to populate `.env` | `app.py:532,599–606,1025,1040`; `researcher.py:102,122–123,545` |
| Brand never flips | `mount(apply_face=True)` deliberately omits `LAB_NAME`/`LAB_LOGO` from `_write_face_env` | `world_mount.py:704–712` |

The fix is one resolver consulted live, plus killing the two module-level caches.

---

## 2. The contract: `effective_identity()`

### 2.1 Location — NEW module `src/arail/identity.py`

Rationale: `brand.py` must not import `world_mount` (layering — `world_mount` already imports `ui_theme`; a `brand → world_mount` edge risks a cycle since the resolver also needs `brand`). A thin new module depends on both and on `ui_theme`, and is imported by the portal + agents. Keep `brand.py`, `ui_theme.py`, `world_mount.py` unchanged in their public APIs (additive only).

### 2.2 The dataclass + function

```python
# src/arail/identity.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from arail.brand import Brand, load_brand
from arail.ui_theme import UITheme, load_ui_theme, default_ui_theme

# Built-in AI/ML defaults (lifted verbatim from the current hardcoded dashboard string)
_DEFAULT_LAB_THEME = (
    "Making SSD-hosted model inference faster — frontier "
    "open-weight models on laptop hardware"
)
_DEFAULT_INTENT_NAME = "AI Engineer"

@dataclass(frozen=True)
class Identity:
    name: str                 # LAB_NAME  ← face.name when mounted
    logo: str                 # LAB_LOGO  ← ⟨face.name⟩ when mounted
    short_name: str
    tagline: str
    version: str
    lab_theme: str            # Mission-card north-star line (was LAB_THEME)
    intent: str               # "ai" | "other" | ...  (was LAB_INTENT)
    intent_name: str          # was LAB_INTENT_NAME
    intent_description: str    # was LAB_INTENT_DESCRIPTION (domain_framing)
    vocabulary_register: str   # face.vocabulary_register ("" when unmounted)
    ui_theme: UITheme          # resolved preset
    world: Optional[str]       # mounted world slug, or None
    mounted: bool

    def brand(self) -> Brand:
        """Back-compat Brand view for code/templates that expect a Brand."""
        return Brand(name=self.name, short_name=self.short_name,
                     tagline=self.tagline, logo=self.logo, version=self.version)


def effective_identity(data_dir: Path | None = None) -> Identity:
    """Live lab identity, resolved at REQUEST time.

    Mounted World  → derive from face.json (+ manifest display_name).
    No World       → operator brand + built-in AI/ML defaults.
    Never raises: any failure falls back to operator/default per field.
    """
```

### 2.3 Resolution logic (exact)

Call `current_mount(data_dir)` (passes `data_dir` through so tests can inject; defaults to `_default_data_dir()` like every other consumer).

**Unmounted path (`record is None`):**
- `b = load_brand()` → name/logo/short_name/tagline/version from `b`.
- `lab_theme = os.getenv("LAB_THEME", _DEFAULT_LAB_THEME)`
- `intent = os.getenv("LAB_INTENT", "ai").lower()`
- `intent_name = os.getenv("LAB_INTENT_NAME", _DEFAULT_INTENT_NAME)`
- `intent_description = os.getenv("LAB_INTENT_DESCRIPTION", "")`
- `vocabulary_register = ""`
- `ui_theme = load_ui_theme()` (reads `LAB_UI_THEME` env or default)
- `world = None`, `mounted = False`

This **exactly** reproduces today's unmounted behaviour (regression-safe): operator may still set `LAB_*` env in `.env` for a non-World custom lab, and it still wins.

**Mounted path (`record is not None`):**
- `face = mounted_face(record)` (may be `None` → tolerated-partial).
- `display_name` = `manifest.display_name` if reachable, else slug. The manifest is **not** in `MountRecord`; read it best-effort from `Path(record.bundle_dir)/"manifest.json"` (it lives at the original bundle path; if unreadable, fall back to `record.world`). Wrap in try/except → on any failure `display_name = record.world`.
- Per-field derivation, each independently falling back to operator/default when the source is missing (tolerated-partial rule, mirrors `load_bundle` face handling at `world_mount.py:235–245`):

  | Identity field | Mounted source | Fallback when face/field missing |
  |---|---|---|
  | `name` | `face["name"]` → else `display_name` | `load_brand().name` |
  | `logo` | `f"⟨{name}⟩"` (uses resolved name) | `load_brand().logo` |
  | `short_name` | `name.lower().replace(" ","-").replace("'","")` | `load_brand().short_name` |
  | `tagline` | `face["tagline"]` | `load_brand().tagline` |
  | `lab_theme` | `face["name"]` (the World's north-star, matching old `_write_face_env` LAB_THEME = face.name) | `_DEFAULT_LAB_THEME` |
  | `intent` | `"other"` (a mounted World is always a custom domain) | `"other"` |
  | `intent_name` | `face["name"]` → else `display_name` | `_DEFAULT_INTENT_NAME` |
  | `intent_description` | `face["domain_framing"]` | `""` |
  | `vocabulary_register` | `face["vocabulary_register"]` | `""` |
  | `ui_theme` | `load_ui_theme(face["palette_hint"])` **iff it resolves to a non-default match**, mirroring `_write_face_env:715–723` (`resolved.id == hint or resolved.env_value == hint`); else `default_ui_theme()` | `default_ui_theme()` |
  | `world` | `record.world` | — |
  | `mounted` | `True` | — |
  | `version` | `load_brand().version` (always operator's app version) | — |

- The palette-hint match rule is identical to `_write_face_env` so the existing `test_unknown_palette_*` semantics carry over to the resolver: unknown hint → default theme, not an error.

**Never raises:** wrap the whole mounted branch in try/except; on any unexpected error, log a warning and return the unmounted/default Identity. Sidecar unreadable is already handled by `current_mount` returning `None`.

### 2.4 Per-request cost decision — NO cache (mirror the dictionary flip)

`effective_identity()` does: one `current_mount()` (1 `stat` + small JSON read of `world-mount.json`, a few hundred bytes) + when mounted one `mounted_face()` (read of staged `face.json`, ~1 KB) + optional manifest read. The **dictionary flip already pays `current_mount()` per request with no cache** (`app.py:2530`, `:2752`), and Buddy's framing block does too (`_builtin_buddy.py:972`). Identity is on the same request paths.

**Decision: no cache in v1.** A 1–2 file stat+small-JSON read is sub-millisecond and dwarfed by template render / inference. Adding a cache introduces an invalidation surface (mount/unmount must bust it) that the instant-flip goal makes risky — a stale cache is exactly the bug we're removing. Matching the established dictionary pattern keeps one mental model.

**ROADMAP (not built):** if profiling ever shows identity reads hot, add an mtime-keyed memo *inside `world_mount.current_mount`* (keyed on `world-mount.json` mtime) so **all** consumers — dictionary, Buddy, identity — benefit uniformly. Do NOT add a private cache in `identity.py`.

---

## 3. Call sites to reroute (EVERY one)

All in `src/arail/portal/app.py` unless noted. The pattern: compute `ident = effective_identity()` at the top of each request handler (or in the shared template-context helper, see 3.1) and read fields off `ident`.

### 3.1 Kill the module-level caches + make Jinja identity per-request

- **`app.py:52`** `_BRAND = load_brand()` — **remove.** (See note on `:243` below for the one legitimate import-time use.)
- **`app.py:53`** `_UI_THEME = load_ui_theme()` — **remove.**
- **`app.py:493,496,497,498`** Jinja globals `brand`, `ui_theme`, `ui_theme_css` — these are import-time constants and CANNOT flip per request as globals.
  - `ui_themes` (`:497`, the static list of all presets) stays a global — it never flips.
  - **Replace the per-request-varying globals with a render helper.** Add:
    ```python
    def _identity_ctx() -> dict:
        ident = effective_identity()
        return {
            "brand": ident.brand(),
            "ui_theme": ident.ui_theme,
            "ui_theme_css": theme_css(ident.ui_theme),
            "identity": ident,
        }
    ```
    Every `templates.TemplateResponse(request, "x.html", {...})` call that renders a page using `{{ brand.* }}`, `{{ ui_theme* }}` must spread `**_identity_ctx()` into its context dict. Because explicit context overrides globals in Jinja2, spreading wins. Keep `ui_themes`, `tier_surfaces`, `lab_tier`, `asset_v` as globals.
  - **Builder action:** grep templates for `brand.`, `ui_theme`, `ui_theme_css` (lists in §"Template inventory" below) → every route rendering one of those templates spreads `**_identity_ctx()`. Routes that render templates using NONE of them may skip it (harmless to add; prefer adding for uniformity on the five main surfaces).

### 3.2 FastAPI app title — `app.py:243`

`app = FastAPI(title=_BRAND.name, ...)`. This is import-time and cannot flip (the OpenAPI title). Replace `_BRAND.name` with a direct `load_brand().name` call (operator brand) so we can delete `_BRAND`. **Document:** the `/api/docs` title is the operator brand even when a World is mounted — acceptable (it's the app's API surface, not lab identity). Not a flip target.

### 3.3 Startup banner — `app.py:532–534`

`intent_name = os.getenv("LAB_INTENT_NAME", "AI Engineer")` then emits `f"{_BRAND.name} portal started — {intent_name} lab."` Startup runs once; using `effective_identity()` here reflects whatever is mounted at boot (correct). Replace with:
```python
ident = effective_identity()
activity_log.emit("system", f"{ident.name} portal started — {ident.intent_name} lab.", "success")
```

### 3.4 Bootstrap goal intent — `app.py:599–606`

Reads `LAB_INTENT`, `intent_name` (local var from `:532`), `LAB_INTENT_DESCRIPTION` as fallbacks for bootstrap goal fields. Route through `ident`: `parsed["intent"] = bg.get("intent", ident.intent)`, `parsed["intent_name"] = bg.get("intent_name", ident.intent_name)`, `bootstrap_desc = bg.get("intent_description", ident.intent_description)`.

### 3.5 Welcome page — `app.py:862`

`"current_lab_name": os.getenv("LAB_NAME", _BRAND.name)` → `effective_identity().name`. (Welcome also renders `ui_theme_css` — `welcome.html:8` — so this route MUST spread `**_identity_ctx()`.)

### 3.6 Dashboard mission card — `app.py:1025–1029` and Mission page `:1040–1044`

Both read `os.getenv("LAB_THEME", "<hardcoded AI/ML string>")`. Replace with `effective_identity().lab_theme` (the default string now lives in `identity._DEFAULT_LAB_THEME`). Add `**_identity_ctx()` to both (dashboard.html + mission.html use `{{ brand.name }}`).

### 3.7 Admin theme display — `app.py:3321`

`"current_ui_theme": _UI_THEME` → `effective_identity().ui_theme`. Spread `**_identity_ctx()` (admin.html uses `{{ brand.name }}`, `{{ brand.version }}`).

### 3.8 `/api/system/theme` — `app.py:3327–3335`

`_UI_THEME.id/name/...` → `ui = effective_identity().ui_theme` then read off `ui`. (This makes the theme API report the live World palette.)

### 3.9 `/api/brand` — `app.py:5093–5097`

`return _BRAND.to_dict()` → `return effective_identity().brand().to_dict()`. Now the dashboard JS personalization flips live.

### 3.10 Researcher agent — `src/arail/agents/researcher.py`

- `_get_lab_intent()` (`:100–102`) reads `os.getenv("LAB_INTENT","ai")`. **Reroute to the resolver:** `from arail.identity import effective_identity; return effective_identity().intent`. This is the gate that makes the researcher reframe; with instant flip it must consult the mount, not env.
- `_get_system_context()` (`:119–132`): when `intent == "other"`, it reads `LAB_INTENT_NAME` / `LAB_INTENT_DESCRIPTION` from env. **Reroute:** pull `ident = effective_identity()`; use `ident.intent_name` / `ident.intent_description`. Keep the existing prompt-composition wording unchanged (only the source of the two strings changes). Because mounted always yields `intent == "other"` with the World's name+framing, the researcher reframes live.
- `:545` `os.getenv("LAB_INTENT_NAME", "AI Engineer")` → `effective_identity().intent_name`.

### 3.11 Buddy framing — `src/arail/agents/_builtin_buddy.py:963–994`

`_world_framing_block()` **already** reads `current_mount` + `mounted_face` live and caps/delimits `domain_framing` + `vocabulary_register`. **No change required** — it already instant-flips and already enforces the security boundary. (Builder: confirm with a test, do not refactor it to use the resolver — it intentionally only pulls the two framing fields, not the full identity, and the caps are security-load-bearing.)

### 3.12 Template inventory (which templates read identity)

`brand.*`: admin, agents, dashboard, graph, notebook, plugins, tuning, chat.legacy, knowledge, dictionary, doc_viewer, marimo, notebooks, docs_hub, mission, opencode, open-notebook, research, terminal, chat, welcome, teacher, `_nav.html` (logo + name).
`ui_theme_css` / `ui_theme`: `welcome.html` only (`:8`). (UI tokens are otherwise baked into static `style.css`; full per-page palette injection is NOT in scope — see §8 ROADMAP.)

**Builder rule:** for each route that renders one of the above templates, add `**_identity_ctx()`. `_nav.html` is `{% include %}`-ed by the five main surfaces and others — those parent routes must supply the identity context. Routes that currently rely on the Jinja global `brand` will break (show stale operator brand) if not converted; converting the five main surfaces (dashboard, chat, research, knowledge, agents) + welcome + admin + mission is mandatory. Convert all listed for correctness.

---

## 4. `--apply-face` / `LAB_INTENT=other` disposition

### Decision: REMOVE the env-flip write path.

Since identity now resolves live from the sidecar, the `.env` face-writes are redundant and become a stale-state hazard (the exact "needs restart / wrong after unmount" class of bug we're killing). Concretely:

- **Delete** `_write_face_env()` (`world_mount.py:691–729`) and its two call sites (`mount()` `:776–777`, `swap()` `:872–873`).
- **Remove** the `apply_face` parameter from `mount()` and `swap()` and the `--apply-face` flag + preview block in the CLI (`_cmd_mount` `:1001–1017`, the restart NOTE `:1045–1049`, `_cmd_swap` `:1077–1078`, parser `:1103–1104`, `:1114–1115`). Mounting is now always a full flip.
- `env_path` parameter on `mount`/`swap`/CLI: remove (no longer used). `_default_env_path()` (`:489–490`) becomes dead — remove it too.
- **`LAB_INTENT=other`**: no longer written to `.env`. The researcher's gate now comes from `effective_identity().intent`, which returns `"other"` whenever a World is mounted (§2.3). The env var `LAB_INTENT` still works for an operator's non-World custom lab (unmounted path reads it). So the gate is preserved, just sourced from the mount when mounted.

**Why remove rather than keep for persistence:** the sidecar (`world-mount.json`) IS the persisted, cross-restart source of truth — it survives restarts already (that's how the dictionary flip persists). There is no scenario where `.env` needs the face values once identity reads the sidecar live. Keeping `--apply-face` would mean two sources of truth that can disagree after unmount. Single source = sidecar.

**Operator's own `.env` brand is untouched:** we never write `LAB_NAME`/`LAB_LOGO`. Unmount reverts to it purely by the resolver taking the unmounted path. No revert logic, no env cleanup needed.

---

## 5. Security / consent boundary (must still hold — state explicitly)

- **Consent model shifts: mounting IS consent.** Previously `--apply-face` was the second, explicit consent to let face text reach Buddy's prompt. Now mounting a World (the operator's deliberate `world mount <dir>`) is itself the consent to adopt that World's identity, including the framing block. This is the owner's decision (full immersion). Document in the mount CLI help + the module docstring.
- **DATA-not-instructions boundary intact.** Verified unchanged:
  - `terms.json` is RAW DATA — only ever template-rendered (dictionary page), never enters a prompt. `term_to_dict_entry` (`world_mount.py:906–939`) and the dictionary route do not feed a model. Unchanged.
  - Only `face.json` text parameterizes a prompt, and ONLY through `_world_framing_block()` (`_builtin_buddy.py:963–994`), which is **delimited** (`# WORLD FRAMING` … `# END WORLD FRAMING`) and **length-capped** (`_MAX_WORLD_DOMAIN_FRAMING=600`, `_MAX_WORLD_VOCAB_REGISTER=300`). Unchanged by this sprint.
  - `name` / `tagline` / `palette_hint` from face flow ONLY to display surfaces (nav, titles, mission card, UI theme id) and to the researcher's `intent_name`/`intent_description` system-context composition — which is the SAME bounded text that already fed it via `LAB_INTENT_DESCRIPTION`. No new prompt-injection surface: the researcher already templated `domain_framing` into its base; we only change the source from env to sidecar.
- **Slug / path-traversal guards** (`_SLUG_RE`, cross-file slug checks in `load_bundle`) are unchanged; the resolver never takes a path from face content. Manifest read in §2.3 uses `record.bundle_dir` (already-validated, resolved path from mount time), not face-derived input.

---

## 6. Failure modes (each → graceful, never crash)

| Condition | Behaviour |
|---|---|
| No World mounted | Unmounted path: operator brand + AI/ML defaults. (Default lab unchanged — regression.) |
| `world-mount.json` missing/corrupt | `current_mount()` returns `None` → unmounted path. |
| `face.json` missing/invalid on a mounted World | `mounted_face()` returns `None` → each face-derived field falls back to operator brand / default per §2.3 table; KB still mounted (tolerated-partial). `name`→operator brand, `lab_theme`→default, `intent_description`→"", `vocabulary_register`→"". |
| Individual face field absent (e.g. no `tagline`) | That field falls back; others still flip. |
| `palette_hint` unknown / unresolvable | `default_ui_theme()` (no error), per the `_write_face_env` match rule reused. |
| `manifest.json` unreachable for display_name | `display_name = record.world`. |
| Any unexpected exception in resolver | Log warning, return unmounted/default Identity. Never raise into a request handler. |

---

## 7. Test strategy (arail weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression)

New tests file: `tests/test_world_identity_flip.py` (plus edits to `test_world_face.py`). Use `TestClient` against the portal app. Per the autouse `_no_ambient_world_mount` fixture (`conftest.py:66–87`), the default data dir is an empty tmp; tests that want a mount **re-`monkeypatch.setattr(world_mount, "_default_data_dir", lambda: <dir with mount>)`** (same monkeypatch instance wins) OR mount into a dir then patch `_default_data_dir` to it. Helper: mount PHYSICS into `tmp/data`, patch `_default_data_dir` → `tmp/data`.

**SETUP (30%)**
1. Instant flip, no restart, no `.env` write: mount PHYSICS (no `apply_face` arg exists), GET `/` (dashboard) via TestClient → response body contains `"Physics — Measurement & Units"` (nav/title) and the mission card shows the World's `lab_theme`; assert NO `.env` file was written by `mount()`.
2. `/api/brand` returns `name == "Physics — Measurement & Units"`, `logo == "⟨Physics — Measurement & Units⟩"` when mounted.
3. `effective_identity()` unit: mounted → `name`/`intent=="other"`/`intent_description`==face domain_framing/`ui_theme.id=="blue-cyan-lab"`/`mounted is True`/`world=="physics"`.
4. `mount()` no longer accepts `apply_face`/`env_path`; CLI `mount` has no `--apply-face` (parser-level assertion).

**BUDDY (30%)**
5. Researcher reframes live: with PHYSICS mounted, `researcher._get_lab_intent() == "other"` and `_get_system_context()` contains the World name + domain_framing; unmount (patch default dir to empty) → returns to AI/ML default context. No restart, no env.
6. Buddy `_world_framing_block()` returns the delimited block with PHYSICS domain/vocab when mounted, `""` when unmounted. (Regression-confirm existing behaviour through the resolver-adjacent path.)
7. `effective_identity().intent_name` / `.intent_description` reflect the mounted World live.

**SECURITY (20%)**
8. `terms.json` never reaches a prompt: assert `_world_framing_block()` output contains NO term text from PHYSICS terms.json (only face domain/vocab).
9. Framing block stays delimited + capped: oversized `domain_framing` (>600) in a crafted face → truncated; delimiters present. (Reuse/confirm existing cap behaviour.)
10. Brand/identity from face flows only to display + the already-bounded researcher context — assert mounting does not write any executable/prompt surface beyond the capped framing block (i.e. no new env keys, `.env` untouched).

**HAPPY (10%)**
11. Operator with custom `.env` `LAB_NAME=MyLab`, no World → dashboard shows `MyLab` (operator brand preserved on unmounted path).

**REGRESSION (10%)**
12. Default lab (no World, no custom env) → dashboard shows `Autoresearch AI Lab` + default `lab_theme` AI/ML string + `blue-cyan-lab` theme. Dictionary flip still works (mounted → World terms; unmounted → generated). STT/OCR mount tests untouched and still pass (`pytest tests/test_world_*.py`).

**EDIT existing `test_world_face.py`:** it asserts the now-removed env-write path. Disposition:
- Tests `test_apply_face_writes_*` (`:44–79`), `test_unknown_palette_leaves_ui_theme_unwritten` (`:107–129`), `test_kb_only_mount_no_env_written` (`:134`), `test_missing_face_no_env_written` (`:148`) all assume `apply_face`/env writes. **Rewrite** the file to assert the NEW contract: mount writes NO `.env`; identity is reflected via `effective_identity()` instead of `read_env_var`. Convert each assertion: e.g. `test_apply_face_writes_lab_theme` → `effective_identity(data_dir).lab_theme == face["name"]`; `test_unknown_palette_*` → `effective_identity(...).ui_theme == default_ui_theme()`; `test_missing_face_*` → mount succeeds + `effective_identity(...).name == load_brand().name` (operator fallback). Drop `test_apply_face_writes_exactly_5_keys` (no keys written now) — replace with `test_mount_writes_no_env`.
- `test_apply_face_does_not_write_lab_name/logo` (`:84–102`) → keep the intent (brand not written to env) but reframe: mount writes no env at all; `effective_identity` reports the World name from the sidecar, and the operator's `.env LAB_NAME` is physically untouched.

---

## 8. Build order (numbered, done-conditions)

1. **Create `src/arail/identity.py`** — `Identity` dataclass + `effective_identity(data_dir=None)` per §2. Unit-tested in isolation.
   *Done:* `effective_identity()` returns operator/default Identity with empty data_dir; returns World Identity with PHYSICS mounted; never raises on missing/corrupt face/manifest/sidecar.
2. **Remove the env-flip path in `world_mount.py`** — delete `_write_face_env`, `_default_env_path`; drop `apply_face`/`env_path` from `mount`, `swap`; remove `--apply-face` + preview + restart NOTE from CLI (`_cmd_mount`, `_cmd_swap`, parser).
   *Done:* `python -m arail.world_mount mount <dir>` mounts with no env write; no `--apply-face` flag; `tests/test_world_mount.py`/`loader`/`dictionary`/`kb`/`buddy`/`curator` still green.
3. **Portal: kill module caches + add `_identity_ctx()`** — remove `_BRAND`/`_UI_THEME` (`:52–53`); `FastAPI(title=load_brand().name)` (`:243`); remove `brand`/`ui_theme`/`ui_theme_css` Jinja globals (keep `ui_themes`); add `_identity_ctx()` helper; spread `**_identity_ctx()` into every route rendering an identity template (§3.12 list).
   *Done:* grep shows no remaining `_BRAND`/`_UI_THEME` references; the five main surfaces + welcome + admin + mission render with live identity.
4. **Portal: reroute the per-request reads** — §3.3 (startup banner), §3.4 (bootstrap), §3.5 (welcome name), §3.6 (mission card both routes), §3.7 (admin), §3.8 (`/api/system/theme`), §3.9 (`/api/brand`).
   *Done:* each listed line reads from `effective_identity()`; no remaining `os.getenv("LAB_THEME"/"LAB_INTENT_NAME"/"LAB_INTENT_DESCRIPTION")` in app.py except via the resolver.
5. **Agents: reroute researcher** — `_get_lab_intent`, `_get_system_context`, `:545` per §3.10. Confirm Buddy `_world_framing_block` unchanged (§3.11).
   *Done:* researcher intent/context come from `effective_identity()`; Buddy framing untouched; mounted → "other"+World framing, unmounted → AI/ML default.
6. **Tests** — write `tests/test_world_identity_flip.py` (§7 cases 1–12); rewrite `tests/test_world_face.py` to the new no-env contract.
   *Done:* `pytest tests/test_world_identity_flip.py tests/test_world_face.py` green; full `pytest tests/test_world_*.py tests/test_brand.py tests/test_dictionary_theme.py` green.
7. **Docs/labels** — update `world_mount.py` module docstring security note (consent = mounting), CLI help. Label BUILT vs ROADMAP in BUILD_LOG.
   *Done:* docstring + CLI help reflect instant-flip / mount-is-consent; no mention of `--apply-face`/restart.

---

## 9. BUILT vs ROADMAP

**BUILT (this sprint):**
- `effective_identity()` resolver; brand+intent+theme+lab_theme+vocab flip live from sidecar.
- Module-cache removal; per-request identity in templates (the listed surfaces) and APIs.
- Researcher live reframe; Buddy framing confirmed live.
- `--apply-face`/env-flip removed; mounting is consent.
- Tests + reworked face tests.

**ROADMAP (NOT this sprint):**
- mtime-keyed memo inside `current_mount` if identity reads ever profile hot (§2.4).
- Full per-page UI-palette CSS injection (today only `welcome.html` injects `ui_theme_css`; other pages use static `style.css` baked to blue-cyan). The resolver already returns the right `UITheme`; wiring `theme_css(ident.ui_theme)` into a `<style>` block on every main surface is a follow-up. Out of scope here to avoid touching every template's `<head>`.
- A `/api/identity` consolidated endpoint (currently `/api/brand` + `/api/system/theme` suffice).
