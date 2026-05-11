# QA test report: min-cloud-first
**Verdict:** WEAK_PASS
**Date:** 2026-05-11
**Allocation:** 35% provider-wiring / 25% setup-flow / 20% security / 10% UI / 10% regression

## Edge cases tested

| # | Edge case | Disposition |
|---|---|---|
| 1 | Airgapped guard on `/api/providers/save` for all 10 providers | TESTED — parametrized over the curated 10 + active-switch variant. All pass; no token reaches disk. |
| 2 | `_write_secrets()` round-trips all 10 env vars; chmod 0600 | TESTED — round-trip + sequential-save + mode check (`mode & 0o077 == 0`). |
| 3 | Sign-up URL never logged to `activity_log` | TESTED — patched `activity_log.emit`; asserted no token + no `signup`/`docs` URL leaks. |
| 4 | Provider IDs are `[a-z_]` only | TESTED — defensive, defends modal `data-prov` attribute. |
| 5 | Modal renders even if `/api/providers/status` returns 500 | NOT TESTED — JS path; would need headless browser. JS code path inspection shows a try/catch around fetch (chat.html:2883–2888), so falls back to local `PROVIDERS` array with empty server metadata. Manual smoke recommended before ship. |
| 6 | min→max→min cycle preserves explicit `LAB_MODE` | TESTED — explicit `airgapped` set on min survives the round-trip. |
| 7 | `custom` row still in chat.html UI | FAIL (xfail) — see Issues. |
| 8 | setup.sh re-run with explicit `LAB_MODE` | TESTED — pins documented behavior: setup.sh OVERWRITES (`_set_env_var` replaces). ARCHITECTURE.md:134 implies preservation; actual code overwrites. See Issues. |

Plus baseline coverage assertions: status payload exposes signup HTTPS for all 10, no `/api/tokens/*` references remain in chat.html.

## New tests added

- `tests/test_min_cloud_first_qa.py` (NEW, 12 cases including 10 parametrized airgapped-save):
  - 4 security (airgapped save+active guard, chmod 0600, no URL leak to activity log)
  - 4 provider-wiring (lowercase-ASCII IDs, write_secrets round-trip, 10 sequential distinct saves, status signup HTTPS)
  - 2 UI (BYOB custom row presence — **xfail**; no dead `/api/tokens` refs)
  - 2 setup-flow / regression (min→max→min preserves explicit LAB_MODE; setup.sh overwrite-on-rerun pin)

## Test run summary

```
tests/test_min_cloud_first_qa.py + sprint tests + predecessor:
  52 passed, 1 xfailed

Full suite:
  1007 passed, 2 xfailed, 33 warnings in 28.84s
```

Zero regressions vs builder's reported 987 passed, 1 xfailed (+20 net from this QA pass).

## Issues found

| # | Issue | Severity | Detail |
|---|---|---|---|
| 1 | `custom` (Bring-Your-Own-Endpoint) row is in `_PROVIDER_KEY_ENVS`, `_PROVIDER_META`, `/api/providers/status`, and `docs/CLOUD_PROVIDERS.md:175` ("**Custom** row in the Connections modal"), but **chat.html contains zero references** to `custom`, `MODEL_API_BASE`, or any "bring your own" surface. The documented path is unreachable. | **Low** | Pre-existing — predecessor template also lacked it. This sprint widens the gap by documenting the feature. Pinned as xfail in `test_chat_html_still_has_custom_byob_ui` with a tracked-followup note. |
| 2 | ARCHITECTURE.md:134 says "Existing installs (.env predates this flag) keep whatever value was there — the helper preserves it on re-run via `_set_env_var()`." Actual `_set_env_var` at `scripts/setup.sh:1207–1218` **replaces** the line. A user who manually flips `LAB_MODE=airgapped` on min and re-runs `./arailctl setup` will lose that value. `upgrade.sh` does the right thing (upsert-when-missing); only `setup.sh` overwrites. | **Low** | Behavior is reasonable for first-run UX. Either correct the architect's spec sentence or change setup.sh to upsert-when-missing for LAB_MODE specifically. Pinned by `test_setup_overwrites_lab_mode_on_rerun` so the behavior is at least documented in code. |

Neither issue blocks ship; both warrant followup. No high-severity findings.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input (token) | Strip + length-untrimmed pass-through to secrets.env; airgapped guard before write | Clean. Token not echoed in logs; not in activity emits. |
| Auth (provider keys) | Stored at `lab/data/secrets.env` chmod 0600; never logged; never echoed; airgapped blocks save/test/active for all 10 new providers (parametrized assertion) | Clean. |
| File I/O | `_write_secrets` uses `p.write_text` + chmod; no temp-file race; sorted-keys output is deterministic | Clean. Pre-existing silent `OSError pass` on chmod is documented debt. |
| Network I/O | New providers are passive metadata; no new HTTP calls in this sprint outside existing `/api/providers/test|models` paths which already honor airgapped | Clean. |
| Deserialization | `_read_secrets` is line-based `partition("=")`, no eval/exec | Clean. |
| Crypto | N/A — no crypto introduced. | N/A |
| Dependencies | No new pip dependencies (10 providers are all OpenAI-compat over existing httpx path) | Clean. |

## Performance

N/A — this sprint adds metadata + UI rows; no hot-path changes.

## Coverage delta

Builder baseline: 987 passed, 1 xfailed.
After this QA pass: 1007 passed, 2 xfailed (+20 net, +1 xfail for tracked debt).

## Notes for the next QA pass

- **Manual smoke needed on a clean VM** for: modal renders when `/api/providers/status` is 500; sign-up links open with `rel=noopener` honored; verify button against a real provider key.
- **Custom row** — when wired, drop the xfail in `test_chat_html_still_has_custom_byob_ui` and convert to a positive assertion.
- **Architect spec drift** at ARCHITECTURE.md:134 about setup.sh preservation — worth a one-line correction in a followup commit.
- **`_write_secrets` silent OSError** still pre-existing debt; consider logging in next sprint touching this file.
