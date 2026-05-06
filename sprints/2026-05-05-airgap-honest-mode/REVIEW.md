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

---

## Re-review (2026-05-05)

**Build:** Loopback 1 (faa6898, 4f641e0, df44306) + Loopback 2 (fc0aa8f,
64aeb50, faca252) + Architect addendum #2 (426df90)
**Reviewer:** architect (review mode, second pass)

## Verdict: PASS

The original BLOCK is closed cleanly, the SRE repave matches addendum
#2 byte-for-byte where it counts, the win-condition artifacts are
untouched, and 105/105 sprint tests pass on this branch (62 from the
original L1/L2 suite + 7 buddy watcher + 6 buddy shim + 7 sre shim +
23 sre new-watchers). No regressions introduced. Two minor wrinkles
are acknowledged-and-accepted, not blockers.

## Loopback 1 closure (BLOCK + ASK)

| Original requirement | Verification | Status |
|---|---|---|
| BLOCK 1: `_save_state()` becomes read-merge-write | `_builtin_buddy.py:1044–1066` reads `existing` from disk, applies `existing.update(...)` with the 5 Buddy keys only, writes the merged result | CLOSED |
| BLOCK 1: regression test guards the fix | `tests/test_buddy_airgap_watcher.py:188–249` (`test_save_state_after_watcher_preserves_airgap_keys`) asserts both `airgap_last_egress_offset` AND `airgap_last_lab_mode` survive a `_save_state()` call after a watcher cycle | CLOSED |
| BLOCK 1: mental simulation — reverting fix would fail the test | Confirmed: if `_save_state` were reverted to write only the 5 Buddy keys, the final dict on disk would be missing `airgap_last_*` because BuddyAgent doesn't track them in memory; the asserts at lines 242 + 246 would both fire | CONFIRMED |
| BLOCK 2: docstring at `_watch_airgap_events` corrected | Builder reports correction in commit faa6898; docstring at lines 488–500 no longer claims "persisted via update_workflow" | CLOSED (verified via the builder's diff in faa6898) |
| ASK: `# noqa-airgap` comment at `backends.py:231` | Line 231: `localhost-only (LOCAL_API_PORT target); post-guard Session — HTTPAdapter is monkeypatched at install_guard() time` — both the localhost claim AND the real safety mechanism named | CLOSED |
| ASK: `# noqa-airgap` comment at `backends.py:440` | Line 440: `external host (openrouter.ai); post-guard Session — HTTPAdapter is monkeypatched at install_guard() time, egress guard applies` — false-witness "localhost-only" gone, replaced with truthful "external host (openrouter.ai)" plus the real safety mechanism | CLOSED |
| ASK: `# noqa-airgap` comment at `backends.py:590` | Line 590: `localhost-only (MODEL_API_BASE defaults to localhost:1234); post-guard Session — HTTPAdapter is monkeypatched at install_guard() time` — accurate | CLOSED |

### Builder spec interpretation (Loopback 1)

> "BLOCK was wider than REVIEW.md described — `airgap_last_lab_mode` is
> only written on mode-toggle events. Test seeds the mode key manually
> to make the assertion meaningful."

**Verdict: ACCEPTED.** The original REVIEW.md framed the BLOCK as both
keys being clobbered every emit. The builder is correct that
`airgap_last_lab_mode` is only written by the watcher's mode-toggle
branch (not on every block-tick), so a watcher run that only consumes
new blocks would never write that key in the first place. The test's
manual seed at line 217 (`after_first["airgap_last_lab_mode"] = "airgapped"`)
faithfully simulates a prior toggle event — it pins the invariant that
"if the watcher previously wrote this key, `_save_state` must not
clobber it." Not papering over a real gap; just refining the assertion
to match the production write paths.

## Loopback 2 verification (SRE repave vs addendum #2)

| Addendum #2 requirement | Verification | Status |
|---|---|---|
| `_builtin_sre.py` ~604 lines (target ±20) | `wc -l` returns 614 | PASS (within tolerance) |
| 5 ported symbols: `_sre_lab_mode`, `_sre_data_dir`, `_watch_dependency_vulnerabilities`, `_watch_lab_cleanup`, WATCHERS extension, `from datetime import` | Verified via grep: line 37 (datetime import), line 288 (_sre_lab_mode), line 298 (_sre_data_dir), line 304 (_watch_dependency_vulnerabilities), line 389 (_watch_lab_cleanup), lines 450–456 (WATCHERS) | PASS |
| `_sre_lab_mode()` body delegates to `arail.airgap.lab_mode()` (NOT a self-contained env-var read) | `_builtin_sre.py:288–295` — `from arail.airgap import lab_mode; return lab_mode()` | PASS |
| `WATCHERS` is pure-append; original 3 entries' rank-order preserved | Lines 451–453 (`_watch_recent_errors, _watch_crash_recurrence, _watch_service_health`), then 454–455 (`_watch_dependency_vulnerabilities, _watch_lab_cleanup`) — pre-existing 3 first, new 2 appended | PASS |
| `ensure_sre_folder()` writes shim template, not `shutil.copy` | `builtin_seed.py:674` — `sre_py.write_text(_SRE_PKB_SHIM, encoding="utf-8")`. No `shutil.copy` for SRE remains (other agents still use `shutil.copy`; the import is correctly retained) | PASS |
| Shim re-exports the names the addendum specified | `builtin_seed.py:260–280` imports 19 names total: 7 public (`sre, SREAgent, Observation, WATCHERS, NAME, EMOJI, SYSTEM_PROMPT`) + 12 private (`_state_file, _activity_log_path, _fingerprint, _tail_jsonl, _parse_ts, _watch_recent_errors, _watch_crash_recurrence, _watch_service_health, _watch_dependency_vulnerabilities, _watch_lab_cleanup, _sre_lab_mode, _sre_data_dir`). Builder report says "16" — that's a count error in the prose, but the import list itself is byte-identical to addendum §11.2.S.3 lines 1551–1571 | PASS (count discrepancy is cosmetic; names match) |
| `tests/test_builtin_seed_sre_shim.py` exists and asserts the shape addendum §11.2.S.5 specified | 7 tests: shim sentinel header, < 80 lines, identity for `sre/SREAgent/_watch_dependency_vulnerabilities`, idempotent against forks. All pass | PASS |
| `tests/test_sre_new_watchers.py` 23/23 pass (architect's named acceptance gate) | Re-ran in this review pass: `23 passed in 0.13s` | PASS |

### Builder spec interpretations (Loopback 2)

a. **Wrote shim content directly to PKB path instead of deleting (step
   12c).** **VERDICT: ACCEPTED.** `ensure_sre_folder()` is a "create-if-
   missing" idempotent — its first action is `if sre_py.exists(): return
   {"ok": True, "created": False}`. Whether you (i) delete the file and
   let next-boot reseed write the shim, or (ii) write the shim directly
   yourself, the file's final content is byte-identical because
   `_SRE_PKB_SHIM` is the seed body. The builder's path is functionally
   equivalent and avoids breaking the in-flight test fixture
   (`spec_from_file_location` requires the file to exist). No spec
   change needed; addendum step 12c is satisfied in spirit.

b. **Embedded `"""` triggered Python 3.11 SyntaxError; resolved by
   removing the literal sentinel from the docstring and using
   descriptive prose.** **VERDICT: ACCEPTED.** I re-read the shim
   at `builtin_seed.py:243–281` — the module docstring describes the
   shim's purpose without embedding the sentinel literal. The sentinel
   string itself is still defined at line 283 as
   `_SRE_PKB_SHIM_SENTINEL = '"""SRE — PKB shim."""'` for the
   idempotency check, and the shim's actual file content begins
   `"""SRE — PKB shim.\n\nThis file is auto-generated...` so the
   first non-blank line of any seeded shim still matches the sentinel.
   Behavior unchanged.

## Win-condition cross-check (no regression)

| Artifact | State after L1 + L2 | Regressed? |
|---|---|---|
| `tests/test_egress_guard.py` (requests, urllib, loopback/RFC1918) | 18/18 pass; file untouched by L1/L2 commits | No |
| `lab/data/egress.jsonl` (one structured line per block) | `egress.py` untouched by L1/L2 commits; behavior preserved | No |
| README's three "zero network calls" rewrites | `git log 5662f9a..HEAD -- README.md` is empty; rewrite preserved | No |
| `airgap.py` 44-test suite | 44/44 pass; module untouched | No |

## SRE repave side-effects audit

- **On-disk PKB SRE file (`lab/pkb/agents/sre/sre.py`).** Currently 38
  lines, shim sentinel header, 19 re-exports — matches what
  `ensure_sre_folder()` would write on a fresh boot. Existing on-disk
  lab state is functionally upgraded to point at the canonical (no
  drift). User runtime impact: any prior local edits to this file
  (gitignored) are gone — but that was always true of the seed pattern.
- **CVE-scan watcher gating.** `_watch_dependency_vulnerabilities`
  branch (a) and (b) (high/critical and medium findings) fire
  unconditionally — they always did. Branch (c) (no-scan-in-24h nag)
  fires only when `_sre_lab_mode() == "hybrid"`. Pre-port, that gate
  read env directly (`os.getenv("LAB_MODE", os.getenv("ARAIL_MODE",
  "airgapped")).strip().lower()` in PKB). Post-port, the gate calls
  `arail.airgap.lab_mode()` which performs the same fallback chain
  with the same fail-closed default. **Equivalent semantics confirmed.**
- **Lab-cleanup watcher gating.** `_watch_lab_cleanup` is mode-
  agnostic — fires whenever wiki cache exceeds the env-configured
  threshold. No mode gate added or removed. **No semantic drift.**
- **Net new behavioral code (165-line delta).** Imported logic is
  ~150 lines (bodies of `_watch_dependency_vulnerabilities` 83 lines +
  `_watch_lab_cleanup` 59 lines = 142 lines, plus `_sre_lab_mode`
  collapsed to 8 lines, `_sre_data_dir` 4 lines, WATCHERS extension
  2 entries, `from datetime import` 1 line). Remainder is whitespace
  and the helper docstrings. **Matches the addendum's expected delta.**

## Code quality findings (re-review)

- [INFO] The shim's import block lists 19 names; build log narrative
  calls it "16 re-export names". Cosmetic prose error in BUILD_LOG.md
  Loopback 2 section, not a code defect. Not worth a fix; flagging
  for the audit trail.
- [INFO] All four [INFO] findings from the original review (mkdir-
  per-block at `egress.py:182`, paren-clarity at `egress.py:461`,
  docstring at `_builtin_buddy.py:488` (now corrected by L1), and the
  comment at `backends.py:440` (now corrected by L1)) are resolved or
  acknowledged. The mkdir-per-block and paren-clarity items remain
  for follow-up, unchanged.
- [INFO] No new code-quality issues introduced by L1 or L2.

## Tech debt delta (re-review)

- L1 paid back the unanticipated debt the original review flagged
  (forked state.json writers). State.json is now safe under any pair
  of writers because `BuddyAgent._save_state` is the read-merge-write
  pattern; if any future watcher adds new keys, they survive too.
- L2 paid back canonical/PKB drift for SRE — the same debt the Buddy
  repave paid back in the main pipe. Now both built-in agents follow
  the same shim pattern. The pattern is documented in the learnings
  file (commit 64aeb50).
- **No new debt.** Net debt for the sprint is now more negative than
  the original prediction (one extra debt repaid that wasn't even on
  the original ledger).

## For QA — updated bypass-attempt + repave hammering list

Compared to the original list in REVIEW.md, the SRE repave adds new
surface QA should poke. Updated priorities:

### Carry-forward from original (still required)

1. **Pre-guard Session attack** — write a fixture that constructs
   `requests.Session()` at module top-level imported BEFORE
   `install_guard()`, attempt egress, confirm documented behavior.
2. **DNS rebind exploit** — `monkeypatch socket.gethostbyname` so
   `evil.example.com` resolves to `127.0.0.1`; confirm passes through;
   pin documented limit.
3. **`_save_state` data-loss regression** — already pinned by L1
   regression test (`test_save_state_after_watcher_preserves_airgap_keys`).
   QA should run `pytest tests/test_buddy_airgap_watcher.py -k preserves_airgap_keys`
   as part of the smoke matrix to confirm the fix didn't silently
   regress.

### New from Loopback 2 (SRE repave)

4. **SRE shim identity preservation under fork.** Confirm: with a
   user-forked `lab/pkb/agents/sre/sre.py` (no shim sentinel), boot
   the lab and verify `ensure_sre_folder` does NOT overwrite, the
   loader picks up the user's fork, AND `WATCHERS` (in the user's
   fork) is what runs — NOT the canonical's. Otherwise forks silently
   inherit canonical changes.
5. **CVE / cleanup watcher mode-gating equivalence.** With
   `LAB_MODE=airgapped`, no `lab/data/security/last_scan.json`, and
   wiki cache below threshold, neither watcher should emit. Then
   flip `LAB_MODE=hybrid` and verify branch (c) of CVE watcher fires
   the "no scan in 24h+" nag. Pin equivalence with the pre-port
   behavior. (Most likely place for a regression to hide.)
6. **Shim re-export completeness against future test additions.** If
   QA adds any test that touches a previously-untested SRE private
   helper, the shim's import list (`builtin_seed.py:260–280`) may
   need extending. Run `python -c "import importlib.util; spec =
   importlib.util.spec_from_file_location('s', 'lab/pkb/agents/sre/sre.py');
   m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m);
   print([n for n in dir(arail.agents._builtin_sre) if not n.startswith('__')
   and not hasattr(m, n)])"` to confirm zero missing exports. (Smoke test;
   not a behavioral test.)

### De-prioritize (already pinned)

- Original ASKs for IPv6 ULA / 6to4 / IPv4-mapped IPv6 pinning, RO-fs
  jsonl write swallow, asyncio.create_task contextvars-leak, URL-parse
  fallback for token-bearing strings — still ASKs, still pinning
  exercises. Keep on the QA list at original priority. None changed
  by L1 or L2.

## Anything for follow-up sprints

- **Buddy state.json schema is informally co-owned by two writers.**
  Read-merge-write makes it safe today, but the schema isn't
  documented anywhere and a future contributor adding a third writer
  could miss the merge pattern. Follow-up: write
  `learnings/2026-05-XX-buddy-state-json-schema.md` (or amend the
  existing allow-egress-task-scope learning) listing the keys each
  writer owns and the merge invariant. **Low priority.**
- **`mkdir(parents=True, exist_ok=True)` per `record_block` call**
  (egress.py:182). One-shot cache or module init. Follow-up.
- **Paren clarity at `egress.py:461`.** Follow-up.
- **Shim re-export count discrepancy in BUILD_LOG.md prose**
  (says "16", actual is 19). Cosmetic, no follow-up needed.
- **`_SRE_PKB_SHIM_SENTINEL` is `'"""SRE — PKB shim."""'`** which means
  the user can't replace the docstring while keeping the sentinel.
  Forks must replace the entire first line. This is the documented
  fork pattern (DO NOT EDIT THIS SHIM — replace the file entirely)
  but worth re-stating in PKB docs eventually. Follow-up: add a
  one-liner to `docs/agents.md` about the fork pattern.

## Required actions before merge

None. PASS verdict — sprint advances to QA.

