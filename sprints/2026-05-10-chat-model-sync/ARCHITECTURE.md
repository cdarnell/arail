# Architecture: Chat Model Sync — Five-Bug Fix + Defaults Reset

**Date:** 2026-05-10
**Sprint:** 2026-05-10-chat-model-sync

---

## Restatement

The ARAIL chat tab has accumulated five interlocked bugs around model selection. AirLLM, a layer-streaming backend designed for CUDA/Linux, is being shown and routed to on Apple Silicon (arm64) machines where it causes Metal GPU timeouts. The picker shows catalog models that are not installed, creating phantom choices that fail at inference time. The `d.current` chip in the UI reads a stale env-var value rather than the live Ollama state, causing the chip to show the wrong model. The compare-mode auto-picker prefers AirLLM as Model B instead of AeroLLM. The `_resolve_default_deep_backend()` fallback returns `"airllm"` on arm64 when AeroLLM is not built, rather than `None`. Additionally, the hardware floor threshold of 35B needs to drop to 30B, and a new default Model A (`ai-engineer:latest`) needs an Ollama Modelfile scaffold (qwen3:8b base).

---

## Assumptions

- `platform.machine() == "arm64"` reliably identifies Apple Silicon. Rosetta-translated x86 processes on arm64 will report `x86_64` and see the standard non-gated path. This is acceptable: the gating is conservative.
- `ARAIL_DEV_AIRLLM=1` is an operator-only escape hatch. Its presence means the operator has explicitly accepted the Metal-timeout risk. No UX affordance exposes this to regular users.
- Ollama's `/api/tags` endpoint (port 11434) is the ground truth for installed Ollama models. The 1.5 s timeout in `_ollama_installed_models()` is sufficient; if Ollama is down, the picker correctly shows zero Ollama models.
- `lab/models/` on-disk scan remains ground truth for MLX in-process models.
- `aerollm_api` importability remains the proxy for "AeroLLM is built and functional."
- The `ai-engineer:latest` Modelfile needs only to exist in `models/ai-engineer/Modelfile`; `ollama create` is wired into setup.
- `chat.legacy.html` is not user-facing (behind a feature flag); the AirLLM option there is patched for consistency but is not a critical path.

---

## Data flow

```
PROCESS START
  └─► _resolve_default_deep_backend()          [app.py:4965]
        1. ARAIL_DEEP_BACKEND env var (operator override)
        2. arm64 + aerollm_api importable → "aerollm"
        3. [FIX] arm64 + aerollm_api NOT importable → None   ← was "airllm"
        4. non-arm64 + aerollm_api importable → "aerollm"
        5. non-arm64 + aerollm_api NOT importable + _show_airllm() → "airllm"
        6. otherwise → None

HTTP GET /api/chat/models                       [app.py ~5270]
  │
  ├─► current = _get_live_ollama_current(be) OR be.model_name OR "ai-engineer:latest"
  │     [FIX: was getattr(be,"model_name") or os.getenv("MODEL_NAME","default")]
  │
  ├─► _show_airllm() helper                     [NEW]
  │     arm64 → always False (absolute block)
  │     ARAIL_DEV_AIRLLM != "1" → False
  │     otherwise → _is_airllm_installed()
  │
  ├─► optional_backends construction            [app.py:5427]
  │     [FIX] airllm entry only when _show_airllm() is True
  │     aerollm entry always included
  │
  ├─► gallery_view() → only installed models    [arail.chat]
  │     _ollama_installed_models() → live /api/tags  ← ground truth
  │     _mlx_openai_server_models() → :11435/v1/models
  │     _mlx_dir_installed_models() → lab/models/ scan
  │
  └─► JSON response → browser

BROWSER init()                                  [chat.html:3292]
  │
  ├─► State.models = d.gallery.installed (installed only)
  │
  ├─► deepEntries filter                        [chat.html:3303]
  │     [FIX] o.installed || o.id === 'aerollm'
  │     (keeps aerollm visible for install; drops airllm unconditional pass)
  │
  ├─► selectModel(cur) — cur = d.current (live Ollama state)
  │
  └─► setCompare()                              [chat.html:2434]
        [FIX] prefer aerollm for Model B (not airllm)
        const aerollm = deeps.find(m => m.runtime === 'aerollm');
        selectModelB(aerollm || deeps[0]);
```

---

## Interface contracts

### `_show_airllm() -> bool` (NEW, app.py — add near line 5576)

```python
def _show_airllm() -> bool:
    """True iff AirLLM should appear in the UI and optional_backends.

    Rules (first match wins):
      1. arm64 → always False (Metal timeout; absolute block).
      2. ARAIL_DEV_AIRLLM != "1" → False (hidden from regular users).
      3. airllm not installed → False.
      4. Otherwise → True.
    """
    import platform as _platform
    if _platform.machine() == "arm64":
        return False
    if os.getenv("ARAIL_DEV_AIRLLM", "0") != "1":
        return False
    return _is_airllm_installed()
```

### `_resolve_default_deep_backend() -> str | None` (modified, app.py:4965)

- arm64 + aerollm importable → `"aerollm"`
- arm64 + aerollm NOT importable → `None` ← **was "airllm", key fix**
- non-arm64 + aerollm importable → `"aerollm"`
- non-arm64 + _show_airllm() → `"airllm"`
- otherwise → `None`

Callers must handle `None`. Audit all call sites before building.

### `_default_teacher_backend() -> str | None` (modified, app.py:5581)

```python
def _default_teacher_backend() -> str | None:
    if _is_aerollm_installed():
        return "aerollm"
    if _show_airllm():
        return "airllm"
    return None
```

### `_get_live_ollama_current(be) -> str | None` (NEW, app.py)

```python
def _get_live_ollama_current(be: Any) -> str | None:
    """Return the running Ollama model name when be is Ollama-backed."""
    base_url = getattr(be, "base_url", "") or ""
    if "11434" not in base_url and "ollama" not in type(be).__name__.lower():
        return None
    from arail.chat import _ollama_installed_models
    tags = _ollama_installed_models()
    if not tags:
        return None
    cached = getattr(be, "model_name", None)
    ids = [t["id"] for t in tags]
    return cached if cached in ids else ids[0]
```

Then at line 5273:
```python
current = _get_live_ollama_current(be) or getattr(be, "model_name", None) or os.getenv("MODEL_NAME", "ai-engineer:latest")
```

### `optional_backends` (app.py:5427) — airllm gated

```python
optional_backends = []
if _show_airllm():
    optional_backends.append({"id": "airllm", "label": "AirLLM", ...})
optional_backends.append({"id": "aerollm", "label": "AeroLLM", ...})
```

### Hard-floor routing (app.py ~4371) — fix hardcoded "airllm"

```python
optional_backend_name = _resolve_default_deep_backend() or "aerollm"
```

If `None` (arm64, neither backend): log warning and skip routing rather than crash.

### `deepEntries` filter (chat.html:3303)

```js
// Old: .filter(o => o && (o.installed || o.id === 'airllm' || o.id === 'aerollm'))
// New:
.filter(o => o && (o.installed || o.id === 'aerollm'))
```

### `setCompare()` (chat.html ~2434)

```js
// Old: deeps.find(m => m.runtime === 'airllm')
// New:
const aerollm = deeps.find(m => m.runtime === 'aerollm');
selectModelB(aerollm || deeps[0]);
```

Also update comment at ~2430: "Auto-pick AeroLLM if present, otherwise first installed deep backend."

### `HARDWARE_FLOOR_TOTAL_B` (model_specs.py:277)

Change `35.0` → `30.0`. Update inline comment at line 276, docstring in `must_stream()` at line 302, and comment + activity_log message in app.py around line 4365/4373.

### `models/ai-engineer/Modelfile` (NEW FILE)

```
FROM qwen3:8b

SYSTEM """You are ai-engineer, ARAIL's default local assistant — a senior AI/ML engineer. You reason carefully, write production-grade code, and explain tradeoffs clearly. When you don't know something, say so."""

PARAMETER temperature 0.7
PARAMETER num_ctx 8192
```

Add `models_catalog.yaml` entry:
```yaml
- id: ai-engineer:latest
  name: AI Engineer
  family: qwen
  size_gb: 5.2
  released: 2026-05
  source: ollama
  good_at: [chat, reasoning, agent, code]
  description: ARAIL's default local assistant — Qwen 3 8B base, AI Engineer Expert persona.
  install: "ollama create ai-engineer -f models/ai-engineer/Modelfile"
  tier: recommended
```

Wire into `scripts/setup.sh`:
```bash
if ! ollama show ai-engineer &>/dev/null; then
  ollama create ai-engineer -f models/ai-engineer/Modelfile
fi
```

`.gitignore` update: add `models/**/` exclusion with `!models/**/Modelfile` exception so weight files are never committed but Modelfiles are tracked.

---

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| AirLLM shown on arm64 | `_show_airllm()` returns False; airllm absent from `optional_backends` | AirLLM never in picker or compare mode |
| Phantom catalog model selected | Picker State.models sourced from `gallery.installed` (live Ollama tags) only | Picker only shows installable/installed; catalog shows install command |
| Ollama down at /api/chat/models time | `_ollama_installed_models()` returns [] after 1.5 s timeout | gallery.installed = []; graceful degradation |
| `_resolve_default_deep_backend()` returns None | Return type `str \| None`; callers check before use | Hard-floor routing logs warning and skips; no crash |
| AeroLLM not built on arm64 | `_is_aerollm_installed()` = False; aerollm entry has `installed: false` | Picker shows aerollm with install command; Model B auto-pick skipped with flash |
| d.current stale | `_get_live_ollama_current()` queries live Ollama; falls back to cached model_name | Chip shows correct model |
| 30-35B model threshold change | `must_stream("deepseek-r1:32b")` now True (was False at 35B) | Routed to deep backend; behavior change is intentional and documented |
| Hard-floor routing on arm64 | Line 4371 now uses `_resolve_default_deep_backend()` | Routes to aerollm; skips with warning if neither available |
| `ai-engineer:latest` not in Ollama | d.current falls back to first installed model | No crash; picker defaults to first installed |
| ARAIL_DEV_AIRLLM=1 on arm64 | `_show_airllm()` checks arm64 first; always False | AirLLM still hidden |

---

## Test strategy

### New test file: `tests/test_chat_model_sync.py`

**`_show_airllm()` gating (4 cases):**
- arm64 + any env → False
- x86_64 + ARAIL_DEV_AIRLLM unset → False
- x86_64 + ARAIL_DEV_AIRLLM=1 + airllm importable → True
- x86_64 + ARAIL_DEV_AIRLLM=1 + airllm NOT importable → False

**`_resolve_default_deep_backend()` (5 cases):**
- arm64 + aerollm importable → "aerollm"
- arm64 + aerollm NOT importable → None ← regression test: was "airllm"
- x86_64 + aerollm NOT importable + ARAIL_DEV_AIRLLM unset → None (airllm also hidden)
- ARAIL_DEEP_BACKEND=aerollm → "aerollm" (override wins)
- ARAIL_DEEP_BACKEND=badvalue → falls through to auto-detect

**`must_stream()` threshold (4 cases):**
- 30.1B → True (new threshold)
- 29.9B → False
- 35.0B → True (still above 30B)
- "" → False

**`_get_live_ollama_current()` (3 cases):**
- Ollama returns ["ai-engineer:latest"] + be.model_name matches → be.model_name
- Ollama returns ["ai-engineer:latest"] + be.model_name = "old" → "ai-engineer:latest"
- Ollama down → None

**`optional_backends` API (3 cases):**
- arm64 mock → airllm entry absent
- x86_64 + ARAIL_DEV_AIRLLM=1 → airllm entry present
- aerollm always present

### Integration
- `GET /api/chat/models` arm64 mock: no airllm in optional_backends
- `GET /api/chat/models` Ollama mocked → ["ai-engineer:latest"]: d.current = "ai-engineer:latest"
- `GET /api/chat/models` Ollama down: 200 response, gallery.installed = []

### Regression
- `must_stream("Llama-3.1-70B")` → True (70 > 30, unchanged)
- `must_stream("Qwen3-8B")` → False (8 < 30, unchanged)
- `must_stream("deepseek-r1:32b")` → True ← intentional behavior change; document in test

---

## Tech debt

**Added:**
- `_get_live_ollama_current()` is a narrow BUG-3 fix; the real fix is a live `model_name` property on the router. Follow-up: "Router should expose live_model() method."
- `_show_airllm()` adds a third boolean helper; could unify into a BackendRegistry. Follow-up: "Consolidate backend availability checks."
- `models/ai-engineer/` establishes a new top-level directory convention. Follow-up: "Define canonical location for custom Ollama Modelfiles."

**Repaid:**
- Removes silent arm64 AirLLM routing failure (OOM / Metal timeout risk eliminated)
- Removes phantom model entries from picker
- Removes stale d.current chip
- Aligns hardware floor with actual fleet specs

**Net: negative debt** — more repaid than added.

---

## Implementation order

1. `model_specs.py` — `HARDWARE_FLOOR_TOTAL_B` 35.0 → 30.0; update comments/docstring
2. `app.py` — add `_show_airllm()` helper
3. `app.py` — fix `_resolve_default_deep_backend()` arm64 fallback → None
4. `app.py` — fix `_default_teacher_backend()` preference order
5. `app.py` — fix hard-floor routing (~line 4371)
6. `app.py` — fix `deep_info` block (~lines 5395–5418)
7. `app.py` — gate `optional_backends` airllm entry on `_show_airllm()`
8. `app.py` — add `_get_live_ollama_current()` + fix `d.current` (~line 5273)
9. `app.py` — update comment at ~line 4365 "35B" → "30B"
10. `chat.html` — fix `deepEntries` filter (line 3303)
11. `chat.html` — fix `setCompare()` aerollm preference (~line 2434)
12. `chat.legacy.html` — remove hardcoded AirLLM `<option>`
13. `models_catalog.yaml` — add `ai-engineer:latest` entry
14. `models/ai-engineer/Modelfile` — create new file
15. `.gitignore` — add models/ pattern with Modelfile exception
16. `tests/test_chat_model_sync.py` — new test file per test strategy above
