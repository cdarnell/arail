# Review: airgap-runtime-toggle

**Date:** 2026-05-07
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 0618519
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 809d9c8
**Branch:** `qukaizen/arail-airgap-runtime-toggle`

## Verdict: WEAK_PASS

## Summary

The build is solid. The env_writer is honest, hand-rolled per spec — every parser branch (BOM, CRLF, single/double quote, inline comment, missing line, missing-final-newline, duplicate, symlink-refusal, value-already-equals no-write) is covered by an explicit test, and the 32-thread torn-write test passes. The endpoint honors the bind-address gate with the exact spec copy, the two-step token flow rejects replay/wrong-target/expired tokens, the side-effect order (disk → `os.environ` → audit → activity-log) matches §7, and the Buddy watcher end-to-end test demonstrates the mode toggle propagates without touching `_builtin_buddy.py`. 42 new tests, 0 regressions on the 69 prior airgap tests. Two minor gaps keep this from a clean PASS: the spec's `Sec-Fetch-Site` header check was not implemented (only `Origin` is checked), and the success response leaks the full `.env` filesystem path (spec-allowed but worth flagging). Both are non-blocking, but document them in BUILD_LOG follow-ups.

## Builder-flagged items

1. **`_toggle_env_path()` parents[3] walk** — verdict: ACCEPTABLE. The loop tries `parents[3]` first then falls back. In editable / dev install `parents[3]` is the repo root (verified). For wheel install the `_TOGGLE_ENV_PATH` override is the documented escape hatch, and tests use it. Recommend a follow-up to make this explicit via `ARAIL_LAB_ROOT` env var rather than path-arithmetic; not blocking.
2. **`_append_audit` cross-process atomicity** — verdict: ACCEPTABLE WITH NOTE. Single-worker uvicorn is the documented portal mode (ARCHITECTURE.md tech-debt §). The `O_CREAT|O_APPEND` (no `O_EXCL`) on first-create allows two simultaneous first-toggles to both `O_CREAT` the file, but `O_APPEND` semantics keep writes atomic on POSIX, so no line-tearing risk. Multi-worker is explicitly out-of-scope.
3. **Concurrency `Semaphore(1)` serialization** — verdict: CORRECT INTERPRETATION. The spec's token-invalidation rule ("issuing a new token for an existing target invalidates older outstanding tokens") makes naive 8-thread parallel step-1 racing on 2 targets self-defeating. Serializing step-1→step-2 within each thread while still letting step-2 disk writes contend in parallel is the right test design and is reinforced by the separate `test_env_writer_concurrent_no_torn_file` 32-thread direct-writer test.

## Spec checklist walk

- **§2 Two-step token flow** — CLOSE. `_issue_token` invalidates prior tokens for same target; `_consume_token` deletes on success (single-use), checks expiry, checks target match. Tests: `test_toggle_token_replay`, `test_toggle_token_expired`, `test_toggle_token_wrong_target`. Token is `secrets.token_urlsafe(24)` (192 bits) — brute-force infeasible.
- **§3 Bind-address gate** — CLOSE. `_toggle_bind_is_loopback()` matches spec exactly. 403 body matches spec copy verbatim (`test_toggle_bind_gate_lan` asserts the exact message). Frontend renders static bind-warning when `bind_is_loopback=false` (nav.js:211-213).
- **§4 `.env` rewriter** — CLOSE. Hand-rolled, never `dotenv.set_key`. All 16 round-trip cases land. Symlink refused. Duplicates: first replaced, rest left, warning logged.
- **§5 Atomic write** — CLOSE. `O_WRONLY|O_CREAT|O_EXCL` + `fsync` + `chmod 0o600` + `os.replace`. On exception, tmp unlinked.
- **§6 Per-path lock** — CLOSE. `WeakValueDictionary[Path, Lock]` keyed on resolved path; module-level `_LOCKS_GUARD` for insertion.
- **§7 Side-effects ordering** — CLOSE. Disk write → `os.environ` mutation → audit append → activity-log emit. Order matches spec; failures stop before `os.environ`.
- **§8 Frontend** — CLOSE. State-dependent button copy, 3s countdown, confirm-cancel, error states all wired in nav.js. HTML matches spec structure.
- **§9 `bind_is_loopback` on /api/airgap/status** — CLOSE. Added at app.py:6577; tests in `TestAirgapStatusBindField`.
- **§11 Failure modes** — MOSTLY CLOSE. Each row covered:
  - File-write race → `test_concurrent_writers_no_torn_line`
  - `.env` symlink → `test_symlink_raises`
  - Token replay → `test_toggle_token_replay`
  - LAN-CSRF → bind-gate tests
  - Path/value leakage in error → `test_toggle_writer_failure` asserts no path/contents in error body
  - Legacy client (no token) → endpoint treats missing token as step-1
  - Multi-worker token-table inconsistency → documented, not implemented (out of scope)

## Open items (non-blocking)

- **OPEN [ASK] `Sec-Fetch-Site` header not checked.** Spec §2 says "Origin / Sec-Fetch-Site CSRF check." Code only checks `Origin == Host`. `Sec-Fetch-Site: same-origin` would be a defense-in-depth backstop for browsers that send it (Chrome/FF). File a follow-up.
- **OPEN [INFO] success body leaks `env_path`.** Spec lists this field in the 200 response, so it's spec-compliant — but a tab-CSRF that *somehow* gets past the Origin check would learn the full filesystem path of the user's `.env`. Consider returning a relative path or `null` in a follow-up.
- **OPEN [INFO] `_toggle_env_path()` parents-walk** is fragile under wheel install. Suggest `ARAIL_LAB_ROOT` env-var resolution as cleaner long-term fix.

## Win-condition cross-check

| VISION clause | Witness |
|---|---|
| `lab_mode()` returns new value | `test_watcher_detects_toggle_to_hybrid` (asserts `os.getenv("LAB_MODE") == "hybrid"`) |
| `os.environ` updated | same test, plus `test_toggle_happy_two_step` |
| `.env` rewritten atomically with comments preserved | `test_env_writer.py` 16 round-trip cases |
| Restart preserves | implicit (file on disk) — manual smoke pending |
| Buddy watcher fires next tick | `test_buddy_watcher_after_runtime_toggle.py` (both directions) |
| Env-rewriter edge cases | `test_env_writer.py` |
| Concurrent-toggle serialization | `test_airgap_toggle_concurrency.py` + `test_env_writer_concurrent_no_torn_file` |
| Bind-address refusal | `test_toggle_bind_gate_lan` (exact spec copy verified) |

## Test coverage assessment

42 new tests, all passing. 69 prior airgap tests still pass. Coverage on changed lines is well above 80% (every branch in `env_writer.py` and the `post_airgap_toggle` route has a test). No untested code paths flagged.

## Performance assessment

Not on a hot path. No benchmark required per spec.

## Tech debt delta

Matches ARCHITECTURE.md prediction: one new audit file format, one new in-memory token table, one hand-rolled parser. No new debt the architect didn't anticipate.

## For QA — the paranoid hammer list

Per arail product gate (30% setup, 30% Buddy, 20% security, 10% happy, 10% regression):

**Security (priority):**
- **Bypass attempts on the bind gate.** Try `BIND_ADDR=0.0.0.0`, `BIND_ADDR=192.168.x.x`, `BIND_ADDR=` (empty), `BIND_ADDR=  127.0.0.1  ` (whitespace), `BIND_ADDR=LOCALHOST` (uppercase). Confirm 403 in every non-loopback case and `.env` mtime untouched.
- **CSRF — try without `Origin` header at all.** The endpoint's `if origin:` guard means a curl without `Origin` slips past the cross-origin check. Verify this is acceptable (legacy-client behavior) and that the bind-gate + token flow + 3s countdown still constitute defense in depth.
- **Token brute force / replay across targets.** Issue token for hybrid; try to use it for airgapped (should 409). Replay a consumed token (should 409). Try 100 random tokens (all should 409).
- **Path leakage on error.** Patch `set_env_var` to raise; confirm 500 body has no path, no `.env` content. (`test_toggle_writer_failure` covers; QA should re-verify by reading the network response body raw.)
- **Symlink attack.** Replace `.env` with a symlink pointing at `~/.ssh/authorized_keys` and click toggle — should refuse with `EnvWriterError`, target untouched.

**Setup (priority):**
- Run `./arail setup && ./arail start` on a clean VM; toggle once; restart; confirm `LAB_MODE=hybrid` survives in `.env`.
- Run with editable install AND with wheel install — verify `_toggle_env_path()` resolves to a real `.env` in both cases or that `_TOGGLE_ENV_PATH` override path is documented.
- Toggle when `.env` is missing entirely (test covers `appended=True`; QA: portal smoke).

**Buddy:**
- After UI toggle, wait one watcher tick (≤60s); confirm Pip's activity feed shows "Door's open now…" or "Sealed back up…" Observation. State.json updates. EgressBlocked fires correctly on next public fetch in airgapped.
- Toggle rapidly back and forth 5 times — confirm Buddy doesn't double-fire or skip an Observation.

**Happy / UX:**
- Click toggle button → confirm panel appears → button reads `Confirm (3)` → counts down → enables → click → modal closes → re-opens → pill shows new mode.
- Click Cancel mid-countdown — confirm idle button restored.
- Network failure mid-confirm — confirm a sane error appears and `.env` is untouched.

**Regression:**
- All PR #35 airgap tests still pass (verified: 69 tests, 0 fail).
- `/api/airgap/status` shape — additive `bind_is_loopback` field doesn't break existing consumers.

## Required actions before merge

None blocking. File three follow-up tickets:
1. Add `Sec-Fetch-Site: same-origin` enforcement (defense-in-depth).
2. Reduce `env_path` leakage in success response.
3. Replace `parents[3]` walk with explicit `ARAIL_LAB_ROOT` resolution.
