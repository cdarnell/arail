# TEST_REPORT — security-hygiene

**Sprint:** 2026-05-14-security-hygiene
**Date:** 2026-05-14
**QA agent verdict:** **PASS**
**Architect review:** PASS (one docstring nit, now fixed)
**Suite result:** 234 passed, 0 failed (4.44s, 16 files)

## Tests added

`tests/test_qa_security_hygiene_paranoid.py` — 27 paranoid tests, all passing.

### Per-item paranoid coverage

**Item 1 — PRIVACY.md trust claim (4 tests)**

Live-verified the "Loopback trust boundary" claim against three unauth
endpoints: `/api/airgap/toggle`, `/api/opencode/start`,
`/api/providers/save`. None reject on auth. Doc claim is truthful.

**Item 2 — Token redaction (9 tests)**

- Three-chunk split (architect only tested two) — tail buffer holds correctly.
- High-bit / non-ASCII / NUL / 0xFF bytes — `bytes.replace` is byte-clean.
- Multiple distinct tokens in one chunk — all redacted.
- Token without trailing newline — `flush_tail()` catches it on EOF.
- Token repeated 3× in one chunk — all three occurrences redacted.
- `.log.1` tombstone-drop verified end-to-end.
- `chmod 0600` verified end-to-end after real subprocess.
- Broken-file-handle write exception handled gracefully (no crash).
- **Regression guard:** `test_token_keys_match_compute_source_env_exactly` —
  asserts every env var name in `_PROVIDER_TOKEN_ENV` appears in
  `_open_log_with_redactor` source. Future provider additions can't
  silently leak.

**Item 3 — `start_new_session=True` (2 tests)**

- Pytest pgid ≠ child pgid (proves session isolation; without this,
  a `killpg` would kill the test runner itself).
- Child is reaped after `wait()` — no zombies.

**Item 4 — Sec-Fetch-Site (8 tests)**

- Whitespace-wrapped value normalized.
- Uppercase value normalized.
- `SAME-ORIGIN` uppercase accepted.
- Empty string falls through.
- Unknown future value + matching Origin → 200 (forward-compat).
- Unknown SFS + mismatched Origin → `cross_origin` (Origin gate still runs).
- `Sec-Fetch-Mode` / `Sec-Fetch-Dest` present but ignored (we key only on Site).
- `GET /api/airgap/toggle` → 405, not 403 cross_site (gate scoped to POST).

## Findings the architect missed

None severe. Informational:

1. **[INFO]** `tests/test_qa_airgap_onetap_paranoid.py` from the prior
   sprint is absent on this branch (it landed on a separate follow-up
   branch as PR #49, not yet merged into main). The 207 pre-existing
   airgap tests still cover the same surface; no regression.
2. **[INFO]** `_TOKEN_KEYS` in `_open_log_with_redactor` duplicates
   `_PROVIDER_TOKEN_ENV` by intent. New regression test makes the
   duplication safe; long-term import is cleaner but non-blocking.
3. **[INFO]** SIGKILL'd portal leaves up to `tail_len` (max-secret-len − 1)
   bytes unflushed. Per architect spec, those bytes are already
   token-redacted (held in `_tail` post-redact), so no leak.
4. **[LOW, fixed in-sprint]** Docstring nit on `post_airgap_toggle`
   (gates 1/2/3 listed without SFS) — fixed in
   `src/arail/portal/app.py` before shipping.

## Security review surface

| Surface | Checked | Result |
|---|---|---|
| User input (SFS header) | Whitespace, case, unknown values, combos with Mode/Dest, GET probe | Clean |
| File I/O | Log dir creation, `0o600`, tombstone-drop of `.log` + `.log.1` | Clean |
| Subprocess | `start_new_session=True` both call-sites; pgid isolation; no zombies | Clean |
| Token handling | byte-clean redaction, high-bit, NUL, multi-chunk, multi-occurrence | Clean; new regression guards future provider adds |

## Tech debt surfaced

- `_TOKEN_KEYS` duplication of `_PROVIDER_TOKEN_ENV` — guarded by
  regression test; refactor optional.

## Verdict

**PASS** — ready to ship.
