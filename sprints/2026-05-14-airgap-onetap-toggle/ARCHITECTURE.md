# Architecture: airgap-onetap-toggle

**Date:** 2026-05-14
**Sprint:** 2026-05-14-airgap-onetap-toggle
**Spec:** [SPRINT.md](./SPRINT.md)
**Prior art:**
- [../2026-05-07-airgap-runtime-toggle/ARCHITECTURE.md](../2026-05-07-airgap-runtime-toggle/ARCHITECTURE.md) — the 2-step toggle being simplified
- [../2026-05-07-airgap-runtime-toggle/REVIEW.md](../2026-05-07-airgap-runtime-toggle/REVIEW.md) — WEAK_PASS, three follow-ups
- [../2026-05-05-airgap-honest-mode/REVIEW.md](../2026-05-05-airgap-honest-mode/REVIEW.md) — egress guard + audit log baseline

## Restatement

The 05-07 sprint shipped a working `LAB_MODE` toggle but wrapped it in
ceremony that the threat model doesn't justify: a confirm-token protocol,
a 3-second forced countdown, a modal close-and-reopen dance after success.
The result feels broken — users describe it as "the lab locking up" — and
the modal CSS sequencing makes the pill flash stale state. This sprint
collapses the toggle to one click: a segmented control or switch that
flips visually on mousedown, POSTs in the background, and reverts on
error. Behind the click, we drop the confirm-token entirely (the CSRF
Origin check + loopback-bind gate cover the threat the token was meant
to address), keep the `.env` atomic write, keep the audit-log append,
keep the loopback-bind gate, keep the CSRF Origin check, and bust the
one in-process cache that observes `lab_mode` indirectly
(`egress._PROBE_CACHE`). Subprocess workers that read `LAB_MODE` at
startup remain stale until restart — that's out of scope and surfaced
in the modal copy.

## Threat-model delta — why dropping the confirm token is safe

The confirm token in the 05-07 design defended against exactly one
scenario: **an unintended same-origin POST from a browser tab that
already has access to the lab portal** — for instance, a sloppy click
inside the modal itself, or an agent-rendered HTML fragment that
contains a `<form action="/api/airgap/toggle">` and a user click. The
two gates we keep already handle the other vectors:

| Vector | Defense (kept) | Confirm-token contribution |
|---|---|---|
| LAN peer on Wi-Fi POSTs `/api/airgap/toggle` | loopback-bind gate refuses unless `BIND_ADDR ∈ {127.0.0.1, ::1, localhost}` | None — bind gate already 403s before token logic runs |
| Cross-origin browser tab CSRF (`evil.com` → user's localhost portal) | `Origin == Host` check (`post_airgap_toggle` lines 7013–7017) | None — CSRF gate already 403s |
| Token brute force | 192-bit `secrets.token_urlsafe` | Infeasible regardless; the gate that matters is CSRF + bind |
| Same-origin unintended click | — | 3s countdown was the only friction |

The "same-origin unintended click" risk reduces to: **does ARAIL render
attacker-controlled HTML inside the portal that could host a
form-submission or fetch?** Review of the codebase says no — agent
output is rendered as text in the Buddy/SRE/Researcher activity stream
(no raw HTML interpretation; the activity feed is escaped). Knowledge
Base previews render markdown via a sanitizer. Nothing in the portal
turns untrusted text into clickable form submissions to
`/api/airgap/toggle`. The 3s countdown was therefore guarding a phantom.

Residual risk after token removal: a user can mis-click the toggle and
not notice. Mitigations baked into the one-tap UX:
1. The control's after-state is obvious and persistent (the pill flips,
   the segmented control's active half flips).
2. The audit log records every flip with timestamp + source_ip; the user
   can review in the modal.
3. The inverse toggle is one click away — there's no costly recovery
   path. (Compare: the 05-07 design treated the toggle as one-shot
   irreversible; it never was.)

Net: dropping the token removes ceremony that was guarding a phantom and
keeps every defense that addresses a real threat.

## Assumptions

- `LAB_MODE` is read per-call via `os.getenv` in the canonical path
  (`arail.airgap.lab_mode`, `arail.airgap.is_airgapped`) — verified at
  `src/arail/airgap.py:48–63`. **There is no `functools.lru_cache` or
  module-level memoization of mode anywhere in `arail.airgap` or
  `arail.egress`.** The phrase "bust cached `lab_mode()` lookups" in
  SPRINT.md scope item 3 is therefore a smaller job than it sounds:
  the only in-process state that is *observably stale* after a flip is
  `egress._PROBE_CACHE` (host-internet probe), and that staleness is
  cosmetic (the modal's "host can reach internet" row, which is
  orthogonal to mode but renders alongside it). We bust it anyway to
  keep the modal honest.
- `app.py:929–934` defines a duplicate `_lab_mode()` / `_is_airgapped()`
  pair. Each call re-reads `os.getenv` — no caching. We leave both
  helpers untouched; they will reflect the new mode on the next request.
- The portal is single-worker uvicorn. Multi-worker is out of scope
  (per 05-07 architecture §11 and reaffirmed by 05-07 REVIEW.md).
- Subprocess workers (AirLLM model server, researcher loop) read
  `LAB_MODE` at startup and do **not** poll `os.environ`. After the
  portal toggles, those subprocesses retain the old mode until the user
  restarts them. **In scope: surface a one-line note in the modal.
  Out of scope: actually restarting them.**
- The `env_writer.set_env_var` API is stable from 05-07; we do not
  redesign it. We continue to call it with `(path, "LAB_MODE", target)`.
- The audit-log append (`_append_audit`) silently swallows failures
  today (see `app.py:6978–6979`). We preserve that exactly. **We do
  surface it explicitly** as a known limit so a future sprint that
  cares about audit durability has a starting point.
- Browser support for `fetch()` with `same-origin` credentials and the
  `Origin` header is assumed (every modern browser since 2020).
- Rapid clicks on the new control are debounced client-side; the server
  serializes through `env_writer`'s per-path lock if anything slips past
  the debounce. Both layers are required (UX + correctness).

## Data flow

```
   ┌─────────────────────────────┐    click    ┌────────────────────────────┐
   │  Network Policy modal       │─────────────▶│ POST /api/airgap/toggle    │
   │  segmented control          │  optimistic │   {target}                 │
   │   [airgapped][ hybrid ]     │  UI flip    │  1. bind-loopback gate ────┼─▶ 403 bind_not_loopback
   │  busy spinner overlay       │             │  2. Origin/Host CSRF ──────┼─▶ 403 cross_origin
   │                             │             │  3. set_env_var(.env,…) ───┼─▶ 500 env_write_failed
   │                             │             │  4. os.environ[LAB_MODE]=… │
   │                             │             │  5. egress._PROBE_CACHE.   │
   │                             │             │     clear()                │
   │                             │             │  6. _append_audit(...)     │
   │                             │             │  7. activity_log.emit(…)   │
   │                             │             │  8. 200 {lab_mode,previous}│
   │                             │◀────────────┤                            │
   │  on 200: confirm UI flip    │             └────────────────────────────┘
   │  on non-200: revert + show  │
   │  inline error               │                       │
   └─────────────────────────────┘                       ▼
                                              (next Buddy tick ≤60s)
                                              _watch_airgap_events posts
                                              "Door's open" / "Sealed back"
                                              Observation; state.json merged
```

## Interface contracts

### `POST /api/airgap/toggle` (CHANGED)

**Request:** `{"target": "airgapped" | "hybrid"}` JSON body.
`confirm_token` field is **removed**. Bodies sent with a leftover
`confirm_token` from a cached client are accepted (the field is ignored).

**Response (200, success):**
```json
{
  "lab_mode": "hybrid",
  "previous": "airgapped",
  "took_effect_at": "2026-05-14T18:22:01.123Z",
  "appended": false
}
```

Note: the `env_path` field is **dropped** from the success body. The
05-07 review flagged it as a path-disclosure smell; one-tap is a good
moment to fix it. Tests asserting `env_path` are updated.

**Errors:**

| Code | When | Body |
|---|---|---|
| 400 | `target` not in `{"airgapped","hybrid"}` (or missing/empty body) | `{"error":"invalid_target"}` |
| 403 | `BIND_ADDR` not loopback | `{"error":"bind_not_loopback","message":"Edit `.env` directly — toggle disabled when bound to non-loopback."}` |
| 403 | `Origin` present and `Origin.netloc != Host` | `{"error":"cross_origin"}` |
| 500 | `EnvWriterError` or unexpected from `set_env_var` | `{"error":"env_write_failed"}` (no path / file contents in body) |

The `409 need_confirm` response is **removed**. The route now succeeds
or fails in one round trip.

### `GET /api/airgap/status` (UNCHANGED)

Shape preserved (additive `bind_is_loopback` from 05-07 stays). The
frontend reads `lab_mode` and `bind_is_loopback` from this endpoint to
seed the segmented control's initial state on modal open.

### `arail.egress._PROBE_CACHE` (NEW: callable invalidator)

Add a tiny helper, **not a public API** — co-located in `egress.py`:

```python
def invalidate_probe_cache() -> None:
    """Clear the host-internet probe cache.

    Called by the airgap toggle endpoint after a successful mode flip so
    the modal's 'host can reach internet' row reflects post-flip reality
    on the next /api/airgap/status fetch. The cache key is time-only
    (not mode-keyed), but the modal renders both fields together; users
    expect both to refresh on toggle.
    """
    _PROBE_CACHE.clear()
```

Preconditions: none. Postconditions: subsequent `probe_internet()`
call performs a fresh socket connect (subject to TTL=0). Thread-safe
under the GIL for a `dict.clear()`.

### `_TOGGLE_TOKENS` / `_issue_token` / `_consume_token` / `_TokenEntry` / `_TOGGLE_TOKEN_TTL` / `_purge_expired_tokens` (REMOVED)

All five symbols are deleted from `app.py`. They had no other call sites
(grep verified). The `dataclasses` import in `app.py` stays — it's used
elsewhere.

### Frontend control (CHANGED) — `_airgap_modal.html` + `nav.js`

**Visual design.** Segmented control with two halves:

```
┌──────────────┬──────────────┐
│  airgapped   │    hybrid    │   ← active half highlighted
└──────────────┴──────────────┘
   ↑ pill mirrors active half ↑
```

Click on the inactive half:
1. **Optimistic flip:** active class moves to the clicked half *immediately*
   (CSS class swap, no transition delay). The pill in the modal header
   updates to match. Both halves become temporarily `aria-disabled="true"`
   and a small spinner appears next to the active label.
2. **Background POST:** `fetch('/api/airgap/toggle', {method:'POST',
   credentials:'same-origin', headers:{'Content-Type':'application/json'},
   body: JSON.stringify({target})})`.
3. **On 200:**
   - Re-enable both halves.
   - Replace the pill text + ok/warn class to reflect server-confirmed
     `lab_mode` (paranoid: read from response body, not from optimistic
     state, so we catch the freak case where server returns `lab_mode`
     ≠ what we POSTed).
   - Append a synthetic recent-activity row: `mode toggled → <target>`.
   - Trigger badge update in nav (existing `updateModeBadge()` helper).
4. **On non-200:**
   - Revert active class to the pre-click half.
   - Revert pill.
   - Show inline error in `#airgap-toggle-error` with body-derived copy:
     - `bind_not_loopback` → "Toggle disabled when lab is bound beyond
       loopback. Edit `.env` directly."
     - `cross_origin` → "This action must be initiated from the lab UI."
     - `invalid_target` → "Toggle failed — please reload the modal."
     - `env_write_failed` → "Save failed — check server log."
     - Network failure (fetch rejects) → "Network error — flip not saved."
   - Re-enable both halves.

**Static elements removed:**
- `#airgap-toggle-btn` (the single button + its label-switching logic)
- `#airgap-toggle-confirm` (the entire confirm panel)
- `#airgap-toggle-confirm-btn`, `#airgap-toggle-cancel-btn`
- The 3-second countdown timer in `nav.js`
- The two-step 409→re-POST handler
- The modal close + `setTimeout(reopen, …)` dance

**Static elements kept:**
- `#airgap-toggle-section` outer container
- `#airgap-toggle-bind-warning` (shown when `bind_is_loopback=false`;
  in that mode the segmented control is replaced by the warning text)
- `#airgap-toggle-error` (now used for inline error display)

**New copy near the segmented control** (one short line, addresses the
out-of-scope worker-staleness):

> Subprocesses (AirLLM, researcher) read `LAB_MODE` at start; restart
> them to pick up a flip.

This sets correct expectations without engineering work to fix it now.

## Failure modes

| # | Failure | Detection | Recovery |
|---|---|---|---|
| 1 | Rapid double-click race (two POSTs in flight) | Client: button debounced via `aria-disabled` set on first click, cleared in `finally` of the fetch promise. Server: `env_writer.set_env_var` per-path `threading.Lock` serializes; second POST that arrives mid-write blocks until the first releases, then re-reads file state and either no-ops (same target) or flips back (opposite target) | Either both succeed in arrival order (correct), or the second is rejected as `invalid_target` if body became malformed. No torn `.env`. UI revert handles whichever the user sees last. |
| 2 | CSRF cross-origin POST | `Origin` header parsed; if `netloc != Host`, 403 | Server: 403 `cross_origin`, no side effects. Client: shows error. **Test:** post with `Origin: http://evil.com:8080` against `Host: 127.0.0.1:8080`, expect 403 + `.env` unchanged + `os.environ["LAB_MODE"]` unchanged. |
| 3 | POST with no `Origin` header (curl, legacy client) | `if origin:` block is skipped — no rejection | Treated as same-origin (legacy-compatible). Bind-gate still applies; loopback-bound portal won't accept LAN-origin requests. Mirrors 05-07 behavior. **Documented, not a defect.** |
| 4 | Non-loopback bind (`BIND_ADDR=0.0.0.0`) | `_toggle_bind_is_loopback()` returns False | 403 `bind_not_loopback`; `.env` and `os.environ` untouched. Modal frontend shows static warning instead of segmented control. **Test:** set `BIND_ADDR=0.0.0.0`, POST, expect 403 + body matches spec copy. |
| 5 | `.env` write fails (disk full, permission, symlink target) | `env_writer` raises `EnvWriterError` | Caught in route; 500 `env_write_failed`; `os.environ` NOT mutated (order preserved: disk → env → audit → activity); audit log NOT appended; activity NOT emitted. Original `.env` untouched. Client reverts optimistic UI. **Test:** monkeypatch `set_env_var` to raise; verify all four side effects skipped. |
| 6 | Optimistic UI flip succeeded but server returned 5xx | `response.ok` is False | Client re-renders pill + segmented control from pre-click state. Inline error visible for 5 seconds (auto-clear) with the body-derived message. User can retry. |
| 7 | Cache-bust happens in portal but a long-running worker holds stale mode | No detection — workers don't watch env | **User-visible symptom:** the portal blocks (or allows) outbound calls per the new mode, but in-flight subprocess actions (autoresearcher fetch, AirLLM remote-tool call) continue per the *old* mode until they finish. New subprocess work spawned after the flip inherits the new env. The modal copy ("restart them to pick up a flip") sets this expectation. **Not a bug to fix this sprint; flagged as known limit.** |
| 8 | Audit log append fails (disk full, RO fs) | `_append_audit`'s broad `except Exception` swallows | Warning logged via `_log.warning`. Toggle returns 200 (audit failure does not fail the flip). **This was the 05-07 behavior; we preserve it explicitly.** The argument: the flip *did happen* on disk; refusing to acknowledge it because the audit log is unavailable would mislead the client into thinking the flip rolled back. The audit log is a "best effort observability surface," not a transactional invariant. Future sprint: make this a hard error if/when audit-log durability matters. |
| 9 | `egress._PROBE_CACHE` retains pre-toggle host-reachable result | Time-based TTL=60s would clear eventually | We force-clear immediately post-toggle so the modal's host-probe row redraws on the next `/api/airgap/status` poll. **Test:** prime cache with `_PROBE_CACHE["result"]=True`; toggle; assert `_PROBE_CACHE == {}`. |
| 10 | Browser back-button / modal-close mid-fetch | Fetch promise resolves into a closed modal | Resolve handler checks `document.getElementById('airgap-toggle-section')` is still present and visible before touching DOM. On absence: no-op (server already committed). Next modal open reads fresh state from `/api/airgap/status`. |
| 11 | Concurrent flips from two browser tabs targeting opposite modes | Server: per-path lock in `env_writer` serializes | Final disk state matches whichever POST landed second. Both tabs receive 200. UI in each tab reflects its own POST's result; they will disagree until refresh. Acceptable for a single-user lab; documented. **Test:** spawn 2 threads POSTing opposite targets via TestClient; assert exactly one of `{airgapped,hybrid}` ends up persisted + 2 audit lines + no torn write. |
| 12 | Legacy client posts `{"target":"hybrid","confirm_token":"abc"}` (cached JS from 05-07 build) | Server ignores `confirm_token`; processes as if absent | Endpoint succeeds in one round trip; the cached client sees 200 (it expected 409 first). Cached client's "confirm-token retry" code path is dead but harmless. **Behavior is a strict superset of the old protocol's success path. No regression.** |
| 13 | Path leakage in error responses | Error bodies are `{"error": "<code>"}` only; no `env_path`, no exception messages | Same as 05-07. **Test:** force `EnvWriterError`; assert response body is `{"error":"env_write_failed"}` byte-exact. |
| 14 | Audit log records `source_ip` from `request.client.host` | Always loopback (since bind-gate enforces loopback) | Audit captures `127.0.0.1` for almost every entry; provides timestamp + from/to. Acceptable. |
| 15 | XSS via error message echoed into modal | All error strings are static client-side; server-supplied `message` field (only set by `bind_not_loopback`) is hard-coded server-side, no user input reflected | Frontend assigns via `.textContent`, not `innerHTML`. **Test:** force a 403 with `bind_not_loopback`; assert `textContent` assignment in nav.js diff. |

## Test strategy

Per `arail/CLAUDE.md` allocation (30% setup / 30% Buddy / 20% security
/ 10% happy / 10% regression), with **security as mandatory minimum**.

### Security (20% — mandatory; covers failure modes 1, 2, 4, 5, 13, 15)

- `tests/test_airgap_toggle_endpoint.py::test_toggle_rapid_double_click_race`
  Spawn 2 threads POSTing the same target concurrently against a shared
  temp `.env`. Assert: both return 200; final disk state is `target`;
  exactly 2 audit lines (one with `appended=True`, one with
  `appended=False` allowed); no torn file. *Failure mode 1.*
- `tests/test_airgap_toggle_endpoint.py::test_toggle_cross_origin_rejected`
  POST with `Origin: http://evil.example:9999`, `Host: 127.0.0.1:8080`.
  Assert 403 `cross_origin`; `.env` unchanged; `os.environ["LAB_MODE"]`
  unchanged; no audit line. *Failure mode 2.*
- `tests/test_airgap_toggle_endpoint.py::test_toggle_bind_gate_lan_rejected`
  `monkeypatch.setenv("BIND_ADDR","0.0.0.0")`; POST; assert 403
  `bind_not_loopback` with exact spec copy. *Failure mode 4.*
- `tests/test_airgap_toggle_endpoint.py::test_toggle_bind_gate_ipv6_loopback_ok`
  `BIND_ADDR=::1`; POST; assert 200 (gate is mode-aware on all three
  loopback forms). *Failure mode 4.*
- `tests/test_airgap_toggle_endpoint.py::test_toggle_writer_failure_no_path_leak`
  Monkeypatch `set_env_var` to raise `EnvWriterError("/secret/.env: oh
  no")`. POST. Assert body is exactly `{"error":"env_write_failed"}` —
  no path, no exception string, no `env_path` field. Assert
  `os.environ["LAB_MODE"]` unchanged; no audit line; no activity emit.
  *Failure modes 5, 13.*
- `tests/test_airgap_toggle_endpoint.py::test_audit_line_emitted_per_flip`
  Happy path. Assert exactly one line appended to `airgap_audit.jsonl`
  with `{ts, from, to, source_ip, confirmed:true, appended:bool}`.
  Re-flip same direction: assert second line appended (no dedup).
  Re-flip opposite direction: assert third line appended.
  *Sprint requirement + failure mode 14.*

### Setup (30% — covers happy path on fresh lab)

- `tests/test_airgap_toggle_endpoint.py::test_toggle_persists_on_disk_only_path`
  Boot with no `.env`; POST `{target:"hybrid"}`; assert file created
  with `LAB_MODE=hybrid` and `chmod 0600`; `appended=True` in response.
- `tests/test_airgap_toggle_endpoint.py::test_toggle_no_confirm_token_field`
  POST with `{target:"hybrid"}` only (no confirm_token). Assert 200 in
  one round trip (regression that protocol is single-shot).
- `tests/test_airgap_toggle_endpoint.py::test_legacy_confirm_token_field_ignored`
  POST with `{target:"hybrid","confirm_token":"stale-abc"}`. Assert
  200; the extra field is silently ignored. *Failure mode 12.*

### Buddy (30% — covers downstream observer)

- `tests/test_buddy_watcher_after_onetap_toggle.py::test_watcher_fires_after_one_tap_toggle`
  Seed Buddy state with `airgap_last_lab_mode="airgapped"`. POST one-tap
  flip to hybrid (one round trip). Tick `_watch_airgap_events()`. Assert
  observation severity=info; assert `state.json` merged correctly
  (`airgap_last_lab_mode="hybrid"` AND any prior Buddy keys preserved —
  this is the 05-05 BLOCK regression).
- `tests/test_buddy_watcher_after_onetap_toggle.py::test_rapid_toggle_5x_no_double_fire`
  Five back-and-forth flips in sequence. Tick watcher once. Assert at
  most one observation (mode-change cooldown is intact).

### Happy / UX (10% — frontend; manual smoke + one DOM test)

- `tests/test_airgap_modal_dom.py::test_modal_renders_segmented_control_when_loopback`
  Render `_airgap_modal.html` with a fixture that mocks
  `bind_is_loopback=true`. Parse the DOM; assert one
  `#airgap-toggle-segmented` element with two children
  `[data-target=airgapped]` and `[data-target=hybrid]`. Assert no
  `#airgap-toggle-confirm` element exists (confirm panel removed).
- `tests/test_airgap_modal_dom.py::test_modal_renders_bind_warning_when_lan`
  Same fixture with `bind_is_loopback=false`. Assert
  `#airgap-toggle-bind-warning` visible, segmented control hidden.
- **Manual smoke (not automated; covered in QA):** click toggle, watch
  pill flip, refresh page, confirm `.env` persisted. Click back. Force
  a 500 by stopping mid-write (chmod a-w on parent dir); confirm UI
  reverts.

### Regression (10%)

- All 05-07 sprint tests (env_writer, audit-log, bind-gate) must
  continue to pass. Tests asserting `409 need_confirm` are **rewritten**
  to assert `200`. Tests asserting `env_path` in the success body are
  **rewritten** to assert its absence (the path-leak fix).
- 05-05 sprint tests (egress guard, airgap.py) must pass unchanged.
- `tests/test_airgap_toggle_endpoint.py::test_probe_cache_invalidated_on_flip`
  Prime `egress._PROBE_CACHE["result"]=True, ts=time.monotonic()`. POST
  flip. Assert `_PROBE_CACHE == {}`.

### Performance / Concurrency

- Not on a hot path; no benchmark. The concurrency test
  (`test_toggle_rapid_double_click_race`) covers correctness under
  contention.

### Test files at a glance

| File | New / Edited | Purpose |
|---|---|---|
| `tests/test_airgap_toggle_endpoint.py` | EDITED | drop 409-flow tests; add one-tap tests; add probe-cache test |
| `tests/test_airgap_toggle_concurrency.py` | EDITED | simplify (no token issuance step); keep 8-thread torn-write check |
| `tests/test_buddy_watcher_after_onetap_toggle.py` | NEW | watcher + state-merge after one-tap flip |
| `tests/test_airgap_modal_dom.py` | NEW (Jinja-render + html.parser) | assert template structure |
| `tests/test_env_writer.py` | UNCHANGED | 05-07 round-trip coverage stays |

## Tech debt

**Removed this sprint:**
- `_TOGGLE_TOKENS` dict + `_TOGGLE_TOKENS_LOCK` + `_TOGGLE_TOKEN_TTL`
  + `_TokenEntry` dataclass + `_issue_token` + `_consume_token`
  + `_purge_expired_tokens` (six in-memory-state surfaces gone from
  `app.py`)
- 3-second countdown timer state machine in `nav.js`
- Modal close + `setTimeout(reopen)` dance
- Confirm panel + cancel button HTML + their CSS classes
- The `env_path` field in the 200 response (05-07 follow-up #2 closed)
- The 409 `need_confirm` response path entirely

**Repaid (cross-sprint):**
- 05-07 REVIEW.md follow-up #2 ("Reduce `env_path` leakage in success
  response") — closed by this sprint.

**Remaining tech debt (untouched, surfaced for tracking):**
- 05-07 follow-up #1: `Sec-Fetch-Site: same-origin` defense-in-depth
  check not added. **Decision: defer.** With confirm-token gone, the
  CSRF Origin check is now the only browser-CSRF defense. Adding
  `Sec-Fetch-Site` would be a +5-line strengthening that we could
  justify, but it's orthogonal to the one-tap UX goal and the spec
  excludes it. File as a follow-up ticket.
- 05-07 follow-up #3: `_toggle_env_path()` parents-walk vs.
  `ARAIL_LAB_ROOT` — unchanged.
- Subprocess workers cache `LAB_MODE` at startup. Documented in modal
  copy; full fix is a future sprint (likely involving a
  `SIGUSR1`-or-equivalent reload signal).
- `_append_audit` silently swallows write failures. Preserved; flagged
  as a known limit. Future sprint can introduce a hard-fail mode if
  audit durability becomes a compliance concern.

**Net:** Negative (debt removed > debt added). One follow-up
re-acknowledged (Sec-Fetch-Site), two new known-limits surfaced for
visibility (worker staleness in modal copy, audit silent-swallow in
the failure-modes table).

## Recommended implementation order

1. **Backend route surgery first** — `src/arail/portal/app.py`:
   - Remove `_TOGGLE_TOKENS`, `_TOGGLE_TOKENS_LOCK`, `_TOGGLE_TOKEN_TTL`,
     `_TokenEntry`, `_issue_token`, `_consume_token`,
     `_purge_expired_tokens`.
   - Simplify `post_airgap_toggle` to a single-pass: bind-gate →
     CSRF → parse → set_env_var → `os.environ` → cache-bust → audit →
     activity → 200.
   - Drop `env_path` from the response body.
2. **Add `invalidate_probe_cache()`** in `src/arail/egress.py` (3-line
   helper); call it from the route between `os.environ` mutation and
   audit append.
3. **Update endpoint tests** in `tests/test_airgap_toggle_endpoint.py`:
   - Delete or rewrite tests that asserted 409 / `confirm_token`.
   - Rewrite happy-path tests to expect one-shot 200.
   - Add the six new security / setup / regression cases listed above.
4. **Update concurrency tests** in
   `tests/test_airgap_toggle_concurrency.py`.
5. **Frontend** — `_airgap_modal.html` + `static/nav.js`:
   - Replace `#airgap-toggle-btn` + `#airgap-toggle-confirm` block with
     segmented-control markup.
   - Delete countdown timer code, confirm-handler, two-step retry, and
     modal close-reopen dance in `nav.js`.
   - Add one-tap click handler with optimistic flip + revert-on-error.
   - Add the "subprocesses cache LAB_MODE" copy.
6. **Add `tests/test_airgap_modal_dom.py`** and
   `tests/test_buddy_watcher_after_onetap_toggle.py`.
7. **Manual smoke** on a running lab: click → pill flips immediately →
   POST returns 200 → reload page → pill still flipped → `.env`
   contains `LAB_MODE=hybrid`. Click back; confirm reverse. Force a
   500 (chmod the parent dir) and confirm UI reverts cleanly.
8. **Modal copy passes** — verify the "subprocesses cache LAB_MODE"
   sentence renders and reads cleanly alongside the new control.

## Files to touch

| File | Action | Notes |
|---|---|---|
| `src/arail/portal/app.py` | EDIT | route surgery; drop token machinery; drop `env_path` from response |
| `src/arail/egress.py` | EDIT | add 3-line `invalidate_probe_cache` helper |
| `src/arail/portal/templates/_airgap_modal.html` | EDIT | segmented control replaces button + confirm panel |
| `src/arail/portal/static/nav.js` | EDIT | one-tap handler; delete countdown / two-step / reopen logic |
| `tests/test_airgap_toggle_endpoint.py` | EDIT | drop 409 tests; add 6 new cases |
| `tests/test_airgap_toggle_concurrency.py` | EDIT | simplify to one-shot POST |
| `tests/test_buddy_watcher_after_onetap_toggle.py` | NEW | downstream observer test |
| `tests/test_airgap_modal_dom.py` | NEW | template-structure assertions |
| `src/arail/env_writer.py` | NO CHANGE | preserved per spec |
| `src/arail/airgap.py` | NO CHANGE | already cache-free |

## Branch recommendation

**Continue on `qukaizen/arail-experiment-branches`.** The branch is
clean (`git status` shows no unshipped commits other than this sprint's
`SPRINT.md`). Cutting a fresh `qukaizen/arail-airgap-onetap` would
duplicate review/PR overhead without isolation benefit. If the build
phase discovers unexpected coupling to the experiment-branches work,
the builder can fork at that point.

## Non-goals

- Restarting AirLLM / researcher subprocesses on toggle. **Future sprint
  with a signal-based reload contract.**
- Hardening audit-log append into a transactional write (today's
  swallow-on-error preserved).
- Adding `Sec-Fetch-Site: same-origin` enforcement. **Follow-up ticket.**
- Refactoring `_toggle_env_path()` parents-walk into `ARAIL_LAB_ROOT`.
- Unifying `airgap_audit.jsonl` and `egress.jsonl`.
- Adding a third toggle target (e.g. "consent-required"). Two-state.
- Multi-worker portal support.
