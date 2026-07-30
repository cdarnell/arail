# Test report: Elite CLI for `arailctl`

**Date:** 2026-07-30
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `47e3dff` (WP1–WP8 + the review-fix pass + the two re-review closes)
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `42e87f4` · **Review:** [REVIEW.md](./REVIEW.md) — WEAK_PASS
**Spec (frozen input):** [../PROMPT-elite-cli.md](../PROMPT-elite-cli.md)
**Tested surface:** `git diff 42e87f4..HEAD` — 46 files, +9224/−299
**Verdict:** **WEAK_PASS**

Nine findings. None ship-blocking: no test fails, the protected baseline is
byte-identical, the full pytest failure set is unchanged, no security finding
rises above low severity, and the one performance regression sits inside the
sprint's own documented budget with 2× headroom.

Two findings are **Medium** and should get a builder fix-pass before the next
release rather than after it: **Q3** (a malformed `stop` target silently
escalates scope) and **Q4** (ARCHITECTURE's own failure mode **F3** —
half-written `lab.conf` — is specified but not implemented; it produces a raw
Python traceback and silently drops the portal row out of `status --json`'s
service list). Both are pinned by strict-xfail tests, so neither can be
quietly forgotten and both go green the moment they are fixed.

What raised my confidence: I could not falsify any of the sprint's substantive
invariants. `install`'s git phase refuses everything it promises to refuse,
**including under `--force`**; the B3 warm-up disclosure fix holds at the HTTP
level under a deliberately poisoned exception; no code path reads, copies,
links or prints another instance's `secrets.env`; and a real end-to-end boot of
the real portal on a randomized port passes its readiness gate, tells the truth
in all three `status` output modes, refuses `install` while live, and releases
the port on a scoped stop.

---

## 1. Test allocation

Repo `CLAUDE.md` sets arail's allocation at 30% setup / 30% Buddy / 20%
security / 10% happy / 10% regression. No Buddy surface is touched by this
sprint, so Buddy's share was reallocated (recorded in
[SPRINT.md](./SPRINT.md)):

| Area | Target | Achieved | What it bought |
|---|---|---|---|
| Setup & lifecycle | 45% | 45% (QA-1, QA-2, QA-3, QA-4, QA-9 + Q1–Q4, Q6, Q7) | The fresh-clone matrix, tty **and** non-tty, plus every hostile registry state |
| Security | 20% | 20% (QA-5, QA-6, QA-S1–QA-S3 — 24 tests) | Secrets, Ollama ownership, git-phase refusals, the anonymous `/api/instance` |
| Regression | 20% | 20% (full driver suite + full pytest ID diff + QA-8) | Zero drift, and the three colour-gated scripts nothing covered |
| Happy path | 15% | 15% (QA-7) | One **real** end-to-end boot — the first non-stub one in the suite |

---

## 2. Test inventory

New: **1 driver (10 scenarios) + 2 pytest modules (35 tests)**.

### Green — assertions that hold today

| # | Test | Category | Covers | Status |
|---|---|---|---|---|
| QA-1 | `tests/cli/qa_edge_driver.sh` — fresh-clone verb matrix | setup | `help`/`status`/`doctor`/`start`/`start --root`/`install`/`install --check`/`stop`/`stop --root` on a clone with no `.env`, no `lab.conf`, no `.venv`: documented exit code + named recovery command + no shell-internal error (F4/A2) | PASS |
| QA-2 | fresh-clone `--json` | setup | `status --json` is still one valid `arail.status/v2` document, `provisioned:false`, verdict 4, zero ANSI; `--json=instances` is `[]` | PASS |
| QA-3 | `setup.sh` flag surface | setup | `--yes`/`-y`/`--quiet`/`--with-coder`/`--no-coder` all parse; unknown flag → 2 naming only itself; **no provisioning runs** and no `.env` is written | PASS |
| QA-4 | hostile registry states | edge | `--json` stays parseable and exits inside `{0,1,3,4}` for a non-object record, `null`, a bare scalar, `{}`, wrong-typed fields, a truncated file, and a `chmod 000` `registry.d`; the human renderer never emits a traceback | PASS |
| QA-5 | control-char `display_name` | security | A shared World's `display_name` full of CSI/CR/LF/BEL/non-BMP bytes cannot break `--json`, cannot put a raw ESC on stdout, and cannot forge an extra instance row | PASS |
| QA-6 | `install --force` refusal matrix | security | `--force` (alone, `+--yes`, `+--models`) does **not** unlock the dirty-worktree or detached-HEAD refusals; HEAD unmoved; the local edit survives — on a repo genuinely behind its remote | PASS |
| QA-7 | **real** end-to-end root boot | happy | Real `uvicorn` + real `arail.portal.app`, randomized port ≥18000: readiness gate ✓, honest banner, URL block, `/api/instance` self-report, `status` 0 in all three modes, URL-only-when-listening, `install --check` refuses (1) against a **genuinely live root lab**, `stop --root` 0, `status` 4, port released | PASS |
| QA-8 | colour gating, 3 uncovered scripts | regression | `install.sh`, `update.sh`, `upgrade.sh` — the three of §13's eight that `color_driver.sh` never reaches — across piped / `NO_COLOR` / `ARAIL_COLOR=never` / `=always` | PASS |
| QA-9 | tty-ish paths | setup | Under a pty: `status` *does* emit ANSI (the inverse assertion a pipe-only driver cannot make), and `install`/`start`/`restart`/`doctor` never block on a prompt an unprovisioned lab cannot answer | PASS |
| QA-S1 | Ollama ownership, hardened | security | No `killall`/`pkill` in any of 7 sprint-touched scripts; no `ollama stop`/`rm`, no `brew services stop`/`systemctl stop`/`launchctl unload` naming ollama; every ollama `kill` in `reset.sh` comes from the pidfile helper — **plus 8 positive controls** proving the detector fires | PASS |
| QA-S2 | cross-instance secrets | security | No `cp`/`ln`/`mv`/`scp`/`rsync`/`tar`/`cat`/`source`/`.` in command position, and no redirection, involving any `secrets.env`, across 7 scripts; nothing prints a token or credential — **plus 7 positive controls + 1 negative control** for the one legitimate `[[ -f ]]` existence test | PASS |
| QA-S3 | `/api/instance` under induced failure | security | A poisoned exception carrying a credentialed provider URL, `$HOME` path, model id and API key at once: **no** banned substring in **any** field, on **both** the root and World branches; `warm_skipped` is the fixed sentence; `backend` ∈ the closed set; and the real text still reaches the authenticated `activity_log` | PASS |

### Red-by-design — product defects, pinned as `xfail(strict=True)`

`strict=True` is deliberate: when the builder fixes one, the test XPASSes and
the run fails, forcing the marker to be deleted rather than leaving a
permanently misleading "expected failure" behind.

| # | Test | Finding | Status |
|---|---|---|---|
| — | `test_q1_restart_does_not_claim_a_stop_that_never_happened` | Q1 | xfail |
| — | `test_q2_doctor_rejects_an_unknown_flag_with_exit_2` | Q2 | xfail |
| — | `test_q3a_stop_rejects_a_malformed_target_with_exit_2` ×2 | Q3a | xfail |
| — | `test_q3b_a_valueless_world_flag_does_not_stop_the_lone_live_world` | Q3b | xfail |
| — | `test_q4_half_written_lab_conf_degrades_honestly` | Q4 | xfail |
| — | `test_q5_hostile_display_name_cannot_emit_control_bytes` | Q5 | xfail |
| — | `test_q6_install_rejects_an_empty_phase_list` | Q6 | xfail |
| — | `test_q7_unknown_tier_is_a_usage_error` ×2 | Q7 | xfail |

Each was verified to fail **for the right reason** (`--runxfail`, assertion
text inspected one by one) — an xfail that passes because its fixture is broken
is worse than no test.

---

## 3. Findings

All are **product** bugs (builder's to fix) except Q9, which is a **test-gate**
weakness that this pass fixed itself.

| # | Finding | Severity | Kind |
|---|---|---|---|
| Q1 | `restart` announces a state change that never happened | Low | product (xfail) |
| Q2 | `doctor` maps a bad flag to `3`, not the documented `2` | Low | product (xfail) |
| Q3 | A malformed `stop` target silently escalates scope | **Medium** | product (xfail) |
| Q4 | **F3 is specified but not implemented** — half-written `lab.conf` | **Medium** | product (xfail) |
| Q5 | Control bytes from a shared World reach the terminal | Low (security) | product (xfail), pre-existing |
| Q6 | `install --only=` silently means "all five phases" | Low | product (xfail) |
| Q7 | Unknown tier exits `1`, documented `2` | Low | product (xfail) |
| Q8 | `status` is 1.6× slower than pre-sprint | Low (perf) | product (in-budget) |
| Q9 | T30/T32's scans are narrower than the invariants they name | Low | test-gate — **fixed here** |

---

### Q1 — `restart` reports the lab "DOWN" when nothing was ever up · Low

`arailctl:626` fires the F13 notice on any non-`130`/`143` start failure,
without regard for whether the stop phase actually stopped anything. On a
fresh clone — the very first thing a new user's `./arailctl restart` hits —
the CLI states, of a lab that has never run:

```
  ✓ Stopping Arail services...
  ✓ No running services found.        ← nothing was stopped
  ✓ Done.
no .venv — run ./arailctl setup

restart: the root lab was stopped, and the start failed (above) — the lab is now DOWN.
```

F13's own rationale ("the operator does not realize the state changed")
presumes a state change occurred. Same shape as REVIEW.md n2, one condition
short: n2 excluded the *interrupt* codes, this needs the *stop-did-nothing*
case too.

**Repro:** `_fresh_clone` fixture → `./arailctl restart`.
**Suggested fix:** gate the notice on the stop phase having reported a stopped
process, the way the notice's own wording already claims.

---

### Q2 — `doctor`'s bad-flag exit code contradicts the contract · Low

`arailctl:840` folds **every** non-zero from `python -m arail.doctor` into `3`
("degraded") — including argparse's own `2` for an unrecognised argument.

```
$ ./arailctl doctor --zzz-bogus-flag
python -m arail.doctor: error: unrecognized arguments: --zzz-bogus-flag
[test-lab] doctor: degraded
rc=3        ← docs/cli.md's table and ARCHITECTURE §5.2 both say 2
```

A CI script cannot tell "this lab is degraded" (act on it) from "I typo'd a
flag" (fix the script) — which is the entire point of having a `2`.

---

### Q3 — a malformed `stop` target silently escalates scope · **Medium**

`reset.sh:788`'s catch-all `*)` arm swallows an unknown flag, and `:786`'s
`STOP_WORLD="${2:-}"` turns a value-less `--world` into an empty slug. Both
then fall through to the **unscoped auto-resolution branch**, which stops the
lone live World *and* the root services, and exits `0`.

Reproduced against a fabricated live instance:

```
$ ./arailctl stop --world          # value missing
  ✓ Stopping 'ai' (the only running World instance)...
  ✓ Stopping World instance 'ai'...
  ✓   stopped 2 verified process(es).
  ✓ Stopping Test Lab services...
rc=0
>>> instance was STOPPED by a value-less --world

$ ./arailctl stop --wrold ai       # typo'd flag
>>> instance was STOPPED by a typo'd flag
```

The parser hole predates this sprint, but the sprint **enlarged its blast
radius**: `--root` is new, so `stop --rot` / `stop --rooot` is a newly reachable
way to type "stop only the root lab" and get "stop the running World as well"
— the same class REVIEW.md B2 was convened to retire, reached through the argv
parser instead of the pid fallback.

`docs/cli.md` also contradicts itself here: the canonical table assigns `2` to
"usage error — bad flag, missing flag value … every verb with flags", while
`stop`'s own section says "`0` always … `2` invalid slug". Whichever half is
meant to win, one of the two must change.

**Suggested fix:** reject unknown `-`-prefixed tokens in `reset.sh`'s parser
(exit 2), and treat a value-less `--world` as a usage error rather than an
empty slug. The scope escalation, not the exit code, is the part that matters.

---

### Q4 — F3 is specified but not implemented · **Medium**

ARCHITECTURE §15 **F3** names this exact input — *"Half-written `lab.conf`
(interrupted `setup`) ⇒ non-numeric `PORTAL_PORT`"* — and specifies the
recovery: *"New readers validate `^[0-9]+$` before use … Warn once, fall back
to the documented default, record in `warnings[]`; never abort."* None of that
happens. `status.sh:310`'s `_status_emit_service_json` calls `int()` on the raw
value:

```
$ printf 'PORTAL_PORT=not-a-number\nBIND_ADDR=127.0.0.1\n' > lab.conf
$ ./arailctl status --json
# stderr:
Traceback (most recent call last):
  File "<string>", line 11, in <module>
  File "<string>", line 7, in i
ValueError: invalid literal for int() with base 10: 'not-a-number'
# stdout (valid JSON, but):
warnings: []
services: [('memory','down'), ('mlx','skipped'), ('terminal','skipped'), ...]
             ↑ the PORTAL row is silently GONE from root.services[]
root.state: down   verdict: {'code': 4, ...}
```

Three separate contract breaks in one input: a raw traceback reaches the user
(arail's failure-mode-grace gate); `warnings[]` stays empty though §7.2 says
every undetectable condition lands there; and a **dashboard iterating
`root.services` finds no `portal` entry at all**, which schema v2's own service
list is supposed to guarantee. `LANCE_PORT=abc` reproduces it identically.

Credit where due: **F18 holds** — stdout alone stays valid JSON. Only a caller
doing the very common `status --json 2>&1 | jq` gets broken output.

**Suggested fix:** the `^[0-9]+$` validation F3 already specifies, in
`_status_emit_service_json`'s `i()` and at the `PORTAL_PORT_EFF` read, with the
fallback recorded in `warnings[]`.

---

### Q5 — control bytes from a shared World reach the terminal · Low (security)

A World bundle is **made to be shared** (world-forge / world-mount), so
`manifest.display_name` is not the operator's own text — it arrives from
whoever built the bundle and lands verbatim in the registry record.
`status.sh:680` prints it raw, **even when stdout is a pipe**:

```
$ ./arailctl status | cat -v
  M-bM-^WM-^O evil       ^[[2J^[[1;31mPWNED^M  M-bM-^WM-^O root  Autoresearch  :8080  pid 1 :29949  pid 53497
```

CSI clear-screen, a colour set, a CR that overwrites the line it is on, and a
forged row fragment — in the same output the sprint's own gap-10/F25 work made
ANSI-free for the CLI's *own* colours. Display spoofing only (no code
execution), it is **pre-existing** (`status.sh:150` at `42e87f4` is the same
line), and it needs the user to mount a hostile third-party World — hence Low.
It sits squarely inside the surface this sprint rewrote and contradicts the
honesty property the sprint claims, which is why it is filed rather than
ignored.

The `--json` renderer is already correct (`json.dumps` escapes control bytes to
``) and QA-5 pins that so it stays correct.

**Suggested fix:** sanitise control characters in the human renderer's `name`
(and `lab_name`) — one `re.sub` at the render boundary, not at ingest, so the
stored record stays faithful.

---

### Q6 — `install --only=` silently means "all five phases" · Low

`--only source` is validated against the closed phase vocabulary, but
`--only=` (empty) skips validation entirely (`install.sh:137` guards on
`-n "$ONLY_PHASES"`) and `_install_phase_enabled` reads an empty list as "no
filter" — so an operator who meant to run **one** phase runs all five,
including `deps` and `source`.

```
$ ./arailctl install --only= --check
  [1/5] source ⚠ 1 commit(s) behind origin/main
  [2/5] deps … [3/5] components … [4/5] models … [5/5] verify …
rc=3
```

---

### Q7 — unknown tier exits `1`, documented `2` · Low

`docs/cli.md:130-131` states, for `tier`: *"Exit: `0` success … `1` pip/tier
failure · `2` unknown tier"*, and ARCHITECTURE §5.1's row agrees.
`scripts/upgrade.sh:42` reaches an unknown tier through its generic `die`,
i.e. exit `1` — indistinguishable from "the pip install failed", which is
precisely the distinction the documented contract draws. Both `tier bogus` and
`upgrade bogus` are affected.

---

### Q8 — `status` is 1.6× slower than pre-sprint · Low (performance)

See [§6](#6-performance). Inside the documented budget; filed because it was
never measured and the mechanism is a one-line design drift.

---

### Q9 — T30/T32's scans are narrower than the invariants they name · Low (test-gate, fixed here)

I tried to falsify the three security gates the review-fix pass added rather
than re-verify them. The **invariants all hold**; two of the **gates** do not
cover them:

1. **T32's pattern set cannot see `killall ollama` or `ollama stop <model>`.**
   Its tuple is `pkill` / `brew services stop` / `systemctl stop` /
   `launchctl unload|stop`, plus a bare `\bkill\b` — and `\bkill\b` does **not**
   match inside `killall` (the `\b` requires a non-word char after `kill`).
   Verified against T32's own tuple:

   ```
   'killall ollama'     -> MISSED by T32
   'ollama stop llama3' -> MISSED by T32
   'pkill -f ollama'    -> detected
   'kill $OLLAMA_PID'   -> detected
   ```

   A line reading `killall ollama` could be added to `install.sh` today and
   T32 would stay green. `ollama stop` matters independently: it is a real
   subcommand that evicts a resident model a *sibling World instance* may be
   mid-inference on — the machine-shared-daemon hazard F15 already names.
2. **T30/T32 scan three files** (`install.sh`, `services.sh`, `status.sh`)
   while the sprint touched seven. `start.sh` in particular is the script that
   composes per-instance env packs — the one place a cross-instance secrets
   copy would plausibly be written.
3. **Neither gate constrains what a script may print.** "Tokens never echoed
   back, never logged" is a standing repo rule (`CLAUDE.md`) with no test.

**Fixed by this pass** in `tests/test_qa_security_hardening.py`: QA-S1 and
QA-S2 widen both scans to all seven scripts and add the missing spellings,
each with **positive controls** (16 synthetic offenders that must be flagged,
1 legitimate line that must not) so neither gate can go vacuously green — the
property that made T31/T32's own `saw_the_pids_kill` controls worth having.

Two smaller coverage gaps, also closed here rather than filed: the F21/F22
live-lab preflight had **no** coverage for a live **root** lab (T26 only
fabricates a live World record) → QA-7; and `color_driver.sh` covers five of
§13's eight colour-gated scripts, leaving `install.sh`/`update.sh`/`upgrade.sh`
unguarded → QA-8.

---

## 4. Exit-code contract conformance

Every verb run in every reachable state, non-tty, actual vs
`docs/cli.md`'s table. **17 of 20 rows conform.**

| Invocation | Documented | Actual | Verdict |
|---|---|---|---|
| `status` (nothing running) | `4` | `4` | ✅ |
| `status` (root lab up, all expected services) | `0` | `0` | ✅ |
| `status` (live instance + stale record) | `3` | `3` | ✅ |
| `status` (`chmod 000` `registry.d`) | `1` | `1` | ✅ |
| `status --bogus` | `2` | `2` | ✅ |
| `status --json=bogus` | `2` | `2` | ✅ |
| `start` / `start --root` (no `.venv`) | `1` | `1` | ✅ |
| `start --port abc` | `2` | `2` | ✅ |
| `start --root --world ai` | `2` | `2` | ✅ |
| `start --bogus` | `2` | `2` | ✅ |
| `stop` (nothing running) | `0` | `0` | ✅ |
| `stop --world 'BAD!!slug'` | `2` | `2` | ✅ |
| `restart --all` | `2` | `2` | ✅ |
| `install` (unprovisioned) | `1` | `1` | ✅ |
| `install` (lab live) | `1` | `1` | ✅ |
| `install daemon` / `install extraposarg` / `install --bogus` | `2` | `2` | ✅ |
| `install --only bogusphase` / `--only x --skip y` | `2` | `2` | ✅ |
| `doctor --bogus` | `2` | **`3`** | ❌ **Q2** |
| `stop --bogus` · `stop --world` (no value) | `2` | **`0`** | ❌ **Q3** |
| `tier bogus` · `upgrade bogus` | `2` | **`1`** | ❌ **Q7** |
| `install --only=` (empty value) | `2` | **`3`** | ❌ **Q6** |

All three failing rows are *usage-error* rows: nothing that reports success or
failure of real work is wrong. The contract's substantive half — `0`/`1`/`3`/`4`
meaning what it says across `status`, `start`, `stop`, `restart`, `install`,
`doctor` — holds everywhere I could reach it, including the two new codes.

---

## 5. Security review

Each row names what was actually checked, not the category.

| Surface | Checked | Result |
|---|---|---|
| Per-instance secrets | Every line mentioning `secrets.env` across `arailctl`, `install.sh`, `status.sh`, `start.sh`, `reset.sh`, `update.sh`, `services.sh`, for a mover verb **in command position** (`cp`/`ln`/`mv`/`scp`/`rsync`/`tar`/`cat`/`source`/`.`) or a redirection naming the file | **Clean.** The only occurrence is `start.sh:768`'s `[[ -f "$REPO_ROOT/lab/data/secrets.env" ]]` — a pure existence test that prints "provider keys are per-instance", reading nothing. Now gated (QA-S2) with 7 positive controls |
| Token/credential echoing | `echo`/`printf`/`say`/`info`/`warn`/`die` lines referencing `ARAIL_INSTANCE_TOKEN`, `instance_token`, `ARAIL_PASSWORD`, `IDE_PASSWORD`, `OPEN_NOTEBOOK_ENCRYPTION_KEY`, or any `*_API_KEY` | **Clean.** `start.sh:852`'s mismatch diagnostic names the *port*, never the token. Now gated (QA-S2) |
| `/api/instance` under induced failure | Drove the real `_warm_primary_router()` into its exception path with one message carrying a credentialed provider URL (`alice:sk-live-SECRET@…`), a `$HOME` path, a model id and `config.json` at once; asserted **every field** of the HTTP body on **both** the root and World branches | **Clean.** `warm_skipped` is the fixed sentence; `backend` ∈ `{None, aerollm, claude, ollama_native, openai_compat}`; no banned substring anywhere. Independently confirmed `ModelRouter.backend_name` is closed by `BACKEND_MAP` validation — the `be.backend_name = f"{provider_type}:openai_compat"` writers in `registry/binding.py` set the *backend* object's attribute, not the router's, so they never reach this field |
| Warm-up detail still diagnosable | That the real exception text reaches `activity_log` (authenticated surface) | **Holds** — asserted, so B3's fix cannot decay into a silent swallow |
| `install` git phase | Whether **anything** makes it do more than `pull --ff-only`: dirty worktree, detached HEAD, no upstream, diverged, and each of those **again under `--force`**, `--force --yes`, `--force --models`, on a repo genuinely behind its remote | **Clean.** Every refusal holds; HEAD never moved; an uncommitted edit to a tracked file survived every attempt. `--force` overrides the airgap refusal **only**, as §6.3 specifies |
| Phase-name injection | `--only 'source;…'`, `--only bogusphase`, `--skip` combinations | **Clean** — closed vocabulary, exit 2. The one hole is the *empty* value (Q6), which under-selects rather than injecting |
| Ollama ownership | All 7 scripts for `killall`/`pkill`, `ollama stop`/`rm`, `brew services stop|restart`, `systemctl stop|restart`, `launchctl unload|stop|kickstart` naming ollama; plus that every ollama `kill` in `reset.sh` derives its pid from `_ollama_pid_if_we_started_it` | **Clean** — but the *gate* was not (Q9). Now widened |
| ANSI / control-char injection | `LAB_NAME` (operator-owned, `.env`) and `display_name` (**third-party**, World bundle) through both `status` renderers, piped and on a pty | `--json` **safe** (control bytes escaped, no forged row). Human renderer **passes them through** — **Q5** |
| Registry as untrusted input | Non-object records, `null`, bare scalars, `{}`, wrong-typed fields, truncated JSON, `chmod 000` directory — through `status`, `status --json`, `status --json=instances`, `restart --root` | **Clean.** Always one valid document, always an in-contract exit code, never a traceback, never a crash. `../..`-style slugs are still jailed by `inst_valid_slug` before any filesystem call |
| Pre-onboarding attack surface | That no new anonymous endpoint appeared and nothing anonymous triggers inference | **Clean** — T29's exact allow-list tuple still passes; `--warm` sets an env var on the portal's *own* process and `/api/instance` reads module globals with zero I/O |
| New dependencies | — | **None.** No new Python or system package in the diff |

---

## 6. Performance

`status` is the only hot path this sprint touched (it gained HTTP probes and a
document builder). Baseline is the parent commit `42e87f4`, measured on the
T34 shape — 3 registered instances, none live, nothing listening — 7 runs each,
median reported, same machine, same fixture, back-to-back.

| Configuration | Runs (ms) | Median | vs baseline |
|---|---|---|---|
| **before** (`42e87f4`) `status` | 673 613 614 606 650 686 620 | **620 ms** | — |
| **after** (HEAD) `status` | 1027 1019 1010 999 999 1034 1002 | **1010 ms** | **+63%** |
| after `status --no-probe` | 999 963 1005 1056 1058 993 1008 | 1005 ms | +62% |
| after `status --json` | 1009 1021 962 933 949 976 942 | 962 ms | +55% |
| after `status --probe` | 963 943 997 1031 1024 1182 1138 | 1024 ms | +65% |

**Threshold:** ARCHITECTURE §16.2 **T34** sets it at **< 2 s**, and the
sprint's own driver asserts it. **Verdict: within budget**, 2× headroom.

**Mechanism (Q8), and why it is worth telling the builder:** it is not the
probes. `--no-probe` is statistically identical to the default (1005 vs
1010 ms) — so the "deterministic CI mode" flag buys correctness, not speed.
The cost is process creation: instrumenting `python3` with a counting shim
shows **29 → 49 invocations per `status` run** (+69%), which tracks the
wall-clock ratio almost exactly at ~20 ms of interpreter startup each. §4.1 and
F19 both describe the design as *"one `python3` pass builds the document"*;
what shipped is roughly one pass per fragment. Batching the collector's
fragments into the single pass the design already specifies would recover most
of the 390 ms.

No BENCHMARK.md filed separately — the whole measurement is above.

---

## 7. Regression

**Protected baseline and full driver suite — all green, re-run at HEAD after
the new tests landed:**

| Driver | Scenarios | Result |
|---|---|---|
| `tests/instance_start_driver.sh` | 11 | ✅ (protected, byte-identical) |
| `tests/instance_qa_driver.sh` | 10 | ✅ (protected, byte-identical) |
| `tests/cli/root_start_driver.sh` | 7 | ✅ |
| `tests/cli/restart_driver.sh` | 14 | ✅ |
| `tests/cli/install_driver.sh` | 18 | ✅ |
| `tests/cli/status_driver.sh` | 13 | ✅ |
| `tests/cli/verbs_driver.sh` | 6 | ✅ |
| `tests/cli/warmup_driver.sh` | 5 | ✅ |
| `tests/cli/color_driver.sh` | 5 | ✅ |
| **`tests/cli/qa_edge_driver.sh`** (new) | **10** | ✅ |

**Full pytest suite, before vs after this QA pass:**

| | Baseline (HEAD, pre-QA) | After (HEAD + QA tests) |
|---|---|---|
| failed | 77 | 77 |
| errors | 14 | 14 |
| passed | 3817 | 3842 (+25) |
| skipped | 4 | 4 |
| xfailed | 2 | 12 (+10) |

The 91 failed+error **test IDs were diffed line-for-line, not just counted**:
`comm -13` and `comm -23` against the baseline set are both **empty** — zero
new failures, zero silently-fixed ones. This matches BUILD_LOG's documented
77-failed/14-error environment-gap set exactly.

**Known pre-existing reds, re-confirmed as unrelated:**

- `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives` and
  `::test_port_scoped_helpers` — the `_ollama_pid_if_we_started_it: command not
  found` awk-extraction gap, already tracked in `sprints/BACKLOG.md`.
- `tests/shell_source_safety_driver.sh` — dies at case #6's `python3 render.py`
  (`ModuleNotFoundError: tomllib`, system `python3` is 3.9.6). **I verified the
  re-review's R6.2 close is real**: cases #7/#8 (the F4 extension for
  `install.sh` and `services.sh`) now run *before* #6 and pass, and with a 3.11
  `python3` shimmed onto `PATH` the whole driver goes green:
  `OK: shell-sourced config files (.env, lab.conf) are injection-safe, and
  install.sh/services.sh callers' guarded sources never abort on a missing file (F4)`.
  The gate is no longer dormant.

---

## 8. What I could not break

Recorded because a QA report that lists only defects overstates the risk:

- **REVIEW.md B2's fix.** `stop --root` and `restart --root` leave a live
  sibling World alone, including one sharing the root's configured port. The
  residual the re-review filed (§R6.3 — a same-port World inside its own
  `[6/8]`→`[8/8]` boot window) is real but requires a same-port collision *and*
  a concurrent boot; I did not attempt to widen it, per instruction. Worth
  noting it has a **second, non-timing route**: a *corrupt* registry record
  also leaves its pids out of the exclusion set, since that set is built from
  readable live records. Same narrow blast radius, no timing needed. Filed as a
  note against the existing backlog entry rather than a new finding.
- **B3's disclosure fix**, at the HTTP level, under a deliberately poisoned
  exception, on both branches (§5).
- **`install`'s git phase**, under every `--force` combination (§5).
- **F18** — `status --json`'s stdout stayed valid JSON in all 12 hostile states
  I could construct, including the one that produces a traceback on stderr.
- **The instance path.** `instance_start_driver.sh` and `instance_qa_driver.sh`
  are byte-identical and green; the 8-stage boot, claim file, token/checkout
  gate and write-after-ready are untouched.

---

## 9. Notes for the next QA pass

- **The pattern behind Q3 and Q4 is the same:** an argv/config value that is
  *malformed* rather than *absent*. Both parsers handle "missing" (defaults,
  guards) and "valid" (the happy path) and fall off the edge in between. Worth a
  sweep of every other `${2:-}` and every `int()` over a config value.
- **`docs/cli.md` now contradicts itself** on `stop`'s exit codes (§3, Q3). The
  F33 drift guard checks that every verb *appears* in the doc; it cannot check
  that the doc agrees with itself or with the code. A conformance test
  generated *from* the table would be the real gate — the table is already
  machine-parseable Markdown.
- **`status`'s per-service "expected" set is computed from the asking
  process's `PATH`.** A `start` under a minimal `PATH` and a `status` under a
  login shell's `PATH` legitimately disagree about whether `ttyd` is expected
  (I hit this while building QA-7 and had to pin both to the same `PATH`). The
  `daemon_active` carve-out covers the launchd case; a `sudo`/cron/CI caller is
  not covered. Not filed — no incorrect verdict in any realistic path — but
  it will confuse someone eventually.
- **Under-tested still:** the daemon/launchd branches (every test stubs
  `launchctl`); `--warm`'s instance path end-to-end (source-pinned only);
  anything Windows/WSL.
- **The harness is in good shape.** `tests/cli/lib.sh`'s randomized-port rule
  (F26/F27) is genuinely load-bearing and its fixtures composed cleanly for
  every scenario I needed, including a real portal boot it was never designed
  for. The `cli_test_fabricate_live_instance_portal_like` trick — making the
  *real* `pgrep` see a real matching argv — is the one to reach for whenever a
  scenario touches `stop_services`.
