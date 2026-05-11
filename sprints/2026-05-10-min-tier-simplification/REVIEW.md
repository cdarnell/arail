# Review: min-tier-simplification (architect, REVIEW mode)
**Verdict:** PASS
**Date:** 2026-05-10

## Failure-mode coverage
All seven rows in ARCHITECTURE.md § Failure modes are addressed in code or test. Upgrade-in-place preservation is pinned by `tests/test_compare_feature_flag.py` (unset env → default `"1"`); the `.env`-missing path is pinned by `tests/test_enable_compare_cli.py` (error exit + clear message); the max→min downgrade leaves the flag alone (upgrade.sh only writes when key absent); the grep audit on AirLLM-in-docs ran (BUILD_LOG § Step 15) and ROADMAP.md line 71 was scoped to max+operator-gated.

## Install contract
`pyproject.toml:58` is `min = []` and lines 59–67 keep `airllm>=2.0` in `max`. Both invariants are pinned by `tests/test_tier_install_min.py` (parses pyproject with `tomllib`; asserts min is empty and max contains airllm) and by the rewrite of `tests/test_setup_extras.py::test_min_extra_does_NOT_include_pip_audit` from regex to tomllib parse so the empty-list form is accepted.

## Compare flag semantics
`src/arail/portal/app.py:869` reads `os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1"` — strict equality, unset default `"1"` preserves upgrade-in-place. `scripts/setup.sh:1130–1131` is the only setup-time writer (`max→"1"`, anything else `→"0"`) — no other override path in setup. `scripts/upgrade.sh:106–107` writes `=1` on min→max only when the key is absent, preserving explicit user values.

## chat.html guard
Jinja `{% if compare_enabled %}` wraps the `+ Compare` button at lines 1474–1475 AND the `<section data-col="B">` block at lines 1502–1504+. `setCompare()` at line 2440 has the early-return `if (!btn || !colB) return`; the listener bindings at 2469–2472 null-check before `addEventListener`. Cloud Model B fallback hooked at line 3084 (`setCompare(true)`); per BUILD_LOG, the no-local-deep path picks `State.gallery.cloud_providers[0]` or emits a "configure a cloud key" hint.

## arm64 invariant
PR #44's arm64 absolute block is unchanged: `src/arail/portal/app.py:5025–5030` still returns `None` on arm64 without aerollm, and `_is_airllm_installed()` / `_show_airllm()` (line 4086) still gate AirLLM visibility. No new code re-enables AirLLM on arm64. The min install simply ships without it; the runtime gates remain authoritative.

## Test coverage
35 passed for the four pinned test files (`test_tier_install_min`, `test_compare_feature_flag`, `test_enable_compare_cli`, `test_setup_extras`); BUILD_LOG reports 955 passed / 1 xfailed across the full suite with zero regressions. New sprint surface: 21 cases across 3 new files. Every failure-mode row maps to a test or to runtime gating already pinned by chat-model-sync.

## Tech debt
Net roughly neutral per ARCHITECTURE.md § Tech debt — three small follow-ups noted (consolidate enable/disable into one parameterized `feature.sh`; feature-flag context processor when a second flag appears; verify `State.gallery.cloud_providers` plumb if not already present). None blocking.

## Must-fix before ship
None.

## Nice-to-have followups
- Consolidate `enable_compare.sh` + `disable_compare.sh` into a single parameterized `scripts/feature.sh on|off compare` when a second add-on appears.
- Promote `compare_enabled` to a Jinja context processor once a second feature flag lands (avoids per-handler plumbing drift).
- Verify `State.gallery.cloud_providers` is populated by `/api/chat/models` (BUILD_LOG flags this as relying on PR #44 payload shape); add an explicit test if not already covered.
- Regenerate `lab/pkb/compiled/` files at next portal start so the cached AirLLM-in-min wording is refreshed (auto-regen path, no manual action needed).
