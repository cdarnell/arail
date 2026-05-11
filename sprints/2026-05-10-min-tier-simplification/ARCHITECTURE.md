# Architecture: Min-tier Simplification — Drop AirLLM, defer Compare

**Date:** 2026-05-10
**Sprint:** 2026-05-10-min-tier-simplification
**Predecessor:** 2026-05-10-chat-model-sync (the AirLLM-gating + `None`-return work this sprint relies on)

---

## Restatement

ARAIL's minimalist (`min`) tier currently advertises "AirLLM 70B (Llama-3.1-70B)" as its deep-mode backend. The recent chat-model-sync sprint made AirLLM invisible on arm64 and gated it behind `ARAIL_DEV_AIRLLM=1` on x86 — so the advertised feature was already nearly unreachable for regular users. This sprint completes the simplification by **removing AirLLM from the `min` install entirely**, **removing all deep-backend defaults from `min`** (Ollama becomes the only local inference path), and **deferring the dual chat-box "Compare" feature to an explicit add-on**.

After this lands:

- `pip install -e ".[min]"` installs no deep-backend packages.
- A fresh `./arailctl setup` with `LAB_TIER=min` writes `ARAIL_COMPARE_ENABLED=0` to `.env`.
- The portal hides the `+ Compare` button when `ARAIL_COMPARE_ENABLED=0`.
- `./arailctl enable compare` flips the flag; `./arailctl disable compare` reverts.
- `max` is unchanged; it keeps AirLLM (subject to chat-model-sync's gating) and `ARAIL_COMPARE_ENABLED=1`.

---

## Assumptions

- `_resolve_default_deep_backend()` returning `None` is handled gracefully at every site (chat-model-sync PR #44 audited this).
- Operators who actively need AirLLM on `min` can `./arailctl upgrade max` or set `ARAIL_DEV_AIRLLM=1` and install AirLLM by hand; both paths are documented.
- The `airllm` Python package install is the only `min`-tier extra worth removing — the rest of the base deps (`lancedb`, `pyyaml`, etc.) stay.
- Upgrade-in-place users (existing min installs without the env var) keep seeing the compare button — the env default is `"1"` when unset. Only NEW `min` installs explicitly write `0`.
- The CLI verb space (`./arailctl enable …`) is currently empty; introducing it doesn't collide with existing verbs (`setup`, `start`, `stop`, `upgrade`, `pkb`, `benchmark_models`, …).
- The Compare add-on UX with no local deep backend uses **cloud Model B**: when the user toggles Compare on min, the picker shows cloud providers as Model B candidates (requires `LAB_MODE=hybrid` and a configured key). This decision was made before sprint start. **Implementation note**: chat.html `setCompare()` and `renderPickerB()` need a small adjustment so cloud providers become valid Model B candidates when no `badge === 'deep'` model is present. The current behavior just flashes "no deep backend installed" — we need to fall back to cloud picks.

---

## Data flow

```
fresh install
  └─► ./arailctl setup
        ├─► capture_tier()                            [scripts/setup.sh:866]
        │     └─► writes LAB_TIER=min|max
        ├─► install_core_deps()                       [scripts/setup.sh:525]
        │     └─► pip install -e ".[dev,<tier>]"
        │           - min: NO airllm (was: airllm>=2.0)
        │           - max: unchanged
        ├─► setup_env()                               [scripts/setup.sh — env writer]
        │     └─► writes ARAIL_COMPARE_ENABLED to .env
        │           - min: "0"
        │           - max: "1"
        └─► (rest of setup unchanged)

post-install add-on
  └─► ./arailctl enable compare
        └─► scripts/enable_compare.sh
              └─► upserts ARAIL_COMPARE_ENABLED=1 in .env
                  (idempotent; uses the same env-writer helper as upgrade.sh)

  ./arailctl disable compare
        └─► scripts/disable_compare.sh
              └─► upserts ARAIL_COMPARE_ENABLED=0 in .env

runtime
  └─► portal app handler renders /chat
        ├─► compare_enabled = os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1"
        ├─► passes compare_enabled into the Jinja template context
        └─► chat.html
              {% if compare_enabled %}
                <button id="btn-compare">+ Compare</button>
                <!-- column B markup -->
              {% endif %}
```

---

## Interface contracts

### `pyproject.toml` — `[project.optional-dependencies]`

```toml
# BEFORE
min = ["airllm>=2.0"]
max = ["jupyterlab>=4.0.0", "anthropic>=0.31.0", "langchain>=0.2.0", "langgraph>=0.2.0", "airllm>=2.0", "pip-audit>=2.7.0,<3"]

# AFTER
min = []                                              # Ollama-only; no Python extras beyond base deps
max = ["jupyterlab>=4.0.0", "anthropic>=0.31.0", "langchain>=0.2.0", "langgraph>=0.2.0", "airllm>=2.0", "pip-audit>=2.7.0,<3"]
```

Empty list (`[]`) is valid TOML and is treated by setuptools as "no extras"; `pip install -e ".[min]"` is a no-op on top of base deps.

### `pyproject.toml` — `[tool.arail.tiers]` description strings

The `description` field for `min` currently mentions "aeroLLM on Apple Silicon... AirLLM on CUDA / Linux x86". Rewrite to:

```toml
min = { description = "Minimalist — Dashboard, Chat (single box), Autoresearch, Knowledge Base (with LanceDB vector recall), Agents. Local inference via Ollama (ai-engineer:latest by default). No deep-streaming backend; upgrade to max or run ./arailctl enable compare to add features.", surfaces = ["dashboard", "chat", "research", "knowledge", "agents"] }
```

`max` description gets a small clarification:

```toml
max = { description = "Maximalist — Everything in min + Admin, Docs, Notebooks, dual chat-box Compare on by default, LangChain/LangGraph, full cloud catalog. Deep mode runs aeroLLM Llama-3.1-70B-4bit on Apple Silicon (~35 GB, needs 48 GB+ Mac) or AirLLM Llama-3.1-405B on CUDA (operator-gated via ARAIL_DEV_AIRLLM=1).", surfaces = [...] }
```

### `pyproject.toml` — comment block at lines 35–47

Rewrite the comment block to match the new reality. Drop the AirLLM advertisement; describe min as Ollama-only.

### `scripts/setup.sh` — tier-default writes

In `capture_tier()` (lines 919–936), modify the tier-specific writes:

- **min**: Skip the `AIRLLM_MODEL_ID` and `AEROLLM_MODEL_ID` assignments. (Or leave the variables empty; the resolver handles `None` deep backend cleanly post-chat-model-sync.)
- **max**: Unchanged.

In `setup_env()` (or wherever `.env` writes happen — find by `grep -n "setup_env\|LAB_TIER" scripts/setup.sh`), add a line that writes `ARAIL_COMPARE_ENABLED`:

```bash
# After LAB_TIER is set, before .env close.
if [[ "$LAB_TIER" == "min" ]]; then
    write_env_var "ARAIL_COMPARE_ENABLED" "0"
else
    write_env_var "ARAIL_COMPARE_ENABLED" "1"
fi
```

In `download_model()` (lines 1262–1294), skip the AirLLM model download instructions when `LAB_TIER == "min"`.

### `scripts/upgrade.sh` — preserve / set the compare flag

When upgrading **min → max**, set `ARAIL_COMPARE_ENABLED=1` if the flag isn't already present in `.env`. (Don't overwrite an explicit user setting.)

When upgrading **max → min**, leave the flag alone — the user keeps compare if they had it on; they can `./arailctl disable compare` to clean up.

### `scripts/enable_compare.sh` (NEW)

```bash
#!/usr/bin/env bash
# Enable the dual chat-box Compare feature.
# Idempotent — flips ARAIL_COMPARE_ENABLED=1 in .env.
set -euo pipefail
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$REPO_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: .env not found at $ENV_FILE. Run './arailctl setup' first." >&2
    exit 1
fi

# Reuse the same env-writer helper used by upgrade.sh.
# (Look at scripts/upgrade.sh's Python helper — likely _write_env_var or similar.)
python3 - "$ENV_FILE" "ARAIL_COMPARE_ENABLED" "1" <<'PY'
import sys
from pathlib import Path
env_path, key, value = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
lines = env_path.read_text().splitlines() if env_path.exists() else []
out, found = [], False
for ln in lines:
    if ln.strip().startswith(f"{key}="):
        out.append(f"{key}={value}")
        found = True
    else:
        out.append(ln)
if not found:
    out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n")
PY

echo "✓ Compare mode enabled (ARAIL_COMPARE_ENABLED=1 in .env)."
echo "  Restart the portal with: ./arailctl restart"
```

### `scripts/disable_compare.sh` (NEW)

Symmetric — same script with `"0"` instead of `"1"`. (Could alternatively share a single script with an argument; keep them separate for clarity and short command lines.)

### `arail` shell script (top-level) — new verbs

Find the verb dispatch (where `setup|start|stop|upgrade|pkb|...` are routed). Add:

```bash
enable)
    if [[ "${2:-}" != "compare" ]]; then
        echo "Usage: ./arailctl enable compare" >&2
        exit 2
    fi
    exec bash "$REPO_ROOT/scripts/enable_compare.sh"
    ;;
disable)
    if [[ "${2:-}" != "compare" ]]; then
        echo "Usage: ./arailctl disable compare" >&2
        exit 2
    fi
    exec bash "$REPO_ROOT/scripts/disable_compare.sh"
    ;;
```

(`enable compare` is the only currently-supported add-on; the verb space is reserved for future ones.)

### `src/arail/portal/app.py` — template context

In the chat page handler, add `compare_enabled` to the template context:

```python
compare_enabled = os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1"
return templates.TemplateResponse("chat.html", {
    "request": request,
    # … existing context …
    "compare_enabled": compare_enabled,
})
```

The unset default of `"1"` preserves current behavior for existing installs.

### `src/arail/portal/templates/chat.html` — Jinja conditional

Wrap the `+ Compare` button (~line 2428) and the column B markup (~line 2426 onwards through the close of the column B div) in:

```jinja
{% if compare_enabled %}
  <!-- existing compare/column-B markup -->
{% endif %}
```

Also wrap the JavaScript `setCompare()` definition + button binding (~lines 2418–2443) so the JS doesn't error out when the button doesn't exist. Alternatively, leave the JS but guard the `addEventListener` calls with null-checks. Pick one approach; prefer the Jinja wrap for clean separation.

### Compare-with-cloud Model B (new behavior on min)

When compare is enabled on a system with no `badge === 'deep'` model available, `setCompare(true)` should fall back to showing cloud providers as Model B candidates. Change in `chat.html`:

```js
// Old (after PR #44):
const deeps = State.models.filter(m => m.badge === 'deep' && m.installed);
if (deeps.length) {
    const aerollm = deeps.find(m => m.runtime === 'aerollm');
    selectModelB(aerollm || deeps[0]);
} else {
    flashStatus('compare on, but no deep backend is installed (AeroLLM)');
}

// New:
const deeps = State.models.filter(m => m.badge === 'deep' && m.installed);
if (deeps.length) {
    const aerollm = deeps.find(m => m.runtime === 'aerollm');
    selectModelB(aerollm || deeps[0]);
} else {
    // No local deep backend (min tier). Fall back to cloud providers.
    const cloud = (State.gallery && State.gallery.cloud_providers) || [];
    if (cloud.length) {
        selectModelB(cloud[0]);
        flashStatus('compare on · column B = cloud provider (no local deep backend)');
    } else {
        flashStatus('compare on, but no deep backend or cloud provider configured. Add a cloud key in Compute Source.');
    }
}
```

Whether `State.gallery.cloud_providers` already exists from `/api/chat/models` needs verification before building. If not, we either (a) plumb it through, or (b) accept a degraded experience where the user manually picks a cloud Model B from the existing Compute Source pivot. **Defer to a follow-up if plumbing cloud_providers into the picker is more than a small change** — the min-with-compare add-on is non-default and we shouldn't block this sprint on a perfect first-iteration.

### `README.md` — tier table

Rewrite the tier table near "Two tiers, two surfaces, one CLI" to reflect:

| Tier  | What's in it                                                                                                                                              |
|-------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `min` | Dashboard · Single-pane Chat · Autoresearch · Knowledge Base · Agents · LanceDB vectors · Ollama (`ai-engineer:latest`) — the everyday lab                 |
| `max` | + Admin · Docs · Notebooks · Dual chat-box Compare · AeroLLM 70B-4bit · AirLLM 405B · Anthropic SDK · LangChain · full cloud SDKs — the frontier-scale bench |

Add a brief "Add-ons" subsection:

```markdown
### Add-ons (min tier)

Min ships intentionally lean. Add features as you need them:

- `./arailctl enable compare` — turn on the dual chat-box comparison view.
  Disable with `./arailctl disable compare`.

The `max` tier includes all add-ons by default.
```

### `docs/CERTIFIED_MODELS.md` — AirLLM section

The "AirLLM fallback" section's tier column says `min default` for the 70B row. Rewrite that paragraph to:

```markdown
## Local inference — AirLLM fallback

AirLLM is a max-tier optional fallback for non-arm64 hosts (CUDA / Linux x86)
where AeroLLM has no fast path. It requires the operator to opt in via
`ARAIL_DEV_AIRLLM=1` — Apple Silicon machines never see it (Metal aborts
caused timeouts; the chat-model-sync sprint closed that risk).

| Model | Quantization | Status | Tier | Notes |
|---|---|---|---|---|
| `meta-llama/Llama-3.1-70B-Instruct` | bf16 | **Compatible** | `max` (operator-gated) | Layered load. Slow but works. |
| `meta-llama/Llama-3.1-405B-Instruct` | bf16 | **Compatible** | `max` (operator-gated) | Frontier-scale bench model. |
| `meta-llama/Llama-4-Maverick-17B-128E-Instruct-fp8` | fp8 | **Compatible** | `max` (operator-gated) | MoE model. |
```

Drop the "downloaded automatically by `./arailctl setup` based on tier selection" sentence — for `min` it's no longer true, and for `max` it requires the dev flag.

### `CLAUDE.md` — tier reference

The tier table in the "Quick reference" section (and the inline reference near "Two tiers, two surfaces, one CLI") needs the same one-line update. Drop "AirLLM 70B (Llama-3.1-70B)" from the `min` row; add a note about Compare being an add-on.

### Tests (new files)

**`tests/test_tier_install_min.py`** (3–4 cases):
- Asserts `[project.optional-dependencies.min]` parses to an empty list (no `airllm`).
- Asserts `[tool.arail.tiers].min.surfaces` matches expected list (`["dashboard", "chat", "research", "knowledge", "agents"]`).
- Asserts `[project.optional-dependencies.max]` still contains `"airllm>=2.0"` (regression guard).

**`tests/test_compare_feature_flag.py`** (4–5 cases):
- `ARAIL_COMPARE_ENABLED=0` + template render → no `+ Compare` button in output.
- `ARAIL_COMPARE_ENABLED=1` → button present.
- Flag absent → defaults to `"1"` (button present; upgrade-in-place users preserved).
- Flag set to a junk value (`"yes"`, `"true"`) → strict `== "1"` → button absent (no surprises).

**`tests/test_enable_compare_cli.py`** (3–4 cases):
- `arailctl enable compare` upserts `ARAIL_COMPARE_ENABLED=1` in a tempdir `.env`.
- `arailctl disable compare` upserts to `0`.
- Both are idempotent (running twice doesn't duplicate the line).
- `arailctl enable garbage` exits 2 with usage.

---

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| min user runs `./arailctl chat` with no Ollama installed | Setup already pulls qwen3:8b and creates ai-engineer; abort condition handled by chat-model-sync | Existing fallback messaging in chat.html |
| min user toggles Compare on (after enabling) with no cloud key | `setCompare()` sees no deeps + no cloud → flashes a clear "configure a cloud key" hint | User adds a key in Compute Source pivot |
| Upgrade-in-place user with no `ARAIL_COMPARE_ENABLED` in .env | env var default is `"1"` when unset → compare visible (current behavior preserved) | None needed |
| User runs `./arailctl enable compare` without a `.env` | Script errors with "Run ./arailctl setup first" exit 1 | Run setup |
| max → min downgrade preserves compare flag | upgrade.sh leaves it alone; user keeps compare if they had it | `./arailctl disable compare` if unwanted |
| `airllm` was already installed in venv from prior `[min]` install | `pip install -e ".[min]"` is idempotent; airllm stays installed but is no longer wired up by setup. `_show_airllm()` still gates visibility. | None; no harm |
| Documentation says "min has AirLLM" somewhere we missed | docs/CERTIFIED_MODELS.md + README.md + CLAUDE.md + pyproject.toml comment block all updated; grep for "AirLLM" + "min" before commit | Final grep audit during review |

---

## Test strategy

QA allocation: **40% tier-correctness / 25% setup-flow / 20% upgrade-path / 15% regression**.

- **40% Tier correctness** — pyproject extras parsing, env-var writes by setup.sh, compare flag respected by template.
- **25% Setup flow** — first-run `min` writes `ARAIL_COMPARE_ENABLED=0`; first-run `max` writes `=1`; setup doesn't write `AIRLLM_MODEL_ID` on min.
- **20% Upgrade path** — `min → max` sets `=1` when unset, leaves explicit user value; `max → min` preserves whatever's there.
- **15% Regression** — chat-model-sync tests still pass (95 sprint, 1037 full repo).

---

## Tech debt

**Added:**
- Two new shell scripts (`enable_compare.sh`, `disable_compare.sh`) — could be consolidated into one parameterized script. Followup: "Consolidate enable/disable into single `feature.sh` script."
- The `compare_enabled` template-context plumb is per-handler — if more feature flags follow, refactor into a context processor. Followup: "Feature-flag context processor."
- Cloud Model B in `chat.html` relies on `State.gallery.cloud_providers` which may or may not exist. Verify during build. Followup: "Plumb cloud_providers into /api/chat/models payload if missing."

**Repaid:**
- Removes the "AirLLM 70B in min" advertisement that was already nearly unreachable.
- Reduces first-run install size for min users (no airllm package pulled).
- Aligns the README and CERTIFIED_MODELS docs with the chat-model-sync gating reality.

**Net:** roughly neutral. The simplification is the point — there's no big-bang architectural change.

---

## Implementation order

1. `pyproject.toml` — empty `min` extras, update tier descriptions, rewrite comment block
2. `scripts/setup.sh` — tier-default writes (skip AirLLM for min; write `ARAIL_COMPARE_ENABLED`)
3. `scripts/upgrade.sh` — min→max sets compare flag when unset
4. `scripts/enable_compare.sh` — NEW
5. `scripts/disable_compare.sh` — NEW
6. `arail` top-level — add `enable` and `disable` verbs
7. `src/arail/portal/app.py` — add `compare_enabled` to chat-template context
8. `src/arail/portal/templates/chat.html` — Jinja-wrap compare button + column B markup + JS bindings; cloud Model B fallback in `setCompare()`
9. `README.md` — tier table + Add-ons subsection
10. `docs/CERTIFIED_MODELS.md` — AirLLM section rewrite
11. `CLAUDE.md` — tier reference one-liner
12. `tests/test_tier_install_min.py` — NEW
13. `tests/test_compare_feature_flag.py` — NEW
14. `tests/test_enable_compare_cli.py` — NEW
15. Grep audit: `grep -ri "airllm" --include='*.md'` and confirm only max-context mentions remain in user-facing docs
