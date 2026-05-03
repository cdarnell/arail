# Build log: Models Admin + Hard 35B Rule + Dashboard Reorg

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-05-03

## Plan

| # | Files | Change | Commit ref |
|---|---|---|---|
| 1 | `src/arail/model_specs.py` | Add `MODEL_METADATA_OVERRIDES`, `HARDWARE_FLOOR_TOTAL_B`, `get_total_params()`, `must_stream()` | pending |
| 2 | `src/arail/portal/app.py` | Wire `must_stream()` into `_prepare_chat_context` + update `_extract_param_hint` | pending |
| 3 | `src/arail/portal/app.py` | Add `streamed: bool` field to `/api/chat/models` payload | pending |
| 4 | `src/arail/portal/templates/chat.html` | Add `streamed-badge` in `makeOpt` + CSS | pending |
| 5 | `src/arail/portal/app.py` | Five `/api/admin/models/*` endpoints + `_scan_local_models()` helper | pending |
| 6 | `src/arail/portal/templates/admin.html` | Admin Models section HTML + CSS + JS driver | pending |
| 7 | `src/arail/portal/templates/dashboard.html`, `src/arail/portal/static/style.css` | Mission card promotion: `card full` + nav strip | pending |
| 8 | `src/arail/portal/templates/dashboard.html` | Mission Status + Activity Feed paired row comment | pending |

## Execution

### Step 1
*pending*

### Step 2
*pending*

### Step 3
*pending*

### Step 4
*pending*

### Step 5
*pending*

### Step 6
*pending*

### Step 7
*pending*

### Step 8
*pending*

## Architect feedback required

*none*

## Final state

*not yet complete*
