# QA test report: min-tier-simplification

**Verdict:** PASS
**Date:** 2026-05-10
**Allocation:** 40% tier-correctness / 25% setup-flow / 20% upgrade-path / 15% regression

## Edge cases tested

| # | Candidate | Disposition |
|---|---|---|
| 1 | Explicit ARAIL_COMPARE_ENABLED survives upgrade cycle | **tested** — `test_upgrade_min_after_explicit_enable_preserves_one` round-trips min→max→min and asserts value stable |
| 2 | enable_compare.sh on commented-out line | **tested** — `test_{enable,disable}_compare_uncomments_a_commented_line` pins the `lstrip("# ")` semantic |
| 3 | Concurrent `arailctl enable compare` calls | **tested** — `test_concurrent_enable_compare_calls_do_not_duplicate` with ThreadPoolExecutor; eventual state must be exactly 1 active line |
| 4 | AIRLLM_MODEL from old install | **inspected** — value is still consumed by `app.py:5411,7865` with `meta-llama/Llama-3.1-70B` default, but visibility is gated by `_show_airllm()` from PR #44; no new code path surfaces it problematically. No new test needed (covered by chat-model-sync). |
| 5 | upgrade min after compare=1 keeps compare on | **tested** — `test_upgrade_min_after_explicit_enable_preserves_one` |
| 6 | upgrade max when ARAIL_COMPARE_ENABLED=0 already | **tested** — `test_upgrade_max_respects_existing_zero` (the load-bearing "respect user choice" test) |
| 7 | enable_compare.sh trailing-newline behavior | **tested** — `test_enable_compare_handles_no_trailing_newline` and `test_enable_compare_on_empty_env` |
| 8 | `arailctl enable compare extra-arg` | **tested via source inspection** — `test_arailctl_dispatch_case_matches_only_on_first_arg`. (See "Issues found" §1 for why subprocess testing was infeasible.) |
| 9 | Min-tier compare with no cloud_providers | **tested** — `test_chat_html_cloud_fallback_message_is_actionable` pins the user-facing flash string |
| 10 | chat.legacy.html guard | **tested** — `test_legacy_chat_template_has_no_compare_markup` confirms legacy has no Compare markup so no guard is needed; fails loudly if someone adds Compare there without the guard |

Also added:
- `test_setup_sh_writes_compare_flag_by_tier` — regression guard on setup_env case statement
- `test_upgrade_sh_does_not_write_airllm_model_on_min` — pins min→no AIRLLM_MODEL leak

## New tests added

- `/Users/netsushi/ProJects/arail/tests/test_min_tier_simplification_qa.py` — 13 cases covering commented-line upsert (×2), no-trailing-newline (×2), arailctl dispatch shape, concurrent invocation, upgrade-path persistence (×3), legacy template, cloud fallback string, setup.sh case statement, AIRLLM_MODEL min-tier omission.

## Test run summary

```
$ python -m pytest tests/test_min_tier_simplification_qa.py -v
13 passed in 0.25s

$ python -m pytest tests/test_min_tier_simplification_qa.py tests/test_tier_install_min.py \
                   tests/test_compare_feature_flag.py tests/test_enable_compare_cli.py \
                   tests/test_setup_extras.py
48 passed in 3.90s

$ python -m pytest tests/ -q --ignore=tests/manual --ignore=tests/portal
968 passed, 1 xfailed, 33 warnings in 28.82s
```

Baseline from BUILD_LOG was 955 passed; +13 new tests, zero regressions, 1 xfailed unchanged.

## Issues found

1. **Test-only isolation gap in `arailctl` REPO_ROOT override** (low severity, no runtime impact). The top-level `arailctl` script at line 46 unconditionally overrides `REPO_ROOT` from `${BASH_SOURCE[0]}`'s computed path, so a `REPO_ROOT=<tmp> bash arailctl enable compare` invocation correctly dispatches but writes to the **real** repo's `.env`, not the test override. Discovered while writing `test_arailctl_dispatch_case_matches_only_on_first_arg`. Subscript-direct tests (`bash scripts/enable_compare.sh` with `REPO_ROOT=<tmp>`) correctly isolate because they read the env-var first. Action taken: rewrote the test to inspect the case-statement source directly. Mitigation: in tests, never run `arailctl enable|disable` through subprocess on a non-throwaway repo. No code change needed unless the team wants future `arailctl` subprocess tests — then `arailctl` would need to respect a pre-set `REPO_ROOT` env-var when present.

## Recommendations before ship

None blocking. Two soft follow-ups for the backlog:

- **Honor pre-set REPO_ROOT in arailctl** — change line 46 to `REPO_ROOT="${REPO_ROOT:-$(cd …)}"` so external tests (and weird shim layouts) can override. Today both the symlink-resolution AND the override paths exist but the latter loses to the former.
- **Plumb `State.gallery.cloud_providers` test** — `setCompare()`'s cloud-fallback branch reads `State.gallery.cloud_providers`. If `/api/chat/models` doesn't actually populate this array (architect review flagged this as needing verification), min-tier compare always lands on the "configure a cloud key" hint — degraded but not broken. A small browser-side test would close this loop; out of scope for this sprint.

## Notes for the next QA pass

- The `arailctl` REPO_ROOT-override-precedence quirk is worth a learning note (`learnings/2026-05-10-arailctl-test-isolation.md`) so the next QA pass doesn't waste 20 minutes re-discovering it.
- Pattern spotted: small Python heredocs in shell scripts (`enable_compare.sh`, `disable_compare.sh`, `upgrade.sh`) all share the same `lstrip("# ")` upsert idiom. The architect's nice-to-have to consolidate into a single `scripts/feature.sh` would also let us pin the upsert helper in ONE place — recommended for the next add-on sprint.
