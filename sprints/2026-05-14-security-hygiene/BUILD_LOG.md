# Build log: security-hygiene (four-item bundle)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5f1dda8
**Started:** 2026-05-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `docs/PRIVACY.md` | Add loopback trust-boundary paragraph | None (doc-only) | b78ff04 |
| 2 | `src/arail/portal/services/opencode.py` | `RedactingLogWriter` class + OS pipe + daemon thread + chmod 0600 + tombstone truncation | `tests/test_opencode_log_redaction.py` | db3265c |
| 3 | `src/arail/portal/services/opencode.py` | `start_new_session=True` at both Popen call-sites | `tests/test_opencode_subprocess_cleanup.py` | 41bbcfe |
| 4 | `src/arail/portal/app.py` | Sec-Fetch-Site gate before Origin check in `post_airgap_toggle` | `tests/test_airgap_sec_fetch_site.py` | 53b9667 |

## Execution

### Step 1 — PRIVACY.md trust paragraph
Added a new "Loopback trust boundary" section immediately before "A note on
schools / shared lab machines". Paragraph names the perimeter explicitly,
explains no-auth design choice, references the CSRF defences on
`/api/airgap/toggle` and their intended scope. No code changes.
Commit: b78ff04

### Step 2 — Token redaction in opencode.log
Added to `opencode.py`:
- `_RedactingLogWriter` class: write-time token replacement with tail-buffer
  (cross-chunk split protection), chmod 0600 on open, idempotent close.
- `_pipe_reader_thread`: daemon thread that drains pipe into the writer.
- `_open_log_with_redactor`: helper that performs tombstone-drop of any
  existing log + rotated `.log.1`, then returns (write_fd, writer, thread)
  for caller to wire into Popen.
- `_maybe_rotate_log` updated to chmod 0600 on the rotated `.log.1`.
- Both `start()` and `_start_inner()` Popen call-sites wired through the
  pipe/redactor instead of a bare `log_file.open("ab")` fd.

Delta from plan: one bug found during TDD — initial tail-buffer logic was
inverted (flushed too early, missing cross-chunk splits). Fixed before commit;
all 10 tests pass.

Commit: db3265c

### Step 3 — start_new_session=True
Added `start_new_session=True` kwarg to both `subprocess.Popen` call-sites
in `start()` and `_start_inner()`. One-line change per site on top of the
Item 2 pipe wiring. Tests confirmed both call-sites carry the kwarg and that
a real child process becomes its own pgid leader with cascading SIGTERM.
Commit: 41bbcfe

### Step 4 — Sec-Fetch-Site gate
Inserted the Sec-Fetch-Site check in `post_airgap_toggle` in `app.py`
between the bind-loopback gate and the Origin gate, exactly per the
ARCHITECTURE.md decision matrix. Rejects `cross-site` and `none` with 403
`cross_site`; accepts `same-origin` / `same-site` and falls through; unknown
or absent values fall through to Origin gate (legacy / curl / TestClient
paths unaffected). 9 new tests in `test_airgap_sec_fetch_site.py` covering
all matrix cells plus header-name case-insensitivity and gate-ordering
proof.
Commit: 53b9667

## Architect feedback required
None. No gaps surfaced. Plan executed as written.

## Final state

| Metric | Value |
|---|---|
| Commits (this sprint) | 5 (skeleton + 4 items) |
| New test files | 3 |
| New tests | 23 (10 redaction + 4 subprocess + 9 sec-fetch-site) |
| Existing airgap tests (regression) | 59 unchanged, all pass |
| Full targeted suite | 92 passed, 0 failed |
| Files touched | `docs/PRIVACY.md`, `src/arail/portal/services/opencode.py`, `src/arail/portal/app.py` |
| Scope drift | None |
| TODOs without owner | None |
| Commented-out code | None |
