# Build log: Concurrent Worlds as independent instances (WP1-WP4)

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-07-28
**Builder scope this pass:** WP1-WP4 only. WP5-WP8 belong to a second builder pass.

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| WP1 | `scripts/lib/instances.sh` (new), `tests/test_instance_registry.py` (new), `tests/test_instance_paths.py` (new), `.gitignore` | Path helpers, registry write/read (python3 tmp+replace), 4-step `inst_alive`, `inst_list`, `inst_prune`, `daemon_active`. No caller changes. | new pytest files; `bash -n` + shellcheck; `git check-ignore` | pending |
| WP2 | `arailctl`, `scripts/start.sh:35`, `scripts/status.sh:42`, `scripts/install-daemon.sh:76-79`, `tests/test_daemon_predicate.py` (new) | Every liveness-check site calls `daemon_active`/`inst_*` from `scripts/lib/instances.sh`. Plist-trap fix (F9). | grep for stray plist/launchctl strings; `test_daemon_predicate.py` | pending |
| WP3 | `scripts/lib/instances.sh`, `scripts/setup.sh` (export `_port_in_use`/`_find_free_port`), `tests/test_instance_ports.py` (new) | Env pack writer, first-boot scaffold, block port allocation + pinning, exclusion list, sub-9100 hard stop. | `test_instance_ports.py` + `test_instance_paths.py`; hand-written pack round-trip | pending |
| WP4 | `scripts/start.sh`, `arailctl` (usage text), `tests/instance_start_driver.sh` (new), `tests/test_instance_start.py` (new) | Arg parsing, picker, attach-on-running, 8-stage launch, claim/trap, instance-service gating, `warn()` fix, `set -a` around `lab.conf`. | `instance_start_driver.sh` suite; manual two-World launch (deferred to QA per orchestrator note) | pending |

## Execution

### WP1 — `scripts/lib/instances.sh`: paths, registry, liveness

Built `scripts/lib/instances.sh` with: path helpers (`inst_root_dir`,
`inst_registry_dir`, `inst_instance_dir`, `inst_env_file`, `inst_data_dir`,
`inst_pkb_dir`, `inst_log_dir`, `inst_registry_file`, `inst_registry_bad_file`,
`inst_claim_file`, `inst_valid_slug` pinned to the same `_SLUG_RE` as
`world_mount.py:141`); registry write (`inst_write_record`, python3
tmp+`os.replace`, JSON validated via `json.loads` before write — never
hand-rolled `echo >`); registry read (`inst_read_record`, corrupt JSON
quarantined to `<slug>.json.bad`, never raises — F16); `inst_record_field`;
`inst_list_slugs`; `inst_prune`/`inst_prune_all` (removes only stale records,
never touches instance data dirs); the 4-step `inst_alive` predicate
(steps 1-3 always; step 4 factored into `inst_probe_matches`, currently
fails closed since `GET /api/instance` doesn't exist until WP6); and
`daemon_plist_installed()`/`daemon_active()` (plist exists AND launchctl
reports a numeric PID line).

Added `.gitignore` entry: `lab/instances/` (one line, no `registry.d/`
negation per §1.4/§2.1 — registry state is machine state, never committed).

Wrote `tests/test_instance_registry.py` (21 tests covering path helpers,
slug jail, write/read round-trip, tmp-file cleanup, missing-record handling,
corrupt-JSON quarantine (F16), the liveness predicate incl. dead-PID (F2)
and PID-reuse (F3) rejection via stubbed `kill`/`ps`, prune behavior, and
`daemon_active` — false-with-no-plist, false-with-plist-but-not-loaded (the
plist trap), true-only-with-a-PID-line) and `tests/test_instance_paths.py`
(6 tests: hand-written pack sources cleanly under `set -euo pipefail`; all
five path keys resolve absolute; `ARAIL_MODELS_DIR`/`ARAIL_WORLDS_DIR` stay
pointed at the shared root, not forked under the instance root — the
`config.py:86` trap; `ARAIL_DATA_DIR`/`LAB_PKB` are per-instance;
`ARAIL_ENV_FILE` beats a parent-directory `.env`).

**Deviation (documented, narrow):** `test_instance_paths.py`'s coverage
excludes the app.py-level half of F14's guard (§6.4 guard 2: "boot assertion
… otherwise raise at startup") — that assertion lives in `src/arail/portal/app.py`,
which is WP6 scope and out of bounds for this builder pass. This file covers
guard 1 only (the pack itself resolves absolute, so the relative-default
branch of `_resolve()` never fires for an instance). Flagged here rather than
silently narrowing the architecture's stated test-file description; the
boot-assertion test belongs in WP6's pass alongside the assertion it tests.

**Gate result:** PASS.
- `bash -n scripts/lib/instances.sh` — clean.
- `shellcheck scripts/lib/instances.sh` — clean except 7x SC2034 ("appears
  unused") on the port/ceiling/claim-staleness constants declared in WP1 for
  consumption by WP3/WP4 — expected, not a defect.
- `PYTHONPATH=src <venv>/bin/python -m pytest tests/test_instance_registry.py
  tests/test_instance_paths.py -q` → **21 passed**.
- `git check-ignore lab/instances/registry.d/x.json` → exit 0.
- Regression check: `test_reset_paths.py` (10 passed), `test_reset_stop_scope.py`
  (2 failed — pre-existing, confirmed via `git stash` on this exact worktree
  before any WP1 change: system `/usr/bin/python3` is 3.9.6, no `tomllib`,
  breaking `test_shell_source_safety.py`'s blueprint-render case; the reset
  stop-scope failures are a pre-existing `awk` function-extraction ordering
  issue unrelated to instances — not introduced by this sprint), and
  `test_shell_source_safety.py` (1 failed, same pre-existing `tomllib` cause).
  None of these three pre-existing failures touch instance code.

Commit: `<pending — see report>`

## Architect feedback required

(empty unless the architect's plan needed revision mid-build)

## Final state

(numbers: tests passing, coverage delta, lines changed — filled in at the end)
