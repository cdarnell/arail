# Build log: elite-cli — WP1 through WP5

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 42e87f4
**Started:** 2026-07-29
**Scope of this log:** WP1 ("Foundations"), WP2 (`scripts/lib/services.sh` +
root-lab readiness gate), WP3 (`--root` for start/stop), WP4 (`restart`
redesign), and WP5 (unified `status` + schema v2 + verdict codes), per two
successive builder tasks. WP6–WP8 (warm-up, `install`/`update`/`upgrade`
consolidation, final docs polish) are not started; `docs/cli.md` still
reflects only what's shipped so far (WP1's verb list + the parts of the
exit-code contract that exist today), per its own stated incremental-build
policy — this log's later WPs deliberately did NOT touch it (see WP3/WP4/WP5
notes below for why), leaving that file's next update to WP8 as planned.

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
| WP3-1 | `scripts/start.sh` | `--root` flag (`ROOT_ONLY`), mutual exclusion with `--world`, daemon-guard refusal, picker/refusal text gains `--root` + F11 disambiguation | `tests/cli/restart_driver.sh` (T18, F11) | WP3 commit |
| WP3-2 | `scripts/reset.sh` | `--root` arm on `stop` — dispatches straight to `stop_services`, skips auto-resolution | `tests/cli/restart_driver.sh` (T18 exercises it indirectly via `start --root`'s own path; no dedicated `stop --root` scenario — see WP3 notes) | WP3 commit |
| WP3-3 | `arailctl` | `start`'s daemon-branch argv-forward bypass list gains `--root` (companion edit — see WP3 notes) | `tests/test_daemon_predicate.py::test_start_refuses_root_only_when_daemon_active` | WP3 commit |
| WP3-4 | `tests/cli/lib.sh` (additions), `tests/cli/restart_driver.sh` (new) | `cli_test_make_world`, `cli_test_fabricate_live_instance`, `cli_test_write_stub_ps_for_slugs` + the T18/F11 driver | self | WP3 commit |
| WP3-5 | `tests/test_daemon_predicate.py` | extraction harness gains `root_only=` (the guard block it pins now reads `$ROOT_ONLY`) + a direct refusal test | self | WP3 commit |
| WP4-1 | `arailctl` | `restart` rewritten: daemon-mode refusal for `--world`/`--root` (F9) + readiness gate; foreground target resolution (registry snapshot, scoped stop, injected `--world`, `--all` refusal, ≥2-live refusal), DOWN notice on post-stop start failure (F13) | `tests/cli/restart_driver.sh` (T19-T21, F9, F12, F13) | WP4 commit |
| WP4-2 | `tests/cli/restart_driver.sh` (extended) | T19-T21/F9/F12/F13 scenarios | self | WP4 commit |
| WP5-1 | `scripts/status.sh` | single collector → one `arail.status/v2` JSON document → two renderers (`--json`/`--json=full` and the human table); HTTP probes (`services.sh`) replace `pgrep` as verdict source; `pgrep` demoted to an owner hint; `--json=instances` preserves the bare v1 array; `--no-probe`/`--quiet`/`--no-sizes` flags; verdict codes 0/3/4; `pwd` → `pwd -P` | `tests/cli/status_driver.sh` (T3, T8, T10-T12, T34), F2, F18, F20 | WP5 commit |
| WP5-2 | `docs/concurrent-worlds.md` | documents `--json=instances` as the stable, byte-compatible form | manual read-through | WP5 commit |
| WP5-3 | `tests/cli/status_driver.sh` (new) | the unified status model + schema v2 + verdict-code driver | self | WP5 commit |

Ordering matched the architecture's recommended sequence (WP1 → WP2 → WP3 →
WP4 → WP5).

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

Commit: `7daeb43` — "elite-cli WP2: scripts/lib/services.sh
+ root-lab readiness gate"

### WP3 — `--root` for start / stop

Built as planned, with these deltas:

- **`arailctl`'s `start`-case argv-forward bypass list also gained `--root`**
  (`--world|--world=*|--list|-h|--help` → `...|--root`) — not in this WP's
  literal `Touches` list in §17 (which names only `scripts/start.sh` and
  `scripts/reset.sh`), but required to make `start --root` under an active
  daemon reach the SAME symmetric refusal `--world` already gets
  (§4.2: "daemon_active? yes + (`--world`|`--root`) → refuse"), rather than
  silently falling through to the existing kickstart branch and discarding
  the flag. This is a one-line addition to a bypass mechanism that already
  exists for exactly this purpose (added for `--world` in WP2), not a new
  mechanism — logged here per the same "small necessary companion edit"
  precedent WP1 set for `src/arail/doctor.py` (also not in WP1's literal
  file list, also required to satisfy the WP's own described behavior).
- **`tests/test_daemon_predicate.py` needed a matching update, not just a
  new test.** `_run_start_guard()` extracts start.sh's daemon-guard block
  verbatim and re-sources it under a controlled environment with
  `LIST_ONLY`/`WORLD_SLUG` pre-set — the guard now also reads `$ROOT_ONLY`
  under `set -u`, so the extraction aborted with "unbound variable" the
  moment `--root`'s new `elif` branch was added, failing a PROTECTED test
  (`test_start_refuses_when_daemon_active`). Fixed by adding a `root_only=`
  parameter (mirroring `world_slug=`) and a new direct test
  (`test_start_refuses_root_only_when_daemon_active`) exercising the new
  branch's exact wording. This is the same class of "extraction pins the
  literal block" maintenance the architecture already anticipated for this
  file (F4/T2's baseline) — not a design change, just keeping the pin
  current.
- **`stop --root` has no dedicated scenario in this WP's driver.** T18/F11
  are both `start`-side per the numbered test list; `reset.sh`'s `--root`
  arm is a straight-line dispatch to the already-well-tested
  `stop_services()` (unchanged itself), so its own new code is the
  three-line `case` arm plus the `elif` dispatch — both exercised
  indirectly (`stop_services` runs as part of every `full`/`env`/bare-stop
  scenario already in `tests/test_reset_paths.py`); a dedicated
  `stop --root` scenario was judged low-value relative to the T18/F11
  scenarios that exercise the actually-novel logic (`ROOT_ONLY`'s
  short-circuit, the mutual-exclusion check, the F11 disambiguation text).
  Flagging this explicitly rather than silently skipping it.
- **F11's disambiguation text is a single NOTE line**, present in both the
  non-interactive refusal and the interactive picker header — worded to
  name the exact fix (`--world root` for the World, `--root` for the root
  lab) rather than just warning something is ambiguous.
- **Reused, did not duplicate, the existing test-harness patterns**: the
  new `--root` driver reuses `tests/world_bundle_builder.py` (via a new
  `cli_test_make_world` wrapper in `tests/cli/lib.sh`, mirroring
  `tests/instance_start_driver.sh`'s own `_make_world`) for the fixture
  World bundles, and the existing `write_stub_uvicorn_serving` +
  `_fixture`-style JSON body for the root-lab identity check — no second
  World-bundle builder, no second serving stub.

Commit: `pending` — "elite-cli WP3: --root for start/stop"

## Architect feedback required

None. No part of the architecture's WP1–WP3 spec was found to be wrong,
ambiguous in a way that blocked implementation, or in conflict with
another interface contract. The deviations above are implementation-level
judgment calls (color-quoting fix, test strategy for a system-mutating
script, minor helper-return-code extension, timing looseness, the
`arailctl` bypass-list companion edit, the `test_daemon_predicate.py`
extraction-harness update) — all documented, none requiring a design
change.

## Final state (through WP3)

- **Commits:** 3 (`fa93992` WP1, `7daeb43` WP2, WP3 pending — see git log).
- **Files changed (WP3):** `arailctl`, `scripts/start.sh`, `scripts/reset.sh`,
  `tests/test_daemon_predicate.py` modified; `tests/cli/lib.sh` extended
  (`cli_test_make_world`, `cli_test_fabricate_live_instance`,
  `cli_test_write_stub_ps_for_slugs` — the last two built for WP4's reuse,
  added now since they belong in the shared library); `tests/cli/restart_driver.sh`
  new.
- **New test scenarios (WP3):** `tests/cli/restart_driver.sh` — 4 scenarios
  (T18a/b/c, F11), all green.
- **Protected baseline:** `tests/instance_start_driver.sh` (11/11),
  `tests/instance_qa_driver.sh` (10/10), `tests/cli/root_start_driver.sh`
  (6/6), `tests/cli/color_driver.sh` (5/5), `tests/cli/verbs_driver.sh`
  (6/6) — all still green.
- **Full pytest suite diffed against a `git stash` baseline** (the
  pre-WP3 tree): identical 88 pre-existing failures/errors before and
  after (an environment gap — several optional packages, e.g. `mlx`, are
  not installed in this `.venv`, plus one apparently order-dependent
  flake in the 3800+-test full run that reproduces green in isolation
  both before and after this change) — **zero net regressions**. The one
  test that DID fail immediately after the `--root` edit
  (`test_daemon_predicate.py::test_start_refuses_when_daemon_active`) was
  fixed in the same commit (see WP3 notes above) and is included in the
  "after" run's green set.
- **Pre-existing, unrelated failure found (not caused by this build):**
  `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` fail on `main` before this sprint's changes
  too (confirmed via `git stash` on `scripts/reset.sh` alone) — the
  test's `awk`-extracted `stop_services()` body calls
  `_ollama_pid_if_we_started_it`, a helper defined outside the extracted
  range, so the sandboxed driver aborts with "command not found". Not
  touched (out of scope; `reset.sh`'s changes for WP1/WP3 are color
  gating and the `--root` arm respectively, neither of which touch
  `stop_services()`'s body). Flagging for the reviewer/QA pass.
- **Doctor/status smoke:** `./arailctl doctor` exits 0 on this checkout
  (healthy); `ARAIL_NO_BROWSER=1 ./arailctl status` (human + `--json`)
  exits 0, unchanged (status.sh is WP5's target, not touched yet).
- **No TODO comments without owner/date added.** No commented-out code.
