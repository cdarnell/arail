# Build log: Production-Readiness Wrappers (Phase 1)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 2b610d1
**Started:** 2026-05-01

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/portal/scheduler.py` | NEW — inference semaphore + fast-path metrics module. `fastpath_meter` middleware wired after `onboarding_gate` in `app.py`. Metrics-only; no behavior change to chat. | None (QA phase) | — |
| 2 | `src/arail/portal/app.py` | Wrap SIX inference call sites with `async with scheduler.inference_slot(label)`. Site at 3532 also gets `await asyncio.to_thread(...)` (approved deviation §2). | None (QA phase) | — |
| 3 | `pyproject.toml` | Add `security = ["pip-audit>=2.7.0,<3"]` extra; append `pip-audit>=2.7.0,<3` to `max` list. | None (QA phase) | — |
| 4 | `src/arail/portal/security_scan.py` | NEW — pip-audit wrapper. `is_available()`, `status()`, `run_and_persist()`, `stream_scan_events()`, `set_auto_scan()`. Atomic write, chmod 0600, single-flight lock. | None (QA phase) | — |
| 5 | `src/arail/portal/app.py` | Add seven admin endpoints at app.py:2807: perf/queue, cleanup/scan, cleanup/prune, security/status, security/run-scan, security/run-scan/stream, security/auto-scan. | None (QA phase) | — |
| 6 | `src/arail/portal/templates/admin.html` | Production Readiness section (3 cards) + CSS + JS driver (loadPerf, loadCleanup, loadSecurity) + 7th Quick Action button. | None (QA phase) | — |
| 7 | `src/arail/portal/app.py` | Boot-scan task inserted at app.py:370 (hybrid mode only, after dream daemon block). | None (QA phase) | — |
| 8 | `lab/pkb/agents/sre/sre.py`, `lab/pkb/agents/sre/AGENT.md` | Add `_watch_dependency_vulnerabilities` and `_watch_lab_cleanup` watchers; update WATCHERS list; add two rows to AGENT.md table. | None (QA phase) | — |
| 9 | `docs/PUBLISH.md`, `README.md` | NEW PUBLISH.md (sections 1-9). One-line README link. No new route (existing `/docs/{path:path}` serves it). | None (QA phase) | — |

## Execution

### Step 1 — scheduler.py + fastpath_meter middleware
**Plan:** Create `src/arail/portal/scheduler.py` per ARCHITECTURE.md contracts. Wire `fastpath_meter` middleware after `onboarding_gate` in `app.py`. Metrics-only commit.

<!-- Filled in after commit -->
Commit: pending

### Step 2 — Wrap six inference call sites
**Plan:** `async with scheduler.inference_slot(label)` around each of the six inference call sites in `_run_chat_completion_stream` and `_run_chat_completion`. Site 3532 also gets `to_thread` promotion (approved deviation §2).

Commit: pending

### Step 3 — pyproject.toml security extra
**Plan:** `security = ["pip-audit>=2.7.0,<3"]` and append to `max`.

Commit: pending

### Step 4 — security_scan.py
**Plan:** Full implementation per ARCHITECTURE.md interface contracts.

Commit: pending

### Step 5 — Admin endpoints
**Plan:** Seven endpoints inserted at app.py:2807.

Commit: pending

### Step 6 — admin.html Production Readiness section
**Plan:** HTML section + CSS + JS driver + 7th Quick Action button.

Commit: pending

### Step 7 — Boot-scan task
**Plan:** `if _lab_mode() == "hybrid": asyncio.create_task(_boot_security_scan())` at app.py:370.

Commit: pending

### Step 8 — SRE watchers
**Plan:** Two new watcher functions + WATCHERS list update + AGENT.md two-row append.

Commit: pending

### Step 9 — PUBLISH.md + README link
**Plan:** New `docs/PUBLISH.md`, one-line README update.

Commit: pending

## Architect feedback required

_None at time of writing. Deviations §1 and §2 are approved and baked into the plan above._

## Final state

<!-- Filled in after all steps complete -->
