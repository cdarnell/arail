# Test report: opencode in Workbench

**Date:** 2026-05-04
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `14fba3b`
**Architect review:** [REVIEW.md](./REVIEW.md) PASS (0 BLOCK, 0 ASK, 2 INFO)
**QA verdict:** **PASS**

---

## Summary

Builder shipped 41 tests; architect verified must-pass coverage was complete.
QA pass added 38 hunt tests targeting edge-cases the builder + architect
both could plausibly miss, with elevated emphasis on the security surface
per `arail/CLAUDE.md` (loopback binding, gate airtightness, no embedded
credentials anywhere).

**No defects above INFO.** Two INFO-level findings filed for follow-up,
neither gates ship. Live-binary verification confirmed opencode actually
binds `TCP 127.0.0.1:<port>` only — the trust boundary holds in reality,
not just in tests.

- Tests added: **38** (36 passing + 2 intentional skips that document
  INFO findings)
- Defects (CRITICAL): 0
- Defects (HIGH): 0
- Defects (MEDIUM): 0
- Defects (INFO): 2 (stale "Four ways" copy; health endpoint may leak
  opencode signal to min-tier — see below)

---

## Test inventory (added by QA)

File: `tests/portal/test_opencode_qa_hunt.py`

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| 1-13 | `TestLabTierEdgeCases::test_gate_closes_unless_tier_resolves_to_max[...]` (12 parametrized) | Security | LAB_TIER edge cases — empty, whitespace, mixed case, near-miss, garbage | PASS |
| 14 | `test_gate_closes_when_lab_tier_unset` | Security | Unset env var defaults to min | PASS |
| 15 | `test_gate_closes_for_all_three_routes_on_unset_tier` | Security | Unset tier closes all three routes | PASS |
| 16 | `test_opencode_host_env_var_is_ignored_by_start` | Security | OPENCODE_HOST env cannot override `--hostname 127.0.0.1` | PASS |
| 17 | `test_host_constant_is_loopback_literal` | Security | Module constant `HOST` is exactly `"127.0.0.1"` (not `localhost`) | PASS |
| 18 | `test_provider_switch_min_tier_does_not_touch_opencode` | Security | Min-tier provider switch never imports/calls opencode | PASS |
| 19 | `test_min_tier_health_does_not_advertise_opencode` | Security | Health endpoint info-disclosure on min tier | SKIP (INFO-1) |
| 20 | `test_install_hint_is_deterministic` | Setup | Pure function, no hidden state | PASS |
| 21 | `test_install_hint_does_not_spawn_subprocess` | Setup | install_hint stays pure | PASS |
| 22 | `test_install_hint_command_contains_no_shell_metachars_unsafely` | Setup | No unrendered template braces in install command | PASS |
| 23 | `test_stop_with_no_listeners_returns_empty_killed` | Edge | stop() on free port → `{ok: True, killed: []}` | PASS |
| 24 | `test_rotate_noop_when_log_missing` | Edge | _maybe_rotate_log on nonexistent file | PASS |
| 25 | `test_rotate_noop_when_log_below_threshold` | Edge | Sub-10MB log not rotated | PASS |
| 26 | `test_custom_provider_with_no_model_api_base` | Config | `custom` + missing MODEL_API_BASE → empty base, no crash | PASS |
| 27 | `test_compute_source_env_app_import_failure_falls_back_to_my_machine` | Edge | Lazy import failure falls back safely (never leaks token) | PASS |
| 28 | `test_compute_source_env_returns_only_three_keys` | Security | Env dict contains exactly the documented keys (no shadowing) | PASS |
| 29 | `test_opencode_html_template_no_server_password` | Security | Template never references `OPENCODE_SERVER_PASSWORD`, no `password` string | PASS |
| 30 | `test_service_module_no_server_password_active` | Security | Service module never assigns `OPENCODE_SERVER_PASSWORD` | PASS |
| 31 | `test_iframe_url_format_strict` | Security | iframe `src` matches `http://127.0.0.1:N/` exactly — no `@`, `?`, `#` | PASS |
| 32 | `test_popout_window_url_no_credentials` | Security | Pop-out window URL is credential-free | PASS |
| 33 | `test_card_count_matches_copy` | Regression | 5 cards in notebooks.html (Workbench rename invariant) | SKIP (INFO-2) |
| 34 | `test_two_concurrent_starts_only_one_succeeds` | Edge / Concurrency | Lock prevents double-spawn (sibling to existing concurrent-restart test) | PASS |
| 35 | `test_is_running_handles_invalid_port` | Edge | is_running(-1) returns False, doesn't raise | PASS |
| 36 | `test_is_running_returns_false_for_high_unused_port` | Edge | High unused port returns False quickly (<1.5s) | PASS |
| 37 | `test_jupyter_page_still_renders` | Regression | Workbench rename didn't break Jupyter page | PASS |
| 38 | `test_marimo_page_still_renders` | Regression | Workbench rename didn't break Marimo page | PASS |
| 39 | `test_open_notebook_page_still_renders` | Regression | Workbench rename didn't break Open-Notebook page | PASS |

(Note: numbered 1-39 above includes the 12-row parametrized expansion of
the LAB_TIER test as separate cases; pytest reports 36 distinct passing
items + 2 intentional skips.)

---

## Failures

None. **0 defects above INFO.**

## Findings (INFO)

### INFO-1: `/api/system/health` exposes opencode signal regardless of tier

**Symptom:** When opencode is up on the host, `/api/system/health` returns
`{"services": {"opencode": true, ...}}` even when the request originates
from a min-tier client.

**Reproduction:**
```bash
LAB_TIER=min curl -s http://127.0.0.1:8080/api/system/health | jq '.services'
# (with opencode running on 4096)
# → contains "opencode": true
```

**Severity:** INFO (information disclosure, not capability escalation —
the min-tier user cannot reach `/opencode*` routes regardless).

**Detail:** `ARCHITECTURE.md §System health probe extension` does not
specify hiding opencode on min tier. The existing pattern for other
optional services has the same property. Fix is one line:
gate the `opencode_up` health probe behind
`"notebooks" in _visible_surfaces()` the same way the `/api/notebooks/status`
endpoint already does. Test
`test_min_tier_health_does_not_advertise_opencode` is in the suite as a
skip; flip the skip to an assertion when the fix lands.

**Recommended action:** file as Sprint 2 follow-up. Not gating ship.

### INFO-2: `notebooks.html` says "Four ways" but five cards now exist

**Symptom:** The Workbench page header reads:
> "Four ways to work in the lab. Notebooks, reactive notebooks,
> NotebookLM alternatives, and opencode for AI-assisted coding..."

But the grid contains five `data-id` cards: `jupyter`, `marimo`,
`notebooklm`, `open-notebook`, `opencode`.

**Severity:** INFO (copy bug, no functional impact).

**Reproduction:** open `/notebooks` on max tier; count cards (5) vs read
the prose ("Four ways").

**Recommended fix:** rewrite the prose, e.g. "Five ways..." or rephrase to
not state a count. Test `test_card_count_matches_copy` is in the suite
as a skip until the copy is updated.

---

## Security review

| Surface | Checked | Findings |
|---|---|---|
| Tier gate (404 on min) | All three routes (`GET /opencode`, `POST /api/opencode/start`, `POST /api/opencode/stop`) parametrized over 12 LAB_TIER edge values incl. unset, empty, whitespace, mixed case, garbage. Verified `_current_tier()`'s `.strip().lower()` normalization closes the gate on every non-`max` input. Confirmed three routes ALL 404 when LAB_TIER unset. | Clean. |
| Loopback binding (defense-in-depth) | (a) Test asserts `--hostname 127.0.0.1` in Popen argv even when `OPENCODE_HOST=0.0.0.0` and `OPENCODE_HOSTNAME=0.0.0.0` are set in env. (b) Test asserts module constant `HOST == "127.0.0.1"` (not `"localhost"` which could resolve via `/etc/hosts`). (c) **LIVE BINARY VERIFICATION:** ran `opencode serve --port 14096 --hostname 127.0.0.1` and confirmed `lsof -iTCP:14096 -sTCP:LISTEN -n -P` reports only `TCP 127.0.0.1:14096 (LISTEN)` — no `0.0.0.0`, no IPv6 wildcard. Trust boundary holds in production, not just tests. | Clean. |
| No embedded credentials | (a) `opencode.html` template scanned: zero occurrences of `password` or `OPENCODE_SERVER_PASSWORD`. (b) iframe `src` regex-checked: starts with `http://127.0.0.1:`, contains no `@`, `?`, or `#`. (c) Pop-out window URL same check. (d) Service module: no `OPENCODE_SERVER_PASSWORD` assignment anywhere. | Clean. |
| Provider-switch hook | Test verifies min-tier provider switch never even calls `opencode.is_running()` — the surface check `if "notebooks" in _visible_surfaces()` is genuinely taken (not just that the response is ok). | Clean. |
| Provider token leak paths | Existing tests (builder's) cover token-not-in-status-JSON and token-not-in-logs. QA added: `_compute_source_env` returns exactly the three documented keys (no shadowing of e.g. `AWS_SECRET_ACCESS_KEY`). Lazy-import failure falls back to `my_machine` (zero-token state), never leaks a stale provider's token. | Clean. |
| Airgapped + cloud provider | Documented limitation per ARCHITECTURE.md F-SEC-5: airgapped is enforced at the API switching layer (`providers_active` rejects cloud switch), so a user already-on-cloud who flips airgapped won't be able to switch back to cloud, but a cloud-active session before airgapped stays cloud. This rides the existing chat-tab gate; not a new surface. | Acknowledged. |
| File I/O | Log file path is `lab/logs/opencode.log` — fixed path, not user-controlled. `_maybe_rotate_log` handles missing file (no-op) and small file (no-op). Parent dir created with `mkdir(parents=True, exist_ok=True)`. | Clean. |
| Subprocess invocation | `subprocess.Popen` invoked with list-form args (no shell). `--port` is `str(int(port))`, `--hostname` is the module-level constant. No user-controlled string ever concatenated into argv. | Clean. |

---

## Performance

N/A. opencode is interactive, not throughput. No hot path changes per
ARCHITECTURE.md.

---

## Coverage delta

Not measured — no coverage tool wired into this repo's suite (per
BUILD_LOG.md). Suite size grew:

- Before sprint: 513 passing, 5 pre-existing failures
- After builder: 554 passing, 5 pre-existing failures
- After QA: **590 passing**, 2 skips (intentional INFO docs), 5
  pre-existing failures, 1 xfailed (unchanged)

The 5 pre-existing failures (`test_buddy_suggesters`, `test_chat_ui`,
`test_drafter`, `test_toast_ui` x2) are unchanged — verified out of
scope of this sprint, present before commit `c7eaf48`.

---

## Live-system verification

Not part of the unit suite, but executed by hand:

1. `which opencode` → `/opt/homebrew/bin/opencode`
2. `opencode --version` → `1.14.31`
3. `opencode serve --port 14096 --hostname 127.0.0.1` (background) +
   `lsof -iTCP:14096 -sTCP:LISTEN -n -P` →
   `TCP 127.0.0.1:14096 (LISTEN)`. No `0.0.0.0`. No IPv6 wildcard.
   **F-SEC-6 confirmed in reality.**

---

## Notes for the next QA pass

- **Health endpoint surface-disclosure pattern (INFO-1)** generalizes to
  *every* optional service in `/api/system/health`. If a future sprint
  adds another max-tier-only optional service, repeat the audit. The
  fix in `_visible_surfaces()` could also be applied to existing
  optional services if the pattern is judged worth tightening.
- **Workbench page copy (INFO-2)**: now that the page is plural in
  intent (Workbench, not "Notebooks"), copy in `notebooks.html` will
  drift again as more cards are added. Consider rephrasing
  "Four ways..." to be count-agnostic to prevent future stale-copy
  bugs.
- **F-PROC-3 orphan child on portal crash** is deferred per
  ARCHITECTURE.md. If a user ever reports "port 4096 stuck after a
  crash," the workaround is `lsof -ti :4096 | xargs kill`. Worth
  adding to TROUBLESHOOTING.md as the architect noted.
- **F-INSTALL-2 (binary too old)** is deferred. The user-visible
  failure mode is opaque: `start()` returns the underlying
  `Popen` error string. If we hit this in the wild, add a
  pre-flight `opencode --version` check.
- The two skipped tests in `test_opencode_qa_hunt.py` are deliberate
  documentation of INFO findings; flip them to assertions when the
  underlying issues are fixed.
