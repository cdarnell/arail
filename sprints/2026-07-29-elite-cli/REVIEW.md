# Review: Elite CLI for `arailctl`

**Date:** 2026-07-30
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `ce98e6b` (WP1–WP8: `fa93992`, `7daeb43`, `98269f5`, `1743a3f`, `0b30e7b`, `320734a`, `7689fba`, `22f817d`, + `ce98e6b`, `1627c24`)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `42e87f4`
**Spec (frozen input):** [../PROMPT-elite-cli.md](../PROMPT-elite-cli.md)
**Reviewed surface:** `git diff 42e87f4..HEAD` — 40 files, +6718/−285

> **Superseded — see [Re-review (2026-07-30)](#re-review-2026-07-30) at the
> end of this file.** The builder landed a fix pass (`13461d7`, `3d57749`,
> `08dacac`, `75b63aa`, `ca9c8aa`, `189439b`, `a362aad`). **Current verdict:
> WEAK_PASS.** Everything from here to the Re-review section is the original
> 2026-07-30 review, kept verbatim for the record — its findings are what
> the fix pass answers, and its numbering (B1–B3, m1–m10, n1–n7) is what
> the Re-review refers to.

---

## Verdict (original pass): **BLOCK**

3 BLOCK · 10 must-fix minors · 7 nits.

Every driver in the sprint is green (57 CLI scenarios + 21 protected
scenarios, all re-run by this review) and the design was followed closely
and honestly — the BUILD_LOG's deviation discipline is the best I have seen
in this repo. The block is not about what was built; it is about three
paths that **no test in the sprint exercises**, two of which I reproduced
end to end and one of which is a disclosure regression on the exact
endpoint this sprint chose *because* it was already audited.

All three BLOCKs share one root cause: where the builder documented a
deliberate coverage trim ("no dedicated `stop --root` scenario", "no
zero-argv `install` scenario", "T22 asserts the field set"), the untested
path is the one that is broken.

---

## 1. Spec adherence

### Gaps 1–10 (PROMPT-elite-cli.md)

| Gap | Landed | Note |
|---|---|---|
| 1. `install` verb + consolidation | ✅ | 5 phases, `update`/`upgrade` permanent aliases, `tier` canonical. Flagship zero-flag invocation is broken — **B1** |
| 2. Non-interactive root start | ✅ | `--root` on `start`/`stop`/`restart`; picker + refusal both teach it; F11 disambiguation present |
| 3. `restart` asymmetries | ⚠️ | `--world` scoping is correct and regression-netted (T19). `--root` scoping is **not** — **B2** |
| 4. Status double-bookkeeping | ✅ | One `root lab: not started` line; five dim rows gone; verified live |
| 5. `pgrep` → connectivity | ✅ | Probe is the verdict, `pgrep` demoted to `owner` hint, URLs gated on `listening` |
| 6. Root-lab readiness gate | ✅ | Pre-spawn port check, per-service ✓/⚠/✗, identity gate, honest banner, exit 1 on portal failure; daemon branch too |
| 7. Warm-up | ⚠️ | Rides the existing warmer, no new endpoint, no anonymous inference — but one field leaks — **B3** |
| 8. `status --json` completeness | ✅ | `arail.status/v2`; `--json=instances` byte-compatible (T12 asserts `jq .instances` equality) |
| 9. Exit-code contract | ✅ | Additive; `0/1/2` unrenumbered (protected drivers green); `3`/`4` new; documented in `docs/cli.md` |
| 10. Polish | ✅ | doctor loop, SC2024 annotation, passphrase mask, `kb_usage()` dedup, ANSI gating in 8 scripts, `status.sh` → `pwd -P` |

Nothing was silently dropped from scope. §3.2's four ruled-out items are
all still ruled out and named in the docs.

### Protected baseline

Re-run for this review, all green:

- `tests/instance_start_driver.sh` — 11/11
- `tests/instance_qa_driver.sh` — 10/10
- `tests/cli/{color,verbs,status,root_start,restart,warmup,install}_driver.sh` — 5/6/13/6/12/5/16
- `pytest tests/test_cli_*.py tests/test_warm_up.py tests/test_daemon_predicate.py tests/test_instance_isolation_audit.py` — 54 passed

The 8-stage `_instance_start` path is behavior-identical modulo the two
spec'd `--warm` additions (`export ARAIL_TIER0_BOOT_WARM=1` at stage
`[6/8]`, `_warm_report` after the banner). Stage sequencing, the claim
file, the token/checkout gate, and registry-write-after-ready are byte-for-
byte untouched. `status --json=instances` is byte-compatible with the v1
rows array (same `json.dumps(rows)` shape, same key set, T12 pins it).

`./arailctl doctor` exits `0` on this checkout with `ttyd`/`code-server`/
`jupyter` absent and no `--strict` — **A8 holds**, CI's
`blueprint-smoke.yml:206` under `set -euo pipefail` is safe. `--strict`
exits `3` as designed.

### Builder deviations — rulings

Every deviation in BUILD_LOG gets an explicit ruling:

| # | Deviation | Ruling |
|---|---|---|
| WP1 | `"\033[1m"` → `$'\033[1m'` across 7 files (latent heredoc bug) | **Accepted, and good work** — a real pre-existing bug found by auditing rather than assumed |
| WP1 | doctor tally split across `arailctl` + `doctor.py` | **Accepted** — §17 names both files |
| WP1 | `kb_usage()` took the fuller of the two drifted texts | **Accepted** — the stale copy was clearly stale; logged, not silent |
| WP1 | T7 scoped to what WP1 ships | **Accepted** — later WPs grew the file as predicted |
| WP1 | T33 via a mirrored snippet, not a real `setup.sh` run | **Partially accepted** — not running the real `setup.sh` is correct; asserting against a *hand copy* instead of an extraction is not — **m6** |
| WP1 | `make_fake_venv` near-miss fix | **Accepted and verified** — `activate|activate.*|Activate.*` are excluded from the symlink loop before the `cat >`; the write target is a real file under a real `mkdir -p`'d dir. Correct fix at the source |
| WP2 | `svc_wait_http_ready` returns `2` when curl is absent | **Accepted as a helper contract** — but the two callers that ignore the distinction are **m2** |
| WP2 | `svc_wait_listening` timing looseness (~13–15s for a "10s" cap) | **Accepted** — caps are targets, documented inline |
| WP2 | T17 stub-launchctl leak fixed with an explicit cleanup | **Accepted** — fixed in the harness, not in the code under test |
| WP2 | `restart`'s daemon branch deferred to WP4 | **Accepted** — WP4 delivered it |
| WP3 | `arailctl` bypass list gained `--root` | **Accepted** — required for §4.2's symmetric refusal; one line on an existing mechanism |
| WP3 | `test_daemon_predicate.py` gained `root_only=` | **Accepted** — extraction-pin maintenance, plus a new direct test |
| WP3 | **No dedicated `stop --root` scenario** ("judged low-value") | **REJECTED** — this is exactly the path that is broken (**B2**). `--root`'s dispatch is three lines, but those three lines route to `stop_services`, whose pre-QA-11 fallback is documented in `reset.sh:163-174` as a *known* cross-scope hazard. A new caller of a function with a documented scoping caveat is never "low-value to test" |
| WP4 | Capture-then-propagate instead of literal `exec` (F13) | **Accepted** — the reasoning is right; T21 is unambiguous and §14.1's essential contract (numerically identical code) is met. See **n2** for one side effect |
| WP4 | bash-3.2 empty-array guard on `_restart_start_argv` | **Accepted** — correct, and `${arr[@]:-}` is correctly rejected as a substitute. The "worth a grep sweep some day, not urgent" note was wrong: the identical bug was introduced three WPs later (**B1**) |
| WP4 | `CLI_TEST_LAST_FABRICATED_PID` global instead of `$( )` | **Accepted** — a false-negative in T19 would have voided the whole WP |
| WP4 | T19/T21b share one fixture; T21a swaps in stand-in scripts | **Accepted** — narrow, documented, targets `arailctl`'s own control flow |
| WP4 | No daemon-mode happy-path scenario | **Accepted with reservation** — near-copy of T17a. `restart --root`'s *foreground* happy path is also uncovered, and T35 (which would have covered it) does not exist — **m10** |
| WP5 | `inst_load_port_helpers` bug found by smoke-testing | **Accepted, and the lesson is right** |
| WP5 | 3 protected `test_instance_stop_scope.py` assertions updated 0→3 | **Accepted** — §12.3 names this exact change; stash-diffed; I re-verified the 2 `test_reset_stop_scope.py` failures are genuinely pre-existing (reproduced at `42e87f4` in a clean extraction: same 2 failures, `_ollama_pid_if_we_started_it: command not found`) |
| WP5 | `docs/cli.md` deferred to WP8 | **Accepted** — WP8 delivered it and F33 passes against the final file |
| WP5 | `--quiet` scope judgment | **Accepted** — documented, no gate contradicts it |
| WP5 | `verdict.state` gains `"error"` | **Accepted** — §12.1's code table is the executable spec; additive |
| WP5 | Verdict combinator formula | **Accepted** — satisfies T8's four cases; "not-started is neutral" only works this way |
| WP5 | `test_cli_restart.py` wrapper added late | **Accepted** |
| WP5 | *(undocumented)* `set -euo pipefail` → `set -uo pipefail` | **NOT ACCEPTED AS-IS** — a real change to a protected file's error discipline, in neither ARCHITECTURE nor BUILD_LOG — **m4** |
| WP6 | F16 beats §11.1's example string (no model id in the warm line) | **Accepted, and correct** — the enforced constraint must win over an illustrative example. But F16 was then violated by a different field — **B3** |
| WP6 | `_boot_warm_explicit()` tested by source inspection | **Accepted** — matches `test_boot_security_scan.py`'s documented precedent, and the CLI driver covers the real path |
| WP6 | `test_instance_isolation_audit.py` allow-list +4 fields | **Accepted as necessary, insufficient as executed** — the audit now admits a key with *no value constraint*, which is what let **B3** through |
| WP6 | No instance-path end-to-end `--warm` scenario | **Accepted** — `_warm_report` is one shared function, exercised end to end on the root path; the path-specific wiring is source-pinned |
| WP6 | `backend` is `str | None` | **Accepted** — honest nullability beats a lying empty string |
| WP7 | `update.sh` airgap/dry-run `return` → `return 3` | **Accepted in substance, incomplete in disclosure** — the reasoning is right (an airgap refusal reporting success is a lie), but two of the resulting behavior changes never reached CHANGELOG — **m9** |
| WP7 | `LAB_MODE`-first mode read scoped to the new argv mode only | **Accepted** — correct restraint |
| WP7 | `arail.install/v1` is verdict-only | **Accepted** — **n4** |
| WP7 | "diverged" = pull's own failure | **Accepted** — matches §6.3's phrasing |
| WP7 | T24's marker had to be prepended | **Accepted** — fixture bug, correctly diagnosed |
| WP7 | T26c asserts absence of the refusal text | **Accepted** — the precise signal for what T26c tests |
| WP7 | models-phase airgap refusal added beyond §6.3's table | **Accepted, and right** — the hard constraint outranks an incomplete table cell |
| WP7 | No real `pip install`/`ollama pull` success path | **Accepted** — matches existing harness limits |
| WP8 | `AGENTS.md` untouched | **Accepted** — condition genuinely not met, checked and logged |
| WP8 | `README`/`INSTALL` teach `tier` over `upgrade` | **Accepted** |
| — | *(undocumented)* T30, T31, T32, T35, T36 never built | **NOT ACCEPTED** — **m5**, **m10** |
| — | *(undocumented)* `shell_source_safety_driver.sh` not extended per F4 | **NOT ACCEPTED** — **m7** |

BUILD_LOG's "Architect feedback required: None" is correct for design
questions. It is not correct as a statement that nothing was omitted:
five numbered gates from §16.2 and one F-mode's detection mechanism were
dropped without a line in the log.

---

## 2. BLOCK findings

### B1 — `install` with no flags dies mid-run with a bash internal error

**File:** `scripts/install.sh:54` (`ORIGINAL_ARGV=("$@")`) and
`scripts/install.sh:297` (`exec bash … "${ORIGINAL_ARGV[@]}"`).

Under bash 3.2 (`/bin/bash` on macOS, and A2's explicit constraint),
`"${arr[@]}"` on a **zero-element** array aborts under `set -u`. A bare
`./arailctl install` — the operator's flagship invocation, the entire
reason gap 1 exists — has `ORIGINAL_ARGV` empty. The line is reached
whenever the `source` phase actually moves HEAD, i.e. the normal case.

Reproduced on a fixture repo one commit behind a local bare remote:

```
  [1/5] source      ✓ 9732521…700e97d (1 commit(s))
scripts/install.sh: line 297: ORIGINAL_ARGV[@]: unbound variable
rc=1
```

**Failure it causes:** `install` pulls new source, then exits `1` with a
raw bash error. Phases `deps`, `components`, `models`, `verify` never run.
The lab is left with new source against old dependencies — the exact
half-updated state F5's re-exec exists to prevent — and the operator is
told it was a hard failure with no phase summary and no JSON.

**Why it escaped:** every `install_driver.sh` scenario that reaches the
source phase passes `--only …` (lines 129, 152, 167, 180, 197, 209). The
one zero-argv invocation (line 289, T27d) is the *unprovisioned* case,
which exits at the preflight before the source phase.

**Fix:** the guard WP4 already got right —
`if (( ${#ORIGINAL_ARGV[@]} > 0 )); then exec … "${ORIGINAL_ARGV[@]}"; else exec … ; fi`.
`"${ORIGINAL_ARGV[@]:-}"` is **not** a substitute (WP4's own note explains
why). Add a driver scenario that invokes `install` with **zero** flags
against a behind-remote fixture.

---

### B2 — `stop --root` / `restart --root` kills a live World instance

**Files:** `scripts/reset.sh:746` (`--root)   STOP_ROOT="true"`),
`scripts/reset.sh:807` (`elif [[ "$STOP_ROOT" == "true" ]]; then stop_services`),
interacting with `scripts/reset.sh:175-201` (the pre-QA-11 port-only
fallback patterns).
**Contradicts:** ARCHITECTURE §9.2 ("the stop phase is always scoped to
exactly one target; `restart` can never again stop a sibling World"), §10
("`--root`: root services only, never instances"), and the shipped
`docs/cli.md:205` ("never touches a live World instance, even while one is
running").

World-instance portals are spawned as
`uvicorn arail.portal.app:app --host H --port P --log-level warning`
(`start.sh:795-797`) — deliberately **without** `--app-dir`. `stop_services`'s
fallback branch takes any pid matching `uvicorn.*arail\.portal\.app.*--port <root port>`
whose argv contains no `--app-dir`. So a World started on the root portal
port — `./arailctl start --world ai --port 8080`, the exact invocation
`.github/workflows/blueprint-smoke.yml:220` uses — is matched and killed by
a "root only" stop.

Reproduced with a process carrying the instance-portal argv shape on a
randomized port pinned as the fake repo's `PORTAL_PORT`:

```
world-instance-like pid=11120 argv: uvicorn arail.portal.app:app --host 127.0.0.1 --port 36202 --log-level warning
  stop:   ✓ Stopped 1 process(es).
RESULT: instance was KILLED by 'stop --root'  <-- contradicts docs/cli.md
```

**Failure it causes:** the sibling-World data-loss shape this sprint was
convened to retire, re-created on a brand-new code path. The instance's
portal dies mid-write while its memory service (different port) survives,
leaving a half-dead instance and a registry record that reads `live` until
the next pid check. `restart --root` inherits it verbatim.

**Why it escaped:** WP3 shipped no `stop --root` scenario by explicit
judgment, and T35 (the golden path, which ends `stop --root`) was never
built. `restart_driver.sh`'s T19 nets the `--world` scoping only.

**Fix:** `stop_services` must not take a fallback pid that belongs to a
live registry record. Simplest correct form: before the fallback loop,
build the set of live instance portal/memory pids from `inst_list_slugs` +
`inst_read_record` and exclude them; or suppress the fallback entirely when
`inst_any_alive` is true and warn instead. Then add the `stop --root` and
`restart --root` sibling-survival scenarios (the T19 shape, `--root`
target) plus T35 end to end.

---

### B3 — `/api/instance` leaks arbitrary exception text anonymously

**Files:** `src/arail/portal/app.py:6716`
(`_MODEL_WARM_SKIP_REASON = f"{type(e).__name__}: {e}"`) surfaced at
`src/arail/portal/app.py:3400-3404` (`warm_fields` → `"warm_skipped"`),
on both the root and instance branches.
**Contradicts:** F16 — *"Fields are booleans/ints/backend-class only; no
model id, no path, no secret."*

`GET /api/instance` is on `onboarding_gate`'s allow-list (`app.py:414-424`)
— reachable with **no passphrase set**, by anything that can reach the
port. The sprint chose this endpoint precisely because its disclosure
surface was already audited and minimal. `warm_skipped` now carries the
verbatim `repr` of whatever `_get_primary_router()` or `router.complete()`
raised. In practice that is:

- `FileNotFoundError: [Errno 2] … '/Users/<user>/…/lab/models/<model>/config.json'`
  — an absolute path (hence the OS username) **and** a model id, the two
  things F16 names.
- `ConnectionError`/`httpx.ConnectError: … https://<provider-host>/v1` for
  `openai_compat` — the configured backend endpoint, including anything
  embedded in a `MODEL_API_BASE` URL.

Reachable on any lab with `ARAIL_AUTOCHECKS=1` or with `start --warm`, and
readable by anyone who can reach the portal — which `docs/PUBLISH.md`
explicitly contemplates.

**Why it escaped:** `test_instance_isolation_audit.py:330` was widened to
admit the four keys with **no constraint on their values**. `test_warm_up.py`
checks `_MODEL_ID_LOOKING_KEYS` against *key names* and greps
`str(body.values())` for two model names in a fixture where `warm_skipped`
is `None`. `test_warm_up.py:167` (`assert "ConnectionError" in
_MODEL_WARM_SKIP_REASON`) actively **pins** the leak as intended behavior.

**Fix:** make `warm_skipped` a closed vocabulary. The three non-exception
cases already are (`"ARAIL_TIER0_BOOT_WARM=0"`, the in-process-backend
sentence). For the exception case, expose `type(e).__name__` only (or a
fixed `"warm failed — see the activity log"`) and keep the full message in
`activity_log`, which is already authenticated surface. Then strengthen
the audit test to assert `warm_skipped` is `None` or a member of the
allowed set — F16's *value* invariant, not just its key set.

---

## 3. Must-fix minors (ship-blocking only in aggregate; fix before merge)

**m1 — `scripts/start.sh:1016` — empty-`PIDS` abort in the moved cleanup trap.**
`trap cleanup INT TERM` is now armed at line 1024, before the first
`PIDS+=` (line 1061). `for pid in "${PIDS[@]}"` aborts under bash 3.2
`set -u` if a signal arrives in the ~100–300 ms window covering
`inst_load_port_helpers` (an `awk`+`eval` over `setup.sh`) and the
`_port_in_use` lsof call. Same class as B1. The file's own
`_instance_cleanup_and_exit` (`start.sh:368`) already uses
`"${_INST_PIDS[@]:-}"` — match it, or guard on `${#PIDS[@]}`.

**m2 — `arailctl:385` and `arailctl:481` — "no curl" reported as "portal is down".**
Both daemon-mode readiness gates treat `svc_wait_http_ready`'s return `2`
(curl absent) and a missing `services.sh` as "not ready" and `die` with
exit 1 + `tail lab/logs/portal.err.log`. A4/F30 is explicit: *"'tool
absent' must never be reported as 'service down'"*, and this path
previously printed the URL and exited `0`. On a minimal Linux box without
curl, `./arailctl start` under an active daemon now always fails. Branch on
rc `2` and fall back to the pre-sprint message plus a `warn`.

**m3 — `scripts/install.sh:103-105` + `:160` — `--_post-source` bypasses the entire preflight.**
`if [[ -z "$POST_SOURCE_SHA" ]]` guards *both* the provisioned check and
the F21/F22 live-lab refusal. Nothing validates the flag or marks it
internal, so `./arailctl install --_post-source x --rebuild-venv` will
`rm -rf .venv` under a running lab with no refusal — F21's named failure
mode, reachable by a documented-in-`--help`-adjacent flag. Gate it on an
env marker the exec'ing process sets (and unsets), and/or validate the sha
with `git cat-file -e`.

**m4 — `scripts/status.sh:12` — errexit silently dropped.**
`set -euo pipefail` → `set -uo pipefail` in a 782-line near-total rewrite of
a protected file. Neither ARCHITECTURE nor BUILD_LOG mentions it. The
choice is defensible (`svc_listening` returns 1/2 as *data*), but it is a
material weakening of the file's failure behavior and it must be documented
in the header next to the other landmine notes — the next maintainer will
otherwise assume errexit is still on. Prefer scoping (`set +e` around the
probe block) if practical.

**m5 — §16.2's security tests T30, T31, T32 do not exist.**
Grepping `tests/` finds nothing asserting (T30) no `secrets.env` reference
in `install.sh`/`services.sh`/`status.sh`, (T31) no `kill`/`pkill`/`pgrep`
in `services.sh`, (T32) that `install`/`status`/the readiness gate never
manage an Ollama they did not start. I verified all three invariants hold
**in fact** today by inspection — the code is correct, the gates are
absent. BUILD_LOG mentions T31 only in passing ("not one of WP2's assigned
gates") and never mentions T30 or T32. This is the 20 % security allocation
the repo `CLAUDE.md` mandates; it is currently unenforced against
regression. T31 needs the `kill -0` carve-out the builder correctly
identified.

**m6 — `tests/test_cli_verbs.py:64-70` — T33 asserts a hand copy, not `scripts/setup.sh`.**
`_PASSPHRASE_MASK_SNIPPET` is a literal re-typing of setup.sh's conditional.
Delete the mask from `setup.sh` and this test still passes. The repo has a
stronger, established pattern for exactly this file
(`test_daemon_predicate.py::_run_start_guard`'s marker extraction,
`inst_load_setup_functions`'s awk extraction). A security gate that cannot
see drift in the artifact is not a gate. Extract the real block.

**m7 — `tests/shell_source_safety_driver.sh` was not extended per F4.**
F4's detection column reads *"extended to cover `install.sh` and
`services.sh`"*. The file still covers only `setup.sh` and `blueprint.sh`
(lines 13-14) and was not touched by this sprint. Undocumented omission.
(Separately: that driver is currently red for a genuinely pre-existing
reason — the system `python3` is 3.9.6, no `tomllib`, via a `blueprint
render` step this sprint does not touch. Confirmed unrelated. But a
permanently-red driver is also why nobody noticed the gap.)

**m8 — `docs/concurrent-worlds.md:189-190` — the compat advice is wrong.**
*"scripts that assumed exit `0` unconditionally should switch to
`--json=instances` (whose *output* shape hasn't changed)"* — but
`--json=instances` also exits the verdict code. Verified live on this
checkout: `./arailctl status --json=instances` prints `[]` and exits `4`.
A script that follows this advice under `set -e` breaks exactly as before.
Say plainly that the exit code applies to every `status` form and that only
stdout is byte-compatible.

**m9 — CHANGELOG omits two shipped behavior changes on the alias paths.**
(a) `scripts/update.sh:236` — `./arailctl update --component <x>` on an
airgapped lab now exits `3` instead of `0` (the builder deliberately applied
the change to the interactive path too, and said so in BUILD_LOG). (b)
`./arailctl update` (bare) now inherits `install`'s live-lab preflight and
refuses with exit `1` while the lab is running — it never did before, and
"stop your lab to check for component updates" is a surprising regression
for a muscle-memory verb. Both belong under `### Changed`.

**m10 — §16.2's T35 (golden path) and T36 (CI check) were never built.**
No file in `tests/` references either. T35 is the 10 % happy-path
allocation *and* the end-to-end sequence
(`start --root` → `status` 0 → `restart --root` → `stop --root` → `status` 4)
that would have caught B2 and would be the only coverage `restart --root`
has. T36 I have discharged myself as reviewer (see §6). T35 should be
built with the B2 fix.

---

## 4. Nits

**n1** — `scripts/status.sh:135` defines `_status_json_lines_to_array()`, but
`:231`'s `INSTANCES_JSON` re-inlines the identical Python instead of calling
it. Two copies of a reducer written to be the one copy.

**n2** — `arailctl:591` — the F13 DOWN notice fires on *any* non-zero start
code, including `130`. `./arailctl restart --world ai` followed by a
deliberate Ctrl+C prints *"the start failed (above) — the lab is now DOWN"*.
True but misleading. Exclude `130`/`143`.

**n3** — `scripts/status.sh:750` — the Scheduler probe still uses `$BIND`
rather than `svc_probe_host "$BIND"`, so it silently never fires under
`BIND_ADDR=0.0.0.0`. F29's normalization is applied everywhere else in the
file; this line was carried forward unchanged.

**n4** — `install --json` emits no JSON on its early exits (unprovisioned →
1, lab live → 1, bad flag → 2), unlike `status --json`'s F18 doctrine.
`arail.install/v1` is also verdict-only (no `phases[]`) — a documented trim,
but the two `--json` verbs now behave differently under failure.

**n5** — `tests/cli/verbs_driver.sh:37` — F33's drift check is `grep -qF`,
so `install` matches vacuously inside `install-daemon`'s heading. The
builder checked the stronger property by hand; the test cannot. A
`^### \`?<verb>` anchor would make it real.

**n6** — `scripts/start.sh:1033` — bare `inst_load_port_helpers` under
`set -e`: with `scripts/setup.sh` absent (a copied-out fixture), the root
path aborts with no message rather than degrading. Relatedly, `services.sh`'s
`[[ -f ]]`-guarded source is illusory — a missing `services.sh` makes every
root start print `✗ Portal did not come up` and exit `1`. Either make the
dependency hard and say so, or make the degrade real.

**n7** — `scripts/start.sh:801` and `:1050` — `export ARAIL_TIER0_BOOT_WARM=1`
leaks into every subsequently spawned child (memory service, ttyd, jupyter,
code-server), not just the portal. Harmless today; the comment explains why
`export` was chosen over an inline prefix, but the blast radius should be
noted.

---

## 5. Security review (named checks, not "I looked at auth")

| Check | Result |
|---|---|
| `install.sh` git phase — can it `stash`/`reset`/`clean`/`merge`/`rebase`? | **No.** `git pull --ff-only` only (`:277`); `fetch --quiet` under `--check` (`:254`). Preconditions run in order: git repo → clean worktree (`status --porcelain`, which includes untracked) → attached HEAD → upstream exists. T25a asserts an untracked file survives a refusal |
| Dirty/detached tree | Refused, named, exit 3, HEAD unmoved (T25a–d assert `HEAD` equality) |
| F5 re-exec (mid-pull script swap) | Correct in design — `--_post-source` prevents a loop and the remaining phases run from new bytes (T24 proves it with a marker only the new file prints). Two problems: **B1** (crashes on the flagship argv) and **m3** (the marker flag disables the preflight for anyone who types it) |
| Airgapped-mode egress refusal in every network phase | **Yes** — `source` (`:230`), `deps` (`:302`), `components` (via `update.sh`, now honestly returning 3), `models`-apply (`:417`, added beyond §6.3's table — correctly). `--check`'s `git fetch` sits *after* the airgap gate. T25e asserts HEAD unmoved under airgap |
| `secrets.env` untouched across instances | **Yes** — zero references in `install.sh`, `services.sh`, `status.sh` (grep-verified). Only mention is the boundary comment at `services.sh:24`. Gate T30 absent — **m5** |
| `/api/instance` exposes no model id | **Key set: yes. Values: no** — **B3** |
| Anything anonymous triggering inference | **No.** `--warm` sets `ARAIL_TIER0_BOOT_WARM=1` on the portal's *own* process env; `/api/instance` reads module globals with zero I/O; `onboarding_gate`'s allow-list is byte-identical (T29 asserts an exact 10-tuple) |
| Passphrase masking in non-tty/redirected output | **Works** — `setup.sh:2402` masks on `ARAIL_QUIET=1` or `! -t 1`; the masked line still names `.env`/`lab.conf` (F24). CI's separate `::add-mask::` redaction is unaffected. Gate is weak — **m6** |
| Ollama ownership ("never touch one we didn't start") | **Holds.** `install.sh` only runs `ollama list`/`pull`/`create`; `status.sh` only reads the pidfile for `managed_by_lab`; `services.sh` has no process control at all; `start.sh`'s root cleanup is unchanged (`OLLAMA_PID` + pidfile only). Gate T32 absent — **m5** |
| Kill scoping in the new root readiness gate | **F1 holds** — the failure path calls `cleanup`, whose kill list is `${PIDS[@]}` (this shell's spawns only). T14 asserts no orphan; T16 asserts a foreign listener survives a refused start. `services.sh`'s only `kill` is `kill -0` (liveness check, same idiom as `inst_alive`) |
| Kill scoping in `stop --root` | **VIOLATED** — **B2** |
| New dependencies | None. No new Python or system packages |

---

## 6. Performance

- `status` default with 3 registered instances: T34 asserts < 2 s and
  passes; live run on this checkout returns promptly with 1 curl + ≤6
  `lsof`.
- `--json` never runs `du` — T34 asserts via a marker file that `du` is
  not invoked. Confirmed: `--json` output contains no `lab/pkb` size line.
- Root readiness caps: portal 60 s, memory/MLX 20 s, terminal/notebook/IDE
  10 s, with dead-pid early-out. The documented `lsof` spawn overhead makes
  the listen caps run ~30 % long; acceptable for degrade-only services,
  and the drivers size their timeouts for it.

**T36 (reviewer checklist item), discharged:** CI's
`blueprint-smoke.yml` remains green-compatible. `./arailctl doctor` exits
`0` here with `ttyd`/`code-server`/`jupyter` absent and no model pulled
(all INFO-level); `setup` runs before `doctor` so the required
`pkb_writable` check has a directory to test; `start --world ai --port 8080`
uses the untouched instance path; the final `./arailctl stop || true` takes
the bare-stop auto-resolution branch, not `--root`, so **B2 does not fire
in CI** — but it fires the moment anyone follows the new docs and types
`stop --root` on that box.

---

## 7. Test coverage assessment

Numbers: 57 new CLI-driver scenarios across 7 drivers, 7 new pytest
wrappers, 19 new Python warm-up tests, 3 protected-test assertions updated
for a documented behavior change, 1 protected allow-list widened.

Where the drivers assert, they assert honestly. I spot-checked the gates
the task named and found no weakened assertions:

- **T13–T17** — T13 checks all five ✓ lines *and* the exact banner; T14
  checks the 401 diagnostic, the absence of "All services running", exit 1,
  **and** that no fixture port is still listening after exit (a stronger
  orphan check than the specified `pgrep`); T15 checks the degraded banner
  names notebook **and** that the Notebook URL is absent; T16 checks the
  refusal text, exit 1, and that the foreign listener survives; T17a/b check
  the URL and the log hint.
- **T19–T21** — T19 asserts `b`'s registry record **and** `b`'s process
  both survive `restart --world a` (the real gap-3 net). T20a asserts the
  injected `--world solo` actually reached start.sh by its error text.
  T20c/d assert no record was removed and no pid killed under the ambiguity
  and `--all` refusals. T21a asserts start.sh was never invoked.
- **T24–T28** — T25a–e each assert HEAD unmoved; T25a also asserts the
  untracked file survived. T26b asserts `.venv` still exists after the
  refused `--rebuild-venv`. T27a asserts `components.json` unmutated.
  T28a asserts the notice is on **stderr** and stdout is valid JSON.
- **T22/F16** — asserts the four keys are present and that no
  *model-id-looking key* exists. It does **not** constrain the values of the
  keys it added. That is the gap in **B3**.

Gaps, by cause:

| Gap | Consequence |
|---|---|
| No zero-argv `install` scenario | **B1** shipped |
| No `stop --root` / `restart --root` scenario (WP3, explicit trim) | **B2** shipped |
| `warm_skipped` value never constrained | **B3** shipped |
| T30, T31, T32 never built | 20 % security allocation unenforced (**m5**) |
| T35, T36 never built | happy-path allocation unenforced; `restart --root` has zero coverage (**m10**) |
| T33 asserts a copy, not the file | passphrase mask can regress undetected (**m6**) |
| `shell_source_safety_driver.sh` not extended | F4's detection mechanism for the two new scripts is absent (**m7**) |

Pre-existing failures, independently verified (not sprint regressions):

- `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` — reproduced at `42e87f4` in a clean tree
  extraction, identical failure (`_ollama_pid_if_we_started_it: command not
  found`, an awk-extraction gap in the test's own driver).
- `tests/shell_source_safety_driver.sh` — `ModuleNotFoundError: tomllib`
  from a `blueprint render` step running under the system `python3` (3.9.6).
  `scripts/blueprint.sh` is not in this sprint's diff.
- The 88-item pytest environment-gap set — the builder diffed FAILED/ERROR
  test **IDs** (not counts) at WP5, WP6, and WP7 and reported an identical
  set. I did not re-run the full suite, but every sprint-adjacent module I
  did run (54 tests) is green, and the two reset failures above are
  confirmed pre-existing, which is the sample that matters for this diff.

---

## 8. Tech debt delta vs ARCHITECTURE §18

Predicted debt, all incurred as expected and all with a home:

- Two readiness-poll implementations (stage `[6/8]` + `svc_wait_http_ready`) ✅
- A 4th reader of the default model name (`install.sh:367`) ✅
- Two names each for the tier and refresh axes ✅ (deliberate, permanent)
- Hand-maintained `docs/cli.md` ✅ (mitigated by F33, weakly — **n5**)
- Color conditional duplicated in 8 scripts ✅ (7 named + `install.sh`)

Unanticipated debt this build added — **file these before a PASS**:

1. **`stop_services`'s pre-QA-11 fallback now has a second caller** that
   promises scoping it cannot deliver (B2). Even after the B2 fix, the
   fallback itself remains a documented cross-scope hazard with two callers
   instead of one.
2. **`status.sh` runs without errexit** (m4) — a new, undocumented error
   posture in the file that is now the liveness oracle for `install`'s
   preflight.
3. **`install.sh` has an unguarded internal flag** (`--_post-source`, m3)
   that disables two safety refusals.
4. **`install`'s preflight shells out to `status.sh`**, which calls
   `inst_prune_all` — so a read-only preflight silently mutates the
   registry. Correct-ish (it only prunes dead records) but surprising.
5. **Five numbered gates from the sprint's own test strategy are missing**
   (m5, m10) with no backlog entry.

Net: still **negative** on the substance — one wrong verdict source, two
dishonest outputs, one sibling-killing bug (for `--world`), and an
undefined exit-code surface are all genuinely retired. But the sprint ships
a *new* sibling-killing bug (`--root`), so the headline claim "restart stops
being able to kill a sibling World" is not yet true.

---

## 9. Required actions before merge

1. **Fix B1** — guard the F5 re-exec's array expansion, and add an
   `install_driver.sh` scenario that invokes `install` with **zero** flags
   against a behind-remote fixture.
2. **Fix B2** — make `stop_services` exclude pids belonging to live registry
   records (or suppress the port-only fallback while any instance is live),
   and add `stop --root` + `restart --root` sibling-survival scenarios in the
   T19 shape. Until then, `docs/cli.md:205`'s "never touches a live World
   instance" is false and must not ship.
3. **Fix B3** — reduce `warm_skipped` to a closed vocabulary (exception
   *class* at most); keep the full message in `activity_log`. Strengthen
   `test_instance_isolation_audit.py` to assert the *value* invariant, not
   just the key set, and re-point `test_warm_up.py:167` at the new contract.
4. **Fix m1, m2, m3** — the three remaining correctness/safety minors
   (empty-`PIDS` trap, curl-absence-as-down, `--_post-source` preflight
   bypass).
5. **Fix m8, m9** — the wrong `--json=instances` compat advice and the two
   missing CHANGELOG entries. Docs that mis-state a compatibility guarantee
   are worse than no docs.
6. **Build m5 and m10** — T30, T31, T32 (security) and T35 (golden path).
   T35 must include the `--root` lifecycle, which currently has no
   end-to-end coverage at all.
7. **Document m4** — the `set -e` removal in `scripts/status.sh`, in the
   file header, with the rationale.
8. **Extend m7** — `shell_source_safety_driver.sh` to cover `install.sh`
   and `services.sh`, per F4.
9. **Amend ARCHITECTURE §18** with the five unanticipated debt items in §8
   above, so they have a home before the PASS.
10. Nits n1–n7 at the builder's discretion; n2 and n5 are cheap and worth
    taking.

Re-review after 1–5 and 7–9. Items 6 and 10 can land in the same pass or as
a documented follow-up ticket, but the sprint should not ship claiming a
20 % security allocation while T30/T31/T32 do not exist.

---

# Re-review (2026-07-30)

**Fix pass:** `13461d7` (B1 + m1) · `3d57749` (B2) · `08dacac` (B3) ·
`75b63aa` (T30–T32, T35, F4/m7) · `ca9c8aa` (m2–m4, m6, m8–m9, n1–n3, n5) ·
`189439b` (fixture-introduced hang) · `a362aad` (BUILD_LOG "Review fixes")
**Re-reviewed surface:** `git diff 70bed95..HEAD` — 21 files, +1342/−64

## Verdict: **WEAK_PASS**

All 3 BLOCKs are fixed and **independently verified — including by
reverting each fix and watching its new regression scenario fail.** All 10
must-fix minors are addressed. 4 of 7 nits fixed; the 3 remaining
dispositions are accepted (below). Nothing outstanding is a correctness,
security, or data-loss defect.

Ship with 4 documented follow-ups (§R6). One of them — the ARCHITECTURE
§18 debt filing — was an explicit required action from the original pass
and is the only reason this is not a clean PASS.

---

## R1. Verification performed (not taken on trust)

**Drivers, all re-run at HEAD.** 68 CLI scenarios (was 57) + 21 protected:

| Driver | Result | Δ |
|---|---|---|
| `color_driver.sh` | 5/5 | — |
| `verbs_driver.sh` | 6/6 | F33 now anchored (n5) |
| `status_driver.sh` | 13/13 | — |
| `root_start_driver.sh` | 7/7 | **+T35 golden path** |
| `restart_driver.sh` | 14/14 | **+2 B2 sibling-survival** |
| `warmup_driver.sh` | 5/5 | — |
| `install_driver.sh` | 18/18 | **+B1 zero-argv, +m3 bypass** |
| `instance_start_driver.sh` | 11/11 | protected, unchanged |
| `instance_qa_driver.sh` | 10/10 | protected, unchanged |

**pytest.** 66 passed across 12 modules (was 54 across 10) — adds
`test_cli_security_scan.py` (T30–T32) and
`test_cli_daemon_readiness_degrade.py` (m2). Separately:
`test_reset_paths.py`, `test_instance_stop_scope.py`, `test_boot_warm.py`,
`test_autochecks_boot.py` → 39 passed. `test_reset_stop_scope.py`'s 2
failures persist with **byte-identical** text
(`_ollama_pid_if_we_started_it: command not found`; line number moved
105→142 only because the extracted `stop_services` body grew) — still the
pre-existing extraction gap, not a new regression.

**Live smokes at HEAD.** `help` 0 · `status` 4 · `status --json` valid JSON
+ 4 · `--json=instances` `[]` + 4 · `--json=bogus` 2 · `doctor` 0 ·
`doctor --strict` 3 · `install --help` 0 · `install daemon` 2 · `tier` 0 ·
zero ANSI escapes in piped `status`.

### B1 — fixed, and the net is real

`scripts/install.sh:329-336` now guards on `${#ORIGINAL_ARGV[@]}` with two
`exec` shapes (not `${arr[@]:-}`, correctly). My own pre-fix reproduction
script now runs to completion:

```
  [1/5] source      ✓ 5ce09bd…d262e42 (1 commit(s))
  [1/5] source      ✓ 5ce09bd…d262e42 (1 commit(s)) — resumed after self-update
  [2/5] deps        ✗ pip install failed — see above     ← fixture has no pyproject.toml
install: hard failure — see above.
```

The re-exec carries argv through to phase 2 and the run ends on a verdict
line, not a bash error. **Fail-pre-fix confirmed independently:** I
reverted *only* the count guard in a scratch tree and re-ran the driver —

```
FAIL: B1: bare zero-flag install crashed with a bash internal error
scripts/install.sh: line 333: ORIGINAL_ARGV[@]: unbound variable
```

**Guard-idiom sweep (as asked).** Every `"${arr[@]}"` expansion in every
sprint-touched shell file is now either count-guarded or provably
non-empty: `arailctl:564` (inside the ≥2 branch), `:610`
(`(( ${#_restart_start_argv[@]} > 0 ))`); `install.sh:133` (`read -ra` on a
non-empty string always yields ≥1 — verified), `:335` (guarded), `:387/389`
(literal 2-element); `start.sh:1023` (guarded, m1), `:1152` (`TTYD_OPTS`,
always populated); `reset.sh:212` (guarded by the new
`_stop_services_pid_is_instance_owned` count check), `:219/249/250/262/267/273/361/367/373/866`
(all inside pre-existing `(( ${#…} > … ))` guards); `update.sh:403`
(literal). No unguarded expansion remains.

### B2 — fixed, and the net is real

`scripts/reset.sh:180-215` builds `_inst_owned_pids` from live registry
records via `inst_list_slugs`/`inst_alive`/`inst_read_record` — instances.sh
stays the single source of truth — and `:234` excludes them from the
**fallback** match only. Reading it closely, the scoping is right:

- The strict patterns still require `--app-dir ${REPO_ROOT}`, which an
  instance never carries, so they cannot reach an instance regardless.
- Only *live* records are protected. A dead/reused pid is deliberately not
  excluded, which preserves QA-17's fallback for a genuinely pre-upgrade
  root-lab process — the right call, and correctly explained in-comment.
- `command -v inst_list_slugs` guards the sandboxed single-file test copies.
- The empty-array expansion is count-guarded.

**Fail-pre-fix confirmed independently:** I reverted *only* the
`&& ! _stop_services_pid_is_instance_owned "$fpid"` clause and re-ran
`restart_driver.sh` —

```
FAIL: B2(stop --root): the sibling World instance was KILLED by 'stop --root'
```

The two new scenarios use `cli_test_fabricate_live_instance_portal_like`,
a fixture whose *real* argv matches an instance portal — necessary because
`stop_services` finds candidates via a real `pgrep -f` that no `ps` stub can
influence. That is the same technique my own repro needed; the builder
reached it independently and documented why.

### B3 — fixed, verified at the **value** level

`app.py:117` introduces `_MODEL_WARM_SKIP_REASON_ON_EXCEPTION =
"warm failed — see the activity log"`; `app.py:6725` assigns it instead of
`f"{type(e).__name__}: {e}"`; the real text still reaches `activity_log`
(authenticated surface). I drove a live `TestClient` with an exception
carrying every shape F16 bans at once — a credentialed provider URL, a
`$HOME` path, and a model id:

```
warm_skipped: "warm failed — see the activity log"
backend:      "openai_compat"
  clean: provider.example.com · sk-secret · Qwen2.5 · config.json · ConnectionError · Errno · ://
```

The only `/Users` occurrence in the whole response is the pre-existing
`checkout` field — the readiness probe's own identity field, shipped and
audited since the Concurrent-Worlds sprint, out of this sprint's scope.

I also closed the loop on the sibling `backend` field, which F16 constrains
to "backend-class only": `ModelRouter.__init__` restricts `backend_name` to
`BACKEND_MAP` keys, and the only other writer,
`ModelRouter.from_backend`, is called with exactly four string literals
(`registry/binding.py:116,126,132` → `"aerollm"`, `"claude"`,
`"ollama_native"`, `"openai_compat"`). It is a genuinely closed set — no
model id can reach it.

The new `test_warm_skipped_value_is_a_closed_vocabulary`
(`test_instance_isolation_audit.py:356`) is the right shape: an AST
assertion that the except-handler's *only* assignment is the bare constant
`Name`, plus a shape check on the constant itself. That pins the invariant
against re-introduction, which the key-set audit alone never could.

---

## R2. Dropped gates — now built

- **T30/T31/T32** (`tests/test_cli_security_scan.py`, 5 tests) — static
  scans with correct carve-outs (`kill -0`) and, importantly, **positive
  controls**: `saw_the_pids_kill` and the `PIDS+=("$OLLAMA_PID")` assertion
  mean the scans cannot pass vacuously if the mechanism they audit is
  renamed away. This is the detail that separates a real gate from a
  green-forever grep.
- **T35** (`root_start_driver.sh:261-353`) — a genuine golden path:
  `start --root` → `status` 0 → `restart --root` → `status` 0 →
  `stop --root` → `status` 4, all non-tty, every code asserted. It is now
  the only end-to-end coverage `restart --root`'s foreground path has. The
  builder found and fixed a real flake while building it (port-polling
  couldn't distinguish "old server still up" from "new server ready";
  replaced with a marker wait on start.sh's own `✓ Portal` line) and
  reported the ~1-in-8 flake rate rather than burying it. Correct
  engineering.
- **T36** — I discharged it myself in §6 of the original review. **The
  builder's disposition is accepted.**

## R3. Minors — dispositions

| # | Fix | Ruling |
|---|---|---|
| m1 | `start.sh:1016-1024` count-guards `${PIDS[@]}` in the early-armed trap | **Accepted** |
| m2 | Both daemon gates branch on rc 2 / missing `services.sh` → warn + URL + exit 0; `test_cli_daemon_readiness_degrade.py` drives the **extracted real blocks** | **Accepted.** I verified the `elif [[ $? == "2" ]]` idiom empirically in bash 3.2 — `$?` after a failed `if` condition is that condition's status; returns 2 → degrade, returns 1 → `die`. Correct |
| m3 | `--_post-source` now requires the inline-only `_ARAIL_INSTALL_POST_SOURCE=1` marker **and** `git cat-file -e <sha>^{commit}`; two driver scenarios prove both halves still hit the live-lab refusal with `.venv` intact | **Accepted** — this is a footgun guard, not a security boundary (an operator can set the env var), which is exactly what m3 asked for |
| m4 | 20-line LANDMINE header on `status.sh:12` explaining the deliberate `-e` omission, and recording that the scoped `set +e`/`set -e` alternative was considered and rejected as out of fix-pass scope | **Accepted** — the ask was documentation, and this documents the road not taken too |
| m6 | `test_cli_verbs.py` now **extracts** the conditional from `scripts/setup.sh` instead of re-typing it | **Accepted.** Deleting the mask makes `src.index()` raise at import — loud, which is the point |
| m8 | `docs/concurrent-worlds.md:187-196` now states plainly that the exit code applies to `--json=instances` too | **Accepted** |
| m9 | Both alias-path behavior changes added to CHANGELOG `### Changed` | **Accepted** |
| m5 | see R2 | **Accepted** |
| m7 | `shell_source_safety_driver.sh` extended (cases #7/#8) | **Accepted with a caveat — see R6.2** |
| m10 | see R2 (T35) | **Accepted** |

## R4. Nits

Fixed: **n1** (`INSTANCES_JSON` now calls `_status_json_lines_to_array`),
**n2** (DOWN notice excludes 130/143), **n3** (scheduler probe uses
`$PROBE_HOST`), **n5** (F33 anchored to a real `###` heading with a word
boundary — `install` can no longer match vacuously inside
`install-daemon`).

Left as-is, **all three dispositions accepted:**

- **n4** (`install --json` emits nothing on early exits) — a consistency
  wart against `status --json`'s F18 doctrine, not a defect; the
  architecture never required it. Accepted.
- **n6** (bare `inst_load_port_helpers` under `set -e`; the `services.sh`
  guard being illusory) — correctly identified as a real
  hard-dependency-vs-real-degrade design decision, not a fix-if-trivial.
  Accepted **on condition it is filed** (R6.1).
- **n7** (`ARAIL_TIER0_BOOT_WARM` export scope) — harmless today,
  restructuring is a real change. Accepted.

## R5. Fix-pass regressions — none found, one self-caught

The fix pass changed shared harness code (`write_stub_uvicorn_serving` no
longer `exec`s, so the wrapper's uvicorn-shaped argv stays visible to
`pgrep -f`). That is a behavioral change to the stub every one of
T13–T17/T18a/warmup depends on. All of those scenarios still pass, and the
early-out contract is preserved: the wrapper `wait`s on the python child, so
it dies immediately after a crash-stub exits. `SO_REUSEADDR` on the stub
server is the right fix for the stop-then-rebind race T35 introduced.

The builder also introduced, caught, diagnosed, and fixed an orphaned-child
hang in its own new fixture (`189439b`) inside the same pass, and wrote it
up. That is the discipline this repo wants.

## R6. Still open (follow-ups — none ship-blocking)

**R6.1 — Required action #9 was not completed.** ARCHITECTURE.md §18 was
not amended, `sprints/BACKLOG.md` was not touched, and BUILD_LOG's fix
section contains no debt entry. Two of the five items I listed are now
moot (the `stop_services` fallback is scoped; `--_post-source` is gated),
but these still need a home, and accepting n4/n6/n7 "as-is" only means
something if they land somewhere durable:

1. `status.sh` runs without errexit (now documented in-file — file it as
   standing debt with the scoped-`set +e` option named).
2. `install`'s preflight shells out to `status.sh`, which calls
   `inst_prune_all` — a read-only preflight mutates the registry.
3. **n6** — the `services.sh`/`setup.sh` hard-dependency-vs-degrade call.
4. **n4** — `install --json`'s early-exit paths.
5. R6.3 below (B2's residual boot window).

**R6.2 — m7's new coverage never executes in the default invocation.**
Cases #7/#8 were appended *after* case #6's
`python3 render.py … || fail "blueprint render failed"`
(`shell_source_safety_driver.sh:59`), which dies on any box whose **system**
`python3` predates 3.11 — including this one (3.9.6) and anything invoking
the driver through `tests/test_shell_source_safety.py`, which does not put
the venv on `PATH`. Both the bare driver and the pytest wrapper are red
before reaching the new cases. I confirmed the new cases are correct by
running the driver with a 3.11 `python3` on `PATH`:

```
OK: shell-sourced config files (.env, lab.conf) are injection-safe, and
install.sh/services.sh callers' guarded sources never abort on a missing file (F4)
```

So the content is right and the gate is dormant. One-line remedy: move
#7/#8 above #6, or skip #6 when `tomllib` is unimportable.

**R6.3 — B2 has a narrow residual: the instance boot window.** The
exclusion set is built from *written* registry records, but
`_instance_start` spawns the portal at `[6/8]` (`start.sh:807`) and writes
the record at `[8/8]` (`start.sh:948`) — write-after-ready is a protected
invariant from the previous sprint, so this ordering is correct and must
not be changed. Consequence: a `stop --root` fired while another World is
mid-boot **on the same port** can still take it via the fallback. Much
narrower than the shipped bug (which fired always), and it requires a
same-port collision plus a concurrent boot. The cheap close, if it is worth
doing: `stop_services` already has a signal available — the claim file
(`registry.d/<slug>.claim`, written with the launcher pid at
`start.sh:658`, i.e. *before* the spawn). Refusing the fallback while any
fresh claim exists would cover the window without touching the protected
write ordering.

**R6.4 — `test_reset_stop_scope.py` is still red**, so the *unit*-level
test of `stop_services`' scoping does not exercise the new exclusion; only
the driver-level B2 scenarios do (which I confirmed fail-pre-fix, so the
coverage is real, just not at both levels). Pre-existing, unrelated to this
sprint, worth a ticket of its own since it is the natural home for a
scoping unit test.

## R7. Verdict rationale

No BLOCKs remain. Every ASK is either fixed or documented as a follow-up
with a named remedy. The three original BLOCKs were each fixed at the root
cause, each netted by a regression scenario I verified fails without the
fix, and — in B3's case — pinned by an AST assertion that constrains the
*value*, which is what the original audit was missing.

**WEAK_PASS** rather than PASS for one reason: required action #9 (file the
unanticipated debt) was not done, and it is the mechanism by which the
three accepted-as-is nits and the two residuals above stop being invisible.
File R6.1's five items and R6.2's one-line driver reorder, and this is a
clean PASS — neither needs another review cycle.
