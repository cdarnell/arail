# Build log: security-hygiene (four-item bundle)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5f1dda8
**Started:** 2026-05-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `docs/PRIVACY.md` | Add loopback trust-boundary paragraph | None (doc-only) | pending |
| 2 | `src/arail/portal/services/opencode.py` | `RedactingLogWriter` class + OS pipe + daemon thread + chmod 0600 + tombstone truncation | `tests/test_opencode_log_redaction.py` | pending |
| 3 | `src/arail/portal/services/opencode.py` | `start_new_session=True` at both Popen call-sites | `tests/test_opencode_subprocess_cleanup.py` | pending |
| 4 | `src/arail/portal/app.py` | Sec-Fetch-Site gate before Origin check in `post_airgap_toggle` | `tests/test_airgap_sec_fetch_site.py` | pending |

## Execution

### Step 1 — PRIVACY.md trust paragraph
pending

### Step 2 — Token redaction in opencode.log
pending

### Step 3 — start_new_session=True
pending

### Step 4 — Sec-Fetch-Site gate
pending

## Architect feedback required
None.

## Final state
pending
