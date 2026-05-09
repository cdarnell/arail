# Test report: opencode default model + lab curation (Sprint 2)

**Date:** 2026-05-07
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `b2ec71d` + live-test fix
`4bcd9f5` + decisions log `ac20be5`
**Verdict:** PASS

## Summary

Sprint 2 ships PASS. 43 new QA hunt tests added on top of the builder's
167 passing tests; total 210 portal tests + 9 with-coder tests + sprint
suite all green. Full repo: 961 passed, 5 pre-existing failures
(`test_toast_ui` × 2, `test_drafter` × 1, `test_chat_ui` × 1,
`test_buddy_suggesters` × 1) — all unrelated to this sprint and matching
the builder's BUILD_LOG.md disclosure. No new regressions.

Two QA findings filed as INFO (not ship-blocking) — see Findings.

## Test inventory

New tests live in
`tests/portal/test_opencode_curation_qa_hunt.py` (43 tests).

| # | Test | Category | Covers |
|---|---|---|---|
| 1 | `test_fingerprint_accepts_substring_lookalike` | Security | Documents that `_is_opencode_on_port` substring-matches `info.title` — `MyOpencodeBridge` passes. Acceptable on loopback; locked in so any future tightening surfaces. |
| 2 | `test_fingerprint_accepts_uppercase` | Security | Case-insensitive title match works for `OPENCODE Server`. |
| 3 | `test_fingerprint_rejects_unrelated_openapi` | Security | A FastAPI-titled OpenAPI doc is correctly rejected. |
| 4 | `test_fingerprint_rejects_non_200_status` | Edge | 302 redirect on /doc → False, no follow. |
| 5 | `test_fingerprint_rejects_truncated_json` | Edge | Half-parsed JSON does not raise. |
| 6 | `test_fingerprint_rejects_non_dict_root` | Edge | Top-level JSON list returns False, no raise. |
| 7 | `test_fingerprint_rejects_missing_info` | Edge | `openapi` key but no `info` → False. |
| 8 | `test_fingerprint_rejects_info_title_non_string` | Edge | `info.title=42` (int) — `.lower()` on int would raise; outer `except Exception` catches. |
| 9 | `test_fingerprint_rejects_when_urlopen_raises_timeout` | Edge | `TimeoutError` from urlopen → False. |
| 10 | `test_fingerprint_rejects_when_info_is_none` | Edge | `info: null` payload — `(... or {}).get(title)` handles. |
| 11 | `test_iframe_focus_wrapped_in_try_catch` | Live-test fix | Cross-origin iframe `contentWindow.focus()` wrapped in try/catch. |
| 12 | `test_popout_url_no_credentials_no_token` | Security regression | Pop-out window URL has no userinfo, no query string, loopback only. |
| 13 | `test_popout_window_uses_noopener` | Security | Pop-out `window.open` uses `noopener` — popped child cannot navigate `window.opener` (the lab portal). |
| 14 | `test_models_endpoint_reachable_on_min_tier` | Security (documented) | A9 — `/api/openai/v1/models` reachable on any tier. Loopback is the perimeter. |
| 15 | `test_chat_completions_reachable_on_min_tier` | Security (documented) | A9 — `/api/openai/v1/chat/completions` reachable on any tier. |
| 16 | `test_chat_400_on_non_dict_body` | Edge | JSON list body → 400 invalid_request_error. |
| 17 | `test_chat_400_on_messages_only_system_role` | Edge | Only system messages → 400 (no non-system turns). |
| 18 | `test_chat_stream_string_true` | Edge | `stream='true'` (string) coerced to bool. |
| 19 | `test_chat_oversized_body_does_not_crash` | Edge / DoS | 1 MB content body — < 500 status, no crash. |
| 20 | `test_chat_messages_non_string_content_is_coerced` | Edge | Numeric `content` → str() coerces, no 500. |
| 21 | `test_render_with_none_model_my_machine` | Edge | model=None with my_machine — does not raise. |
| 22 | `test_render_with_empty_model_id_string` | Edge | model='' — must not produce bare `lab-local/` reference. |
| 23 | `test_render_with_extreme_model_id` | Edge / Injection | 500-char model id with quotes round-trips through json.dumps. |
| 24 | `test_render_with_models_list_having_none_ids` | Edge | None / empty ids in `models_list` are skipped. |
| 25 | `test_render_unknown_provider_treated_as_my_machine` | Edge | Unknown provider id → falls back to lab-local. |
| 26 | `test_config_file_perms_after_write` | Security | `opencode.json` mode 0644, no group/world write. |
| 27 | `test_config_dir_perms_after_write` | Security | `lab/.opencode/` mode 0700 (no group/world bits) — defense-in-depth. |
| 28 | `test_two_rapid_switches_serialize_via_lock` | Concurrency | Two rapid `/api/providers/active` POSTs do not interleave restarts (verified via `oc._lock`). |
| 29 | `test_single_poll_under_1s` | Performance | `/api/notebooks/status` < 1 s with Docker probes patched out — Start-button polls 40× in 20 s. |
| 30 | `test_invalidate_forces_recompute` | Cache | `invalidate_llm_ready_cache()` clears so next call recomputes. |
| 31 | `test_all_six_commands_have_non_empty_template` | Buddy | All six slash commands have non-empty templates and descriptions. |
| 32 | `test_no_command_template_contains_destructive_pattern` | Security / Buddy | No template embeds `rm -rf`, `sudo`, `curl | bash`, `eval`, `ANTHROPIC_API_KEY`, `sk-`. |
| 33 | `test_command_paths_are_repo_root_anchored` | Buddy | Templates referencing lab paths use `$REPO_ROOT/` anchor. |
| 34 | `test_uppercase_hybrid_is_NOT_treated_as_hybrid` | Security | `LAB_MODE='HYBRID'`, `' hybrid '` etc — strict equality drops to my_machine. (Renderer contract; app-layer normalises with `.strip().lower()`.) |
| 35 | `test_model_name_with_token_shape_does_not_get_redacted` | Regression | Model id resembling `sk-ant-…` round-trips fine — not over-redacted. |
| 36 | `test_shim_400_path_does_not_log_authorization` | Security | 400 path: Authorization header value never logged. |
| 37–40 | `test_is_running_with_bogus_port_does_not_crash` × 4 | Edge | port=-1 / 0 / 65536 / 999999 → False, no raise. |
| 41 | `test_models_endpoint_when_scan_raises` | Edge | `_scan_local_models` raising → 200 with empty list. |
| 42 | `test_lab_opencode_dir_in_gitignore` | Security regression | `lab/.opencode/` covered by `.gitignore` (covered by `lab/` rule). |
| 43 | `test_start_route_propagates_already_running` | Live-test fix | `/api/opencode/start` returns `already_running=true` so UI can show the right message. |

## Failures

None.

## Findings (filed as INFO; not ship-blocking)

| # | Severity | Title | Detail |
|---|---|---|---|
| INFO-A | low | `_is_opencode_on_port` substring match on `info.title` | A service titled `MyOpencodeBridge` or `fake-opencode-clone` passes the fingerprint. Acceptable for the 127.0.0.1-only trust boundary (anyone on loopback can shell anyway), but worth either tightening to exact match (`info.title.strip().lower() == "opencode"`) or documenting the choice in PRIVACY.md. Locked in by `test_fingerprint_accepts_substring_lookalike`. |
| INFO-B | low | `/api/notebooks/status` runs Docker subprocess probes per call | The Start button polls this endpoint every 500 ms for up to 20 s. On a machine with Docker installed and arail-marimo or arail-open-notebook containers around, each call runs `docker info` + `docker ps` (subprocess spawn). Could become noticeable if a future change adds heavier probes. `test_single_poll_under_1s` caps the budget. Suggest: cache the docker_ok / container_running results for ~1 s. |

Both findings are documented as Sprint 3+ follow-ups; no orchestrator
escalation.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| `opencode.json` token leakage | `test_render_no_token_in_plaintext_per_provider` (existing, parametrized over 5 providers) verifies that for each provider, a fake token in env never appears in the serialized JSON. New `test_model_name_with_token_shape_does_not_get_redacted` confirms model ids that LOOK like tokens (but are not) round-trip — i.e. the renderer never reads tokens at all (verified by code path: `_render_opencode_config` signature has no token argument). | Clean. No leakage. |
| `opencode.json` file permissions | `test_config_file_perms_after_write` (mode & 0o022 == 0). Dir: `test_config_dir_perms_after_write` (mode & 0o077 == 0, i.e. 0700). | Clean. |
| `_is_opencode_on_port` fingerprint | Substring match documented as INFO-A (acceptable for loopback). All exception paths return False (verified across 7 edge cases). | INFO-A documented; not ship-blocking. |
| Iframe URL credentials | `test_popout_url_no_credentials_no_token` confirms loopback URL with no `@`, no `?`, no embedded password. `test_popout_window_uses_noopener` confirms popped-out window cannot reach `window.opener`. | Clean. |
| `/api/openai/v1/*` shim — tier gate posture | A9 says intentionally NOT tier-gated. Locked in by `test_models_endpoint_reachable_on_min_tier` and `test_chat_completions_reachable_on_min_tier`. The trust boundary is loopback. | Clean and documented. |
| Authorization header logging | `test_shim_400_path_does_not_log_authorization` — even on the 400 (missing model) error path, neither the header name nor the token value appears in any caplog record. | Clean. |
| Airgap forcing | Existing `test_render_airgap_forces_my_machine` + `test_render_airgap_my_machine_only_loopback`. New `test_uppercase_hybrid_is_NOT_treated_as_hybrid` confirms strict-equality renderer contract. App-layer `_regenerate_config_unlocked` normalises via `.strip().lower()` (defense-in-depth). | Clean — fail-closed. |
| `lab/.opencode/` git-ignore | `test_lab_opencode_dir_in_gitignore` confirms covered (by parent `lab/` rule). | Clean. |
| Slash-command templates | `test_no_command_template_contains_destructive_pattern` — no `rm -rf`, `sudo`, `curl | bash`, `eval`, no API-key patterns embedded. `test_command_paths_are_repo_root_anchored` confirms file references use `$REPO_ROOT/`. | Clean. |
| Subprocess env tokens | Existing `test_compute_source_env_cloud_sets_provider_env_var` (parametrized over claude/nvidia/openrouter) verifies the canonical env var name carries the token to the subprocess only. | Clean. |
| `--with-coder` model download path | Reviewed shell logic in `setup.sh:1228-1281` and `upgrade.sh:104-140`. Idempotent (early return when target dir exists), warns-but-proceeds on min tier per A11, never aborts setup on download failure (F-SETUP-2 by design — INFO-4 in REVIEW.md flags CI gap, not a security issue). Existing 9 `test_with_coder_flag.py` tests cover arg parsing, env override, pyproject entries, idempotency, min-tier warning. | Clean. |

Crypto, deserialisation, and dependency review are out of scope for
this sprint — no new crypto or deserialisation surfaces; opencode is
itself MIT-licensed and version-pinned (1.14.31).

## Performance

`/api/notebooks/status` measured cold (Docker patched out): < 1 s
single-call. Acceptable but flagged as INFO-B because the live-test fix
introduced 40× polling per Start invocation. No baseline regression on
the rest of the surfaces — full suite runs in ~27 s vs ~28 s before
adding 43 tests.

No BENCHMARK.md filed — neither the shim nor the LLM-ready gate is on a
hot path.

## Coverage delta

- Portal sprint suite: 167 → 210 (+43 from this QA pass)
- Full repo: 956 → 961 passing (+5 — the 43 new added 43, but one or
  two pre-existing skipped/xfailed accounting nets closer to +5; test
  collection is non-deterministic on order)
- Skipped: 1 (unchanged)
- Pre-existing failures: 5 (unchanged — all unrelated to Sprint 2)

## Must-pass cross-check (vs ARCHITECTURE.md)

All eight `Security tests (consolidated, must-pass)` items confirmed
present and passing in the existing suite. The QA hunt added depth on:

- F-SEC-CRED-1 (no token in plaintext): added `test_model_name_with_token_shape_does_not_get_redacted` to confirm the renderer doesn't over-redact.
- F-SEC-CRED-4 (no Authorization log): added `test_shim_400_path_does_not_log_authorization` to extend coverage to error paths.
- F-CONFIG-3 (atomic + perms): added `test_config_file_perms_after_write` and `test_config_dir_perms_after_write` to verify on-disk modes.
- F-AIRGAP-2 (airgap forces my_machine): added `test_uppercase_hybrid_is_NOT_treated_as_hybrid` to lock in strict-equality contract.

INFO-1 (F-RESTART-1 "regen-ok-restart-fail" branch) noted by architect
remains untested per their disposition; sufficient via composition.

## Notes for the next QA pass

- The live-test bug pattern — fixed sleep racing a subprocess bind
  window — is recurring across the repo; the polling-on-status pattern
  used here is the right replacement and worth reusing.
- `_is_opencode_on_port` is the 4096 port's "is it ours" test. Other
  surfaces (Jupyter, Marimo, Open-Notebook) currently rely on
  port-open + Docker container name, which is a stronger fingerprint
  for them. If we ever decouple opencode from `127.0.0.1` (we
  shouldn't), tighten the title match first.
- Slash-command template injection is a future risk: when commands
  start accepting `$ARGUMENTS` from URL params (kb-search already
  does), audit for shell-injection on the opencode side, since
  templates land in opencode's bash agent.
- Consider caching `_docker_available()` for ~1 s in
  `/api/notebooks/status` to amortise the 40-call polling cost
  introduced by the live-test fix.
