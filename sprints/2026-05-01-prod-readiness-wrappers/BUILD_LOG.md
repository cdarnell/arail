# Build log: Production-Readiness Wrappers (Phase 1)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 2b610d1
**Started:** 2026-05-01
**Completed:** 2026-05-02

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/portal/scheduler.py`, `src/arail/portal/app.py` | NEW scheduler.py — inference semaphore + fast-path metrics. Wire `fastpath_meter` middleware after `onboarding_gate` in app.py. Metrics-only; no behavior change to chat. | None (QA phase) | df74090 |
| 2 | `src/arail/portal/app.py` | Wrap SIX inference call sites with `async with scheduler.inference_slot(label)`. Site at 3532 also gets `await asyncio.to_thread(...)` (approved deviation §2). | None (QA phase) | afd264b |
| 3 | `pyproject.toml` | Add `security = ["pip-audit>=2.7.0,<3"]` extra; append `pip-audit>=2.7.0,<3` to `max` list. | None (QA phase) | d02d8eb |
| 4 | `src/arail/portal/security_scan.py` | NEW — pip-audit wrapper. `is_available()`, `status()`, `run_and_persist()`, `stream_scan_events()`, `set_auto_scan()`. Atomic write, chmod 0600, single-flight lock. | None (QA phase) | db92de2 |
| 5 | `src/arail/portal/app.py` | Add seven admin endpoints at app.py~2999: perf/queue, cleanup/scan, cleanup/prune, security/status, security/run-scan, security/run-scan/stream, security/auto-scan. | None (QA phase) | 3ac1be2 |
| 6 | `src/arail/portal/templates/admin.html` | Production Readiness section (3 cards) + CSS + JS driver (loadPerf, loadCleanup, loadSecurity) + 7th Quick Action button. | None (QA phase) | 0d71997 |
| 7 | `src/arail/portal/app.py` | Boot-scan task inserted at end of _startup() (hybrid mode only, after dream daemon block). | None (QA phase) | f893a33 |
| 8 | `lab/pkb/agents/sre/sre.py`, `lab/pkb/agents/sre/AGENT.md` | Add `_watch_dependency_vulnerabilities` and `_watch_lab_cleanup` watchers; update WATCHERS list; add two rows to AGENT.md table. | None (QA phase) | cd76949 |
| 9 | `docs/PUBLISH.md`, `README.md` | NEW PUBLISH.md (sections 1-9). One-line README link. No new route (existing `/docs/{path:path}` serves it). | None (QA phase) | bcc0726 |
| 10 | `src/arail/portal/scheduler.py`, `src/arail/portal/app.py`, `docs/PUBLISH.md`, `tests/test_health_metrics.py` | Observability: `_INFLIGHT_BY_LABEL`/`_COMPLETED_BY_LABEL` + `per_label_snapshot()`; `_BOOT_PERF`/`_BOOT_VERSION`/`_render_metrics()`; `/health`, `/healthz`, `/metrics` routes; allowlist extended; PUBLISH.md §10; 5 tests covering OBS1–OBS9. | 5 tests in `tests/test_health_metrics.py` (all pass) | a092c2c |

## Execution

### Step 1 — scheduler.py + fastpath_meter middleware
Commit: df74090
Delta: None from plan. Middleware registration ordering documented in docstring (FastAPI applies middleware in reverse registration order; fastpath_meter registered second, so runs outermost). Failure modes covered: A1 (try/finally), A2 (clamp), A5 (pure perf_counter), A7 (lazy init), A8 (ordering), A9 (prefix guard comment).

### Step 2 — Wrap six inference call sites
Commit: afd264b
Delta: None from plan. The `chat-stream` slot wraps the full `async for item in _stream_sync_iterator(...)` loop body with corrected indentation. `chat-default` at app.py:3532 received both `asyncio.to_thread` promotion and `inference_slot` per approved deviation §2. Failure modes: A1 (slot release on exception), A3 (documented), A6 (sixth site wrapped).

### Step 3 — pyproject.toml security extra
Commit: d02d8eb
Delta: None. pip-audit in `max` and `security`, absent from `min` and base. Verified 2 occurrences.

### Step 4 — security_scan.py
Commit: db92de2
Delta: Minor. `stream_scan_events()` uses `{"event": "__keepalive__"}` sentinel that the step-5 SSE handler converts to `: keepalive\n\n` SSE comment. `_SCAN_LOCK` uses lazy-init to avoid event-loop binding at import time. Failure modes: C1, C2, C4, C5, C7, C9, C10, F2.

### Step 5 — Admin endpoints
Commit: 3ac1be2
Delta: Actual insertion point was app.py:2999 (not :2807 — post-rebase the check-updates/stream handler body was longer). All seven endpoints present. `_PRUNE_LOCK = asyncio.Lock()` module-level is safe in Python 3.10+ (no explicit loop arg required). Failure modes: B1, B2, B3, B4, B5, B6, B7, B8, F3.

### Step 6 — admin.html Production Readiness section
Commit: 0d71997
Delta: None from plan. PR cards at admin.html:552 post-service-status. Visibility-change pause for perf polling (F4). 7th Quick Action button links `/docs/PUBLISH.md` (approved deviation §1). Failure mode: F1 (all fetches wrapped in try/catch with pr-err block + adminLog).

### Step 7 — Boot-scan task
Commit: f893a33
Delta: Insertion is at the natural end of `_startup()` (~line 472 post-rebase), not app.py:370. The architect's :370 ref was pre-rebase. `asyncio.CancelledError` explicitly re-raised (D3). Failure modes: C3, C8, D1, D3.

### Step 8 — SRE watchers
Commit: cd76949
Delta: Operational issue only — edits were initially applied to wrong branch and had to be re-applied. Content is identical to spec. `git add -f` required because `lab/pkb/agents/` is in `.gitignore` but the sre files are tracked. Failure modes: E1, E2, E5, E6.

### Step 9 — PUBLISH.md + README link
Commit: bcc0726
Delta: Minor. Cloudflare Access section links to current docs rather than embedding screenshots (H2). Apache not covered (H5). README link placed after INSTALL.md in "Where to read next". Failure modes: H1, H2, H3, H4, H5.

### Step 10 — /health + /metrics observability endpoints (mid-sprint addition)
Commit: a092c2c

Files changed:
- `src/arail/portal/scheduler.py`: +57 LOC. Added `_INFLIGHT_BY_LABEL`/`_COMPLETED_BY_LABEL` module dicts; threaded through `inference_slot` context manager (increment after acquire, decrement in finally — OBS6 mirror pattern); added `per_label_snapshot() -> dict[str, dict]`.
- `src/arail/portal/app.py`: +175 LOC. Added `PlainTextResponse` to top-level import; added `_BOOT_PERF`, `_read_version()`, `_BOOT_VERSION` at import time; extended `onboarding_gate` allowlist with `/health`, `/healthz`, `/metrics` + explanatory comment (OBS4); added `_escape_label_value()`, `_render_metrics()`, `liveness_probe()`, `prometheus_metrics()` adjacent to `/api/system/health`.
- `docs/PUBLISH.md`: +68 LOC. Appended §10 "Observability endpoints" with nginx restrict snippet (OBS7), per-metric table (OBS1), liveness vs. readiness distinction (OBS3), multi-worker note (OBS8).
- `tests/test_health_metrics.py`: +197 LOC (new file). 5 tests covering OBS1–OBS9.

Deviations from plan:
- Test OBS1 (package-name leak) initially used "requests" as sentinel package name — the word "requests" appears verbatim in HELP text ("Inference requests waiting..."), causing a false failure. Fixed by using synthetic sentinel "xyzzy-vuln-pkg-sentinel" that cannot collide with any help text. The implementation is correct; the test framing was the issue.
- `ARAIL_DATA_DIR` env override for security_scan in test relies on arail.config reading that env var. Confirmed working via test pass.

Failure modes covered (step 10): OBS1 OBS2(doc+arch: in-memory reads only) OBS3(doc: PUBLISH.md + handler docstring) OBS4(allowlist + 5 tests) OBS5(test_metrics_format_parses regex) OBS6(try/finally mirror) OBS7(PUBLISH.md §10 nginx snippet) OBS8(PUBLISH.md §10 multi-worker note) OBS9(try/except in _read_version and _render_metrics security block)

Pre-existing test failures (not introduced by this step, verified by stash check):
- `test_buddy_suggesters.py::test_next_experiment_flags_uncovered_term`
- `test_chat_ui.py::test_chat_page_renders_compact_single_thread_shell`
- `test_drafter.py::test_loader_resolves_drafter_via_seed`
- `test_toast_ui.py::test_css_includes_toast_styles`
- `test_toast_ui.py::test_activity_event_level_suggest_renders`

## Architect feedback required

None. Both approved deviations (§1 no new docs route, §2 sixth inference wrap) were baked into the build from the start. Step 8 branch confusion was an operational issue, not an architecture gap. Step 10 test sentinel fix was a self-contained correction within the commit; no architecture revision needed.

## Final state

**Commits:** 10 implementation commits + 1 BUILD_LOG skeleton = 11 total on this branch above the architect design commit.

**SHAs in build order:**
1. df74090 — scheduler.py + fastpath_meter middleware
2. afd264b — wrap six inference call sites
3. d02d8eb — pyproject.toml security extra
4. db92de2 — security_scan.py
5. 3ac1be2 — seven admin endpoints
6. 0d71997 — admin.html Production Readiness section
7. f893a33 — hybrid-mode boot security scan
8. cd76949 — SRE watchers
9. bcc0726 — PUBLISH.md + README link
10. a092c2c — /health + /metrics endpoints (Prometheus text)

**Tests:** 5 new tests in `tests/test_health_metrics.py`, all passing. All modules import cleanly.

**LOC delta (approximate, cumulative):**
- `src/arail/portal/scheduler.py` (step 1 NEW + step 10): ~232 LOC (+57)
- `src/arail/portal/security_scan.py` NEW: ~557 LOC
- `src/arail/portal/app.py`: ~590 LOC added (+175 for step 10)
- `src/arail/portal/templates/admin.html`: ~222 LOC added
- `lab/pkb/agents/sre/sre.py`: ~170 LOC added
- `lab/pkb/agents/sre/AGENT.md`: ~5 LOC added
- `docs/PUBLISH.md` NEW + §10: ~338 LOC (+68)
- `tests/test_health_metrics.py` NEW: ~197 LOC
- `README.md`: +1 LOC
- `pyproject.toml`: +3 LOC
- **Total: ~2315 LOC added**

**Failure modes covered:** A1 A2 A3(doc) A4(doc) A5 A6 A7 A8 A9 | B1 B2 B3 B4 B5 B6 B7 B8 | C1 C2 C3 C4 C5 C6 C7 C8 C9 C10 | D1 D2(doc) D3 | E1 E2 E3(no action needed) E4(post-ship follow-up per architect) E5 E6 | F1 F2 F3 F4(doc) | G1-G4 (existing handler verified) | H1 H2 H3 H4 H5 | OBS1 OBS2(doc) OBS3(doc) OBS4 OBS5 OBS6 OBS7(doc) OBS8(doc) OBS9

**Intentional deferred items (per ARCHITECTURE.md):**
- A3: streaming holds slot for full duration — Phase-2 per-token reacquire
- A4: background callers (researcher/agents) bypass queue — Phase-2
- E4: SRE severity=error flattened to "warn" in emit — post-ship follow-up
