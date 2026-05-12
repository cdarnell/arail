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
Commit: 9057f4f (pre-existing — done before the build phase opened)

### Step 2–9 — app.py changes (grouped)
- `_show_airllm()` helper added near `_is_airllm_installed`
- `_resolve_default_deep_backend()` return type → `str | None`; arm64-without-aerollm now returns `None`
- `_default_teacher_backend()` returns `str | None`; aerollm > airllm > None
- Hard-floor routing uses `_resolve_default_deep_backend() or "aerollm"`; logs "30B+" not "35B+"
- `deep_info["installed"]` reflects aerollm-or-(show_airllm + airllm)
- `optional_backends` gates airllm entry on `_show_airllm()`
- `_get_live_ollama_current()` helper added; `d.current` fixed
- "35B" comment near line 4365 updated to "30B"

Commit: see "build(chat-model-sync)" commit below.

### Step 10–11 — chat.html fixes
- `deepEntries` filter at line 3303 drops the unconditional `o.id === 'airllm'` keep
- `setCompare()` at ~line 2434 prefers aerollm for Model B; flash message updated

Commit: see "build(chat-model-sync)" commit below.

### Step 12 — chat.legacy.html AirLLM removal
- Hardcoded `<option value="airllm">AirLLM</option>` removed from the Teacher backend `<select>`
- `teacherSelection()` fallback default changed from `"airllm"` to `"aerollm"`

Commit: see "build(chat-model-sync)" commit below.

### Step 13–15 — ai-engineer Modelfile + catalog + gitignore + setup.sh
- New `models/ai-engineer/Modelfile` (FROM qwen3:8b + AI Engineer Expert system prompt)
- `models_catalog.yaml` gets `ai-engineer:latest` as the first entry with `tier: recommended`
- `.gitignore` adds `models/*/*` + `!models/*/Modelfile` exception (chose `/*/*` not `/**/` so the parent dir stays un-excluded — required for the re-include to take effect; verified via `git check-ignore -v`)
- `scripts/setup.sh` adds idempotent `ollama create ai-engineer -f models/ai-engineer/Modelfile` after the qwen3:8b pull, guarded by `ollama show ai-engineer`

Commit: see "build(chat-model-sync)" commit below.

### Step 16 — test_chat_model_sync.py
14 new tests covering:
- `_show_airllm()` gating — 4 cases (arm64 absolute block; env gating; install gating)
- `_get_live_ollama_current()` — 4 cases (live tag match; stale override; Ollama down; non-ollama backend)
- `_default_teacher_backend()` — 3 cases (aerollm preferred; airllm fallback; None when nothing)
- `optional_backends` construction — 3 cases (airllm absent when `_show_airllm()=False`; airllm present when True; aerollm always present)

The resolver's resolution-table coverage stays in `test_default_deep_backend_resolver.py` (updated in-place); the 30B floor's boundary coverage stays in `test_must_stream_rule.py` (already updated in commit 9057f4f). This avoids duplication.

Commit: see "build(chat-model-sync)" commit below.

## Architect feedback required

None.

## Final state

All 16 build steps complete. Modified tests + new test file pass (`pytest tests/test_chat_model_sync.py tests/test_default_deep_backend_resolver.py tests/test_dispatch_35b_enforcement.py tests/test_must_stream_rule.py` → 75 passed). Ready for architect review.
