# Build log: elite-cli — WP1 & WP2

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 42e87f4
**Started:** 2026-07-29
**Scope of this log:** WP1 ("Foundations") and WP2 ("`scripts/lib/services.sh` +
root-lab readiness gate") only, per the builder's task. WP3–WP8 are not
started; `docs/cli.md` and the exit-code contract are written to reflect
only what WP1+WP2 actually ship, not the full sprint vision.

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| WP1-1 | `arailctl`, `scripts/{setup,start,status,reset,update,upgrade}.sh` | ANSI color gating (`[[ -t 1 ]]` / `NO_COLOR` / `ARAIL_COLOR`) | `tests/cli/color_driver.sh` | WP1 commit |
| WP1-2 | `arailctl`, `src/arail/doctor.py` | doctor findings tally + `--strict`, exit 0/1/3 | `tests/cli/verbs_driver.sh` (T9) | WP1 commit |
| WP1-3 | `scripts/setup.sh` | `--yes\|-y`, `--quiet`, unknown-flag rejection (exit 2), passphrase masking, SC2024 annotation | `tests/cli/verbs_driver.sh` (T7), snippet test (T33) | WP1 commit |
| WP1-4 | `arailctl` | dedup `kb help` heredocs into `kb_usage()` | manual (`./arailctl kb help`) | WP1 commit |
| WP1-5 | `docs/cli.md` (new) | canonical verb reference, F33 drift-test target | `tests/cli/verbs_driver.sh` (F33) | WP1 commit |
| WP1-6 | `tests/cli/lib.sh`, `color_driver.sh`, `verbs_driver.sh` (new) | shared harness + the two WP1 drivers | self | WP1 commit |
| WP2-1 | `scripts/lib/services.sh` (new) | root-lab per-service readiness probes (`svc_listening`, `svc_http_status`, `svc_wait_listening`, `svc_wait_http_ready`, `svc_identity_root`, `svc_probe_host`) | `tests/cli/root_start_driver.sh` | WP2 commit |
| WP2-2 | `scripts/start.sh` | root path: cleanup trap armed before first spawn, pre-spawn port check, per-service readiness phase, honest banner | `tests/cli/root_start_driver.sh` (T13-T16) | WP2 commit |
| WP2-3 | `arailctl` | daemon-mode `start` readiness gate (poll + identity check instead of print-and-exit-0) | `tests/cli/root_start_driver.sh` (T17) | WP2 commit |
| WP2-4 | `tests/cli/stub_uvicorn_serving.py`, `root_start_driver.sh` (new); `tests/cli/lib.sh` (additions) | the real-binding stub server + its driver | self | WP2 commit |

Ordering matched the architecture's recommended sequence (WP1 → WP2).

## Execution

### WP1 — Foundations

Built as planned, with these deltas:

- **Found and fixed a latent bug while wiring `${BOLD}`/`${RESET}` into
  `arailctl`'s `usage()` heredoc**: color variables were `"\033[1m"`
  (double-quoted) — the literal 4-char sequence backslash/0/3/3, not an
  escape byte. That only renders as color through `echo -e`/`printf`'s own
  escape reinterpretation; a plain `cat <<EOF` heredoc (no escape
  processing at all) just prints the literal characters. Not a new bug my
  edit introduced in isolation — `setup.sh`'s `capture_tier`/
  `capture_mode` heredocs already had the identical latent bug, pre-dating
  this sprint, discovered while auditing for the same pattern. Fixed at
  the source in the same commit: every color variable is now assigned via
  `$'\033[1m'` (ANSI-C quoting, a real ESC byte at assignment time)
  instead of `"\033[1m"`, across all 7 gated files. Backward compatible
  with every existing `echo -e` call site (a raw ESC byte is not itself a
  backslash-escape sequence, so `-e` passes it through unchanged).
- **`doctor`'s findings tally spans two files by design**: `arailctl`'s
  bash wrapper owns `.venv`/import/`uvicorn`-presence/optional-binaries
  and the final exit-code merge; `src/arail/doctor.py` owns the two
  required checks only Python can evaluate (egress-guard installability,
  PKB-root writability) plus one info finding (model installed), and
  reports its own exit code (0/3) which the bash wrapper folds in. This
  matches the architecture's file list for WP1 (`arailctl` **and**
  `src/arail/doctor.py` both named).
- **`kb_usage()` dedup picked the fuller of the two drifted texts**
  (the pre-discovery variant had a `validate` line and the numbered
  discovery order; the post-discovery variant was missing both — clearly
  the stale copy). Used the complete text for both call sites, varying
  only the header line. Logged here per "Output text preserved" from
  §13's ruling, since this is a judgment call, not a byte-identical
  merge.
- **T7 scoped to what WP1 actually ships**: `verbs_driver.sh` currently
  covers `setup`'s unknown-flag row and `doctor`'s four rows (T9). It does
  **not** yet cover `restart`/`install`/`status`'s new codes, `--root`, or
  `--warm` — those verbs don't exist yet (WP3–WP7). The driver's header
  comment says so explicitly; later work packages are expected to grow
  this file, not replace it.
- **T33 tested via a mirrored snippet, not a live `setup.sh` run.**
  Running `setup.sh`'s real `main()` mutates the machine it runs on
  (installs packages, creates `.venv`, may touch `~/.local/bin`) — this
  was confirmed the hard way: an early exploratory `source scripts/setup.sh`
  piped through `head -3` was caught by a lucky `SIGPIPE` before any real
  installation/download step ran, but it made the risk concrete. Every
  actual invocation of the real `setup.sh` in this build (in the driver
  and in manual verification) is either (a) the unknown-flag path, which
  exits before `main()`'s first real step runs, or (b) a copy of the file
  in a throwaway directory. `tests/test_cli_verbs.py::TestPassphraseMasking`
  mirrors the exact masking conditional (same pattern
  `tests/test_with_coder_flag.py` already uses for `setup.sh`'s argument
  parsing, for the identical reason) rather than adding a second,
  dangerous "run the real thing" test.
- **`tests/cli/lib.sh`'s `make_fake_venv` corrupted the real project
  `.venv/bin/activate` once during development** (writing a heredoc to a
  path that was — at that point — a symlink into the real venv it was
  supposed to be overriding). Caught immediately by a `system-reminder`
  showing the real file's new content, regenerated via
  `python3.11 -m venv .venv` (no `--clear`, so site-packages were
  untouched — verified `import arail`, `pytest`, and `uvicorn` all still
  worked afterward, and the full protected test suite still passed). Fixed
  at the source: `activate`/`activate.*`/`Activate.*` are now explicitly
  excluded from the symlink loop, with a `CRITICAL` comment explaining
  why, and a working-tree diff confirmed the real `.venv/bin/activate` is
  byte-identical before and after a fresh `make_fake_venv` run.

Commit: `fa93992` — "elite-cli WP1: color gating, doctor findings tally +
--strict, setup flags, polish"

### WP2 — `scripts/lib/services.sh` + root-lab readiness gate

Built as planned, with these deltas:

- **`svc_wait_http_ready` returns `2`** (curl absent) in addition to the
  documented `0`/`1` — a small, defensive extension beyond the literal
  table text, consistent with A4's system-wide rule ("every probe must
  have a defined answer when the tool is absent"). Not exercised by any
  WP2 test (curl is assumed present, same assumption the existing
  instance path already makes); flagging here for the record, not as an
  open gap.
  Where curl absence for the root path's degrade-only services (memory/
  MLX) matters, the caller (`scripts/start.sh`) checks `command -v curl`
  itself first, matching the existing instance-path convention, so
  `services.sh`'s own functions stay simple.
- **Timing looseness in `svc_wait_listening`'s poll loop**: each tick's
  `sleep 0.1` is followed by a real `lsof` invocation (~30-50ms observed
  overhead on this machine), so a nominal "10s" (100-decisecond) cap runs
  closer to 13-15s in practice. This is the same class of looseness the
  existing instance-path curl-based polls already have (subprocess-spawn
  overhead on top of the sleep), just more pronounced here because `lsof`
  costs more to spawn than `curl`. Not treated as a bug to fix in this
  WP — the architecture specifies caps as target values, not deadlines
  with sub-second precision — but `tests/cli/root_start_driver.sh`'s T15
  timeout is sized generously to account for it (documented inline).
- **`root_start_driver.sh`'s T17 (daemon-mode readiness)** needed a stub
  `launchctl` that, on `kickstart`, spawns a real process to simulate
  "launchd already had the job loaded" — that spawned process is outside
  every process-group/PID tracking this harness or `arailctl` itself
  does (by design: in production, launchd owns it). Discovered via a
  leaked `stub_uvicorn_serving.py` process surviving the driver on the
  first run; fixed with an explicit `cli_test_kill_port_listener` cleanup
  call after the scenario, not by changing anything under test.
- **F1 exercised by both T14 (foreign services never orphaned when
  our own PIDS get cleaned up) and T16 (an unrelated foreign listener
  survives a refused start untouched)** — `services.sh` itself contains
  no `kill`/`pkill`/`pgrep` beyond `kill -0` (a liveness *check*, not a
  signal; the same idiom `scripts/lib/instances.sh:inst_alive` already
  uses) for the "early-out if pid died" contract the architecture's own
  helper table requires. T31 ("services.sh contains no kill/pkill/pgrep
  at all") is not one of WP2's assigned gates (it's listed under WP2's
  gates as F1/F29/F30/F31, not T31) — noting this distinction for
  whoever picks up the broader security pass later, since a literal
  substring-grep test would need to special-case `kill -0`.
- **`restart`'s daemon-mode branch was deliberately left untouched.**
  §8.3 describes an "identical gate" for `restart`, but the work-package
  table assigns `restart`'s redesign to WP4, which is out of scope for
  this delivery. Only `start`'s daemon branch in `arailctl` was changed.

Commit: `<to be filled after commit>` — "elite-cli WP2: scripts/lib/services.sh
+ root-lab readiness gate"

## Architect feedback required

None. No part of the architecture's WP1/WP2 spec was found to be wrong,
ambiguous in a way that blocked implementation, or in conflict with
another interface contract. The deviations above are implementation-level
judgment calls (color-quoting fix, test strategy for a system-mutating
script, minor helper-return-code extension, timing looseness) — all
documented, none requiring a design change.

## Final state

- **Commits:** 2 (`fa93992` WP1, plus WP2 — see git log for the second SHA).
- **Files changed:** WP1 — 14 files (8 modified, 6 new). WP2 — adds
  `scripts/lib/services.sh`, `tests/cli/stub_uvicorn_serving.py`,
  `tests/cli/root_start_driver.sh`, `tests/test_cli_root_start.py` (new);
  modifies `scripts/start.sh`, `arailctl`, `tests/cli/lib.sh`.
- **New test drivers:** `tests/cli/color_driver.sh` (5 scenarios),
  `tests/cli/verbs_driver.sh` (6 scenarios), `tests/cli/root_start_driver.sh`
  (6 scenarios: T13-T15, T16, T17a/b) — 17 new scenarios total, all
  green.
- **Protected baseline:** `tests/instance_start_driver.sh` (11/11),
  `tests/instance_qa_driver.sh` (10/10), `tests/shell_source_safety_driver.sh`,
  and the full pytest suite for `test_instance_*`, `test_daemon_predicate`,
  `test_reset_paths`, `test_shell_source_safety`, `test_setup_extras`,
  `test_with_coder_flag`, `test_qa_airgap_toggle_setup_happy`,
  `setup_ladder/`, `test_boot_warm`, `test_autochecks_boot` — all still
  green after both commits (260+ pytest cases, 0 regressions).
- **Pre-existing, unrelated failure found (not caused by this build):**
  `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` fail on `main` before this sprint's changes
  too (confirmed via `git stash` on `scripts/reset.sh` alone) — the
  test's `awk`-extracted `stop_services()` body calls
  `_ollama_pid_if_we_started_it`, a helper defined outside the extracted
  range, so the sandboxed driver aborts with "command not found". Not
  touched (out of WP1/WP2 scope; `reset.sh`'s only WP1 change is color
  gating). Flagging for the reviewer/QA pass.
- **Doctor/status smoke:** `./arailctl doctor` exits 0 on this checkout
  (healthy); `ARAIL_NO_BROWSER=1 ./arailctl status` exits 0.
- **No TODO comments without owner/date added.** No commented-out code.
