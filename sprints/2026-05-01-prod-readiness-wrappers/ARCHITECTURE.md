# Architecture: Production-Readiness Wrappers (Phase 1)

**Date:** 2026-05-01
**Sprint:** [2026-05-01-prod-readiness-wrappers](./SPRINT.md)
**Approved plan seed:** `/Users/netsushi/.claude/plans/i-have-the-site-tranquil-milner.md`
**Branch:** `qukaizen/arail-prod-readiness` (off main, fast-forwarded to `89bbcda`)

---

## Restatement

ARAIL is about to ship as a publishable product. Three concrete pre-ship
gaps exist: (1) inference-thread starvation makes lightweight tabs lag
when chat is running locally, (2) there is no CVE / dependency security
surface despite the user planning to expose instances on the public
internet, and (3) there is no operator runbook for users who want to
publish their own lab the way the user did with `qukaizen.com`. This
sprint adds an in-process inference semaphore + fast-path bypass
middleware (Phase 1; multi-worker isolation deferred to Phase 2), a
"Production Readiness" admin section with three live cards
(Performance / Cleanup / Security), a `pip-audit`-backed security scan
module that runs at boot in hybrid mode and on demand always, two new
SRE watchers (CVE + cleanup), and `docs/PUBLISH.md`. None of this
breaks the airgapped default, none touches the rebrand surface, and
none modifies external-package contracts.

---

## Line-reference verification (post-rebase)

The plan's line refs are stale due to a 23-commit fast-forward. Verified
current locations below; **all line numbers in the rest of this document
are post-rebase**:

| Plan claim | Actual location | Notes |
|---|---|---|
| `onboarding_gate` middleware @ app.py:108 | **app.py:108–144** | Unchanged |
| Startup hook @ app.py:195–289 | **app.py:195–370** | Body grew; `seed_all_on_startup` is at **app.py:285–286**; the agent-loader / dream-daemon block ends at **app.py:370**. Boot-scan task should be appended at **app.py:370** (immediately before `_register_canvas_goal_listener` at app.py:373) so it runs after every other startup task is launched. |
| `_lab_mode()` / `_is_airgapped()` @ app.py:687–692 | **app.py:693–698** | Unchanged shape. |
| Airgapped guard call sites @ app.py:788, 834, 856, 888 | **app.py:794, 840, 867, 897** | All four still present and structurally identical. |
| `_stream_sync_iterator` @ app.py:3285 | **app.py:3277–3299** (definition); the call site to wrap is **app.py:3405–3412** (`async for item in _stream_sync_iterator(router.stream_complete(…))`). | The wrap target is the `async for` block, not the helper. |
| Deep-backend stream @ app.py:3335–3341 | **app.py:3341–3347** | `await asyncio.to_thread(deep_backend.complete, …)` inside `_run_chat_completion_stream`. |
| Runtime override stream @ app.py:3374–3377 | **app.py:3380–3383** | `await asyncio.to_thread(runtime_backend.complete, …)`. |
| Deep-backend non-stream @ app.py:3484–3487 | **app.py:3490–3493** | `await _aio.to_thread(deep_backend.complete, …)` inside `_run_chat_completion`. |
| Runtime non-stream @ app.py:3505–3508 | **app.py:3517–3520** | `await _aio.to_thread(runtime_backend.complete, …)`. Plus a fifth synchronous call at **app.py:3532** (`response = router.complete(...)` — no `to_thread`). **NEW FINDING — see "Failure modes" §F1.** |
| `markdown_it` import @ app.py:1314 | **app.py:1320** | Imported lazily inside `_render_markdown_page` (app.py:1317). Renderer uses `html=False` already. |
| `/docs/{name}` route — plan says "small ~15 LOC handler" | **already implemented as `/docs/{path:path}` at app.py:1409–1433** | Existing handler enforces `.md` whitelist, no `..`, path containment, 404 on missing. **`docs/PUBLISH.md` is reachable today via `/docs/PUBLISH.md` with no new code.** See "Plan deviations requested" §1. |
| Quick Actions @ admin.html:521–545 | **admin.html:521–545** | Unchanged; 6 buttons today, the new "Publish Guide" makes 7. |
| Service Status block @ admin.html:548 | **admin.html:548–551** | Unchanged. New `<div class="admin-section">` for Production Readiness inserts at **admin.html:552** (immediately after the Service Status section closes). |
| Live-Checks SSE modal helper @ admin.html:499–515 | **admin.html:499–515** (modal shell) + **admin.html:744–841** (JS driver `runLiveChecks` / `_streamLiveChecks` / `_lcInitPending` / `_lcUpdateRow` / `_lcFinish`) | The modal expects events `{event:"check", index, total, name, status, duration_ms, detail?}` and `{event:"done", passed, warned, failed, total, total_ms}`. `/api/admin/security/run-scan/stream` MUST emit this exact shape. |
| `check-updates` endpoint @ app.py:2730 (insertion target) | **app.py:2736–2761 (`check-updates`) + app.py:2764–2807 (`check-updates/stream`)** | New `/api/admin/{perf,cleanup,security}/*` group inserts at **app.py:2807** (after the existing stream handler returns). |
| SRE `_watch_service_health` end @ sre.py:283 | **sre.py:283** | Unchanged. New watchers insert at **sre.py:284**. |
| SRE `WATCHERS` list @ sre.py:286 | **sre.py:286–290** | Append two new names. |
| AGENT.md watcher table @ lines 31–35 | **AGENT.md:31–35** | Unchanged; append two rows. |
| `[project.optional-dependencies]` in pyproject.toml | **pyproject.toml:35** (header) | `min` at L51, `max` at L54–60. New `security` extra inserts before `# ── Hardware/runtime extras ───` at L62. Append `pip-audit>=2.7.0,<3` to the `max` list. |
| `markdown-it-py` base dep | **pyproject.toml:28** | Confirmed base. No new base deps required. |
| `scripts/start.sh` uvicorn invocation @ L36–38 | **scripts/start.sh:36–38** | Single-worker; no `--workers` flag. Phase 2 candidate. |

---

## Assumptions

1. **uvicorn runs single-worker** (`scripts/start.sh:36–38`). The
   `INFERENCE_SEMAPHORE` lives in process memory and is therefore one
   global queue. If anyone sets `--workers >1` later, the semaphore
   becomes per-worker — that's acceptable but must be documented as
   the Phase-2 trigger.
2. **The asyncio event loop is the same loop for the lifetime of the
   app.** Lazy semaphore init happens via `_get_semaphore()` inside
   `inference_slot()`, so the first call materializes it on the running
   loop. The plan does not call `asyncio.Semaphore(...)` at import
   time (which would bind to the wrong loop in some test harnesses).
3. **`asyncio.to_thread` uses the default loop executor** (a
   `ThreadPoolExecutor` with `min(32, os.cpu_count()+4)` workers as of
   Python 3.10+). The semaphore caps inference concurrency BEFORE we
   reach `to_thread`, so the thread pool is never the bottleneck for
   inference. Lightweight `to_thread` calls elsewhere (probes, file
   I/O) are unwrapped and continue to share the executor — fine because
   the semaphore is the bottleneck-of-last-resort, not the only queue.
4. **`LAB_MODE` is loaded by `dotenv` at `arail.config` import time**
   (`config.py:22`), and `app.py` imports `arail.config` at module
   top (app.py:26). Therefore `_lab_mode()` is correct by the time the
   `@app.on_event("startup")` handler runs. **No race**. Verified.
5. **`pip-audit` JSON schema is stable across the `>=2.7.0,<3` window.**
   We pin a major-version cap and validate the parsed JSON shape
   (`dependencies: [{name, version, vulns: [{id, fix_versions, …}]}]`)
   on every parse. On schema mismatch we fall back to `available=False`
   with a clear error rather than crashing.
6. **There is no live `LAB_MODE` change hook.** Flipping `.env`
   requires a portal restart. The boot scan triggers on restart in
   hybrid mode; the manual "Run scan now" button works in either mode
   (explicit user click satisfies the no-involuntary-outbound-call
   rule).
7. **`activity_log.emit()` accepts levels `info | success | warn |
   error`** (verified at `arail/activity.py:50–57`); SRE's existing
   convention is to call `emit("sre", …, "warn")` regardless of
   internal Observation severity (verified at `sre.py:399–408`). New
   watchers follow the same pattern; severity ranking is internal-only.
8. **`markdown-it-py` is already a base dep** (`pyproject.toml:28`).
   Renderer is initialized with `html=False` at `app.py:1324` — raw
   HTML in markdown is escaped, not executed. PUBLISH.md inherits
   this safety.
9. **The `/docs/{path:path}` route at app.py:1409–1433 already exists
   and already enforces `.md` whitelist + path containment + 404.**
   Serving `docs/PUBLISH.md` requires no new route. (See "Plan
   deviations requested" §1.)
10. **`DATA_DIR`, `MODELS_DIR`, `LAB_ROOT` are stable absolute paths**
    resolved at `config.py:64–66`. Cleanup endpoint scans only those
    three roots plus `LAB_ROOT/pkb/.wiki-cache`. No symlink-following.
11. **Single-flight at module level is sufficient** for the security
    scan because uvicorn is single-worker (assumption #1). When that
    changes (Phase 2), the lock becomes per-worker and we add a
    file-lock at `DATA_DIR / "security" / ".scan.lock"` — out of scope
    here.

---

## Data flow

### Inference queue (per-request, fast path vs heavy path)

```
                  ┌──────────────────────────────────┐
client request -->│ uvicorn (single worker)          │
                  │  ↓                               │
                  │ @app.middleware onboarding_gate  │  app.py:108
                  │  ↓                               │
                  │ @app.middleware fastpath_meter   │  NEW (next after onboarding_gate)
                  │  if path in FAST_PATH_PREFIXES:  │
                  │     t0 = perf_counter()          │
                  │     resp = await call_next(req)  │
                  │     scheduler.fast_path_record(  │
                  │         path, (perf_counter()-t0)*1000)
                  │     return resp                  │
                  │  else:                           │
                  │     return await call_next(req)  │  ← heavy path falls through
                  │  ↓                               │
                  │ FastAPI router → handler         │
                  └──────────────────────────────────┘
                                ↓
              (heavy path: chat handlers wrap each
               inference call site below)

   async with scheduler.inference_slot("chat-stream"):       app.py:3405–3412
       async for item in _stream_sync_iterator(
           router.stream_complete(...)):
           ...
   async with scheduler.inference_slot("chat-stream-deep"):  app.py:3341–3347
       response = await asyncio.to_thread(deep_backend.complete, ...)
   async with scheduler.inference_slot("chat-stream-runtime"): app.py:3380–3383
       response = await asyncio.to_thread(runtime_backend.complete, ...)
   async with scheduler.inference_slot("chat-deep"):          app.py:3490–3493
       response = await _aio.to_thread(deep_backend.complete, ...)
   async with scheduler.inference_slot("chat-runtime"):       app.py:3517–3520
       response = await _aio.to_thread(runtime_backend.complete, ...)
   # Fifth call site at app.py:3532 is a SYNC router.complete in
   # _run_chat_completion's else branch — it currently blocks the
   # event loop. See Failure mode §F1 — must wrap with to_thread AND
   # the slot, or document why we don't.
```

`inference_slot` flow inside the context manager:

```
__aenter__:
  _pending += 1
  t_wait_start = perf_counter()
  await sem.acquire()           # may block; pending stays, released to
                                #   in_flight on success
  t_wait_end = perf_counter()
  _pending -= 1
  _inflight += 1
  push wait sample to deque[label] (maxlen 256)
  store t_run_start in context

__aexit__:                      # try/finally guarantees release
  t_run_end = perf_counter()
  _inflight -= 1
  push run sample to deque[label]
  push completion sample to deque["__completed__"] (5m rolling)
  sem.release()
```

### Boot-scan task (hybrid mode only)

```
@app.on_event("startup")  app.py:195
  ... existing seeding/loader work (app.py:200–369) ...
  ── INSERT AT app.py:370 (after dream-daemon block, before _register_canvas_goal_listener) ──
  if _lab_mode() == "hybrid":
      asyncio.create_task(_boot_security_scan())

  async def _boot_security_scan():
      await asyncio.sleep(30)              # let lab settle; never block startup
      try:
          from arail.portal import security_scan
          await security_scan.run_and_persist(trigger="boot")
      except ImportError:
          activity_log.emit("security",
              "pip-audit not installed — install via ./arail upgrade max to enable CVE scans.",
              "warn")
      except Exception as e:               # noqa: BLE001
          activity_log.emit("security", f"Boot CVE scan failed: {type(e).__name__}: {e}", "warn")
```

`security_scan.run_and_persist` flow:

```
acquire module-level asyncio.Lock _SCAN_LOCK   # single-flight
  if not is_available():
      write status JSON with {available: false, error: "pip-audit not installed"}
      emit activity_log warn, return
  proc = await asyncio.create_subprocess_exec(
      "pip-audit", "-f", "json", "--progress-spinner=off",
      stdout=PIPE, stderr=PIPE)
  out, err = await proc.communicate()      # may take minutes
  if proc.returncode not in (0, 1):        # 1 = vulns found, normal
      write status JSON with {available: true, error: stderr[:500], findings: []}
      emit activity_log warn, return
  parsed = _parse(out)                      # validate schema
  status = {
      last_run_ts, trigger, summary{critical,high,medium,low,total},
      findings[{package,version,id,severity,fix,description}],
      tool: "pip-audit",
      tool_version: <captured at install>,
      available: true,
      auto_scan_enabled: <preserved from prior file>,
  }
  atomic write to DATA_DIR/security/last_scan.json (chmod 0600)
  emit activity_log line:
      severity = error if (critical+high) else warn if medium else info
release lock
return status
```

### Cleanup scan / prune

```
GET /api/admin/cleanup/scan:
  results = []
  for root, kind in [(DATA_DIR, "data"), (MODELS_DIR, "models"),
                     (LAB_ROOT/"pkb"/".wiki-cache", "cache")]:
      for path in safe_walk(root):
          stat = path.stat()
          age_days = (now - mtime) / 86400
          stale = (
              (kind == "cache" and age_days > 30) or
              (kind == "models" and subtree_bytes > 5 * 2**30)
          )
          results.append({path: str, size_bytes, age_days, stale, kind})
  cache_last_scan(results)        # in-memory; key by absolute path
  return {items: results, total_bytes, stale_bytes}

POST /api/admin/cleanup/prune  (single-flight asyncio.Lock _PRUNE_LOCK)
  body.paths must be a non-empty list[str]
  for p in body.paths:
      abs_p = Path(p).resolve(strict=False)
      if not _in_known_root(abs_p):                        return 400
      if not _was_marked_stale(abs_p):                     return 400
      if abs_p.is_symlink():                               skip
      if not abs_p.exists():                               skip
      st = abs_p.stat()                                    # re-stat
      removed_bytes += st.st_size
      abs_p.unlink()  # files only — no dir recursion in v1
  return {removed: count, freed_bytes}
```

---

## Interface contracts

### `src/arail/portal/scheduler.py` (NEW — module surface)

```python
"""In-process inference priority queue + fast-path metrics.

This module exposes a single async semaphore that gates calls into
the local-LLM router. Lightweight HTTP paths (dashboard polls, system
health, etc.) bypass the semaphore via the FAST_PATH middleware so
they never queue behind a 30-second inference response.
"""

from __future__ import annotations
import asyncio, os
from collections import deque
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

# Path prefixes that the fast-path middleware times AND lets through
# without acquiring the inference semaphore. Anything not in this list
# is "heavy" — heavy paths still pass through the middleware (it just
# doesn't time them) and acquire the semaphore inside the handler.
FAST_PATH_PREFIXES: tuple[str, ...] = (
    "/api/system/", "/api/jobs/", "/api/activity/", "/api/agents/status",
    "/api/admin/components", "/api/admin/check-updates",
    "/api/admin/perf", "/api/admin/cleanup", "/api/admin/security",
    "/api/pkb/", "/api/research/", "/static/", "/favicon.ico",
)

def _capacity() -> int:
    """Read ARAIL_INFERENCE_CONCURRENCY env, clamp [1, 4], default 1."""

_SEM: asyncio.Semaphore | None = None
_INFLIGHT = 0
_PENDING = 0
_WAIT_SAMPLES: dict[str, deque[float]] = {}   # ms; per label, maxlen 256
_RUN_SAMPLES: dict[str, deque[float]] = {}    # ms; per label, maxlen 256
_FAST_SAMPLES: deque[float] = deque(maxlen=512)  # ms
_COMPLETED: deque[float] = deque(maxlen=4096)    # epoch sec; for 5m count

def _get_semaphore() -> asyncio.Semaphore:
    """Lazy init on the running loop. Called from inside inference_slot."""

@asynccontextmanager
async def inference_slot(label: str = "chat") -> AsyncIterator[None]:
    """Acquire one inference slot. Records wait_ms + run_ms per label.

    Postcondition: the slot is released even if the body raises. The
    acquire/release uses try/finally so handler exceptions never deadlock.
    Preconditions: caller is inside a running asyncio loop. Bad input:
    label = ""  → recorded under "_unknown"; never raises.
    """

def fast_path_record(path: str, ms: float) -> None:
    """Append a fast-path latency sample. Never raises. Drops on overflow."""

def snapshot() -> dict:
    """Return a JSON-safe metrics snapshot. Always succeeds.

    {
      "capacity": int,
      "in_flight": int,
      "pending": int,
      "completed_5m": int,                       # count of run-completes in last 300s
      "wait_ms":     {"<label>": {"p50": float, "p95": float, "n": int}},
      "run_ms":      {"<label>": {"p50": float, "p95": float, "n": int}},
      "fast_path_ms": {"p50": float, "p95": float, "n": int},
    }
    """
```

### `src/arail/portal/security_scan.py` (NEW — module surface)

```python
"""pip-audit wrapper. Single source of truth for last_scan.json."""

from __future__ import annotations
import asyncio, json, os, shutil
from pathlib import Path
from typing import Literal

_SCAN_LOCK = asyncio.Lock()         # single-flight; one scan at a time

def is_available() -> bool:
    """True iff `pip-audit` CLI is on PATH OR `pip_audit` package is importable."""

def status() -> dict:
    """Read DATA_DIR/security/last_scan.json. If missing, return:
        {"available": is_available(), "last_run_ts": None, "summary": {},
         "findings": [], "tool": "pip-audit", "auto_scan_enabled": False,
         "error": None}
    """

async def run_and_persist(trigger: Literal["boot","manual","sre","sse"]) -> dict:
    """Run pip-audit, write last_scan.json, emit one activity_log line.

    Postcondition: returns the dict that was written. last_scan.json is
    chmod 0600. activity_log is emitted at error if any high/critical,
    warn if medium, info otherwise. Single-flight via _SCAN_LOCK; if a
    scan is already running, waits for it and returns the result.
    """

async def stream_scan_events(trigger: str = "sse"):
    """Async generator yielding the SSE event shape the live-checks
    modal expects: {event:"check", index, total, name, status, duration_ms,
    detail} during the run, then {event:"done", passed, warned, failed,
    total, total_ms} at the end. Wraps run_and_persist so one scan run
    feeds both the JSON endpoint and the SSE endpoint."""

def set_auto_scan(enabled: bool) -> None:
    """Persist auto_scan_enabled toggle into last_scan.json (creating
    the file with {available, auto_scan_enabled} stub if missing)."""
```

### New endpoints (all under `/api/admin/*` — same auth posture as existing)

| Method | Path | Body | Response | Errors |
|---|---|---|---|---|
| GET | `/api/admin/perf/queue` | — | `scheduler.snapshot()` shape (above). | n/a — always returns. |
| GET | `/api/admin/cleanup/scan` | — | `{items: [{path, size_bytes, age_days, stale, kind}], total_bytes, stale_bytes, scanned_roots: [str]}` | n/a; missing roots are skipped silently. |
| POST | `/api/admin/cleanup/prune` | `{paths: [str]}` (≤200 paths) | `{ok: true, removed: int, freed_bytes: int, skipped: [{path, reason}]}` | 400 `{ok:false, error: "no paths"}` if list empty; 400 `{ok:false, error: "path not eligible: <p>"}` if any path is outside known roots OR not previously marked stale; 409 `{ok:false, error:"prune already running"}` if lock held. |
| GET | `/api/admin/security/status` | — | `{last_run_ts: str ISO8601 \| null, trigger: str \| null, summary: {critical:int, high:int, medium:int, low:int, total:int}, findings: [{package:str, version:str, id:str, severity:str, fix:str \| null, description:str}], tool: "pip-audit", tool_version: str \| null, available: bool, auto_scan_enabled: bool, error: str \| null}` | n/a — never raises. |
| POST | `/api/admin/security/run-scan` | — | `{ok: bool, status: <status() shape>, started_at: str}` | 503 `{ok:false, error:"pip-audit not installed"}` if unavailable. |
| GET | `/api/admin/security/run-scan/stream` | — | SSE; events `{event:"check", index, total, name, status:"pass"|"warn"|"fail", duration_ms, detail?}` then `{event:"done", passed, warned, failed, total, total_ms}`. Headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`. | If unavailable, emits one `check` event with `status:"fail"` + install hint, then `done`. |
| POST | `/api/admin/security/auto-scan` | `{enabled: bool}` | `{ok: true, auto_scan_enabled: bool}` | 400 if `enabled` not bool. |

### `last_scan.json` schema (under `DATA_DIR/security/last_scan.json`, chmod 0600)

| Field | Type | Required | Notes |
|---|---|---|---|
| `last_run_ts` | str (ISO8601 UTC) \| null | required | null on stub-only file. |
| `trigger` | `"boot"\|"manual"\|"sre"\|"sse"` \| null | required | null on stub. |
| `summary` | `{critical:int, high:int, medium:int, low:int, total:int}` | required | All zeros on stub. |
| `findings` | `[{package:str, version:str, id:str, severity:str, fix:str\|null, description:str}]` | required | Empty list on stub. `id` is the CVE / GHSA / PYSEC id from pip-audit. `fix` is the smallest version >= current that resolves it (null if none). |
| `tool` | `"pip-audit"` | required | Hardcoded. |
| `tool_version` | str \| null | required | Captured from `pip-audit --version` at scan time. |
| `available` | bool | required | False if `pip-audit` not on PATH. |
| `auto_scan_enabled` | bool | required | Default False; toggled via `/api/admin/security/auto-scan`. |
| `error` | str \| null | required | Last-run error if scan failed; null on success. |

### SRE Observation payloads (verbatim)

**`_watch_dependency_vulnerabilities()`** — three branches:

```python
# (a) High/Critical present, hybrid OR airgapped
Observation(
    watcher="dependency-vulnerabilities",
    severity="error",                                                  # internal rank
    fact=f"[CVE] {n_high+n_crit} High/Critical vulnerabilities in pip dependencies (Admin → Production Readiness → Security).",
    cooldown_key=f"cve::{last_run_ts}::{n_crit}::{n_high}",            # re-fires on new scan
    cooldown_sec=6 * 3600,                                              # 6 h
)

# (b) Medium-only present
Observation(
    watcher="dependency-vulnerabilities",
    severity="warn",
    fact=f"[CVE] {n_med} Medium vulnerabilities in pip dependencies (review in Admin).",
    cooldown_key=f"cve::med::{last_run_ts}::{n_med}",
    cooldown_sec=12 * 3600,
)

# (c) File missing AND hybrid AND last_run >24h old (or never)
Observation(
    watcher="dependency-vulnerabilities",
    severity="warn",
    fact=f"[CVE] No security scan in 24h+. Run a scan in Admin → Production Readiness → Security.",
    cooldown_key=f"cve::nag::{date.today().isoformat()}",
    cooldown_sec=24 * 3600,
)
```

**`_watch_lab_cleanup()`** — env-overridable thresholds
`LAB_CLEANUP_CACHE_MAX_GB` (default 5), `LAB_CLEANUP_LOG_AGE_DAYS` (default 30):

```python
# Severity = "warn" over threshold; "error" at 2× threshold
Observation(
    watcher="lab-cleanup",
    severity=("error" if cache_gb > 2 * threshold_gb else "warn"),
    fact=f"[CLEANUP] Wiki cache is {cache_gb:.1f} GB (threshold {threshold_gb} GB). Prune in Admin → Production Readiness → Cleanup.",
    cooldown_key=f"cleanup::cache::{round(cache_gb)}::{age_bucket}",
    cooldown_sec=24 * 3600,
)
```

Both watchers read env directly via `os.getenv` — they do **NOT** import
from `arail.portal` (sre.py stays portal-free). They read
`last_scan.json` from `DATA_DIR / "security" / "last_scan.json"` where
`DATA_DIR` resolves the same way as the portal does (via
`arail.config`).

### `/docs/{path:path}` — already exists at app.py:1409–1433

The plan's "small ~15 LOC handler" is **already implemented**. The
existing route enforces `.md`-only, no `..`, path containment under
`docs/`, 404 on missing. `docs/PUBLISH.md` is reachable today as
`/docs/PUBLISH.md`. **No new route required.** See "Plan deviations
requested" §1.

---

## Failure modes (paranoid pass)

### A. Inference queue (`scheduler.py` + the five wrap sites)

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| A1 | Semaphore deadlock if a wrapped handler raises before `release` | Reproducible by raising in `to_thread` body | Use `@asynccontextmanager` with `try: yield; finally: sem.release()`. Verified by test that aborts mid-acquire. |
| A2 | Capacity-0 misconfig from `ARAIL_INFERENCE_CONCURRENCY=0` | n/a — silent | `_capacity()` clamps to `max(1, min(4, parsed))`. Empty / non-int → 1. |
| A3 | Streaming response holds the slot for the entire stream — slow client can monopolize a slot | Observable in `snapshot.in_flight` | Intentional in v1 (correctness > throughput). Operators set client timeout in reverse proxy (PUBLISH.md §3 includes `proxy_read_timeout 600s`). Phase-2 unblock: per-token reacquire. |
| A4 | Background callers (researcher, agents) bypass the queue | Researcher heartbeats won't appear in `snapshot` | **Intentional Phase-1 scope.** Wrap at FastAPI handler boundaries only. Document in REVIEW.md and file Phase-2 ticket. |
| A5 | Fast-path middleware adds latency to every fast-path request | Measure via `snapshot.fast_path_ms.p95` | Target overhead <1 ms (pure `perf_counter` + deque append). QA must include a benchmark; reject if p95 > 1 ms. |
| A6 | The fifth call site at **app.py:3532** is a SYNCHRONOUS `router.complete(...)` — it blocks the event loop entirely | Code grep | **Plan-missed bug.** Either (a) wrap with `await asyncio.to_thread(router.complete, ...)` AND `inference_slot("chat-default")`, or (b) document why we leave it blocking. Recommendation: wrap. See "Plan deviations requested" §2. |
| A7 | Lazy `_get_semaphore()` race — two coroutines hit `_SEM is None` simultaneously | Concurrent first-acquire | `asyncio` is cooperative on a single thread; the assignment is atomic between awaits. But to be safe, gate with a module-level `_INIT_LOCK = asyncio.Lock()` or use `if _SEM is None: _SEM = asyncio.Semaphore(_capacity())` after first await — the latter is fine because no `await` happens between check and assignment. |
| A8 | Middleware ordering — `fastpath_meter` must run AFTER `onboarding_gate` so unauthenticated probes don't bypass the gate | FastAPI applies middlewares in reverse registration order | Register `fastpath_meter` AFTER `onboarding_gate` in source order — FastAPI then runs `fastpath_meter` outermost (timed) → `onboarding_gate` (auth) → handler. Document in BUILD_LOG; verify with a route trace test. |
| A9 | `FAST_PATH_PREFIXES` accidentally includes a heavy path (e.g. someone adds `/api/chat`) | Manual review | Guard the constant with a comment; QA must run a regression check that `/api/chat`, `/api/teacher/ask`, `/api/agents/<id>/ask` are NOT prefix-matched. |

### B. Cleanup endpoint (`/api/admin/cleanup/{scan,prune}`)

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| B1 | Path-traversal in `prune` body (`../etc/passwd`) | Server-side validation | `Path(p).resolve(strict=False)` then check `_in_known_root(abs_p)` (one of `DATA_DIR`, `MODELS_DIR`, `LAB_ROOT/pkb/.wiki-cache`). Reject 400. |
| B2 | Path-traversal via the path being marked stale by a previous scan but moved | Re-stat + re-validate at prune time | Always re-check `_in_known_root` AND `_was_marked_stale` at prune time. Cache is in-memory dict keyed by absolute path; expires when scan re-runs. |
| B3 | Symlinks pointing outside lab | `Path.is_symlink()` check before unlink | Skip symlinks entirely in v1; `skipped` field reports them. |
| B4 | Concurrent prune calls clobber each other | n/a | Single-flight via module-level `_PRUNE_LOCK = asyncio.Lock()`. Second caller gets 409 immediately (use `lock.locked()` check before `await lock.acquire()`). |
| B5 | File deleted between scan and prune | `Path.exists()` check | Skip + report in `skipped`. |
| B6 | File grew between scan and prune (so we charge the wrong freed_bytes) | Re-stat at prune time | Use `re_stat.st_size`, not the cached scan value. |
| B7 | Disk full / read-only filesystem | `OSError` on `unlink()` | Catch and add to `skipped` with `reason="OSError: <type>"`. Never 500. |
| B8 | Cleanup scan walks billions of files | Time the walk | Cap walk at 50,000 entries per root; emit warn in response body if hit; QA must verify on a tarred-up models dir. |

### C. Security scan (`security_scan.py` + `/api/admin/security/*`)

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| C1 | `pip-audit` JSON schema changes in a future release | Parse-time validation | Pin `pip-audit>=2.7.0,<3`. On parse: validate top-level `dependencies: list` and per-dep `vulns: list`. On mismatch: write `{available:true, error:"unexpected pip-audit output", findings:[]}` and return without crashing. |
| C2 | PyPI unreachable (offline / firewall in hybrid mode) | `pip-audit` exits non-zero with stderr | Capture stderr, write `{available:true, error:"network: <stderr first 500 chars>"}`, emit `activity_log.emit("security", "Scan failed: network", "warn")`. Don't crash boot task. |
| C3 | Long scan blocking startup (pip-audit can take 60–300s) | Code review | Boot task wrapped in `asyncio.create_task(_boot_security_scan())` with `await asyncio.sleep(30)` first; **never** awaited inline in the startup function. |
| C4 | Concurrent scans (boot + manual + SRE + SSE) | Module-level `_SCAN_LOCK = asyncio.Lock()` | All entry points go through `run_and_persist`. If lock held, the second caller awaits — no parallel `pip-audit` subprocesses. SSE endpoint serializes its events behind the lock. |
| C5 | `pip_audit` Python import vs `pip-audit` CLI mismatch | n/a | Always invoke as subprocess via `asyncio.create_subprocess_exec("pip-audit", ...)`. The Python import is only used by `is_available()` as a fallback signal. Avoids API drift between releases. |
| C6 | Activity-log spam if scan fires too often (e.g. SRE re-triggers) | SRE cooldown_key includes `last_run_ts` | `cve::{last_run_ts}::{n_crit}::{n_high}` only re-fires when `last_run_ts` changes — i.e. a new scan ran. Identical scans never re-emit. |
| C7 | `last_scan.json` contains dependency version inventory — sensitive | File mode | Write with `chmod 0600`. Mirror `_write_secrets()` pattern at app.py:719–731 (parent.mkdir + write_text + chmod 0600 in try/except OSError). |
| C8 | Boot scan in airgapped mode (assumption #4 violation) | Code review | Verified — `dotenv` loads at `arail.config` import time (config.py:22), which is imported by app.py:26. `_lab_mode()` is correct by the time `@app.on_event("startup")` runs. |
| C9 | Atomic write failure leaves `last_scan.json` half-written | Crash mid-write | Write to `last_scan.json.tmp`, then `os.replace(tmp, final)`. POSIX rename is atomic. |
| C10 | `pip-audit` output > stdout buffer (huge dep tree) | `subprocess` PIPE limit | `asyncio.create_subprocess_exec` PIPE has no hard limit on Linux/macOS; we `await proc.communicate()` which buffers in memory. Acceptable; the largest realistic output is ~500 KB. |

### D. Boot scan in airgapped mode

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| D1 | Gate `_lab_mode() == "hybrid"` checked before env loaded | Walk import order | **Verified safe:** `dotenv` loads at `arail.config` import (line 22); `app.py` imports `arail.config` at line 26; `_lab_mode()` not called until startup runs. No race. |
| D2 | User flips `.env` to hybrid without restart | n/a | **Acknowledged limitation.** Manual button works in airgapped mode. PUBLISH.md notes "restart required after `.env` change." |
| D3 | `_boot_security_scan()` task survives shutdown and writes after the loop closes | Shutdown ordering | `asyncio.create_task` tasks are cancelled on app shutdown. `await asyncio.sleep(30)` will raise `CancelledError`, which we catch implicitly via the bare `except Exception` (NOT — `CancelledError` is BaseException in 3.8+; we should explicitly `except (asyncio.CancelledError, ImportError, Exception)` and re-raise CancelledError). Documented for builder. |

### E. SRE watchers

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| E1 | `last_scan.json` missing on first run (no scan ever ran) | Watcher invocation | Watcher must catch `FileNotFoundError` and either (a) return None (airgapped or recent run elsewhere) or (b) emit the "you should run a scan" nudge (hybrid + 24h+ since boot). Never raises. |
| E2 | Clock skew makes `last_run_ts` parse-fail | `datetime.fromisoformat` errors | Wrap parse in try/except; on failure treat as "unknown age" and skip the nudge branch. |
| E3 | Activity log full disk → emit() raises | Watcher loop | `activity_log.emit` already swallows OSError internally (verified at `activity.py:69`). Watchers don't need extra protection. |
| E4 | SRE Observation `severity="error"` is ignored — emit always uses `"warn"` | Verified at `sre.py:399–408` | Acceptable for v1 — severity is preserved in `data.severity` for downstream consumers. Document in REVIEW.md as a follow-up. |
| E5 | `os.getenv("LAB_MODE")` in sre.py drifts from portal's `_lab_mode()` (different env name) | Code review | Portal uses `os.getenv("LAB_MODE", os.getenv("ARAIL_MODE", "airgapped"))`. SRE must match. Builder MUST replicate the fallback chain in `sre.py`. |
| E6 | Cache-size walk is slow (`Path.rglob`) on huge wiki-cache | Time the walk | Use `os.scandir`-based walk; cap entries; cache the result for 5 min in module-level state. |

### F. Admin UI

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| F1 | Card endpoints return 5xx → JS shows blank | Per-card try/catch in fetch handlers | Each `loadPerf/loadCleanup/loadSecurity` wraps `fetch().then(r => r.ok ? r.json() : Promise.reject())` in try/catch and renders a clear error block (not a console-only failure). Reuse the existing `adminLog` helper for the error toast. |
| F2 | SSE modal + multi-minute `pip-audit` — connection times out | Existing modal does not handle keep-alives | The existing `runLiveChecks` driver has no client-side timeout (verified at admin.html:760–793 — it just `await reader.read()` until done). Server MUST emit periodic keep-alive comments (`: keepalive\n\n` every 15 s) during the long subprocess wait so reverse proxies don't kill the connection. Add to the SSE generator. |
| F3 | Reverse proxy buffers SSE → modal renders nothing until done | Headers + PUBLISH.md | Both new SSE endpoints set `X-Accel-Buffering: no` (mirroring app.py:2806). PUBLISH.md must document `proxy_buffering off` for nginx. |
| F4 | Card auto-poll (5 s perf interval) wakes the user's CPU on the admin tab | n/a | Intentional. Document. Pause polling when document.hidden via existing pattern (vanilla JS — visibilitychange listener pauses interval). |

### G. `/docs/{name}` route (existing — verifying)

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| G1 | Path traversal via `..` | app.py:1417 | Existing handler rejects `..` and absolute paths up front. Verified. |
| G2 | Markdown XSS via raw HTML in PUBLISH.md | app.py:1324 | `MarkdownIt("commonmark", {"html": False, ...})` — raw HTML escaped. Verified. |
| G3 | File not found | app.py:1428–1432 | Returns 404 HTMLResponse with a friendly message. No traceback. Verified. |
| G4 | Markdown contains `<script>` via fenced code | n/a | Code blocks render as `<pre><code>`; the renderer escapes content because `html=False`. Safe. |

### H. PUBLISH.md operator runbook

| # | Failure | Detection | Recovery / Mitigation |
|---|---|---|---|
| H1 | Bad reverse-proxy snippet that disables SSE | Operator-tested | Include `proxy_buffering off` AND `proxy_cache off` AND `proxy_read_timeout 600s` for nginx; for Caddy include `flush_interval -1`. Note `X-Accel-Buffering: no` is server-set but `proxy_buffering off` is required for nginx to honor it. |
| H2 | Stale advice on Cloudflare Access UI | n/a | Link to Cloudflare's current docs rather than embedding screenshots / step-by-step that will rot. Frame as "options" not "instructions." |
| H3 | Operator forgets to chmod 0600 on `.env` | Document in §7 hardening | Include the explicit `chmod 0600 lab/data/secrets.env` check in pre-flight. |
| H4 | Operator runs PUBLISH.md but skips the "lock /admin behind real auth" step | Document loudly | §5 states the in-app `onboarding_gate` is a passphrase, NOT a substitute for an auth proxy. Bold the warning. |
| H5 | Operator copy-pastes the nginx snippet into Apache config | n/a | Section headers clearly call out per-server snippets; provide one nginx + one Caddy. Don't try to cover Apache in v1. |

---

## Test strategy

Per ARAIL CLAUDE.md QA allocation: **30% setup / 30% Buddy / 20% security / 10% happy / 10% regression.** The QA persona executes; the architect specifies coverage.

### Setup tests (30%) — does the new surface install + boot cleanly on a fresh machine?

| Test | File | Asserts |
|---|---|---|
| `test_max_extra_includes_pip_audit` | `tests/test_install_extras.py` (new) | Parse `pyproject.toml`; `pip-audit>=2.7.0,<3` is in both `[security]` and `[max]`. |
| `test_security_extra_isolated_from_min` | `tests/test_install_extras.py` (new) | `min` extra does NOT contain `pip-audit`. |
| `test_lab_boots_airgapped` | `tests/test_startup.py` (new) | With `LAB_MODE=airgapped`, app starts; no boot security task is created; activity log contains startup line. (Mock the asyncio.create_task to count.) |
| `test_lab_boots_hybrid_creates_boot_task` | `tests/test_startup.py` (new) | With `LAB_MODE=hybrid`, app start schedules the boot scan task (verify via task count or fake `security_scan` module). |
| `test_fast_path_middleware_registered_after_onboarding_gate` | `tests/test_middleware_order.py` (new) | Walk `app.user_middleware`; ensure `fastpath_meter` is registered AFTER `onboarding_gate` in source order. |
| `test_arail_upgrade_max_includes_pip_audit` (manual) | `tests/manual/upgrade_max.md` | Document the manual `./arail upgrade max` then `which pip-audit` check. |

### Buddy / agent tests (30%) — SRE watchers behave correctly

| Test | File | Asserts |
|---|---|---|
| `test_dependency_vuln_watcher_no_file` | `tests/test_sre_watchers.py` (new) | With no `last_scan.json`, watcher returns None in airgapped; emits "run a scan" nudge in hybrid + last_run >24h ago. |
| `test_dependency_vuln_watcher_high_crit` | `tests/test_sre_watchers.py` | With a fixture file containing `critical:1, high:2`, returns Observation with severity="error", `cooldown_key` includes the `last_run_ts`. |
| `test_dependency_vuln_watcher_refires_on_new_scan` | `tests/test_sre_watchers.py` | Two fixture files (different `last_run_ts`, same counts) produce DIFFERENT cooldown keys → re-fires. Same `last_run_ts` → cooldown matches → no re-fire. |
| `test_dependency_vuln_watcher_no_refire_identical` | `tests/test_sre_watchers.py` | Same fixture invoked twice produces same cooldown_key — second invocation suppressed by SRE loop. |
| `test_lab_cleanup_watcher_threshold` | `tests/test_sre_watchers.py` | At cache_gb < threshold, returns None. At cache_gb > threshold, returns "warn". At cache_gb > 2*threshold, returns "error". |
| `test_lab_cleanup_env_overrides` | `tests/test_sre_watchers.py` | `LAB_CLEANUP_CACHE_MAX_GB=10` overrides default 5; threshold logic respects env. |
| `test_sre_agent_md_voice_consistent` | `tests/test_sre_watchers.py` | New AGENT.md rows match the existing terse-clinical voice (programmatic — assert no emoji except in column header, sentence ≤25 words). |

### Security tests (20%) — adversarial pass

| Test | File | Asserts |
|---|---|---|
| `test_docs_route_path_traversal` | `tests/test_docs_route.py` (new) | GET `/docs/../../../etc/passwd` → 404. GET `/docs/PUBLISH.md` → 200 + rendered HTML. GET `/docs/secrets.env` → 404 (`.md` whitelist). |
| `test_cleanup_prune_path_validation` | `tests/test_admin_security_endpoints.py` (new) | POST `/api/admin/cleanup/prune` with `{paths:["/etc/passwd"]}` → 400. With a path under DATA_DIR but NOT marked stale → 400. With a stale path → 200 + freed_bytes. |
| `test_cleanup_prune_symlink_skipped` | `tests/test_admin_security_endpoints.py` | Symlink pointing outside lab is not followed; skipped with reason. |
| `test_cleanup_prune_concurrent` | `tests/test_admin_security_endpoints.py` | Two concurrent prune calls — second gets 409 or queues; never both delete the same file twice. |
| `test_airgapped_no_outbound_security_scan` | `tests/test_admin_security_endpoints.py` | With `LAB_MODE=airgapped`, boot scan is NOT scheduled. Manual `/api/admin/security/run-scan` STILL works (explicit user action). |
| `test_inference_slot_releases_on_exception` | `tests/test_inference_queue.py` (new — note: `tests/test_scheduler.py` exists but is for `arail.scheduler`, not `arail.portal.scheduler`) | A handler that raises inside `inference_slot` releases the semaphore; subsequent calls acquire immediately. |
| `test_inference_slot_capacity_clamp` | `tests/test_inference_queue.py` | `ARAIL_INFERENCE_CONCURRENCY=0` → capacity=1. `=99` → capacity=4. Empty/non-int → 1. |
| `test_last_scan_json_chmod_0600` | `tests/test_security_scan.py` (new) | After `run_and_persist`, file mode is `0o600`. (Skip on Windows.) |
| `test_security_scan_pip_audit_unavailable` | `tests/test_security_scan.py` | Mock `is_available()` False → `run_and_persist` writes status with `available:false`, emits warn, returns without raising. |
| `test_security_scan_subprocess_mocked` | `tests/test_security_scan.py` | Mock `asyncio.create_subprocess_exec` to return crafted JSON; verify summary counts and findings shape. |
| `test_security_scan_malformed_json` | `tests/test_security_scan.py` | Mock subprocess returns `{"foo":"bar"}` → status is written with `error:"unexpected pip-audit output"`, no crash. |
| `test_security_scan_single_flight` | `tests/test_security_scan.py` | Two concurrent `run_and_persist` calls — only one subprocess spawned, both return the same dict. |

### Happy path (10%)

| Test | File | Asserts |
|---|---|---|
| `test_admin_perf_queue_endpoint` | `tests/test_admin_security_endpoints.py` | GET returns the snapshot dict shape; counts increment after a wrapped call. |
| `test_admin_cleanup_scan_endpoint` | `tests/test_admin_security_endpoints.py` | GET returns `items + total_bytes + stale_bytes` over a tmp DATA_DIR. |
| `test_admin_security_status_endpoint` | `tests/test_admin_security_endpoints.py` | GET returns `available:false` initially; after a mocked scan, returns full payload. |
| `test_publish_guide_renders` | `tests/test_docs_route.py` | GET `/docs/PUBLISH.md` returns 200 + HTML containing the section headers. |
| `test_perf_card_renders_admin_html` | manual smoke | Open `/admin`, visually confirm three Production Readiness cards load (no JS errors). |

### Regression (10%)

| Test | File | Asserts |
|---|---|---|
| `test_existing_chat_path_still_works` | extend `tests/test_chat_ui.py` | `/api/chat` POST still returns the existing dict shape with the wrapper applied. Mock backends. |
| `test_existing_admin_cards_render` | extend `tests/test_chat_ui.py` or new | `/api/admin/components`, `/api/admin/check-updates` still respond with their original shapes. |
| `test_existing_sre_watchers_still_fire` | extend an existing SRE test (or `tests/test_sre_watchers.py` new) | The three pre-existing watchers (recent-errors, crash-recurrence, service-health) still appear in `WATCHERS` and are callable. |
| `test_fast_path_overhead_under_1ms` | `tests/test_inference_queue.py` (perf bench) | 1000 fast-path requests through the middleware add <1 ms p95 overhead vs no middleware. May be flaky in CI — mark `@pytest.mark.slow` and gate on a perf-CI runner; document threshold for manual run. |

### Tests we cannot reasonably write

- **Real `pip-audit` invocation in CI** — flaky (PyPI availability, vuln DB drift, multi-minute runtime). Mock the subprocess; test the parser against captured fixture JSON files (commit a `tests/fixtures/pip-audit-*.json` set covering empty, all-clear, mixed-severity, malformed).
- **End-to-end perf comparison against pre-change baseline** — requires real local model. Document as a manual smoke test in the QA report; provide a script that hits `/api/system/health` 100x while a chat is running and reports p50/p95.
- **Real Cloudflare Access flow** — manual, gated on a real domain.

---

## Tech debt assessment

### Added

- **In-process semaphore is per-worker.** When uvicorn moves to `--workers >1`, each worker gets its own queue. Acceptable now (single worker today) but Phase 2 must address.
- **Background callers (researcher, agents) bypass the queue** — they call `arail.router` directly. Phase 2 must wrap there too OR move all callers through the FastAPI handler boundary.
- **SRE watcher reads `last_scan.json` written by the portal** — coupling between two modules via a file format. Acceptable (file is the schema), but document. If the schema changes, both modules must update in lockstep.
- **No live `LAB_MODE` change hook** — flipping `.env` requires restart. Acceptable for v1.
- **`/api/admin/perf/queue` is polled at 5 s** — negligible load, but if many admins watch concurrently it adds up. Document; pause polling on `document.hidden`.
- **PUBLISH.md operator docs are read-only via the existing `_render_markdown_page` helper** — no embedded images or attached static assets. If PUBLISH.md grows linked diagrams, the route needs static-asset support (or use external image links).
- **The Production Readiness section grows the admin page vertically** — if more cards land in the future (e.g. backups, telemetry), we need a tabbed structure. Not now.
- **No client-side keep-alive on the SSE modal** — relying on server-sent `: keepalive\n\n` comments. Standard pattern but worth noting as a coupling.
- **Cleanup scan caches "stale paths" in process memory** — restarting the portal between scan and prune invalidates the cache; the prune call must succeed-or-error cleanly. Document in the response shape.
- **`pip-audit` is invoked as subprocess every scan** — no caching of the dep-tree resolution; each run re-walks `pip list`. Acceptable; fix when scans get slow.

### Repaid

- **First inference-throttling primitive** — closes the gap that made the dashboard feel laggy under chat. Future work can build on `snapshot()`.
- **First security surface** — gives operators visibility into CVE state without reading a separate file.
- **First operator-facing publication runbook** — closes the "how do I publish my own?" question that was email-only before.
- **Centralizes airgapped-mode policy in one place** (the boot-task gate) — easier to audit than spreading checks across handlers.
- **Reuses the existing live-checks SSE modal** — no new modal code; one driver, two endpoints. Less surface to maintain.
- **Uses the existing `_render_markdown_page` helper for PUBLISH.md** — no duplicated rendering pipeline.

### Net

**Slightly debt-positive** — we add five small coupling points (semaphore-per-worker, sre↔scan file, no live mode hook, in-memory stale cache, sse keepalive contract). All are documented; all are bounded. Phase 2 retires the largest two.

---

## Phase-2 deferral

**Worker isolation is intentionally deferred** to a follow-up sprint. Recommendation when that sprint fires: try **multi-worker uvicorn first** (`--workers 2` in `scripts/start.sh:36–38`). The semaphore becomes per-process, which is acceptable if the bottleneck is inference-CPU (not I/O). `snapshot()` should grow a `worker_id` field so the admin card aggregates correctly. If a single worker still saturates because all heavy chat lands there (no work-stealing across uvicorn workers without a load balancer), extract `arail.router` into an out-of-process inference daemon over a Unix socket so FastAPI workers stay purely I/O-bound and inference is shared by every worker. Filed as a follow-up sprint; do not build now.

---

## File-by-file change list (atomic-commit-friendly, in build order)

The builder lands these in the sequence below. Each numbered group is one logical commit.

### Commit 1 — `scheduler.py` skeleton (metrics-only, no behavior change)

- **NEW: `src/arail/portal/scheduler.py`** — module per "Interface contracts" above. Implement `_capacity()`, `_get_semaphore()`, `inference_slot()`, `fast_path_record()`, `snapshot()`, `FAST_PATH_PREFIXES`. Do NOT wire into anywhere yet.

### Commit 2 — fast-path middleware

- **MODIFY: `src/arail/portal/app.py`** — insert new `@app.middleware("http")` named `fastpath_meter` immediately after the `onboarding_gate` middleware definition (after **app.py:144**). Body: if `request.url.path` startswith any `FAST_PATH_PREFIXES` element, time + record; else just `await call_next(request)`. Imports `from arail.portal import scheduler`.

### Commit 3 — wrap the five inference call sites

- **MODIFY: `src/arail/portal/app.py`** — five `async with scheduler.inference_slot(label):` wraps:
  1. **app.py:3341–3347** (deep_backend stream) → label `"chat-stream-deep"`.
  2. **app.py:3380–3383** (runtime stream) → label `"chat-stream-runtime"`.
  3. **app.py:3405–3412** (router.stream_complete via `_stream_sync_iterator`) → label `"chat-stream"`.
  4. **app.py:3490–3493** (deep_backend non-stream) → label `"chat-deep"`.
  5. **app.py:3517–3520** (runtime non-stream) → label `"chat-runtime"`.
- **DECISION REQUIRED:** the sixth synchronous call at **app.py:3532** (`response = router.complete(...)`) — see "Plan deviations requested" §2. Recommendation: also wrap with `await asyncio.to_thread(...)` AND `inference_slot("chat-default")`.

### Commit 4 — `pyproject.toml` + `security_scan.py` skeleton

- **MODIFY: `pyproject.toml`** — at L60 (after `airllm>=2.0` in `max`), append `"pip-audit>=2.7.0,<3"` to the `max` list. Add new section before `# ── Hardware/runtime extras ───` at L62:
  ```toml
  security = ["pip-audit>=2.7.0,<3"]
  ```
- **NEW: `src/arail/portal/security_scan.py`** — module per "Interface contracts". Implement `is_available()`, `status()`, `run_and_persist()`, `stream_scan_events()`, `set_auto_scan()`. Module-level `_SCAN_LOCK = asyncio.Lock()`. Atomic-write last_scan.json (tmp + rename). chmod 0600.

### Commit 5 — admin endpoints

- **MODIFY: `src/arail/portal/app.py`** — insert new endpoint group at **app.py:2807** (after `admin_check_updates_stream` returns), in this order:
  - `GET /api/admin/perf/queue` → returns `scheduler.snapshot()`.
  - `GET /api/admin/cleanup/scan` (with helper `_cleanup_walk_root`).
  - `POST /api/admin/cleanup/prune` (with module-level `_PRUNE_LOCK = asyncio.Lock()`).
  - `GET /api/admin/security/status` → returns `security_scan.status()`.
  - `POST /api/admin/security/run-scan` → calls `await security_scan.run_and_persist(trigger="manual")`.
  - `GET /api/admin/security/run-scan/stream` → SSE wrapping `security_scan.stream_scan_events("sse")`.
  - `POST /api/admin/security/auto-scan` → calls `security_scan.set_auto_scan(bool)`.
- All handlers use the same auth posture as the existing `/api/admin/*` endpoints.

### Commit 6 — admin.html: Production Readiness section + JS driver

- **MODIFY: `src/arail/portal/templates/admin.html`** — at **admin.html:552** (after the Service Status section closes at L551), insert:
  ```html
  <!-- ═══ Production Readiness ═══ -->
  <div class="admin-section">
    <h2>Production Readiness</h2>
    <div class="pr-grid">
      <div class="pr-card"><h3>Performance</h3><div id="pr-perf">loading…</div></div>
      <div class="pr-card"><h3>Cleanup</h3><div id="pr-cleanup">loading…</div></div>
      <div class="pr-card"><h3>Security</h3><div id="pr-security">loading…</div></div>
    </div>
  </div>
  ```
  Add `.pr-grid` and `.pr-card` styles to the existing `<style>` block (above `.lc-overlay` styles, around L18–48).
- **MODIFY: `src/arail/portal/templates/admin.html`** — append JS driver to the trailing `<script>` block (after **admin.html:841** `closeLiveChecks`):
  - `loadPerf()` — fetch `/api/admin/perf/queue`, render gauges/numbers, `setInterval(loadPerf, 5000)`. Pause on `document.hidden`.
  - `loadCleanup()` — fetch `/api/admin/cleanup/scan`, render checkbox rows; "Prune selected" → `confirm()` → POST.
  - `loadSecurity()` — fetch `/api/admin/security/status`. If `available=false` show "Install with: `./arail upgrade max`". "Run scan now" calls `runLiveChecks('Security Scan', '/api/admin/security/run-scan/stream')` (reuses existing modal). Auto-scan toggle POSTs `/api/admin/security/auto-scan`.
  - Initialize all three from the existing `DOMContentLoaded` handler.
- **MODIFY: `src/arail/portal/templates/admin.html`** — Quick Actions block (**admin.html:521–545**): add a 7th button at the end of the grid (before L543's closing `</div>`):
  ```html
  <a href="/docs/PUBLISH.md" class="qa-button qa-primary" style="text-decoration: none; display: flex; flex-direction: column; justify-content: flex-start;">
    <div class="qa-title" style="color: var(--blue);">↗ Publish Guide</div>
  </a>
  ```

### Commit 7 — boot-scan task

- **MODIFY: `src/arail/portal/app.py`** — insert at **app.py:370** (immediately before `_register_canvas_goal_listener` at app.py:373), inside the `_startup` function:
  ```python
  if _lab_mode() == "hybrid":
      async def _boot_security_scan():
          await asyncio.sleep(30)
          try:
              from arail.portal import security_scan
              await security_scan.run_and_persist(trigger="boot")
          except asyncio.CancelledError:
              raise
          except ImportError:
              activity_log.emit("security",
                  "pip-audit not installed — install via ./arail upgrade max to enable CVE scans.",
                  "warn")
          except Exception as e:  # noqa: BLE001
              activity_log.emit("security", f"Boot CVE scan failed: {type(e).__name__}: {e}", "warn")
      asyncio.create_task(_boot_security_scan())
  ```

### Commit 8 — SRE watchers

- **MODIFY: `lab/pkb/agents/sre/sre.py`** — insert two new functions at **sre.py:284** (between `_watch_service_health` end and the `WATCHERS` list):
  - `_watch_dependency_vulnerabilities()` — per "Interface contracts" payload spec.
  - `_watch_lab_cleanup()` — per "Interface contracts" payload spec.
  - Both use `os.getenv("LAB_MODE", os.getenv("ARAIL_MODE", "airgapped"))` (matching portal's helper).
- **MODIFY: `lab/pkb/agents/sre/sre.py`** — append both names to the `WATCHERS` list at **sre.py:286–290**.
- **MODIFY: `lab/pkb/agents/sre/AGENT.md`** — append two rows to the watcher table at **AGENT.md:31–35**:
  ```
  | `dependency-vulnerabilities` | warn/error | 6–24 h per scan | High/Critical CVEs in pip dependencies, OR no scan in 24h+ (hybrid mode) |
  | `lab-cleanup`                | warn/error | 24 h per bucket  | Wiki cache exceeds LAB_CLEANUP_CACHE_MAX_GB (default 5) |
  ```
  Add a brief paragraph: "The CVE watcher reads `lab/data/security/last_scan.json` (written by the portal's security scan); cleanup thresholds are env-configurable via `LAB_CLEANUP_CACHE_MAX_GB` and `LAB_CLEANUP_LOG_AGE_DAYS`."

### Commit 9 — PUBLISH.md + README link

- **NEW: `docs/PUBLISH.md`** — outline per the approved plan §E. Sections 1–9. Operator-facing prose, terse, includes both nginx and Caddy snippets; Cloudflare Access framed as "options" not "instructions."
- **MODIFY: `README.md`** — add one line near getting-started (placement to be confirmed by builder against current README structure): `Publishing to the public internet? See [docs/PUBLISH.md](docs/PUBLISH.md).`
- **NO new route required** — `/docs/PUBLISH.md` is already served by the existing `/docs/{path:path}` handler at **app.py:1409–1433**. Verified.

---

## Dependency map

- **NEW (opt-in):** `pip-audit>=2.7.0,<3` in `[project.optional-dependencies] security` AND appended to `max`.
- **NO base-deps additions.** `markdown-it-py` is already base (pyproject.toml:28). `asyncio` and `subprocess` are stdlib.
- **NO JS framework additions.** Admin JS stays vanilla — extends the existing `runLiveChecks` driver pattern.
- **NO new sibling-repo deps.** ARAIL stays self-contained.

---

## Plan deviations — APPROVED 2026-05-01

These are deviations from the approved plan that the architect surfaced during design. The orchestrator + user approved both on 2026-05-01. They are now part of the design the builder must implement.

### 1. APPROVED — Drop the new `/docs/{name}` route

The plan calls for a "small (~15 LOC) handler" at `/docs/{name}`. The existing handler at **app.py:1409–1433** (`@app.get("/docs/{path:path}")`) already serves any `.md` file under `docs/` with path-traversal protection, `.md` whitelist, 404 on missing, and markdown rendering. `docs/PUBLISH.md` is reachable as `/docs/PUBLISH.md` with no new code.

**Builder action:** do NOT add a new docs route. Keep the README line and the Quick Actions button — both link to `/docs/PUBLISH.md` against the existing handler. Verify `_render_markdown_page` (called at app.py:1433) handles PUBLISH.md the same way it handles other docs. Net diff: ~15 LOC less than the plan estimated.

### 2. APPROVED — Add the sixth inference wrap at app.py:3532

The plan lists five inference call sites to wrap. There is a sixth at **app.py:3532** in `_run_chat_completion`'s `else` branch (the "no deep, no runtime override" path) — the *default* chat path:

```python
else:
    assert router is not None
    response = router.complete(   # ← SYNCHRONOUS, NOT to_thread
        prompt, max_tokens=max_tokens, temperature=temperature, top_p=top_p,
    )
```

This blocks the event loop entirely during the most common code path. It is the largest single source of the lag symptom this sprint exists to fix. The plan's five wraps cover deep + runtime + streaming variants but miss the default case.

**Builder action:** add a sixth wrap (label `"chat-default"`) that BOTH `to_thread`s the `router.complete` call AND wraps it in `inference_slot`:

```python
else:
    assert router is not None
    async with scheduler.inference_slot("chat-default"):
        response = await asyncio.to_thread(
            router.complete, prompt,
            max_tokens=max_tokens, temperature=temperature, top_p=top_p,
        )
```

This is the highest-impact change of the sprint. The file-by-file change list (above) and the failure-modes section now treat **six** inference call sites, not five. Update tally everywhere relevant.

### 3. NOTED — Severity="error" Observations flattened to "warn" by SRE emit path

The Observation `severity` field is preserved as data but the activity-log entry is always emitted at `"warn"` level (sre.py:399–408). For the CVE watcher this means a yellow warn line in the activity feed even when many critical CVEs are present.

**Builder action:** out of scope for this sprint. File as a follow-up after ship: "SRE emit honors Observation.severity — error → activity_log.emit(level='error')". No build-time blocker; CVE watcher still emits the right `severity` field on the Observation, the activity log just renders it less loudly than ideal for v1.

---

## Verdict

**Ready to build.** Both deviations approved 2026-05-01. Builder implements the plan with the line-ref corrections in this document AND the two approved deviations baked in: (1) no new `/docs/{name}` route, (2) six inference wraps not five.
