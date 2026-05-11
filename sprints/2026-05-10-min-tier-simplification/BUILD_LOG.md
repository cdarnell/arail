# Build log: Min-tier Simplification — Drop AirLLM, defer Compare

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-05-10
**Predecessor:** sprints/2026-05-10-chat-model-sync (PR #44)

## Plan

| # | Files | Change | Status |
|---|---|---|---|
| 1 | `pyproject.toml` | Empty `[project.optional-dependencies.min]`; rewrite tier descriptions; update comment block | done |
| 2 | `scripts/setup.sh` | `capture_tier()` skips AirLLM model resolution for min; `setup_env()` writes ARAIL_COMPARE_ENABLED based on tier | done |
| 3 | `scripts/upgrade.sh` | min → max sets ARAIL_COMPARE_ENABLED=1 when unset; only writes AIRLLM_MODEL on max | done |
| 4 | `scripts/enable_compare.sh` | NEW — upserts ARAIL_COMPARE_ENABLED=1 | done |
| 5 | `scripts/disable_compare.sh` | NEW — upserts ARAIL_COMPARE_ENABLED=0 | done |
| 6 | `arailctl` (top-level) | New `enable` / `disable` verb dispatch | done |
| 7 | `src/arail/portal/app.py` | `chat_page` handler adds `compare_enabled` to template context | done |
| 8 | `src/arail/portal/templates/chat.html` | Jinja `{% if compare_enabled %}` wrap on `+ Compare` button + Column B; setCompare() null-safe; cloud Model B fallback when no local deep backend | done |
| 9 | `README.md` | Tier table rewrite + Add-ons subsection | done |
| 10 | `docs/CERTIFIED_MODELS.md` | AirLLM section: max-tier only, operator-gated | done |
| 11 | `CLAUDE.md` | Tier reference one-liner; new enable/disable verbs in main verbs list | done |
| 12 | `tests/test_tier_install_min.py` | NEW — 5 cases pinning the min-tier install contract | done |
| 13 | `tests/test_compare_feature_flag.py` | NEW — 9 cases (template render + handler default + strict equality) | done |
| 14 | `tests/test_enable_compare_cli.py` | NEW — 7 cases (enable/disable scripts + arailctl verb dispatch) | done |
| 15 | Grep audit | ROADMAP.md AirLLM-tier line updated; lab/pkb/compiled/ left as auto-regen; pre-existing test_setup_extras regex generalized to accept `min = []` | done |

## Execution notes

### Step 1 — pyproject.toml

`min = []` (empty TOML array) is valid; setuptools treats it as "no extras." Comment block at lines 35–47 rewritten to drop the AirLLM-70B-in-min advertisement and describe Ollama-only minimalism. Tier description strings under `[tool.arail.tiers]` rewritten to match.

### Step 2 — scripts/setup.sh

- `capture_tier()` interactive prompt text updated to remove AirLLM-in-min wording.
- The tier-resolution block (lines ~929–946) split: max sets `AIRLLM_MODEL_ID` and `AEROLLM_MODEL_ID`; min leaves both empty and prints an Ollama-only line plus the `arailctl enable compare` hint.
- `setup_env()` appends a tier-based `ARAIL_COMPARE_ENABLED` write (`0` for min, `1` for max) using the existing `_set_env_var` helper.

### Step 3 — scripts/upgrade.sh

- pip-install line comment updated to reflect that `[min]` is now empty.
- The inline Python helper now skips the AIRLLM_MODEL upsert when tier=min and conditionally upserts `ARAIL_COMPARE_ENABLED=1` only on min→max when the key is unset (preserves explicit user values).

### Step 4–6 — enable/disable scripts + arailctl verbs

Both scripts honor an external `REPO_ROOT` env override (added during step 12 when CLI tests needed isolation). The arailctl `enable`/`disable` verbs route through a feature-name case statement so future add-ons can extend the pattern.

### Step 7–8 — portal app.py + chat.html

`compare_enabled = os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1"` is read per-request in the `/chat` handler. The unset default of `"1"` preserves behavior for upgrade-in-place users; `setup.sh` writes the explicit value for new installs.

`chat.html`:
- `+ Compare` button at line 1474 wrapped in `{% if compare_enabled %}`.
- Column B `<section data-col="B">` (lines 1500–1527) wrapped likewise.
- `setCompare()` rewritten with an early `if (!btn || !colB) return` — when the markup isn't present the function is a no-op.
- Listener bindings (`btn-compare` click + `btn-compare-close`) null-guarded so the page loads cleanly when the elements are absent.
- New cloud-Model-B fallback path: when no local deep backend is installed, `setCompare(true)` picks the first cloud provider from `State.gallery.cloud_providers` as Model B. This is the min-tier path. If neither deep backend nor cloud is configured, the user gets a clear "add a cloud key in Compute Source" message.

### Step 9–11 — Docs

- `README.md`: tier table rewritten to show "single-pane Chat" / "Ollama" for min and "dual chat-box Compare" / "AeroLLM 70B-4bit" / "AirLLM 405B (operator-gated)" for max. New "Add-ons (min tier)" subsection documents `./arailctl enable compare`.
- `docs/CERTIFIED_MODELS.md`: AirLLM section rewritten — clear "max-tier only, operator-gated" framing, with the arm64 Metal-timeout explanation. Tier column values flipped from `min default` to `max (operator-gated)`.
- `CLAUDE.md`: § "Where ARAIL sits in this workspace" updated to say Ollama is the min-tier local backend (was: AirLLM 70B); § "Two tiers, two surfaces, one CLI" table updated; verbs list adds `enable` / `disable`.

### Step 12–14 — Tests

| File | Cases | What they pin |
|---|---|---|
| `tests/test_tier_install_min.py` | 5 | min extras empty; max keeps airllm; surface matrix matches blueprint; max surfaces superset min; tier descriptions reflect new reality |
| `tests/test_compare_feature_flag.py` | 9 | template renders correctly with flag on/off; handler defaults to enabled when env unset; strict `== "1"` semantics (junk values → disabled) |
| `tests/test_enable_compare_cli.py` | 7 | enable upserts =1; disable flips to =0; idempotent; errors without .env; arailctl rejects unknown features + missing arg |

The template-render tests inject the same Jinja globals that `app.py:355–367` registers at startup (`brand`, `tier_surfaces`, `lab_tier`, `ui_theme`, …) so the template renders without booting the FastAPI app.

The CLI tests run the scripts in a tmpdir via `REPO_ROOT=$tmp_path bash scripts/enable_compare.sh`, which required adding the `${REPO_ROOT:-...}` override hook to both scripts.

### Step 15 — Grep audit

`grep -rn -i "airllm" --include="*.md"` confirmed user-facing docs are clean:
- `README.md` mentions AirLLM only in the operator-gated max context.
- `CLAUDE.md` mentions AirLLM correctly in the max context and one design note (line 148 — "Don't bake AirLLM into the surface").
- `ROADMAP.md` line 71 updated from "both tiers" → "max tier, operator-gated".
- `BLUEPRINTS.md` mentions AirLLM in historical context (the Metal-torch-tensor case study); kept as-is.
- `lab/pkb/compiled/` files mention AirLLM in old compiled state — these are auto-regenerated and not hand-maintained; rebuild on the next portal start will refresh them.

Pre-existing `tests/test_setup_extras.py::test_min_extra_does_NOT_include_pip_audit` was using a regex that didn't tolerate `min = []` — rewritten to parse pyproject.toml with `tomllib` instead.

## Test results

```
$ python -m pytest tests/ -q --ignore=tests/manual --ignore=tests/portal
955 passed, 1 xfailed, 33 warnings in 26.71s
```

Zero regressions. New sprint tests: 21 cases across 3 files, all passing.

## Architect feedback required

None.

## Final state

All 15 build steps complete. The branch `qukaizen/arail-min-tier-simplification` is layered on top of chat-model-sync (PR #44) — it inherits the AirLLM-gating + `_resolve_default_deep_backend() → None` semantics and extends them with the install-time and template-time changes described above. Will need a rebase if PR #44 merges before this PR.

Ready for architect review.
