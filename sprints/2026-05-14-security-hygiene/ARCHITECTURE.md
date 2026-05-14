# Architecture: security-hygiene (four-item bundle)

**Date:** 2026-05-14
**Sprint:** [SPRINT.md](./SPRINT.md)
**Branch:** `qukaizen/arail-security-hygiene`
**Mode:** design

## Restatement

Four deferred security follow-ups, all small, framed together for review
amortization but partitioned for independent build/revert. Item 1 makes
the lab's loopback trust boundary explicit in `docs/PRIVACY.md`. Item 2
prevents provider tokens that opencode receives via subprocess env from
ending up in `lab/logs/opencode.log` on disk. Item 3 makes the opencode
subprocess a process-group leader (`os.setsid`) so a portal SIGTERM
cascades and the child is not orphaned. Item 4 adds a `Sec-Fetch-Site`
defense-in-depth gate to `/api/airgap/toggle`, now that the
confirm-token two-step is gone and `Origin` is the sole CSRF defense.

## Independent-revertability invariant

Each item lives in its own commit (or commits) and touches a disjoint
file set wherever possible. Cross-item file overlap is only items 2+3,
both in `src/arail/portal/services/opencode.py`. Items 2 and 3 land in
separate commits so either can be reverted alone. If any one item fails
review, the other three ship.

## Cross-item concerns

- **Shared file (items 2 & 3):** `src/arail/portal/services/opencode.py`,
  specifically the two `subprocess.Popen` spawn sites in `start()`
  (~line 192) and `_start_inner()` (~line 327). Builder must apply both
  changes at both call-sites and not leave the helpers divergent.
- **Shared test surface (items 2 & 3):** both add new test files under
  `tests/`. Neither extends an existing file. Independent imports.
- **No other shared state.** Items 1 and 4 touch disjoint files
  (`docs/PRIVACY.md`, `src/arail/portal/app.py`).

---

# Item 1 — PRIVACY.md trust-model paragraph (doc-only)

## Assumptions

- Anyone reaching `127.0.0.1:8080` already has full host privileges
  through the portal API. **Verified against code:**
  - `BIND_ADDR` defaults to `127.0.0.1` (PRIVACY.md §"What the lab itself
    never sends").
  - The portal has no auth (PRIVACY.md §"A note on schools" already
    states "Anyone who reaches `127.0.0.1:8080` is 'the user'").
  - The airgap toggle gates on `BIND_ADDR` being loopback (§Bind-address
    gate), confirming loopback is treated as trusted.
  - opencode subprocess management endpoints (`/api/opencode/start`,
    `/api/opencode/stop`) have no auth.
- The existing schools/shared-machines paragraph already implies the
  trust boundary; this item makes it the *primary* statement, not a
  closing aside.

## Interface contract

- **Promises:** A new paragraph (or short subsection) is appended to
  `docs/PRIVACY.md` that names "loopback = trust boundary" explicitly.
- **Requires:** Nothing at runtime.
- **Bad input:** N/A — Markdown only.

## Data flow

```
docs/PRIVACY.md (existing)
        │
        ▼  (append paragraph under or before §"A note on schools")
docs/PRIVACY.md (updated, same file, no other artifacts)
```

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Paragraph claims something the code doesn't enforce | Architect review reads paragraph against `app.py` endpoints | Edit paragraph or fix code before merge |
| Paragraph contradicts existing §"A note on schools" copy | Builder reads existing paragraph and harmonizes | Merge or rewrite both as one section |
| Markdown rendering breaks (broken heading level, list nesting) | Visual inspection at review | Fix syntax |

## Test strategy

- **None.** Doc-only change. Architect review verifies the claim against
  current code (`/api/airgap/toggle`, `/api/opencode/start`, no auth
  middleware in `app.py`). This is acceptable per `arail/CLAUDE.md` QA
  allocation — docs are not in the 30/30/20/10/10 split.

## Tech debt assessment

- **Added:** None.
- **Repaid:** Removes the implicit-knowledge tax — operators no longer
  have to infer the trust boundary from scattered hints.
- **Net:** Negative (debt removed).

## Recommended landing

Land first. Trivial, unblocks reasoning about items 2-4 (item 4 in
particular cites the loopback trust boundary).

---

# Item 2 — Token redaction in `lab/logs/opencode.log`

## Assumptions

- opencode inherits provider tokens via subprocess env (verified in
  `src/arail/portal/services/opencode.py:_compute_source_env()` at
  lines 371-431): `ANTHROPIC_API_KEY`, `NVIDIA_API_KEY`,
  `OPENROUTER_API_KEY`, `HF_TOKEN`, `MODEL_API_KEY`, plus the legacy
  `OPENCODE_API_KEY` mirror.
- opencode's own log output may include those values when it errors
  on auth, prints debug traces, or echoes config. Worst case is a
  401-body echo; best case is none. We must defend the worst case.
- `OPENCODE_LOG_LEVEL=WARN` is already set, which reduces but does not
  eliminate the risk (a WARN-level auth failure can still print headers
  on some clients).
- The log file is currently created by `log_file.open("ab")`. It is NOT
  explicitly `chmod 0600` after open — Python `open(..., "ab")` uses
  `0o666 & ~umask`, typically `0o644`. **This is a separate hardening
  item; we will fix it in this same commit (Item 2) since the threat
  model is identical.**
- The log already rotates at 10 MB to `opencode.log.1`. The rotated file
  inherits the same permission story.

### Choice: write-time redaction (NOT rotation/truncation)

**Argued:** Rotation alone does not redact — it just bounds the window
in which a token sits on disk. A 10 MB log can contain hundreds of
token impressions; an attacker with read access between rotations wins.
Truncation on every start is brittle (it erases legitimate debug
context) and still leaks during the run.

**Write-time redaction** intercepts the file descriptor that `Popen`
inherits as stdout/stderr. We wrap the log file with a thin
`RedactingLogWriter` that:
1. Holds a list of *current* secret strings (the env values
   `_compute_source_env()` exports for the spawning provider, plus the
   `OPENCODE_API_KEY` mirror).
2. On every `write(bytes)` call, replaces each non-empty secret with
   `***REDACTED***` (case-sensitive byte match; tokens are
   high-entropy so collision risk is negligible).
3. Buffers a tail of `max(secret_len)-1` bytes across writes so a token
   split across two `write()` calls is still caught on the second write.
4. Is wired in by replacing `subprocess.Popen(..., stdout=f, stderr=f)`
   with a redirecting fd produced by an OS pipe + a daemon reader
   thread that consumes the pipe and forwards through the redactor to
   the actual log file.

**Backward redaction:** Existing log content from prior runs is NOT
redacted by this sprint. On portal start (in `start()` before the
spawn), if `lab/logs/opencode.log` exists and is non-empty, we
*truncate* it to zero bytes after copying to `opencode.log.0` (a
single-shot "pre-redaction tombstone" that is then unlinked — i.e., the
data is dropped, not preserved). This is the cleanest path: we cannot
safely retroactively redact arbitrary content because we may not know
all tokens that were valid during a prior run. Document this in the
docstring and BUILD_LOG.

**Permission hardening:** After opening the log, call
`os.chmod(log_file, 0o600)`. Apply to the rotated `.log.1` as well in
`_maybe_rotate_log`.

## Interface contract

- **`RedactingLogWriter`** (new class in `opencode.py`, private):
  - Constructed with `path: Path, secrets: list[bytes]`.
  - Method `write(chunk: bytes) -> int`. Returns bytes accepted.
  - Method `close() -> None`. Idempotent.
  - Promises: every byte sequence equal to a non-empty secret is
    replaced with `b"***REDACTED***"` before reaching disk. The
    redactor never raises on bad bytes; it falls back to writing the
    chunk through (defensive) and logs a single WARN per process.
  - Bad input: empty/None secrets are filtered out at construction
    (cannot redact an empty string — would loop).
- **`start()` / `_start_inner()`** Popen calls:
  - Replace `stdout=f, stderr=f` with a redirect through an OS pipe.
  - A daemon thread reads the pipe, forwards through
    `RedactingLogWriter`, exits on EOF (child death).
  - Promises the existing `{"ok": True, "pid": int}` shape is unchanged.

## Data flow

```
opencode child stdout/stderr
        │
        ▼
   OS pipe (write end given to Popen)
        │
        ▼
daemon reader thread (per-process)
        │
        ▼
RedactingLogWriter.write(chunk)
   │
   │  splits chunk on secret bytes, replaces with ***REDACTED***
   │  carries a tail buffer of (max_secret_len - 1) bytes
   ▼
lab/logs/opencode.log  (chmod 0600)
```

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Tokens already in the log from prior runs | Builder truncates `opencode.log` on start (after rotation check) | Document: existing log is dropped; rotated `.log.1` is also dropped on the first post-upgrade start to avoid carrying old tokens forward |
| Partial-line writes split across two `write()` calls | Tail buffer of `max(len(s) for s in secrets) - 1` bytes across writes | Tested by feeding a token in two chunks |
| False positive (string looks like a token but isn't) | High-entropy values only; minimum length check (skip secrets shorter than 8 bytes) | Document in code comment; acceptable for security-over-precision |
| Log permission too permissive (`0o644`) before fix | `os.stat().st_mode` check at unit test | `os.chmod(log_file, 0o600)` after open; also on `.log.1` rotation target |
| Reader thread crashes mid-read | Daemon thread; failure logged once; subsequent child output is lost (worst case logs are gone but no token leaks). Pipe write end stays open in child, so child does not block (pipe buffer caps; if it fills, child blocks on write — acceptable degraded mode for a debug log) | Operator sees missing logs → restart opencode |
| Secret list goes stale (provider switch after spawn) | Provider-switch path already calls `restart()` (`app.py:1088`); on restart a fresh log writer is built with fresh secrets | No action needed |
| Token contains regex metacharacters | We use byte-level `str.replace`, not regex | N/A — no regex escaping needed |
| Writer is given a secret equal to `***REDACTED***` | Hardcoded sentinel collision is theoretical (high-entropy tokens never collide with this literal) | Documented |
| `os.chmod` fails on a filesystem that does not support modes (Windows on FAT, some WSL paths) | Wrap in `try/except OSError`, `_log.warning` once | Best-effort; document |

## Test strategy

New file: `tests/test_opencode_log_redaction.py`.

- **Unit (RedactingLogWriter):**
  - `test_redacts_single_token_in_chunk`
  - `test_redacts_token_split_across_two_writes`
  - `test_redacts_multiple_distinct_tokens`
  - `test_passes_through_when_no_secrets`
  - `test_ignores_empty_or_short_secrets` (< 8 bytes)
  - `test_chmod_0600_after_open` (skip on Windows)
- **Unit (rotation/truncation behavior):**
  - `test_existing_log_truncated_on_start` (mock Popen; assert
    pre-existing content is dropped)
  - `test_rotated_log_also_redacted_permissions`
- **Integration:**
  - `test_subprocess_stdout_through_redactor` — spawn a tiny Python
    `-c "print('SECRET_TOKEN_ABCDEF1234')"` process via the redactor
    path; assert file contains `***REDACTED***` and not the token.

## Tech debt assessment

- **Added:** A daemon reader thread per opencode subprocess. Minor; the
  thread is a few dozen lines and dies with the child. Adds one new
  class to `opencode.py`.
- **Repaid:** Closes architect F-SEC-4 (carryover #4 from 05-04 sprint).
  Also opportunistically fixes log file mode (0o644 → 0o600).
- **Net:** Slightly positive (one new internal abstraction), justified
  by closing a security follow-up.

## Recommended landing

Land second (after item 1, before item 3) — both touch `opencode.py`
but item 2 is the larger change; landing it first means item 3 is a
clean one-line addition on top.

---

# Item 3 — `os.setsid` on opencode subprocess

## Assumptions

- The spawn sites are `subprocess.Popen` calls in `start()` (line ~192)
  and `_start_inner()` (line ~327) in `opencode.py`.
- Portal runs under uvicorn/FastAPI. On portal SIGTERM, no current code
  signals the opencode child — it relies on the user clicking Stop or
  on `lsof -ti :PORT | kill` via the stop endpoint. If the portal dies
  unexpectedly, the child is orphaned and keeps the port bound.
- Adding `start_new_session=True` (preferred Python 3.2+ idiom; equivalent
  to `preexec_fn=os.setsid` but without the `preexec_fn` thread-safety
  caveats) makes the child a process-group and session leader. A signal
  delivered to the **process group** of the child reaches the child and
  any of its grandchildren.
- This does NOT install a signal handler in the portal to forward
  SIGTERM. That is an explicit non-goal (would need a supervisor
  pattern); we document it.

### Choice: `start_new_session=True` (NOT `preexec_fn=os.setsid`)

`start_new_session=True` was added in 3.2 specifically to avoid the
fork-thread deadlock hazard of `preexec_fn`. It is the standard
recommendation. We use it.

## Interface contract

- **`Popen` kwargs** in both call-sites add `start_new_session=True`.
- **Promises:** child is its own process-group leader. Killing the pgid
  (`os.killpg(pid, SIGTERM)`) reaches the child and any of its
  grandchildren. No other behavior changes.
- **Bad input:** N/A (kwarg is a literal).

## Data flow

```
subprocess.Popen([...], start_new_session=True)
        │
        ▼
Child setsid() → new session → new pgid == child.pid
        │
        ▼
Any grandchildren the opencode binary spawns inherit the pgid
        │
        ▼
On portal-issued stop: os.killpg(child.pid, SIGTERM)
   reaches child + grandchildren
```

**Note:** We do NOT change `stop()` in this item — current `stop()`
uses `lsof -ti :PORT | kill` which is unaffected and orthogonal. The
benefit of `setsid` here is *future-proofing* (if/when stop is rewritten
to use the pid we tracked) and reducing orphan blast radius if the
portal itself dies.

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Portal receives SIGTERM, sends SIGTERM to pgid — long-running opencode shutdown handlers truncated | Out of scope this sprint (we do NOT install portal SIGTERM handler) | Future ticket: add a 2-second SIGTERM → SIGKILL grace in a supervisor |
| Portal crashes with SIGKILL (uncatchable) | pgid cleanup does NOT happen automatically — child survives in its own session, retains the port | Operator runs `./arailctl start` → idempotent restart detects port busy with opencode fingerprint and reuses it (existing behavior at `_is_opencode_on_port`) |
| macOS vs Linux delta | `setsid(2)` is POSIX; `start_new_session=True` works identically on Darwin and Linux. Windows is not supported (Popen raises ValueError on Windows for this kwarg in older Pythons; arail's opencode flow is not exercised on Windows in any case) | If Windows ever becomes a target, gate the kwarg on `platform.system() != "Windows"` |
| daemon-mode interaction (uvicorn `--workers N > 1`) | Each worker spawns its own opencode if asked; setsid does not change that. The `_lock` in `opencode.py` is per-process, not cross-worker — pre-existing limitation, not in scope | Documented in opencode.py module docstring (existing) |
| Test isolation: spawning subprocesses with new sessions in pytest under macOS sometimes inherits parent process group oddly | Pytest test wraps `Popen` and asserts `os.getpgid(child.pid) == child.pid` | If flaky on CI, mark with `@pytest.mark.skipif(sys.platform == ...)` and run locally |

## Test strategy

New file: `tests/test_opencode_subprocess_cleanup.py`.

- **Unit:**
  - `test_popen_kwargs_include_start_new_session` — monkeypatch
    `subprocess.Popen` to capture kwargs; call `oc.start()`; assert
    `start_new_session is True`. Do this for both `start()` and
    `_start_inner()` paths (the latter via `restart()`).
- **Integration (POSIX only):**
  - `test_child_is_pgroup_leader` — spawn a `python -c "import time;
    time.sleep(30)"` shim via the same Popen kwargs the production code
    uses; assert `os.getpgid(pid) == pid`. Clean up with `os.killpg`.
  - `test_killpg_cascades_to_grandchild` — shim launches a grandchild
    sleeper; assert `os.killpg(pid, SIGTERM)` ends both.
- **Skip on Windows** with `@pytest.mark.skipif(sys.platform == "win32")`.

## Tech debt assessment

- **Added:** None (one kwarg).
- **Repaid:** Closes architect F-PROC-3 (carryover #5 from 05-04
  sprint). Reduces orphaned-child surface area on portal hard-kill.
- **Net:** Negative.

## Recommended landing

Land third — sits on top of item 2's changes in the same file. One-line
addition to each of the two `Popen` calls.

---

# Item 4 — `Sec-Fetch-Site` defense-in-depth on `/api/airgap/toggle`

## Assumptions

- `/api/airgap/toggle` currently gates on (1) loopback bind, (2) Origin
  matches Host (when Origin is present), (3) body validation. Origin is
  the sole *browser* CSRF defense.
- `Sec-Fetch-Site` is a Fetch-Metadata header browsers force-set on
  every navigation/fetch since Chrome 76, Firefox 90, Safari 16.4. It
  cannot be forged from JavaScript on the attacker's page. Non-browser
  clients (curl, Python `requests`, pytest TestClient) do NOT send it.
- Sec-Fetch-Site legal values per spec: `same-origin`, `same-site`,
  `cross-site`, `none`.

### Decision matrix (legal values)

| Sec-Fetch-Site value | Meaning | Verdict | Justification |
|---|---|---|---|
| absent | Not a fetch-metadata-capable client (curl, old browser, tests) | **fall through** to Origin gate | Don't break legacy clients or local CLI tests |
| `same-origin` | Browser fetch from the portal itself | **accept** | Legitimate path |
| `same-site` | Same eTLD+1 but different origin — n/a for loopback (no eTLD), but treat as accept since loopback "site" is degenerate | **accept** | Loopback peers are already trusted (item 1) |
| `cross-site` | Cross-site fetch — classic CSRF vector | **reject 403 cross_site** | The exact threat we're defending against |
| `none` | User typed URL in address bar / opened from bookmark / app-initiated | **reject 403 cross_site** | A POST to `/api/airgap/toggle` cannot originate from the address bar (GET only); a `none` POST is anomalous and rejecting is safe. Browsers also set `none` for some service-worker-initiated POSTs which are not relevant for this endpoint. **If this turns out to break a legitimate path during QA, we soften to accept and document.** |
| unknown / future value | Spec evolution | **fall through** to Origin gate (treat like absent) | Forward-compatible |

### Interaction with existing Origin check

The two gates must compose cleanly — no request receives a double
rejection with conflicting error messages.

**Order:** Sec-Fetch-Site is checked *before* Origin. If
Sec-Fetch-Site is present and indicates `cross-site` or `none`, return
403 `cross_site`. If Sec-Fetch-Site is `same-origin` or `same-site`,
the Origin check is still evaluated (defense in depth — both must pass
if both are present). If Sec-Fetch-Site is absent or unknown, skip
straight to the Origin check (current behavior preserved).

Error codes are distinct: existing `cross_origin` vs new `cross_site`.
A single request only ever returns one of them because Sec-Fetch-Site
short-circuits before Origin runs.

## Interface contract

- **`/api/airgap/toggle`** request gate logic:
  1. Bind-loopback gate (unchanged).
  2. **NEW:** Sec-Fetch-Site gate (see decision matrix). 403 `cross_site`
     on reject.
  3. Origin-vs-Host gate (unchanged, runs after Sec-Fetch-Site passes
     or is absent).
  4. Body validation (unchanged).
- **No JS change** in `nav.js`. Browsers force-set Sec-Fetch-Site; we
  do not opt into it client-side.
- **Promises:** Cross-site `<form>` POST or `fetch()` from `evil.com` is
  rejected by Sec-Fetch-Site even if the attacker has somehow
  Origin-spoofed (they cannot, but defense in depth). Existing
  loopback fetches (the portal's own UI) continue to work because
  browsers send `same-origin` for them.

## Data flow

```
POST /api/airgap/toggle
        │
        ▼
1. BIND_ADDR loopback? ── no ──► 403 bind_not_loopback
        │ yes
        ▼
2. Sec-Fetch-Site header present?
        │
        ├── absent / unknown ──► fall through to step 3
        ├── same-origin / same-site ──► proceed to step 3
        └── cross-site / none ──► 403 cross_site
        │
        ▼
3. Origin header present?
        │
        ├── absent ──► proceed to step 4
        ├── matches Host ──► proceed to step 4
        └── mismatch ──► 403 cross_origin
        │
        ▼
4. Parse body, validate target, write .env, audit, 200
```

## Failure modes

| Failure | Detection | Recovery |
|---|---|---|
| Browser sends `Sec-Fetch-Site: cross-site` from evil.com | Reject 403 cross_site | Primary defense — tested |
| Browser sends `Sec-Fetch-Site: same-origin` from portal | Accept, continue to Origin check | Tested |
| Sec-Fetch-Site absent (curl, pytest TestClient) | Fall through to Origin gate (existing behavior) | Tested: existing tests pass without modification |
| Sec-Fetch-Site `none` (typed URL) | Reject 403 cross_site | Justified above; if QA finds a legit `none` POST we soften |
| Sec-Fetch-Site unknown future value | Treat as absent — fall through | Forward-compatible |
| Both Sec-Fetch-Site cross-site AND Origin mismatch | Sec-Fetch-Site short-circuits → 403 cross_site only | Single error path; documented |
| Case-insensitivity of header name | FastAPI Headers are case-insensitive via Starlette MultiDict; `request.headers.get("sec-fetch-site")` works | Tested with mixed case |
| Header value parsing — extra whitespace | Strip + lower-case before comparison | Tested |
| Spoofing from attacker page | Sec-Fetch-Site is forbidden-header in browsers; JS cannot set it. From non-browser clients (curl, etc.) the attacker has shell on the host already → item 1 trust boundary | Documented |
| Legacy browsers that pre-date Sec-Fetch-Site | Absent → fall through to Origin gate | No regression for legacy clients |

## Test strategy

**Choice:** New file `tests/test_airgap_sec_fetch_site.py`, NOT extending
`tests/test_qa_airgap_onetap_paranoid.py`. Two reasons:

1. The paranoid file is QA-owned (created by the prior sprint's PR #49)
   and we should not pre-empt QA's allocation by editing it during the
   architect-build phase.
2. A dedicated file keeps the item self-contained and revertable.

Tests:

- `test_sec_fetch_site_cross_site_rejected` — POST with header
  `Sec-Fetch-Site: cross-site`; assert 403 + body `{"error":
  "cross_site"}`; assert env unchanged; assert no audit line.
- `test_sec_fetch_site_none_rejected` — same, with `none`.
- `test_sec_fetch_site_same_origin_accepted` — same-origin + matching
  Origin; assert 200 + env changed.
- `test_sec_fetch_site_same_site_accepted` — same as above with
  `same-site`.
- `test_sec_fetch_site_absent_falls_through_to_origin` — no header;
  matching Origin; assert 200 (verifies legacy/curl/test client path).
- `test_sec_fetch_site_absent_with_mismatched_origin_rejected` — no
  Sec-Fetch-Site, mismatched Origin; assert 403 cross_origin (not
  cross_site — proves the gates don't double-reject).
- `test_sec_fetch_site_unknown_value_falls_through` — header value
  `weird-future-value`; matching Origin; assert 200.
- `test_sec_fetch_site_mixed_case_header_name` — header sent as
  `sec-fetch-site` lowercase; assert behaves identically.
- `test_sec_fetch_site_cross_site_short_circuits_origin_check` — both
  cross-site AND mismatched origin in same request; assert response is
  `cross_site` (not `cross_origin`), demonstrating order.

## Tech debt assessment

- **Added:** None.
- **Repaid:** Closes 05-07 follow-up #1 and re-confirmed deferral in
  05-14-airgap-onetap-toggle REVIEW.md (lines 111-118).
- **Net:** Negative.

## Recommended landing

Land last. Independent of items 1-3. Smallest blast radius if it has
to be reverted post-merge.

---

## Recommended implementation order

1. **Item 1** — `docs/PRIVACY.md` paragraph. Trivial. Single commit.
2. **Item 2** — Token redaction + log permission hardening in
   `src/arail/portal/services/opencode.py`. New `RedactingLogWriter`,
   new pipe-reader thread, both Popen call-sites wired through.
   `tests/test_opencode_log_redaction.py`. Single commit.
3. **Item 3** — Add `start_new_session=True` to both Popen call-sites in
   `opencode.py`. `tests/test_opencode_subprocess_cleanup.py`. Single
   commit. Trivially revertable.
4. **Item 4** — Add Sec-Fetch-Site gate in
   `src/arail/portal/app.py:post_airgap_toggle`. No JS change.
   `tests/test_airgap_sec_fetch_site.py`. Single commit.

Total: 4 commits, 4 file edits, 3 new test files, 1 doc edit. Each
commit is independently revertable.

## Sprint-level test strategy summary

Per `arail/CLAUDE.md` QA allocation (30/30/20/10/10 — setup / Buddy /
security / happy / regression), this sprint is dominated by **security**
tests by construction. QA's pass should:

- **Security (20%):** verify the new tests run green; spot-check that
  Sec-Fetch-Site `cross-site` actually reaches the rejection branch via
  a live curl with `-H "Sec-Fetch-Site: cross-site"`; live-test that
  `lab/logs/opencode.log` does NOT contain a known provider token after
  a real cloud-provider opencode session.
- **Setup (30%):** confirm clean-machine startup is unaffected (no new
  import errors, opencode start still works on first launch).
- **Buddy (30%):** confirm Buddy's logs are untouched (item 2 only
  redacts opencode's log).
- **Happy (10%):** UI flow for airgap toggle still works from the
  portal nav.
- **Regression (10%):** the 29 airgap tests from sprint
  2026-05-14-airgap-onetap-toggle still pass.

## Out-of-scope confirmations

- Token redaction in other log files (lab portal log, agent logs) — NOT
  this sprint. File as ticket if needed.
- Process-group supervisor (systemd-style portal-managed lifecycle) —
  NOT this sprint. `setsid` only.
- Full CSP / CORS audit of the portal — NOT this sprint. Only
  `/api/airgap/toggle` gets Sec-Fetch-Site.
- Backward redaction of historic `opencode.log.1` content — explicit
  tombstone-drop on first post-upgrade start (covered in item 2);
  retroactive content-aware redaction is not attempted.
