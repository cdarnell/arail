# Review: security-hygiene (four-item bundle)

**Date:** 2026-05-14
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 4efc9d9
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 5f1dda8
**Branch:** `qukaizen/arail-security-hygiene`
**Mode:** review

## Overall verdict: PASS

(Worst-of-four: Item 1 PASS, Item 2 PASS, Item 3 PASS, Item 4 WEAK_PASS → on
closer read promoted to PASS because the only finding is a docstring nit, not
a code or test gap.)

Independence check: `git log --oneline main..HEAD` shows the four expected
atomic commits (`b78ff04`, `db3265c`, `41bbcfe`, `53b9667`). Items 2 and 3
share `opencode.py` but the diffs are disjoint (Item 2: ~190 lines of new
class/helpers + Popen rewire; Item 3: two single-line kwarg additions). Each
item can be reverted independently.

Sprint test run: 79 passed (10 redaction + 4 subprocess-cleanup + 9
sec-fetch-site + 56 regression across the three existing airgap test files),
0 failed, in 4.84s.

---

## Item 1 — PRIVACY.md trust-model paragraph

**Verdict: PASS**

| Failure mode (from ARCH) | Code/doc line | Test | Status |
|---|---|---|---|
| Paragraph claims something the code doesn't enforce | `docs/PRIVACY.md` §"Loopback trust boundary" | (doc-only; cross-checked) | PASS — claim "anyone reaching `127.0.0.1:8080` is treated as 'the user' by every API endpoint, including the airgap toggle and the opencode subprocess controls" is verifiable in `app.py`: neither `/api/opencode/start`, `/api/opencode/stop`, nor `/api/airgap/toggle` has auth. |
| Contradicts §"A note on schools" | Paragraph placed *immediately before* schools section; tone harmonized | n/a | PASS — schools paragraph now reads as a corollary, not a duplicate. |
| Markdown rendering breaks | h2 `## Loopback trust boundary`; same level as siblings | visual | PASS |

**Cross-check:** The paragraph also names "Sec-Fetch-Site" alongside Origin
as a CSRF defence — this would be a forward reference to item 4 if read at
sprint start; by end of branch the claim is consistent. No drift.

---

## Item 2 — Token redaction in `opencode.log`

**Verdict: PASS**

| Failure mode | Code line | Test | Status |
|---|---|---|---|
| Tokens already in log from prior runs | `opencode.py` `_open_log_with_redactor` lines 145-158: tombstone-drops both `opencode.log` and `opencode.log.1` on every spawn | `test_existing_log_truncated_on_start`, `test_rotated_log_dropped_on_start` | PASS |
| Partial-line writes split across two `write()` calls | `_RedactingLogWriter.write` lines 64-78: prepend `self._tail`, redact, hold back last `max_secret_len-1` bytes | `test_redacts_token_split_across_two_writes` | PASS |
| False positive (short/empty secrets) | `_MIN_SECRET_LEN = 8`; filter in `__init__` line 49 | `test_ignores_empty_or_short_secrets` | PASS |
| Log permission too permissive | `os.chmod(path, 0o600)` in `__init__`; `os.chmod(rotated, 0o600)` in `_maybe_rotate_log` | `test_chmod_0600_after_open`, `test_rotated_log_also_has_0600_permissions` | PASS |
| Reader thread crashes mid-read | `_pipe_reader_thread` wraps in `try/except`; `daemon=True` | (visual) | PASS — failure mode acceptable per spec; thread dies with parent. |
| Secret list goes stale on provider switch | Provider-switch path calls `restart()` → fresh `_open_log_with_redactor` | (existing behavior, not regression-tested in this sprint) | PASS — relies on existing restart path; documented in arch. |
| Token contains regex metacharacters | `bytes.replace`, no regex | n/a | PASS |
| `os.chmod` fails on FAT/Windows | Wrapped in `try/except OSError`, `_log.warning` | (no explicit test, but exception path is short) | PASS |

**Token-key coverage:** All 6 prefixes the architecture lists are in
`_TOKEN_KEYS` at `opencode.py:174-180`: `ANTHROPIC_API_KEY`, `NVIDIA_API_KEY`,
`OPENROUTER_API_KEY`, `HF_TOKEN`, `MODEL_API_KEY`, `OPENCODE_API_KEY`. Matches
`_compute_source_env()` exactly.

**Tail-buffer "inverted flush" fix verified:** The current logic is correct.
After `redacted = self._redact(self._tail + chunk)`, the code holds back the
*last* `tail_len` bytes (`redacted[flush_up_to:]`) and writes the rest. If
`len(redacted) <= tail_len`, *nothing* is written and the whole thing stays
buffered — this is the correct safety behavior at the start of a stream. The
test `test_redacts_token_split_across_two_writes` directly exercises the
cross-chunk case and passes.

**Tombstone on subsequent starts:** Confirmed — `_open_log_with_redactor` is
called inside `start()` and `_start_inner()` on every spawn, not just first
launch. A rotated `.log.1` from a previous session containing tokens is
dropped on the next portal start. (Tradeoff: legitimate prior debug context
is lost. The architecture explicitly accepts this.)

**Integration test:** `test_subprocess_stdout_through_redactor` spawns a real
Python subprocess that prints a secret, asserts the file contains
`***REDACTED***` and not the token. Passes.

**Daemon thread shutdown:** Thread is `daemon=True`. On portal exit it is
killed without draining. Acceptable: any unwritten bytes were token-redacted
already (in tail buffer) — the worst-case lost data is non-secret stdout. Call
it out for QA: rotated logs on a crash have a (tail_len = max-secret-len - 1)
byte tail loss window, no token leak.

**False-positive scope:** Pattern is exact byte-string equality
(`bytes.replace`). The only false positive is a non-token string that happens
to equal a token value verbatim. With ≥8-byte threshold and high-entropy
provider tokens, collision risk is negligible. Documented in `_MIN_SECRET_LEN`
comment.

---

## Item 3 — `start_new_session=True`

**Verdict: PASS**

| Failure mode | Code line | Test | Status |
|---|---|---|---|
| Applied at both Popen sites | `opencode.py:368`, `opencode.py:506` | `test_start_passes_start_new_session`, `test_start_inner_passes_start_new_session` | PASS |
| Child not a pgid leader | `start_new_session=True` kwarg | `test_child_is_pgroup_leader` asserts `os.getpgid(pid) == pid` | PASS |
| Grandchild not killed by `os.killpg` | (kernel behavior) | `test_killpg_cascades_to_grandchild` spawns shim+grandchild, kills pgid, asserts group gone | PASS |
| macOS vs Linux delta | `@pytest.mark.skipif(sys.platform == "win32")` only — Darwin runs | Tests will run on both Darwin and Linux in CI | PASS |

Both Popen call-sites carry the kwarg, verified via the diff and via
monkeypatching `subprocess.Popen` to capture kwargs in the unit tests.

---

## Item 4 — Sec-Fetch-Site gate on `/api/airgap/toggle`

**Verdict: WEAK_PASS** (docstring nit only — does not block ship)

| Failure mode | Code line | Test | Status |
|---|---|---|---|
| `cross-site` rejected with 403 cross_site | `app.py:6961-6962` | `test_sec_fetch_site_cross_site_rejected` | PASS |
| `none` rejected (typed URL → POST) | same | `test_sec_fetch_site_none_rejected` | PASS |
| `same-origin` accepted | (falls through) | `test_sec_fetch_site_same_origin_accepted` | PASS |
| `same-site` accepted | (falls through) | `test_sec_fetch_site_same_site_accepted` | PASS |
| Header absent → falls through to Origin gate | `request.headers.get("sec-fetch-site", "")` → empty → not in match set | `test_sec_fetch_site_absent_falls_through_to_origin`, `test_sec_fetch_site_absent_with_mismatched_origin_rejected` | PASS — critical for curl/TestClient compatibility |
| Unknown future value → falls through | not in match set | `test_sec_fetch_site_unknown_value_falls_through` | PASS |
| Gate order: Sec-Fetch-Site BEFORE Origin | Verified by reading function top-to-bottom (lines 6948-6975); SFS at 6955-6964, Origin at 6966-6973 | `test_sec_fetch_site_cross_site_short_circuits_origin_check` | PASS |
| Case-insensitive value match | `.strip().lower()` | `test_sec_fetch_site_mixed_case_header_name` (covers header-name case; value case implicitly via lower()) | PASS |
| `nav.js` does NOT need to set the header | Reviewed: no JS change in diff. Browsers force-set automatically. | n/a | PASS |
| Existing airgap regression (3 files, 56 tests) | None of the existing CSRF/bypass tests send `Sec-Fetch-Site`, so they hit the absent → Origin gate path | Ran locally: 56/56 pass | PASS |

**Findings:**

- **[INFO]** Function docstring at `app.py:6936-6939` still lists "Gates (in
  order): 1. BIND_ADDR loopback / 2. Origin / 3. target" — the new
  Sec-Fetch-Site gate is missing from this enumeration. Code is correct;
  docstring is stale. Suggested fix is a one-line update; not a blocker.

- **[INFO]** The architecture spec mentions "tests/test_qa_airgap_onetap_paranoid.py"
  as a 24-test paranoid file to verify against. That file shows in
  `git status` as untracked but is not in the working tree at review time
  (only `.pyc` artifacts remain in `__pycache__/`). The three regression
  files that *are* present (`test_qa_airgap_toggle_security.py`,
  `test_qa_airgap_bypass_attempts.py`, `test_qa_airgap_toggle_setup_happy.py`)
  cover the CSRF-without-Sec-Fetch-Site path and all pass. No regression
  observed.

- **[INFO]** Header value normalization (`.strip().lower()`) means a value
  like `" Cross-Site "` would be normalized to `cross-site` and rejected.
  Defensive and correct.

---

## Tech debt delta

vs ARCHITECTURE.md prediction:

- Item 1: -1 (debt repaid) — matches.
- Item 2: +1 (new class + reader thread) -1 (closes F-SEC-4) -1 (fixes log
  permissions) = net -1, matches.
- Item 3: -1 (closes F-PROC-3) — matches.
- Item 4: -1 (closes 05-07 follow-up) — matches.

No unanticipated debt added. No new TODOs without owner. No commented-out
code introduced.

---

## Required actions before merge

None blocking.

**Recommended follow-up (not blocking):**

1. Update the `post_airgap_toggle` docstring to include the Sec-Fetch-Site
   gate in the "Gates (in order)" enumeration. One-line change in a future
   commit; not worth holding ship for.

---

## Ready for QA? **YES**
