# Build log: elite-cli — WP1 through WP8

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 42e87f4
**Started:** 2026-07-29
**Scope of this log:** WP1 ("Foundations"), WP2 (`scripts/lib/services.sh` +
root-lab readiness gate), WP3 (`--root` for start/stop), WP4 (`restart`
redesign), WP5 (unified `status` + schema v2 + verdict codes), WP6
(warm-up), WP7 (`install` verb + `update`/`upgrade` consolidation), and WP8
(docs + CHANGELOG), across three successive builder tasks (WP1-2, WP3-5,
WP6-8). `docs/cli.md` reflected only WP1's verb list through WP5 per its own
stated incremental-build policy (WP2-5 deliberately did NOT touch it — see
their notes below); WP8 is where it, and the rest of the user-facing docs,
are finalized against the complete, shipped CLI.

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
| WP6-1 | `src/arail/portal/app.py` | `_warm_primary_router` gains timing/backend/skip-reason globals + `_boot_warm_explicit()`; `_startup()`'s gate becomes `_autochecks_on or _boot_warm_explicit()`; `GET /api/instance` gains `warm`/`warm_ms`/`warm_skipped`/`backend` (both branches) | `tests/test_warm_up.py`, `tests/test_boot_warm.py`/`test_autochecks_boot.py` (must stay green) | WP6 commit |
| WP6-2 | `scripts/start.sh` | `--warm` flag; shared `_warm_report()` helper; conditional `ARAIL_TIER0_BOOT_WARM=1` export on both the instance and root portal invocations; report call after each path's own banner | `tests/cli/warmup_driver.sh` (T23) | WP6 commit |
| WP6-3 | `arailctl` | daemon-branch `--warm` hint (`start` and `restart` daemon arms) | manual + `tests/cli/warmup_driver.sh` wiring pin | WP6 commit |
| WP6-4 | `tests/test_instance_isolation_audit.py` | protected allow-list test's `allowed_instance` set gains the 4 new fields (F16-mandated, additive) | self (companion edit) | WP6 commit |
| WP6-5 | `tests/cli/warmup_driver.sh`, `tests/test_cli_warmup.py` (new) | the `--warm` regression driver + pytest wrapper | self | WP6 commit |
| WP7-1 | `scripts/install.sh` (new) | 5-phase refresh verb (source/deps/components/models/verify), preflight (provisioned + live-lab via WP5's status collector + airgap), `--check`/`--only`/`--skip`/`--models`/`--rebuild-venv`/`--allow-running`/`--force`/`--json`, F5 self-update re-exec, F32 `install daemon` hint | `tests/cli/install_driver.sh` (T24-T28, F5-F7, F21, F22, F28, F32) | WP7 commit |
| WP7-2 | `scripts/update.sh` | new `--apply --non-interactive` argv mode; airgap-mode/dry-run-mode `return` → documented exit codes (3); manifest-unreadable → 1; canonical `LAB_MODE`-first mode resolution for the new mode only | `tests/cli/install_driver.sh` | WP7 commit |
| WP7-3 | `arailctl` | dispatch: `install`, `update`→alias (stderr notice), `tier` (canonical; no-arg prints current tier, exit 0), `upgrade`→alias (stderr notice); usage/header rewrite | `tests/cli/install_driver.sh` (T28) | WP7 commit |
| WP7-4 | `tests/cli/install_driver.sh`, `tests/cli/lib.sh` (additions) (new) | local bare-remote fixture builder + the T24-T28/F-gate driver | self | WP7 commit |
| WP8-1 | `docs/cli.md` | finalized verb matrix/exit-code table against the complete, shipped CLI | `tests/cli/verbs_driver.sh` (F33) | WP8 commit |
| WP8-2 | `README.md`, `docs/INSTALL.md`, `CLAUDE.md`, `AGENTS.md` (if needed), `CHANGELOG.md` | user-facing docs + behavior-change entries (§12.3) | manual read-through | WP8 commit |

Ordering matched the architecture's recommended sequence (WP1 → WP2 → WP3 →
WP4 → WP5 → WP6 → WP7 → WP8).

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

Commit: `98269f5` — "elite-cli WP3: --root for start/stop"

### WP4 — `restart` redesign

Built as planned (§9's target-resolution table, F9/F12/F13), with these
deltas:

- **F13's exact mechanics required NOT using a literal `exec` for the start
  phase**, in tension with one clause of §14.1 ("the start is exec'd, so
  the final code is still the child's") and one reading of F13's own
  parenthetical ("the pre-`exec` notice is printed unconditionally...
  before `exec`, so it survives the exec"). The DOWN notice's own wording
  — `"...and the start failed (above)..."` — only makes grammatical sense
  if printed AFTER observing a failure (the numbered test, T21, is
  unambiguous: "whose start fails after a successful stop ⇒ the 'lab is
  now DOWN' line appears" — a conditional, not an unconditional, print).
  A literal `exec` cannot support that: once the process image is
  replaced, this script cannot run another `echo` afterward no matter
  what start.sh's own exit code turns out to be. Resolved by capturing
  start's exit code (`if bash scripts/start.sh ...; then rc=0; else
  rc=$?; fi`) instead of `exec`ing it, printing the notice only when
  `rc != 0`, then `exit "$rc"` — which still satisfies "the final code is
  still the child's" (§14.1's essential contract: numerically identical
  to what `start.sh` itself would have exited with) via propagation
  rather than a literal process-image replacement. Judged a resolvable
  internal ambiguity (one prose clause vs. one concrete, executable test)
  rather than an architect-escalation gap: no external interface,
  exit-code table entry, or behavioral contract had to change to resolve
  it, and the concrete numbered test settles it unambiguously. Documented
  here per the "implementation-level judgment call" precedent WP1/WP2/WP3
  already set, not silently.
- **Found and fixed a bash-3.2 "empty array + `set -u`" trap while wiring
  the capture-not-exec change above.** `"${_restart_start_argv[@]}"`
  aborts with `unbound variable` when the array has ZERO elements — a
  real case here, since a bare `./arailctl restart` with 0 live World
  instances legitimately has nothing to inject (T20b). This is a
  documented bash bug fixed only in 4.4+ (macOS's shipped `/bin/bash` is
  3.2 — A2). `"${arr[@]:-}"` is NOT a safe substitute: verified
  empirically that it silently turns "zero args" into "one empty-string
  arg", which start.sh's parser would then reject as an unknown flag
  (`exit 2`) — a subtly wrong behavior masquerading as a fix. Guarded
  with an explicit `(( ${#arr[@]} > 0 ))` branch instead (two call
  shapes, no default-value expansion). Caught by T20b failing, not by
  static review — flagging the general class (any new `"${arr[@]}"` on a
  possibly-empty array under this repo's `set -euo pipefail` convention)
  as worth a grep sweep some day, not urgent enough to do unprompted here.
- **Found and fixed the same "subshell swallows the background job"
  class of bug the harness already knows about, in a NEW shape.**
  `tests/cli/lib.sh`'s new `cli_test_fabricate_live_instance` originally
  returned its fabricated `sleep` pid via `printf` for the caller to
  capture as `pid=$(cli_test_fabricate_live_instance ...)` — but a
  background job started INSIDE a command-substitution subshell does not
  survive that subshell's own exit in this environment (confirmed
  empirically: the `sleep` was dead within ~0.3s, silently). This is the
  process-lifetime analogue of the lesson `root_start_driver.sh`'s
  `_new_scenario()` already documents for plain variable globals ("NOT
  called inside `$( )`"), discovered here because T19 (the gap-3
  regression net — the one test this whole WP exists to protect) would
  otherwise have reported a FALSE NEGATIVE: "b survived" only because b
  was already dead for an unrelated reason, not because `restart --world
  a` actually left it alone. Fixed by having the function set a global
  (`CLI_TEST_LAST_FABRICATED_PID`) instead of printing to stdout, so
  every call site invokes it directly (never inside `$( )`).
- **T19 and T21(b) share one fixture** (two fabricated live instances,
  neither with a real World bundle so the subsequent start fails fast and
  deterministically at stage `[2/8]`) rather than two separate ones — the
  same failed start that proves T19's "b survives" is also the trigger
  T21(b) needs for the DOWN notice, and standing up the fixture twice
  bought no additional coverage.
- **T21(a) (stop phase fails) swaps in tiny stand-in `reset.sh`/`start.sh`
  scripts for that ONE scenario only** — a deliberate, narrow exception
  to "always drive the real scripts." The real `stop_instance`/
  `stop_services` are best-effort by design (matching `stop`'s own "0 =
  it is down now" contract, §12.1) and do not have an obvious real
  failure path to construct in a black-box driver; this scenario targets
  `arailctl`'s OWN stop-then-start control flow (does it abort before
  starting when the stop's exit code is nonzero?), not `reset.sh`'s
  internal stop logic (covered elsewhere — `tests/test_reset_stop_scope.py`,
  `tests/instance_start_driver.sh`).
- **No dedicated scenario for the daemon-mode HAPPY path** (kickstart -k
  + readiness gate reaching success for `restart`). It is a near-line-for-
  line copy of already-tested logic (`root_start_driver.sh`'s T17a, same
  poll-then-identity-check shape) applied to a new call site; F9's two
  refusal scenarios exercise the actually-new, actually-risky code (the
  argv scan + refusal branches) directly. Judged a reasonable scope trim,
  not a gap — flagging the choice rather than silently skipping it.

Commit: `1743a3f` — "elite-cli WP4: restart redesign"

### WP5 — Unified `status` + schema v2 + verdict codes

Built as planned (§7's collector/document/renderer split, §7.1's root-state
priority table, §7.2's probe rules, §7.3's schema, §12's exit codes), with
these deltas:

- **Found and fixed a real bug while smoke-testing the first cut**:
  `svc_listening` (`scripts/lib/services.sh`) requires `_port_in_use`
  already loaded into the CALLING shell via `inst_load_port_helpers` —
  `services.sh`'s own header says so explicitly, and `start.sh` already
  does this before its readiness phase. The first draft of `status.sh`
  never called it, so every `svc_listening` call silently reported
  "undetectable" (bash's own `declare -F _port_in_use` failing), making
  every service render `state: "unknown"` regardless of whether it was
  actually up or down. Caught by manual smoke-testing against the real
  checkout (a genuinely running `.venv` with real `lsof` should never
  report "no lsof/ss" — output that was allowed to `warnings[]` in F30's
  intended shape but not in THIS shape), not by the driver — flagging the
  general lesson (verify a probe's OWN "why did this say unknown" path
  once, don't just trust the happy-path assertions) for whoever extends
  this file next.
- **The exit-code contract change broke 3 pre-existing, PROTECTED tests**
  (`tests/test_instance_stop_scope.py::test_status_command_under_two_seconds_with_three_instances`,
  `::test_status_renders_unreadable_row_for_corrupt_registry_record`,
  `::test_status_json_is_valid_and_includes_registered_slugs`) — each
  hardcoded `returncode == 0`, which is exactly the behavior
  ARCHITECTURE.md §12.3 names as an intentional, documented breaking
  change ("`status` now exits `3`/`4` instead of always `0`"). This is
  not a regression to revert: it is the WP's own mandate colliding with a
  test written before the mandate existed. Updated each assertion to the
  correct NEW exit code for its exact scenario (3 in all three cases —
  stale/unreadable records degrade the verdict) with an inline comment
  explaining why, leaving every other assertion in those tests (rendering,
  timing, quarantine-file behavior) untouched. Verified via a full
  `git stash`-diffed pytest run before and after this specific edit that
  no OTHER test's failure set changed.
- **`docs/cli.md` deliberately NOT touched**, even though `status`'s verb
  row and the exit-code table both describe now-superseded behavior. The
  work-package table (§17) assigns `docs/cli.md`'s next update to WP8
  ("final" polish, after every verb is done); WP3/WP4 already established
  this precedent (their touch lists don't include it either) and
  `docs/cli.md`'s own header explicitly says it "reflects the verbs and
  behavior that exist **today**... grows as later work packages land."
  `docs/concurrent-worlds.md` — the file §17 DOES name for WP5 — is
  updated instead, documenting `--json=instances` as the byte-compatible
  stable form and naming the new exit codes.
- **`--quiet`/`-q`'s exact effect is a judgment call**: the architecture
  lists it as a new flag (§5.2) but never pins its behavior in prose, and
  no numbered test gates it. Implemented as "suppress the top banner and
  the `Runtime state` (`du`) section" — the two most obviously decorative
  parts of the human view — documented here since a future WP could
  reasonably want something narrower or broader.
- **`root.state`'s "up"/"degraded" split for the OTHER root services
  (memory/mlx/terminal/notebook/ide) is computed AFTER the portal probe**,
  not folded into one pass, because "expected" for those services is
  itself conditioned on `root.state != not-started` (§7.1's per-service
  table) — a genuine ordering dependency, not a stylistic choice: portal
  must be probed and root.state derived FIRST, then the other five probes
  run, and only then can "up" be downgraded to "degraded" if any of them
  came back down. Mirrors `start.sh`'s own root-readiness phase shape
  (spawn/probe portal first, degrade-track the rest) rather than
  inventing a new pattern.
- **verdict.state gains a 4th value, `"error"`, for the registry-unreadable
  case (exit `1`)** — §7.3's prose only lists `{ok, degraded, not-running}`
  for the 3-way `verdict.state` enum, but §12.1's own exit-code table
  defines code `1` as a distinct "internal failure" condition with no
  state-string counterpart. Treated as an incomplete enum in the prose
  (the code table is more specific and was written to be executable/T8-
  testable), not a conflict requiring escalation — `"error"` is additive,
  never emitted for any of the three originally-documented cases.
- **The verdict combinator (root contribution + per-instance contributions
  → one code) is not spelled out anywhere in the architecture as a formula**
  — only as prose examples and T8's four concrete cases. Implemented as:
  registry-unreadable forces `1`; else if ANY contribution is `3`
  (degraded), that wins; else if ANY contribution is `0` (something
  healthy is up), that wins; else `4`. This is the minimal combinator that
  satisfies T8's four cases exactly (verified by test) and is the only
  one under which "not-started"'s documented neutrality ("never degrades
  the verdict") and a live instance's own health can coexist correctly.
  Documented here as a resolved ambiguity, not a gap, since no numbered
  test contradicts it and every one confirms it.
- **`tests/cli/status_driver.sh` surfaced a second copy of WP4's
  subshell-swallows-a-background-job class of bug in its OWN plumbing**:
  the first draft's `_run_status()` helper omitted the per-scenario
  `<fake>/stubbin` directory from `PATH`, so `inst_alive`'s `ps -p <pid>`
  check silently fell through to the REAL system `ps` for several
  scenarios that had carefully built a stub — making a "live + stale"
  scenario (T8c) accidentally test "stale + stale" and still pass, for
  the wrong reason. Fixed by always prepending `<fake>/stubbin` to `PATH`
  in the helper (harmless when a scenario never created one). Flagging
  the general lesson again: a driver scenario passing is not evidence it
  tested what its name says until the fixture's actual liveness is
  independently confirmed (T19 in WP4 hit the literal same shape once
  already).
- **`test_cli_restart.py` (a WP4 gap) added in this commit** —
  `restart_driver.sh` shipped in WP3/WP4 without the pytest-discoverable
  wrapper every other `tests/cli/*_driver.sh` gets (§16.1's own file
  list). Caught while writing WP5's own wrapper and fixed here rather
  than left silently missing; `restart_driver.sh` itself is unchanged.

Commit: `0b30e7b` — "elite-cli WP5: unified status, schema v2, verdict codes"

### WP6 — Warm-up

Built as planned (§11's three-piece design: Python timing/backend
recording, the additive `/api/instance` fields, the CLI `--warm` flag on
both paths), with these deltas:

- **`§11.1`'s example warm-up line names a model id ("ai-engineer via
  ollama_native"); F16 and T22 both require NO model id anywhere in
  `/api/instance` or its consumers.** These two parts of the same
  architecture section are in direct tension for that one illustrative
  string. Resolved in favor of the enforced, testable contract (F16's
  "Fields are booleans/ints/backend-class only; no model id" + T22's
  "and no model id" clause) over the prose example, which I read as
  illustrative shorthand, not a schema requirement — no field named
  `model`/`model_id`/anything resolvable to a checkpoint name exists
  anywhere in the new surface. The shipped success line reads
  `warm-up: ✓ via <backend> in <N.N>s` (backend class only, e.g.
  `ollama_native`), never a model name. Judged a resolvable textual
  inconsistency (one example string vs. two concrete, testable
  constraints elsewhere in the same ruling) rather than an
  architect-escalation gap, per the WP1-WP5 precedent for this class of
  issue (documented, not silently chosen).
- **`_boot_warm_explicit()`'s interaction with `_startup()`'s
  `asyncio.create_task` scheduling is tested at the source-inspection
  level, not by driving a live `TestClient` through the fire-and-forget
  task.** `tests/test_boot_security_scan.py` (pre-existing, this
  sprint's own protected baseline) already documents exactly this
  limitation for a sibling boot task ("We can't easily run the FastAPI
  startup hook here... we can directly assert the gate's behaviour").
  Followed the same precedent: `_boot_warm_explicit()` itself is
  unit-tested directly (every env-var shape), and a regex/AST assertion
  pins `_startup()`'s scheduling condition reads
  `_autochecks_on or _boot_warm_explicit()`. The full end-to-end
  "warm actually runs during a real boot" path is covered instead by the
  CLI-level `tests/cli/warmup_driver.sh`, which drives a REAL portal
  process (the serving stub) through `start.sh --warm` — arguably a
  stronger test of the actually-observable behavior than a TestClient
  race would have been.
- **`/api/instance`'s new fields required updating ONE pre-existing
  PROTECTED test**: `tests/test_instance_isolation_audit.py
  ::test_api_instance_and_api_instances_expose_no_field_beyond_spec`
  hardcodes the endpoint's exact allowed key set (a disclosure-surface
  audit). This is the same class of situation WP5 hit with the
  `status`-exit-code tests — the WP's own mandate (F16: "Fields are
  ...booleans/ints/backend-class only") collides with a test written
  before the mandate existed, not a regression to revert. Updated the
  allow-list to include exactly the 4 new fields, with an inline comment
  citing F16, and left every other assertion in that test file
  untouched. Verified via a full pytest run that no OTHER test's
  pass/fail status changed.
- **The instance-path end of `--warm` has no dedicated end-to-end
  scenario in `tests/cli/warmup_driver.sh`** — building one would require
  either (a) a second, hand-rolled "serving" stub that echoes back the
  instance path's runtime-generated UUID token (minted inside
  `_instance_start`, unknowable to a driver's static fixture ahead of
  time) into its `/api/instance` body, which no existing harness
  primitive supports and would duplicate real identity-check logic in a
  test double, or (b) extending `tests/cli/stub_uvicorn_serving.py` to
  read `ARAIL_INSTANCE_TOKEN`/`ARAIL_INSTANCE` from its own inherited
  environment and merge them into the served body. (b) is buildable and
  was scoped out as a deliberate trim, not an oversight: `_warm_report()`
  is ONE shared function called with a different URL by each path — its
  actual polling/reporting behavior (success/timeout/absent-fields) is
  already fully exercised end-to-end against the root path (T23a-T23d).
  What's genuinely path-specific (the conditional
  `ARAIL_TIER0_BOOT_WARM=1` export and the `_warm_report` call site) is
  pinned with source-text assertions in the same driver rather than
  silently left untested. Flagging the trim explicitly, with the
  buildable alternative named, rather than skipping it silently.
- **Warm-up's CLI line for the "not applicable" (in-process backend) case
  reads `warm-up: — not applicable for backend <name> (weights load
  in-process; the portal warms itself on boot)`, matching §11.1 verbatim**
  — the one part of that section's example text with no F16 tension
  (backend class name only).
- **`GET /api/instance`'s `backend` field is `str | None`, not `str`** as
  §11.1's schema prose literally states — on a genuinely quiet boot
  (autochecks off, no `--warm`), `_warm_primary_router()` never runs at
  all, so no backend has ever been observed; the field must be able to
  say so honestly rather than lie with an empty string or a stale value.
  Every consumer (the CLI's `_warm_report`, the new pytest assertions)
  already treats it as nullable. Same class of "the code table is more
  specific/executable than the prose" resolution WP5 documented for
  `verdict.state`'s enum — not treated as a gap.

Commit: `320734a` — "elite-cli WP6: warm-up (--warm, /api/instance fields,
timing)"

### WP7 — `install` verb + `update`/`upgrade` consolidation

Built as planned (§6's five-phase design, the preflight order in §4.3, the
alias rulings in §6.2/§6.4), with these deltas:

- **`update.sh`'s pre-existing airgap-refusal and dry-run branches used to
  `return` bare (implicit exit 0) regardless of what they actually did.**
  Neither is named in §14.3's contract (which only documents the NEW
  `--apply --non-interactive` mode's exit codes), but both are load-bearing
  for THIS WP's own hard constraint ("no egress in airgapped mode... no
  scope drift" + "`install --check` exits 3 when changes are pending",
  §5.1). Changed both to `return 3` — airgap-refused now degrades instead
  of silently reporting success, and a pending-updates dry run now signals
  it. This is the SAME class of situation §6.4 itself already documents
  ("`update --check` previously exited 0 always" — an explicitly announced
  behavior change), extended to the airgap-refusal branch by the same
  reasoning: nothing currently checks either exit code (confirmed via a
  grep sweep, same method A9 used originally), so there was nothing to
  silently break, and `install`'s own airgap doctrine is unsatisfiable
  without it. Applies to BOTH the interactive and non-interactive callers
  of `update.sh` (a deliberate, minimal, documented scope decision, not an
  accidental side effect — the alternative, gating it behind
  `--non-interactive` only, would leave `./arailctl update --check` lying
  about airgap refusals exactly as it does today).
- **`update.sh`'s pre-existing interactive-path mode read
  (`${ARAIL_MODE:-airgapped}`, missing the canonical `LAB_MODE` precedence
  every other script in this repo uses) was found while wiring the new
  `--apply --non-interactive` mode and left UNTOUCHED for that path** —
  the new mode reads mode via `${LAB_MODE:-${ARAIL_MODE:-airgapped}}`
  instead, so `install`'s own airgap doctrine (this sprint's explicit hard
  constraint) is correct without silently changing the muscle-memory
  `update --component X` path's pre-existing (if arguably already-buggy)
  behavior. Logged here per precedent (WP5's "found and fixed a real bug"
  entries) — a real latent bug, but the FIX is scoped to only the new code
  path that depends on it, not a blanket "fix" of old behavior nobody
  asked to touch.
- **`install --json`'s `arail.install/v1` document is intentionally
  minimal** — `{"schema", "check", "verdict": {"code", "state"}}`, no
  per-phase array. §5.1 names the schema but no numbered test (T24-T28,
  F5-F7/F21/F22/F28/F32) asserts its exact shape; the phase-by-phase detail
  that DOES need machine parsing already exists as the exit code + the
  stderr narration (still available to an operator running `--json`
  interactively — §14.1's "no human decoration on stdout" moves it to
  stderr, it doesn't delete it). A follow-up could add a `phases: [...]`
  array without a schema-version bump (additive), and is flagged here as a
  deliberate scope trim rather than left silently thin.
- **The five refusal reasons in F6 (not a git repo · dirty · detached ·
  no upstream · diverged) are each a SEPARATE precondition check run
  in order**, so "diverged" specifically means "every precondition passed,
  but `git pull --ff-only` itself still failed" — the one case genuinely
  indistinguishable from "some other pull failure" without deeper
  inspection, and the one case the architecture's own phrasing implies is
  detected by the pull's own failure rather than a precondition (§6.3:
  "diverged (non-ff)" reads as `pull --ff-only`'s own natural failure
  mode, unlike the other four which are all `git` state queryable before
  ever touching the remote).
- **T24's re-exec marker had to be a PREPENDED line, not an appended
  one** — an appended `echo` after the script's own `exit "$VERDICT_CODE"`
  is dead code (discovered empirically: the first version of the driver's
  fixture silently never printed the marker, output otherwise looking
  completely correct — the re-exec genuinely happened, `--_post-source`
  genuinely worked, but the test's OWN marker placement was the bug, not
  install.sh). Fixed at the fixture, not flagged as an install.sh defect.
- **T26's `--allow-running` scenario asserts the ABSENCE of the liveness-
  refusal message, not a specific exit code** — with `--only verify`, the
  fake repo's fabricated `.venv` has no real `uvicorn` installed, so
  `doctor` itself legitimately degrades (exit 3) even once the liveness
  gate is bypassed; asserting "no 'stop it first' text" is the precise,
  correct signal for what T26c is actually testing (F21/F22's own
  refusal, not verify's independent cleanliness).
- **The `models` phase's airgap refusal (only reached under `--models`)
  is NOT spelled out in §6.3's per-phase table** (only "ollama absent /
  daemon unreachable → ⚠ skipped" is listed there) — added anyway,
  because the DETECTION half (`ollama list`) is local-only and always
  safe (A5: loopback/local state, not "network"), while the APPLY half
  (`ollama pull`) is genuine egress, and the task's own hard constraint
  ("no egress in airgapped mode without the spec'd explicit override")
  applies to every install phase that can reach out, not just the three
  the table happens to spell out. Resolved in favor of the hard
  constraint (an incomplete table cell, not a deliberate carve-out for
  models specifically — every other network-touching phase in this same
  ruling gets the identical refusal).
- **No dedicated scenario for a REAL `pip install`/`ollama pull` network
  success path** — both would need real network access (or a fully
  mocked pip/ollama toolchain) this harness doesn't have elsewhere either
  (the existing `instance_start_driver.sh`/`root_start_driver.sh` never
  exercise a real `pip install` or `ollama pull` for the same reason).
  `--only <phase>` isolation is what makes T24-T28/F5-F7/F21/F22/F28/F32
  testable without one; the deps/models phases' OWN control flow (airgap
  gate, --check no-op, --models gate, error mapping) is exercised via
  those phase-selection scenarios and F7's synthetic-manifest apply
  failure — the underlying `pip install -e`/`ollama pull` COMMANDS
  themselves are the same well-established invocations `setup.sh`/
  `upgrade.sh` already run unchanged.

Commit: `7689fba` — "elite-cli WP7: install verb + update/upgrade
consolidation"

### WP8 — Docs + CHANGELOG

Built as planned (§17: `docs/cli.md` finalized, `README.md`,
`docs/INSTALL.md`, `CLAUDE.md`'s verb list, `CHANGELOG.md`'s §12.3
behavior-change entries), with these deltas:

- **`AGENTS.md` was NOT touched**, despite being a conditional WP8 item
  ("if the setup flag surface changed in WP1"). Checked explicitly:
  `AGENTS.md` is the platform-*porting* manifest (detect_platform,
  install_services, accelerator deps) and never documents `setup.sh`'s
  CLI flag surface anywhere — its one relevant reference,
  `ARAIL_NONINTERACTIVE=1` (the env-var spelling WP1's new `--yes`/`-y`
  flags are literally defined as equivalent to), is unchanged and still
  100% accurate. Judged "checked, condition not met" rather than a
  silent skip — logged here per the same discipline as every other
  deviation in this log.
- **`docs/cli.md`'s full rewrite is the load-bearing WP8 deliverable**
  (F33's own drift test target) — every verb section now reflects the
  complete, shipped CLI: the finalized exit-code table (0/1/2/3/4/
  130/143), `install`'s full phase table, `restart`'s target-resolution
  table, `status`'s flag set and root-state rendering rules, `start`'s
  `--root`/`--warm` semantics. Verified against F33's own mechanism
  (`tests/cli/verbs_driver.sh`) — every `case` arm in `arailctl`
  (including the two new ones, `install` and `tier`) resolves to a real,
  substantive section in this file, not just an incidental substring
  match (checked by hand: `install` happening to appear inside
  `install-daemon`'s heading would have passed the driver's own
  substring check vacuously, which is why F33's own text is "appears
  somewhere below," not "has its own section" — both are true here, the
  stronger property wasn't accidentally skipped).
- **`README.md`/`docs/INSTALL.md`'s existing `upgrade maximus` examples
  were changed to `tier maximus`** (the new canonical spelling) with a
  one-line note that `upgrade` still works — rather than leaving the
  user-facing quick-start teaching the alias as the primary name, which
  would read oddly next to `docs/cli.md` now calling `tier` canonical.
  `upgrade`/`update` are never removed from these docs entirely (they
  still work, forever, per §6.4) — just no longer the *taught* spelling.
- **`CHANGELOG.md`'s new section is split into `### Added` (the new
  surface: `install`, `tier`, `--root`, `--warm`, the readiness gate,
  the scoped `restart`, the unified `status`, `--strict`) and
  `### Changed` (every §12.3 behavior change, plus the two more this
  build surfaced beyond the architecture's own list: `install --check`
  exiting `3` for pending changes, and `setup`'s passphrase masking)** —
  matching this file's own established convention (e.g. the 2026-07-18
  entry's Added/Fixed split) rather than inventing a new section shape.

Commit: `22f817d` — "elite-cli WP8: docs + CHANGELOG"

## Review fixes

**Review:** [REVIEW.md](./REVIEW.md) at `70bed95` — verdict BLOCK (3 blocks,
10 must-fix minors, 7 nits, 5 dropped test gates + F4's detection mechanism
never extended to the two new scripts). This section documents the fix pass
in commit order: `13461d7` (B1), `3d57749` (B2), `08dacac` (B3), `75b63aa`
(dropped gates), `ca9c8aa` (minors m2–m4/m6/m8–m9 + nits n1–n3/n5),
`189439b` (a real bug this fix pass's own new test fixture introduced,
found and fixed before it could ship).

### B1 — `install` dies on a bare, zero-flag invocation

**Finding:** `scripts/install.sh:307`'s F5 re-exec, `exec bash
"$REPO_ROOT/scripts/install.sh" --_post-source "$old_sha"
"${ORIGINAL_ARGV[@]}"`, aborts under bash 3.2's `set -u` with
`ORIGINAL_ARGV[@]: unbound variable` whenever `ORIGINAL_ARGV` is a
genuinely zero-element array — exactly the case for the flagship, zero-flag
`./arailctl install` invocation once the source phase actually pulls a
change.

**Fix:** the guarded-length idiom WP4 already used for `_restart_start_argv`
in `arailctl` (`(( ${#arr[@]} > 0 ))`, never `${arr[@]:-}`), applied at both
call sites of the re-exec. Swept the sprint's other new/edited scripts for
the same pattern (arailctl, install.sh, reset.sh, start.sh, status.sh) and
found one more real instance: `scripts/start.sh`'s root-path `cleanup()`
trap is armed before the first `PIDS+=`, so a signal in that window hits
the identical abort (**m1**, fixed in the same commit). Every other new
`"${arr[@]}"` in the sprint's diff was either a literal non-empty array or
already count-guarded.

**Evidence:** reproduced against the pre-fix tree via a fixture one commit
behind a local bare remote:
```
  [1/5] source      ✓ 1dad235…bb8da64 (1 commit(s))
scripts/install.sh: line 297: ORIGINAL_ARGV[@]: unbound variable
rc=1
```
Post-fix, the same fixture reaches the deps phase (a real, unrelated
failure there — the fixture repo has no `pyproject.toml` — proves the
re-exec's argv survived). Added a zero-argv scenario to
`tests/cli/install_driver.sh` (18/18 green, was 16/16 pre-review).

### B2 — `stop --root` / `restart --root` kill a live World instance

**Finding:** World-instance portals are spawned by `start.sh`'s instance
path without `--app-dir` (uvicorn already defaults it to the instance's own
cwd). `reset.sh`'s pre-QA-11 `stop_services()` fallback matches any uvicorn
on the root's configured port with no `--app-dir` requirement — so a World
started on the root lab's own port (`./arailctl start --world ai --port
8080`, the exact shape `.github/workflows/blueprint-smoke.yml:220` uses)
was indistinguishable from a genuine pre-upgrade root-lab process and got
killed by a "root only" stop. Contradicted `docs/cli.md:205` and
re-created the sibling-killing shape this sprint exists to retire.

**Fix:** `instances.sh` stays the sole source of truth for what is an
instance. `stop_services()` now builds the set of LIVE registered
instances' portal/memory pids (`inst_list_slugs` + `inst_alive` +
`inst_read_record`) before the fallback loop runs, and excludes them
explicitly — the fallback still reaches a genuinely pre-upgrade root-lab
process (QA-17's own reason for existing), just never a pid instances.sh
already accounts for.

**Evidence:** reproduced against the pre-fix tree (`git stash` of just
`scripts/reset.sh`) with a real process carrying the instance-portal argv
shape, pinned to the fake repo's own randomized "root" port:
```
world-instance-like pid=14898 argv: bash …/fake-world-portal/uvicorn arail.portal.app:app --host 127.0.0.1 --port 31898 --log-level warning
  ✓ Stopping Test Lab services...
  ✓ Stopped 1 process(es).
RESULT: instance was KILLED by 'stop --root'  <-- contradicts docs/cli.md
```
Post-fix, same repro:
```
  ✓ Stopping Test Lab services...
  ✓ No running services found.
RESULT: instance SURVIVED 'stop --root' (correct)
```
Confirmed identically for `restart --root`. WP3's "no dedicated `stop
--root` scenario" trim (explicitly REJECTED by the review) is filled in:
two new sibling-survival scenarios (the T19 shape, `--root` target) in
`tests/cli/restart_driver.sh`, backed by a new fixture
(`cli_test_fabricate_live_instance_portal_like`, `tests/cli/lib.sh`) that
spawns a REAL process with an instance-portal-shaped argv — required
because `stop_services()` finds its candidates via a real `pgrep -f`,
which no stubbed `ps` can influence.

### B3 — `warm_skipped` leaks exception text on the anonymous `/api/instance`

**Finding:** `_MODEL_WARM_SKIP_REASON = f"{type(e).__name__}: {e}"`
surfaced the verbatim exception text — in practice an absolute path (hence
the OS username) for a missing model file, or the configured provider
host/URL for a connection failure — on `GET /api/instance`'s
`warm_skipped` field, reachable with no passphrase set (`onboarding_gate`'s
allow-list, A6). Violates F16 ("no model id, no path, no secret").

**Fix:** `warm_skipped`'s exception case is now the single fixed sentence
`_MODEL_WARM_SKIP_REASON_ON_EXCEPTION = "warm failed — see the activity
log"` — a closed vocabulary alongside the three cases that were already
closed. The real exception text still reaches `activity_log`
(authenticated surface), unchanged.

**Evidence:** `tests/test_instance_isolation_audit.py`'s F16 allow-list had
widened the KEY set with no VALUE constraint — the gap that let this
through. Added `test_warm_skipped_value_is_a_closed_vocabulary`, which
statically confirms the exception handler's only assignment to
`_MODEL_WARM_SKIP_REASON` is the fixed constant, never anything built from
the caught exception. Re-pointed `tests/test_warm_up.py:167` (which
actively pinned the leak — `assert "ConnectionError" in
_MODEL_WARM_SKIP_REASON`) at the new contract, simulating an exception
carrying a fake path/model-id/URL and asserting none of it survives. Both
new assertions verified to FAIL against the pre-fix code (`git stash`)
before verifying they pass against the fix.

### Dropped test gates — T30–T32, T35, T36, F4/m7

- **T30/T31/T32** (new `tests/test_cli_security_scan.py`, the 20% security
  allocation's static half): source-text scans mirroring
  `test_instance_isolation_audit.py`'s existing style. T30 — `secrets.env`
  never referenced outside a comment in install.sh/services.sh/status.sh.
  T31 — services.sh contains no `kill`/`pkill`/`pgrep` except `kill -0` (the
  carve-out BUILD_LOG's WP2 section already flagged); start.sh's root path
  signals only `${PIDS[@]}`. T32 — install.sh/status.sh never
  stop/kill ollama; start.sh's root readiness gate folds its own
  `OLLAMA_PID` into `${PIDS[@]}` rather than a separate kill path. Each
  assertion verified to fail against a deliberately-broken copy of its
  target before verifying it passes against the real file.
- **T35** (`tests/cli/root_start_driver.sh`): golden path — `start --root
  --no-browser` → `status` (0) → `restart --root` → `status` (0) → `stop
  --root` → `status` (4). The only end-to-end coverage `restart --root`'s
  foreground path has at all, and would have caught B2 on its own even
  without a fabricated sibling instance. Building a real stop/restart cycle
  against the CLI harness's serving stub surfaced two real stub bugs (not
  product bugs — test infrastructure only), fixed as part of building this
  gate: `write_stub_uvicorn_serving`'s wrapper used to `exec` into the
  python stub, dropping `--app-dir`/`--port` from the process's own argv
  (invisible to `stop_services()`'s real `pgrep -f`); now backgrounds the
  child and forwards TERM/INT instead. `stub_uvicorn_serving.py` never set
  `SO_REUSEADDR`, so an immediate re-bind of the same port (the restart
  cycle) intermittently failed with "Address already in use" — added.
  Both fixes verified against every other consumer (root_start_driver.sh,
  restart_driver.sh, warmup_driver.sh, status_driver.sh) before landing.
  T35 flaked once in early iterations from a genuine race in the test's
  OWN readiness detection (polling the port cannot distinguish "the OLD
  server is still up" from "the NEW one came up for real" — fixed by
  waiting for start.sh's own `✓ Portal` log line instead); 5 consecutive
  clean runs with no leftover process after the fix.
- **T36**: not a test to build — ARCHITECTURE.md §16.2 names it a
  "reviewer checklist item" when a live CI run isn't feasible locally, and
  REVIEW.md §6 already discharged it. No further action.
- **F4/m7** (`tests/shell_source_safety_driver.sh` extended): install.sh's
  `.env`/`instances.sh` guards and a services.sh caller's guard (start.sh's)
  are each extracted verbatim (`grep -F`) and run under `set -euo pipefail`
  with the target file absent, asserting the shell reaches the end of the
  script rather than aborting — F4's exact failure mode. The driver's
  pre-existing red status (system `python3` 3.9.6, no `tomllib`, via
  `blueprint.sh`'s render step — confirmed unrelated, both by the original
  build and by REVIEW.md) meant the two new sections had to be validated
  with a `python3.11` PATH shim standing in for that unrelated step.

### Must-fix minors

- **m2** — arailctl's two daemon-mode readiness gates (`start`, `restart`)
  treated `svc_wait_http_ready`'s rc 2 (curl absent) and a missing
  `scripts/lib/services.sh` the same as a genuinely-down portal (A4/F30
  violation). Both gates now degrade (print the URL, warn once, exit 0) on
  either "cannot verify" case, still die on a real failure. New
  `tests/test_cli_daemon_readiness_degrade.py` drives both gates' real code
  extracted verbatim from arailctl; all 4 new assertions verified to fail
  against the pre-fix arailctl.
- **m3** — `install.sh --_post-source <sha>` was trusted at face value,
  bypassing the provisioned check AND the F21/F22 live-lab refusal for
  anyone who typed the flag by hand. `_ARAIL_INSTALL_POST_SOURCE=1` (set
  only inline on the F5 exec's own command line) plus a `git cat-file -e`
  check on the sha are now both required; either failing means treat
  `--_post-source` as though it was never passed. New install_driver.sh
  scenarios (both the flag alone, and the env marker with a bogus sha)
  proved the pre-fix bypass (exit 3, degraded, .venv survives only by
  accident) and now assert the correct refusal (exit 1, "stop it first").
- **m4** — `status.sh` runs under `set -uo pipefail` without `-e`
  (undocumented). Documented as a landmine note in the file header; the
  narrower "scope set +e/-e around just the probe block" alternative was
  considered and not attempted (no numbered test pins that boundary — a
  materially larger, riskier change than this fix's scope).
- **m6** — `test_cli_verbs.py`'s T33 asserted a hand-retyped copy of
  setup.sh's passphrase-masking conditional. Extracted verbatim instead;
  verified it now fails both when the real conditional is removed
  (extraction target moved — a collection-time error, impossible to pass
  silently) and when its logic is quietly broken (masking assertion
  fails).
- **m8** — `docs/concurrent-worlds.md` claimed switching to
  `--json=instances` was a compat path for scripts that assumed exit 0.
  Verified live that `--json=instances` also exits the verdict code (`4`
  on an idle checkout). Reworded: the exit-code change applies to every
  status form; only stdout is byte-compatible for `--json=instances`.
- **m9** — two shipped behavior changes were missing from CHANGELOG:
  `update --component <x>` on an airgapped lab now exits 3 (both the new
  install-backed path and the old interactive muscle memory), and bare
  `update` now inherits install's live-lab preflight (refuses, exit 1,
  while the lab is running).

m1, m5, m7, m10 are covered above (bundled with B1, the dropped-gates
commit, and F4 respectively).

### Nits taken

n1 (status.sh's `INSTANCES_JSON` now calls the shared
`_status_json_lines_to_array` reducer instead of re-inlining an identical
copy), n2 (restart's DOWN notice excludes 130/143 — a deliberate Ctrl-C
isn't "the start failed"), n3 (the Scheduler probe uses the
loopback-normalized `$PROBE_HOST` instead of raw `$BIND`, matching F29's
normalization everywhere else in the file), n5 (verbs_driver.sh's F33
drift check anchors to a real `### ...`<verb>`...` heading instead of a
vacuous substring match — verified against both a removed heading and a
de-backtick'd one).

### Nits deliberately left as-is

n4, n6, n7 each require a real behavior change beyond "fix-if-trivial"
(new `--json` emission paths on install's early exits; a genuine
hard-dependency-or-real-degrade design decision for a missing
`scripts/setup.sh`; restructuring `ARAIL_TIER0_BOOT_WARM`'s export scope)
and none is ship-blocking on its own per REVIEW.md's own framing. Left
undone, documented here rather than silently skipped.

### A bug this fix pass's own new test infrastructure introduced (and fixed)

While building B2's `cli_test_fabricate_live_instance_portal_like` fixture
(`tests/cli/lib.sh`), its `trap 'exit 0' TERM INT` exited immediately on
SIGTERM without killing its own `sleep 300` child — orphaning it. Every
`*_driver.sh` script survives this harmlessly (each runs under
`_timeout`'s own process-group SIGKILL); the new
`tests/test_cli_restart.py` pytest wrapper does not, so
`subprocess.communicate()` blocked for the full 180s waiting for EOF on
stdout/stderr held open by the orphan — discovered via the full pytest
run's FAILED list, isolated by reproducing the exact `subprocess.run()`
call directly (`Popen` showed `returncode: 0` well before the reported
`TimeoutExpired`). Fixed to kill+wait its own child first, matching
`write_stub_uvicorn_serving`'s already-correct pattern (commit `189439b`).
Flagged here per this build's own deviation-logging discipline — an
error introduced and caught within the same fix pass, not shipped.

### Verification

- `bash -n` clean on every touched script.
- Protected baseline: `tests/instance_start_driver.sh` (11/11),
  `tests/instance_qa_driver.sh` (10/10) — unchanged.
- Every `tests/cli/*_driver.sh`: `color` (5/5), `verbs` (6/6, F33's
  stricter n5 check), `status` (13/13, n1/n3/m4 changes), `root_start`
  (7/7, +T35), `restart` (14/14, +2 B2 scenarios), `warmup` (5/5),
  `install` (18/18, +B1 zero-argv, +2 m3 scenarios).
- `./arailctl help` renders the full verb table (exit 0);
  `ARAIL_NO_BROWSER=1 ./arailctl status` exits `4` on this idle checkout
  with well-formed output.
- Full `pytest` suite (see `## Final state — review-fix pass` below for
  the exact before/after counts).

### Re-review closes (WEAK_PASS → clean PASS, REVIEW.md `b69ad71`)

The re-review verified every B1/B2/B3 fix independently (including
reverting each one and watching its regression scenario fail) and returned
**WEAK_PASS** for one remaining reason: required action #9 (file the
unanticipated debt) was still outstanding, plus one dormant test gate.
Both closed in one commit:

1. **Required action #9.** Amended `ARCHITECTURE.md` §18 with a new
   "Unanticipated (found during the review-fix pass)" table (7 rows) and
   filed 7 corresponding `sprints/BACKLOG.md` entries — the accepted-as-is
   nits n4/n6/n7, the two items from the original §8 unanticipated-debt
   list that the review-fix pass didn't already moot (`status.sh`'s `-e`
   omission, `install`'s preflight mutating the registry via
   `inst_prune_all`), and the re-review's two named residuals: B2's narrow
   same-port/mid-boot window (§R6.3 — the claim-file close is filed as a
   follow-up only, per the coordinator's explicit instruction NOT to
   implement it here; write-after-ready is a protected invariant and the
   close deserves its own review cycle) and `test_reset_stop_scope.py`'s
   pre-existing failure leaving B2 unit-untested (§R6.4).
2. **m7's dormant cases (§R6.2).** Cases #7/#8 (the F4 extension) were
   appended AFTER case #6's `python3 render.py` call
   (`shell_source_safety_driver.sh:59`), which dies on any box whose
   system `python3` predates 3.11 (no `tomllib`) — including this one
   (3.9.6). Applied the reviewer's named one-line remedy: moved #7/#8
   above #6. Verified on this exact box (3.9.6, "a perfect test bed" per
   the coordinator): a scratch copy with case #6 stripped out reaches and
   passes #5/#7/#8 cleanly (`OK: ...`); the real, unmodified file now
   correctly fails at #6 for the same pre-existing, unrelated reason as
   before — but only AFTER #7/#8 have already run and passed, proving
   they are no longer dormant. Separately confirmed the full driver
   (including #6) passes end-to-end with a `python3.11` PATH shim, same
   as the original review-fix pass's own validation method.

## Architect feedback required

None. No part of the architecture's WP1–WP8 spec was found to be wrong in
a way that blocked implementation or conflicted with another interface
contract. WP5's two most notable resolved ambiguities — the verdict
combinator formula (no explicit formula given, only prose + T8's four
cases) and verdict.state's incomplete 3-value enum vs. §12.1's 4-code
table — were both resolved in directions the concrete numbered tests
either require or are silent-but-consistent with, documented above rather
than treated as blockers. WP4's F13/§14.1 tension and WP6's F16/§11.1
example-string tension were resolved the same way — a concrete, testable
constraint (a numbered test or another ruling in the same section) always
won over an ambiguous or inconsistent piece of prose, and every such
resolution is documented at its own WP's section above, not silently
chosen. All other deviations across WP1-WP8 (color-quoting fix, test
strategy for a system-mutating script, minor helper-return-code
extension, timing looseness, the `arailctl` bypass-list companion edit,
the `test_daemon_predicate.py` extraction-harness update, the bash-3.2
empty-array guard, two separate instances of the subshell-swallows-a-
background-job harness bug, the `--quiet` scope judgment call, the
protected-test exit-code updates (WP5's three `status.sh` tests, WP6's
`/api/instance` field-allowlist test), the missing `test_cli_restart.py`
wrapper, the instance-path `--warm` end-to-end scope trim, the
`update.sh` airgap/dry-run return-code fix, the `AGENTS.md` no-op
decision) are documented at their own WP's section, none requiring a
design change.

## Final state

- **Commits:** 8 — `fa93992` WP1, `7daeb43` WP2, `98269f5` WP3, `1743a3f`
  WP4, `0b30e7b` WP5, `320734a` WP6, `7689fba` WP7, `22f817d` WP8.
- **Files changed, WP6-8** (WP1-5 are summarized in their own sections
  above): `src/arail/portal/app.py` (`_warm_primary_router` timing +
  `_boot_warm_explicit()`, `/api/instance` warm fields);
  `scripts/start.sh` (`--warm`, shared `_warm_report()`); `arailctl`
  (daemon `--warm` hints; `install`/`update`/`tier`/`upgrade` dispatch;
  usage/header rewrite); **new** `scripts/install.sh` (5-phase refresh
  verb); `scripts/update.sh` (`--apply --non-interactive` mode, two
  documented exit-code fixes); `tests/test_instance_isolation_audit.py`
  (allow-list +4 fields, F16); `tests/cli/lib.sh` (git-repo + provisioned
  fixtures); **new** `tests/cli/warmup_driver.sh`, `install_driver.sh`;
  **new** `tests/test_warm_up.py`, `test_cli_warmup.py`,
  `test_cli_install.py`; `docs/cli.md` (finalized), `README.md`,
  `docs/INSTALL.md`, `CLAUDE.md`, `CHANGELOG.md` (WP8, docs-only).
- **New test scenarios, WP6-8:** `tests/test_warm_up.py` — 19 (gating
  logic, timing/backend recording, `/api/instance` field set + no model
  id, T29 allow-list snapshot); `tests/cli/warmup_driver.sh` — 5 (T23a-d
  + the instance-path wiring pin); `tests/cli/install_driver.sh` — 16
  (T24, T25a-e, T26, T27a-d, F7, T28a-d); WP8 added none (docs-only,
  gated by the pre-existing F33 driver).
- **Protected baseline, final check:** `tests/instance_start_driver.sh`
  (11/11), `tests/instance_qa_driver.sh` (10/10),
  `tests/cli/root_start_driver.sh` (6/6), `tests/cli/color_driver.sh`
  (5/5), `tests/cli/verbs_driver.sh` (6/6, including F33 against the
  final `docs/cli.md`), `tests/cli/restart_driver.sh` (12/12),
  `tests/cli/status_driver.sh` (13/13) — all green after WP8.
- **Full pytest suite diffed against the WP5 baseline (88 pre-existing
  failures/errors) at both WP6 and WP7**: identical failure set both
  times, confirmed by a line-for-line diff of the FAILED/ERROR test IDs
  (not just the count) — **zero net regressions** across WP6-WP8 (WP8 is
  docs-only, no pytest re-run needed/expected to differ).
- **Pre-existing, unrelated failures (not caused by this build, carried
  forward from WP1-5's own findings):**
  `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` (an `awk`-extraction gap unrelated to any
  `reset.sh` change this sprint makes); `tests/shell_source_safety_driver.sh`
  (`ModuleNotFoundError: tomllib` from a `blueprint render` step using
  the system `python3`, unrelated to any script this sprint touches).
  Both flagged again here for the reviewer/QA pass.
- **Smoke tests (final, this checkout):** `./arailctl help` renders the
  full new verb table; `./arailctl install --help` and
  `ARAIL_NO_BROWSER=1 ./arailctl status` both produce well-formed,
  correctly-exiting output; `./arailctl tier`/`./arailctl upgrade`
  (bare) both print the current tier and exit `0`; `bash -n` clean on
  every touched script.
- **No TODO comments without owner/date added anywhere in WP6-8. No
  commented-out code.**

## Final state — review-fix pass

- **Commits:** 6 — `13461d7` (B1 + m1), `3d57749` (B2), `08dacac` (B3),
  `75b63aa` (dropped gates T30-T32/T35/T36/F4/m7), `ca9c8aa` (minors
  m2-m4/m6/m8-m9 + nits n1-n3/n5), `189439b` (fix for a bug this pass's
  own new test fixture introduced).
- **Findings disposition:** B1/B2/B3 fixed and evidenced (repro-then-fixed
  transcripts in the "Review fixes" section above). m1-m10 all addressed
  (m1/m5/m7/m10 bundled into their respective BLOCK/dropped-gate commits;
  m2/m3/m4/m6/m8/m9 in the minors commit). T30, T31, T32, T35 built; T36
  confirmed a reviewer-checklist item, already discharged by REVIEW.md
  itself, no test to build. F4 extended to install.sh and services.sh.
  n1/n2/n3/n5 taken; n4/n6/n7 assessed and left, each requiring a real
  behavior change beyond "fix-if-trivial," documented above rather than
  silently skipped.
- **Files changed:** 20 (`git diff 70bed95..HEAD --stat`, excluding
  SPRINT.md which this build did not touch): `arailctl`, `scripts/{install,
  reset,start,status}.sh`, `src/arail/portal/app.py`, `docs/concurrent-worlds.md`,
  `CHANGELOG.md`; **new** `tests/test_cli_security_scan.py`,
  `tests/test_cli_daemon_readiness_degrade.py`; extended
  `tests/cli/{install,restart,root_start,verbs}_driver.sh`,
  `tests/cli/lib.sh`, `tests/cli/stub_uvicorn_serving.py`,
  `tests/shell_source_safety_driver.sh`, `tests/test_cli_verbs.py`,
  `tests/test_instance_isolation_audit.py`, `tests/test_warm_up.py`.
  1014 insertions, 64 deletions.
- **New test coverage:** 1 zero-argv `install` scenario (B1); 2
  sibling-survival `--root` scenarios (B2); 2 new pytest assertions +
  1 static AST-level assertion (B3); 5 security static-scan tests (T30-T32);
  1 golden-path scenario (T35, +2 fixed test-infrastructure bugs found
  while building it); 2 F4-extension driver sections; 6 daemon-readiness-
  degrade pytest tests (m2); 2 `--_post-source` bypass-attempt scenarios
  (m3); 2 passphrase-mask extraction tests, now real (m6, was already 2,
  now actually pinned to setup.sh).
- **Protected baseline (final):** `tests/instance_start_driver.sh` (11/11),
  `tests/instance_qa_driver.sh` (10/10) — byte-identical to pre-review.
- **`tests/cli/*_driver.sh` (final):** `color` 5/5, `verbs` 6/6, `status`
  13/13, `root_start` 7/7 (was 6/6), `restart` 14/14 (was 12/12), `warmup`
  5/5, `install` 18/18 (was 16/16).
- **Full pytest suite:** run twice on the final tree — 77 failed, 3817
  passed, 4 skipped, 2 xfailed, 14 errors (91 failed+errors) both times,
  byte-identical except for exactly one line each run: `test_cli_restart.py`
  disappeared from the FAILED list after the `189439b` fix (confirmed via a
  before/after run of that one commit), and one of two known
  order-dependent, timing-sensitive tests unrelated to this build
  (`test_autochecks_boot.py::test_health_interval_zero_is_one_shot`,
  `test_runtime_profile_api.py::test_post_emits_activity_event` — a
  model-registry health-thread `join(timeout=2.0)` and an unrelated
  activity-log timing assertion, respectively) surfaced depending on
  collection-order shifts from the new test files. Both confirmed to pass
  in isolation and in a 19-file targeted rerun (110/113 passed, only the 3
  genuinely pre-existing failures below).
- **Pre-existing failures, re-confirmed via a git-worktree checkout of the
  PRE-review-fix tree (`70bed95`) running the identical targeted test
  set:** `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives`
  and `::test_port_scoped_helpers` (the same `_ollama_pid_if_we_started_it:
  command not found` awk-extraction gap, unaffected by this pass's
  `reset.sh` change — its new code is inside `stop_services()`, correctly
  outside the awk-extracted range: the nested function's closing brace is
  indented, never at column 0) and `tests/test_shell_source_safety.py`
  (the tomllib gap, unaffected by this pass's driver extension — the two
  new sections are never reached because the pre-existing failure happens
  first, in an unrelated blueprint-render step).
- **Smoke tests:** `bash -n` clean on every touched script;
  `ARAIL_NO_BROWSER=1 ./arailctl status` exits `4` on this idle checkout
  with well-formed output; `./arailctl help` exits `0` and renders the full
  verb table; `./arailctl install --help` exits `0`.
- **No leftover processes** after any driver run (verified via `ps aux`
  after every `*_driver.sh` invocation in this pass, including the T35/B2
  scenarios that spawn real background processes).
- **No TODO comments without owner/date added anywhere in this pass. No
  commented-out code.**
