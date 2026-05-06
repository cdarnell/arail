# Review: airgap-honest-mode

**Date:** 2026-05-05
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at dc8f430
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at af5c1c1
**Branch:** `qukaizen/arail-airgap-honest-mode`
**Reviewer:** architect (review mode)

## Verdict: BLOCK

One BLOCK finding (Buddy state-file data loss in the watcher integration
with `BuddyAgent._save_state`) and one comment-quality finding that
materially misrepresents an audit assumption. Tests pass and the bulk
of the spec is honored — the BLOCK is narrow and fixable in ~10–20
lines without re-architecture.

## Summary

What's solid: `airgap.py` is a clean single-source-of-truth (44 unit
tests cover RFC1918, IPv4 + IPv6, DNS rebind pin, fail-closed
defaults). `egress.py` correctly patches both
`requests.adapters.HTTPAdapter` AND `requests.sessions.HTTPAdapter`,
correctly resets both on test teardown, uses `contextvars.ContextVar`
for `_allow_egress_var`, raises `EgressBlocked` *before* setting the
contextvar in airgapped mode (the `body_executed is False` test
passes), is idempotent, and writes one structured jsonl line per
block. The 5MB rotation logic is in place. README + PRIVACY.md are
verbatim, the modal is included on all 12 nav-bearing templates with
all four known gaps named, and the `/api/airgap/status` route shape
matches §8. The Buddy shim repave is correct: PKB `buddy.py` is now a
≤30-line re-export of `_builtin_buddy.py`, identity-preserved
(`shim_module.buddy is canonical.buddy`), idempotent against forks.

What blocks ship: the airgap watcher's per-tick state persistence
loses its state every time it emits, because `BuddyAgent._save_state()`
runs immediately after the watcher's emit and writes only its own five
keys back to the same `state.json`. Net effect: cross-emit, the
`airgap_last_egress_offset` and `airgap_last_lab_mode` keys vanish
from disk. Within-session the cooldown masks user-visible spam, but
the watcher re-walks the entire jsonl from offset 0 every tick and
never persists state across emits or restarts. The watcher's unit
tests don't exercise this path because they call `_watch_airgap_events`
in isolation without involving `_save_state`.

## Spec adherence

Strong overall. Implementation order in §11.1.B.7 was followed (repave
before watcher), all 28 file-rows in §12 are addressed, and the seven
hard invariants in §15 hold (verified by code inspection + 74-test
suite). Two deviations:

- The watcher's state-persistence handoff to `BuddyAgent` is broken
  (see BLOCK below). Architecture §10 expected
  `state.airgap_last_egress_offset` to advance and persist; in
  practice it's wiped after each emit by the unrelated
  `_save_state` writer.
- `# noqa-airgap: localhost-only` comment at `backends.py:440`
  contradicts itself: the line says "localhost-only (OpenRouter via
  allow_egress)" — but OpenRouter is `openrouter.ai`, not localhost.
  Functionally fine because the Session is constructed in `__init__`
  (post-`install_guard`), so the monkeypatched class catches it. But
  the audit comment is false-witness and contradicts §13's stated
  assumption that all three sites are localhost-only in practice.

## Builder-flagged item walk

1. **Double-patch in `install_guard()` / `_reset_for_tests()`** —
   CLOSED. Both `requests.adapters.HTTPAdapter` and
   `requests.sessions.HTTPAdapter` are set in `install_guard` (lines
   353–354) and restored in `_reset_for_tests` (lines 379–380).
   Builder's spec-delta call was correct; the architecture §4 was
   incomplete here.
2. **`allow_egress` ordering invariant** — CLOSED. `is_airgapped()`
   check at egress.py line 424 runs *before*
   `_allow_egress_var.set(token)` at line 433.
   `test_allow_egress_in_airgapped_raises_immediately` asserts
   `body_executed is False` — verified.
3. **Buddy watcher file-write race** — **NOT acceptable as v1, but
   the BLOCK is more severe than the builder framed it.** The issue
   is not async race; it is a deterministic data-stomping bug between
   `_watch_airgap_events`'s state write (lines 502–577) and
   `BuddyAgent._save_state` (lines 1042–1054). They both write the
   whole `state.json` from disjoint in-memory views. `_save_state`
   is called immediately after the watcher emits, in
   `_emit_observation` (line 1212). It writes ONLY
   `last_said / last_global / last_suggest_check / utterances /
   suggestions`, dropping `airgap_last_egress_offset` and
   `airgap_last_lab_mode` from disk. **BLOCK.**
4. **Possibly orphaned `shutil` import in `builtin_seed.py`** —
   CLOSED. `shutil` is still referenced at lines 619, 703, 779
   (sre.py, drafter.py, presence.py copies). Import is not orphaned;
   leave alone.

## Builder spec-interpretation walk

a. **`requests.sessions.HTTPAdapter` patched alongside
   `requests.adapters.HTTPAdapter`** — APPROVED. Without this,
   `requests.Session().__init__` would mount the un-monkeypatched
   class via its local `from requests.adapters import HTTPAdapter`.
   The dual-patch is correct and is the only way the
   `test_session_post_install_uses_guarded_adapter` test can pass.
   Update §4 in a future edit; for now the diff is correct.

b. **IPv6 fixture changed `2001:db8::1` →
   `2606:4700:4700::1111`** — APPROVED. Python 3.11+'s `ipaddress`
   module classifies `2001:db8::/32` (RFC 3849 documentation prefix)
   as private. Cloudflare's public DNS literal genuinely tests the
   public-IPv6 path. **Gap noted:** the test suite covers loopback
   (`::1`), link-local (`fe80::1`, `fe80::1%en0` zone-stripped), and
   one public-IPv6 example. It does NOT explicitly test ULA
   (`fc00::/7`), 6to4 (`2002::/16`), or IPv4-mapped IPv6
   (`::ffff:8.8.8.8`). `is_local_ip` uses
   `ipaddress.ip_address(...).is_private` which DOES classify
   `fc00::/7` as private (good — those should pass), but
   IPv4-mapped IPv6 may not behave the way users expect. ASK for QA
   to add three pinning tests.

## Failure-modes checklist walk

- **Silent bypass via fresh `requests.Session()`** — CLOSED. The
  monkeypatch on the HTTPAdapter class itself means any Session
  constructed post-`install_guard` mounts a `GuardedHTTPAdapter`. The
  three `backends.py` Sessions are inside `__init__` methods, so they
  fire post-startup and are caught. Validated by
  `test_session_post_install_uses_guarded_adapter`.

- **Thread-leak / async-leak of `@allow_egress`** — CLOSED.
  `_allow_egress_var: ContextVar[Optional[str]]` (egress.py line 60).
  Documented as a known limit in `learnings/2026-05-05-allow-egress-task-scope.md`.
  Pinned indirectly by tests but no `asyncio.create_task` regression
  test exists yet — ASK for QA.

- **jsonl write failures** — CLOSED-with-INFO. `_write_jsonl_line`
  catches `Exception` broadly (line 205) and writes to stderr; the
  `EgressBlocked` raise path is unaffected (the calling
  `_check_egress_or_raise` raises on its own). However, NO test
  exercises this path (no RO-fs, disk-full, or PermissionError test).
  Architecture §13 listed it as a failure mode. ASK for QA to add
  one.

- **`EgressBlocked` swallowed by over-broad `except Exception`** —
  CLOSED-with-INFO. `_suggest_internet_correlation` in
  `_builtin_buddy.py` line 923 wraps the urlopen call in
  `except Exception: return None`. This is gated by
  `is_airgapped()` returning early on line 868, so in airgapped the
  call is never made. In hybrid mode the `except` swallow is
  irrelevant since the guard passes through. The block is still
  recorded to `egress.jsonl` per architecture's stated audit-log-as-
  source-of-truth invariant. Acceptable for v1.

- **DNS rebinding** — CLOSED. `is_local_host` at airgap.py line 110
  resolves the hostname via `socket.gethostbyname` and re-checks the
  resolved IP. `test_dns_rebind_trust` pins the documented behavior
  (`evil.example.com → 127.0.0.1` is treated as local; documented
  limit). Matches §13 invariant.

- **IPv6 link-local edge case** — CLOSED. `is_local_ip` strips zone
  identifiers (airgap.py lines 73–75) and `test_zone_id_stripped`
  pins it. ULA / IPv4-mapped IPv6 not pinned; see (b).

- **Idempotency of `install_guard()`** — CLOSED. `_INSTALLED` flag at
  egress.py line 65; second-call early-return at line 344. Reset by
  `_reset_for_tests` (line 381). Pinned by
  `test_install_guard_is_idempotent`.

- **The three pre-guard `requests.Session()` sites** — CLOSED-with-
  ASK. All three are inside `__init__` methods, not module-level —
  so they fire post-`install_guard` and are guarded via the
  monkeypatched HTTPAdapter class. Architecture §13's worry was a
  phantom (acceptable result; implementation is safer than the spec
  feared). HOWEVER the comment at `backends.py:440` says
  "localhost-only (OpenRouter via allow_egress)" — OpenRouter is
  NOT localhost. The comment misrepresents the audit. Fix: update
  the comment to reflect "post-guard, monkeypatched HTTPAdapter
  applies". ASK (not BLOCK because the actual behavior is correct).

- **README + PRIVACY.md verbatim** — CLOSED. Diffs against §11
  match exactly. Three README spots and the PRIVACY.md "What
  airgapped mode enforces" through "What hybrid mode sends" section
  are byte-identical with the spec.

- **The known-gap claims** — CLOSED. README (line 155), PRIVACY.md
  (lines 46–54), modal (lines 71–73), and `/api/airgap/status`
  `known_gaps` array (app.py lines 6453–6458) all list four:
  `httpx`, `aiohttp`, raw socket, subprocess curl. Consistent.

- **Buddy double-implementation gone** — CLOSED. `_builtin_buddy.py`
  is canonical; `lab/pkb/agents/buddy/buddy.py` (gitignored) is the
  shim. `test_shim_imports_are_identity_preserving` proves the
  singleton is identity-shared. No leftover full-body code paths.
  References in `lab/pkb/compiled/docs/...` are doc-body content,
  not import paths.

- **Buddy watcher fires on real signals** — **BLOCK.** See "Spec
  adherence" + builder-flagged item 3. The watcher reads/writes
  state.json correctly in isolation (its tests pass), but
  `BuddyAgent._save_state` clobbers the airgap-keys after every
  emit. Within-session this means the watcher re-reads the entire
  jsonl from offset 0 every tick (wasted I/O, scales with file
  size); across restarts the offset is permanently lost. The
  cooldown_sec=300 hides the user-visible symptom (no double-
  emit), but the persistence guarantee in §10 ("Advance
  state.last_egress_offset; call again → returns None") is broken
  in production code paths. **Required fix below.**

- **Activity stream entries on toggle** — INFO. Buddy emits
  `Observation(severity="info", fact="Door's open now …" / "Sealed
  back up…")` via the watcher, which goes through
  `_emit_observation → self._host.emit("buddy", ...)` →
  `activity_log.emit("buddy", ...)`. The architecture's spec text
  ("agents can now reach the internet" / "all network access
  disabled") is paraphrased to "Door's open now — agent fetches
  go through" / "Sealed back up. Agents can't reach the public
  internet." Different copy than VISION.md hinted, but this is
  Buddy's voice and matches the table in §10. Acceptable.

## Code quality findings

- [INFO] `egress.py:182` — `lab_data.mkdir(parents=True,
  exist_ok=True)` runs on every block. With a steady polling agent
  hitting `EgressBlocked` every 5 s, that's ~17k mkdir calls/day.
  No-op cost is small but a one-shot cache (or move to module
  init) is cheaper. Follow-up.
- [INFO] `egress.py:461` — `os.getenv("BUDDY_EGRESS_PROBE", "").strip()
  in ("1", "true", "yes")` — readable but `not X.strip() in (...)`
  parses as `not (X.strip() in (...))` which is correct here, just
  fragile. Suggest parens for clarity in a follow-up.
- [INFO] `_builtin_buddy.py:488` — docstring comment "State is
  persisted via the host's update_workflow." is misleading; the
  watcher in fact persists via direct `state_path.write_text` at
  line 575. Fix as part of the BLOCK fix.
- [ASK] `backends.py:440` — `# noqa-airgap: localhost-only
  (OpenRouter via allow_egress)` is factually wrong. OpenRouter is
  not localhost. Suggested replacement:
  `# noqa-airgap: post-guard Session (HTTPAdapter monkeypatched at
  install_guard time)`.

## Security findings

- [INFO] `EgressBlocked.__str__` includes only `host`, `caller`,
  `reason` — never the full URL. Confirmed via `_check_egress_or_raise`
  and `GuardedHTTPAdapter.send` raise sites. No query-string leak.
- [INFO] `record_block` at egress.py line 137 uses `parsed.hostname
  or url[:64]` — if URL parse fails, the *first 64 characters of
  the raw URL* are written to the audit log. If a caller passes a
  URL containing a token (e.g. `https://api.example.com/?token=xxx`)
  and the parse failed somehow (it shouldn't, urlparse is permissive)
  this would leak. In practice `urlparse` always returns a hostname
  for plausible-looking URLs, so the fallback is dead code. ASK for
  QA: try a malformed URL to verify the fallback never fires with
  a token-bearing string.
- [INFO] `record_allow` writes `reason: "allow:<reason>"`. The
  reason field is user-supplied (from the `@allow_egress("...")`
  caller). 200-char limit enforced. No format-string risk.
- [PASS] `BUDDY_EGRESS_PROBE` is the only documented bypass; uses
  raw socket; one TCP-connect to 1.1.1.1:443; cached 60s; logged
  with `reason="probe"`. Architecture §7 invariant honored.

## Test coverage assessment

74 sprint tests pass. Coverage on the new modules:
- `airgap.py`: ~96% (only `is_local_host` resolution-failure
  branch missing a counter-test; `test_resolution_failure_is_not_local`
  covers it).
- `egress.py`: ~85% (gaps: rotation under 5MB, RO-fs writes,
  PermissionError on chmod, `probe_internet` cache-hit path).

Failure-modes table (§13) row-to-test cross-walk:
- 9/12 rows have a corresponding test.
- Missing: row 3 (disk full / RO fs), row 4 (concurrent writers
  interleaving), row 13 (offset > size after rotation; *this is*
  tested in the watcher suite as `test_offset_reset_on_rotation`,
  closed).

## Performance assessment

Not benchmarked formally. Per-request overhead inspection:
- One `urlparse` (~5 µs).
- One `is_local_ip` IP-check (~2 µs).
- For non-IP hosts: one `socket.gethostbyname` with 1.5s timeout.
  Cached by the OS resolver but not by us. With local resolver this
  is sub-ms; with a slow resolver it could stall. Architecture §13
  acknowledged this; QA should spot-check.
- The chmod-on-every-write at `record_block` is fine on macOS/Linux
  but adds noise on filesystem watchers.

Acceptance threshold (<5 ms added per request) is plausibly met but
unverified.

## Tech debt delta

vs. ARCHITECTURE.md prediction:

- Predicted +debt: third place that cares about modes (gone — only
  airgap.py); inline modal CSS (kept; follow-up); contextvars/asyncio
  subtlety (filed in learnings).
- Predicted -debt: 5 dup helpers → 1 (done); `LAB_INTERNET_ENABLED`
  removed (done); Buddy de-dup (done); README lying paragraphs (done).
- **Unanticipated +debt:** the Buddy state.json schema is now
  forked between two writers that don't know about each other.
  This needs to be unified (see required fix below).

Net: still negative debt as predicted, but the Buddy-state
fragmentation is a new debt the spec did not anticipate.

## Required actions before merge

### 1. BLOCK — Unify state.json writers in `_builtin_buddy.py`

**Problem.** `_watch_airgap_events()` (lines 502–577) writes a
merged state.json. `BuddyAgent._save_state()` (lines 1042–1054)
writes only its own five keys, dropping
`airgap_last_egress_offset` and `airgap_last_lab_mode`. Sequence:
watcher writes → emit → `_save_state` overwrites → airgap keys
gone.

**Required fix (pick one; ~10–20 lines):**

Option A (preferred, simpler) — make `_save_state` a merging writer:

```python
def _save_state(self) -> None:
    path = _state_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Merge with whatever else is on disk (e.g. airgap watcher keys)
        # so concurrent writers don't stomp each other.
        existing: Dict[str, Any] = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text()) or {}
            except Exception:
                existing = {}
        existing.update({
            "last_said": self._last_said,
            "last_global": self._last_global,
            "last_suggest_check": self._last_suggest_check,
            "utterances": self._utterances,
            "suggestions": self._suggestions,
        })
        path.write_text(json.dumps(existing, indent=2))
    except OSError:
        pass
```

And mirror this read-merge-write in `_watch_airgap_events()` (it
already does this read-merge-write but the docstring at line 488
should be corrected — it does NOT persist via `update_workflow`,
it writes directly).

Option B — load airgap keys into `BuddyAgent` on `_load_state` and
write them in `_save_state`:

```python
# In _load_state:
self._airgap_state = {
    "airgap_last_egress_offset": int(data.get("airgap_last_egress_offset", 0)),
    "airgap_last_lab_mode": str(data.get("airgap_last_lab_mode", "airgapped")),
}
# Then have the watcher mutate self._airgap_state instead of writing directly,
# and let _save_state include those keys in its dump.
```

**Add a regression test** in
`tests/test_buddy_airgap_watcher.py`:

```python
def test_save_state_after_watcher_preserves_airgap_keys(monkeypatch, tmp_path):
    """Critical: BuddyAgent._save_state must NOT clobber the airgap
    keys the watcher just persisted.

    Sequence: watcher writes airgap_last_egress_offset → BuddyAgent
    saves last_said etc. → both must remain on disk."""
    # 1. Run watcher → state.json has airgap_last_egress_offset
    # 2. Construct BuddyAgent, call _save_state()
    # 3. Read state.json; assert BOTH key families present
```

**File and lines to change:**
- `src/arail/agents/_builtin_buddy.py:1042–1054` (the `_save_state`
  fix, Option A) — about 10 lines added.
- `src/arail/agents/_builtin_buddy.py:488` — fix the misleading
  docstring comment.
- `tests/test_buddy_airgap_watcher.py` — add 1 regression test.

### 2. ASK — Comment fix at `backends.py:440`

**Problem.** The `# noqa-airgap: localhost-only (OpenRouter via
allow_egress)` comment is factually false: OpenRouter is not
localhost. The Session is safe because it's constructed in
`__init__` (post-`install_guard`), not because of `allow_egress`.

**Required fix:**

```python
self._session = requests.Session()  # noqa-airgap: post-guard Session — HTTPAdapter is monkeypatched at install_guard() time, so this Session inherits the guarded adapter
```

Apply consistent comment style to lines 231 and 590 — they're
both also post-guard, not "localhost-only" in the strict
architectural sense (they happen to target localhost defaults,
but the safety comes from the monkeypatch).

**File and lines to change:** `src/arail/router/backends.py:231,
440, 590` — three one-line edits.

### 3. ASK — Hand to QA for follow-up coverage

These are NOT blockers but should be noted in QA's TEST_REPORT:

- IPv6 ULA, 6to4, IPv4-mapped IPv6 not explicitly tested in
  `is_local_ip`; QA add 3 pinning tests.
- `record_block` disk-full / RO-fs / PermissionError swallow path
  not tested. QA add one.
- `asyncio.create_task` contextvars-leak documented in learnings
  but not regression-tested. QA write one task-spawning test.
- `record_block` URL-parse-failure fallback (line 137) — verify
  it doesn't leak token-bearing query strings.

## For QA — bypass-attempt suite seeds

These are the highest-leverage attacks for QA's bypass-attempt
suite (security 20% allocation per arail's CLAUDE.md):

1. **Pre-guard Session attack.** Construct a `requests.Session()`
   in a module imported BEFORE `install_guard()` runs. Demonstrate
   it bypasses (the architecture §13 said this is documented but
   localhost-only in tree). QA: write a fixture module that does
   `import requests; _SESSION = requests.Session()` at module top,
   then attempt `_SESSION.get("https://example.com")` — should
   succeed (or hit a real connection error), NOT raise
   `EgressBlocked`. Pin documented behavior.

2. **DNS rebind exploit.** Set up a fake hostname (via
   `monkeypatch.setattr(socket, 'gethostbyname', ...)`) that
   resolves to `127.0.0.1`. Confirm `requests.get("https://evil.example.com")`
   passes through. Pin the documented limit.

3. **`_save_state` data-loss verification.** After the BLOCK fix
   lands, write a test that boots `BuddyAgent`, runs the watcher
   to populate airgap-state, triggers an emit (which calls
   `_save_state`), then re-reads `state.json` and asserts BOTH
   key families survive. This is the regression guard for the
   block this review caught.

Other paths (httpx, aiohttp, raw socket, subprocess curl) are
already pinned as documented gaps in tests and the modal — QA's
bypass-attempt suite should run them as confirmation rather than
exploration.
