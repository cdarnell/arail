# Build log: Chat Model Sync — Five-Bug Fix + Defaults Reset

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at f1e29cbc
**Started:** 2026-05-10

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/model_specs.py` | `HARDWARE_FLOOR_TOTAL_B` 35.0 → 30.0; update docstring/comments | Update `test_must_stream_rule.py` boundary tests | TBD |
| 2 | `src/arail/portal/app.py` | Add `_show_airllm()` helper | New test file step 16 | TBD |
| 3 | `src/arail/portal/app.py` | `_resolve_default_deep_backend()`: arm64 + no aerollm → None; update annotation and docstring | Update `test_default_deep_backend_resolver.py` | TBD |
| 4 | `src/arail/portal/app.py` | `_default_teacher_backend()`: aerollm first, then `_show_airllm()` gate | New test file step 16 | TBD |
| 5 | `src/arail/portal/app.py` | Hard-floor routing: replace `"airllm"` with `_resolve_default_deep_backend() or "aerollm"`; update "35B+" log to "30B+" | Update `test_dispatch_35b_enforcement.py` | TBD |
| 6 | `src/arail/portal/app.py` | `deep_info` block: `"installed"` reflects aerollm first, airllm only if `_show_airllm()` | New test file step 16 | TBD |
| 7 | `src/arail/portal/app.py` | `optional_backends`: gate airllm on `_show_airllm()` | New test file step 16 | TBD |
| 8 | `src/arail/portal/app.py` | Add `_get_live_ollama_current()` helper + fix `d.current` at line ~5273 | New test file step 16 | TBD |
| 9 | `src/arail/portal/app.py` | Update remaining "35B" comment → "30B" near line 4365 | (visual only) | TBD |
| 10 | `src/arail/portal/templates/chat.html` | `deepEntries` filter: drop `|| o.id === 'airllm'` | Manual / browser test | TBD |
| 11 | `src/arail/portal/templates/chat.html` | `setCompare()`: prefer aerollm for Model B | Manual / browser test | TBD |
| 12 | `src/arail/portal/templates/chat.legacy.html` | Remove `<option value="airllm">AirLLM</option>` | N/A | TBD |
| 13 | `src/arail/chat/models_catalog.yaml` | Add `ai-engineer:latest` as first entry with `tier: recommended` | N/A | TBD |
| 14 | `models/ai-engineer/Modelfile` | CREATE new file with qwen3:8b base + AI Engineer persona | N/A | TBD |
| 15 | `.gitignore`, `scripts/setup.sh` | Add `models/**/` pattern + `!models/**/Modelfile`; wire ollama create in setup | N/A | TBD |
| 16 | `tests/test_chat_model_sync.py` | NEW test file; 20 cases from ARCHITECTURE.md test strategy | Must pass | TBD |

### Pre-existing tests that need updates due to spec changes

| File | Reason |
|---|---|
| `tests/test_must_stream_rule.py` | `test_hardware_floor_constant_is_35` checks `== 35.0` — must update to 30.0 |
| `tests/test_default_deep_backend_resolver.py` | arm64-without-aerollm, x86_64, Linux, Windows tests expect `"airllm"` — now return `None` or depend on `_show_airllm()` |
| `tests/test_dispatch_35b_enforcement.py` | Hard-floor routing now uses `_resolve_default_deep_backend()` and logs "30B+" |

## Execution

### Step 1 — model_specs.py: HARDWARE_FLOOR_TOTAL_B 35.0 → 30.0
Commit: TBD

### Step 2–9 — app.py changes (grouped)
Commit: TBD

### Step 10–11 — chat.html fixes
Commit: TBD

### Step 12 — chat.legacy.html AirLLM removal
Commit: TBD

### Step 13–15 — ai-engineer Modelfile + catalog + gitignore + setup.sh
Commit: TBD

### Step 16 — test_chat_model_sync.py
Commit: TBD

## Architect feedback required

None yet.

## Final state

TBD
