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

Commit: `pending` — "elite-cli WP5: unified status, schema v2, verdict codes"

## Architect feedback required

None. No part of the architecture's WP1–WP5 spec was found to be wrong in
a way that blocked implementation or conflicted with another interface
contract. WP5's two most notable resolved ambiguities — the verdict
combinator formula (no explicit formula given, only prose + T8's four
cases) and verdict.state's incomplete 3-value enum vs. §12.1's 4-code
table — were both resolved in directions the concrete numbered tests
either require or are silent-but-consistent with, documented above rather
than treated as blockers. WP4's F13/§14.1 tension (documented in the WP4
section) was resolved the same way. All other deviations across WP1-WP5
(color-quoting fix, test strategy for a system-mutating script, minor
helper-return-code extension, timing looseness, the `arailctl` bypass-list
companion edit, the `test_daemon_predicate.py` extraction-harness update,
the bash-3.2 empty-array guard, two separate instances of the subshell-
swallows-a-background-job harness bug, the `--quiet` scope judgment call,
the three protected-test exit-code updates, the missing `test_cli_restart.py`
wrapper) are documented, none requiring a design change.

## Final state (through WP5)

- **Commits:** 5 (`fa93992` WP1, `7daeb43` WP2, `98269f5` WP3, `1743a3f`
  WP4, WP5 pending — see git log).
- **Files changed (WP5):** `scripts/status.sh` rewritten (single collector
  → `arail.status/v2` document → two renderers; `pwd -P`); `arailctl`
  unchanged this WP (status is invoked via the existing `status)` case,
  unmodified); `docs/concurrent-worlds.md` updated (`--json=instances`,
  the new exit codes); `tests/cli/lib.sh` extended
  (`cli_test_spawn_stub_portal`); `tests/cli/status_driver.sh` new;
  `tests/test_cli_status.py`, `tests/test_cli_restart.py` new (the latter
  a WP4 gap, see WP5 notes); `tests/test_instance_stop_scope.py` — 3
  pre-existing assertions updated for the intentional, documented
  `status` exit-code change (§12.3), not reverted.
- **New test scenarios:** `tests/cli/status_driver.sh` — 13 scenarios
  (T8a/F20, T8b/T10, T8c, T8d/T11/F2, F2-symlink, T12, T34, T8e/F18a,
  F18b, T3/--probe-mismatch, T3/daemon-a, T3/daemon-b), all green.
- **Protected baseline:** `tests/instance_start_driver.sh` (11/11),
  `tests/instance_qa_driver.sh` (10/10), `tests/cli/root_start_driver.sh`
  (6/6), `tests/cli/color_driver.sh` (5/5), `tests/cli/verbs_driver.sh`
  (6/6), `tests/cli/restart_driver.sh` (12/12) — all still green after
  WP5.
- **Full pytest suite diffed against a `git stash` baseline** at each of
  WP3, WP4, and WP5: WP3/WP4 showed identical 88 pre-existing
  failures/errors before and after (an environment gap — several optional
  packages, e.g. `mlx`, are not installed in this `.venv`, plus one
  apparently order-dependent flake in the 3800+-test full run that
  reproduces green in isolation both before and after). WP5 initially
  showed 3 NEW failures — `tests/test_instance_stop_scope.py`'s three
  `status.sh` tests, each hardcoding the pre-WP5 `returncode == 0`
  contract the architecture explicitly retires (§12.3) — fixed by
  updating those three assertions to the correct new exit code (see WP5
  notes); the diff was re-run after the fix and is clean again (identical
  88 pre-existing failures, **zero net regressions**).
- **Pre-existing, unrelated failure found (not caused by this build):**
  `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` fail on `main` before this sprint's changes
  too (confirmed via `git stash` on `scripts/reset.sh` alone) — the
  test's `awk`-extracted `stop_services()` body calls
  `_ollama_pid_if_we_started_it`, a helper defined outside the extracted
  range, so the sandboxed driver aborts with "command not found". Not
  touched across WP1-WP5 (no `reset.sh` change in this sprint touches
  `stop_services()`'s body). Also unrelated:
  `tests/shell_source_safety_driver.sh` fails on `main` (pre-existing,
  confirmed via `git stash`) with `ModuleNotFoundError: No module named
  'tomllib'` from a `blueprint render` step invoked with the system
  `python3` (not this repo's `.venv` python3.11) — unrelated to any
  script this sprint touches (`arailctl`, `start.sh`, `reset.sh`,
  `status.sh`). Both flagged for the reviewer/QA pass.
- **Doctor/status smoke:** `./arailctl doctor` exits 0 on this checkout
  (healthy); `ARAIL_NO_BROWSER=1 ./arailctl status` (human + `--json` +
  `--json=instances`) all produce well-formed output; the human and
  `--json` runs both correctly exit `4` on this checkout (nothing
  running) — the FIRST time `status` has ever exited non-zero, by design.
- **No TODO comments without owner/date added.** No commented-out code.
