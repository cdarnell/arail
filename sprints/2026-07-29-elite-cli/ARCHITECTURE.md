# Architecture: Elite CLI for `arailctl`

**Date:** 2026-07-29
**Sprint:** `2026-07-29-elite-cli`
**Spec (frozen input):** [../PROMPT-elite-cli.md](../PROMPT-elite-cli.md) — mission, verified baseline, the 10 gaps, constraints
**Ledger:** [SPRINT.md](./SPRINT.md)
**Repo conventions:** `CLAUDE.md` (root) — `scripts/lib/instances.sh` is the single source of truth for liveness; per-instance secrets are never shared; bash 3.2 (macOS `/bin/bash`) compatibility

---

## 1. Restatement

`./arailctl` is the first thing anyone who clones ARAIL touches, and today it is
three-quarters excellent: the Concurrent-Worlds instance path (`start --world`)
is an 8-stage launch with a real readiness gate, registry-verified stop, and an
honest instance table in `status`. Everything *outside* that path has not caught
up. The root-lab launch prints "All services running" before uvicorn has bound a
socket and cannot detect a crashed portal at all; `status` proves processes exist
with `pgrep` patterns rather than proving ports answer, prints "Portal not
running" while a World instance is happily serving, and always exits 0; `restart`
runs an unscoped stop before starting one World and deadlocks at an interactive
picker in CI; there is no flag for "start the root lab" once two Worlds exist; and
the version-management surface is three overlapping verbs (`setup`, `update`,
`upgrade`) with no verb for the thing operators actually want — "get me the latest
of everything." This sprint makes every lifecycle verb non-interactive-safe,
machine-readable, honest about which URLs actually answer, and gives the whole CLI
a documented, tested exit-code contract — **without redesigning the instance path
that was verified green on 2026-07-29**, which becomes protected-by-regression-test
territory instead.

---

## 2. Assumptions

Explicit, because each one is a way this design can be wrong:

- **A1.** The verified baseline in `PROMPT-elite-cli.md` is accurate and current for
  this checkout. I re-read `scripts/start.sh`, `scripts/status.sh`,
  `scripts/reset.sh`, and `scripts/lib/instances.sh` and found the described
  behaviors present; I did not re-run the live boot. If the live baseline has since
  drifted, the regression tests in §17 will surface it before the builder's changes
  are blamed.
- **A2.** `bash` on the target machine may be 3.2 (macOS ships it as `/bin/bash`).
  No associative arrays, no `readarray`/`mapfile`, no `${var,,}`, no `declare -A`,
  and `source <missing-file>` aborts a non-interactive shell **even under a
  trailing `|| true`** (documented in `status.sh:18-27` and `start.sh:34-41`).
- **A3.** `python3` is always available to any script that needs to build or parse
  JSON. Every script here already relies on this; the design does not add a new
  dependency.
- **A4.** `curl` is *usually* available but not guaranteed. `lsof` **or** `ss` is
  usually available (`setup.sh:_port_in_use` already degrades to "assume free" with
  neither). Every probe must have a defined answer when the tool is absent, and
  "tool absent" must never be reported as "service down."
- **A5.** Loopback HTTP is not "network" for the purposes of ARAIL's airgap
  contract. `LAB_MODE=airgapped` blocks *cloud providers*; probing
  `http://127.0.0.1:8080/api/instance` is local state inspection. `status --probe`
  already does exactly this and shipped under the airgap doctrine.
- **A6.** `GET /api/instance` and `GET /health` are reachable **pre-onboarding** —
  they are on `onboarding_gate`'s allow-list (`app.py:404-415`). `/api/ready`,
  `/api/chat/*`, and `/api/models/*` are **not**: they 401 on a lab whose
  passphrase has not been set. Any probe or warm-up signal usable on first boot
  must therefore ride on `/api/instance` or `/health`.
- **A7.** The root lab's `/api/instance` returns `{"slug":"root","token":null,
  "checkout":<cwd>,...}` (`app.py:3378-3388`). The instance identity check
  (token + checkout) therefore generalizes to the root path as **slug=="root" +
  checkout match** — root has no token by construction, so the token half is
  replaced, not dropped.
- **A8.** `arail.doctor.main()` currently always returns 0, and CI runs
  `./arailctl doctor` under `set -euo pipefail`
  (`.github/workflows/blueprint-smoke.yml:206`). Any new non-zero doctor exit must
  fire **only** on conditions that are false on the CI runner (which has `.venv`,
  `uvicorn`, and a writable PKB, and legitimately lacks `ttyd`, `code-server`, and
  any pulled model).
- **A9.** `status --json`'s only in-repo documented consumer is
  `docs/concurrent-worlds.md:158`; a grep of `.github/`, `tests/`, `scripts/`, and
  `src/` found no programmatic consumer. A schema bump is therefore a
  documentation-and-CHANGELOG problem, not a breaking-integration problem.
- **A10.** Warming a model only survives the warming process when the weights live
  **outside** it. That is true for `ollama_native` and `openai_compat` (a shared
  daemon holds residency) and false for in-process MLX/AeroLLM. `--warm` must
  therefore act *through* the portal process, not beside it.
- **A11.** The operator running `install` on a metered or slow link would not
  thank us for silently pulling multi-gigabyte weights. Model refresh is
  detect-and-report by default, apply behind a flag.
- **A12.** No test or CI job asserts an exit code for `status`, `restart`, or
  `install` today (`status` always exits 0; `install` does not exist), so those
  codes are free. `start.sh`'s existing codes are **not** free: the protected
  driver `tests/instance_start_driver.sh` asserts exit `2` for bad flags/unknown
  slug and exit `1` for the claim race and the instance ceiling.

---

## 3. Scope rulings up front

### 3.1 What is already solved (do not rebuild)

- **Warm-up already exists in-process.** `app.py:_warm_primary_router()` issues a
  real 1-token completion and is gated by `arail.autochecks` (default off = quiet
  boot, per `sprints/2026-07-23-clean-experience/`) plus
  `ARAIL_TIER0_BOOT_WARM`. Gap 7 is therefore **not** "build a warmer"; it is
  "give the CLI an explicit, honest opt-in door to the warmer that exists, and
  report its time." Building a second warm path in bash would duplicate backend
  selection and would warm a throwaway process for in-process backends. See §11.
- **The `_port_in_use` primitive exists** (`setup.sh:298`) and is already
  reused-not-copied via `inst_load_port_helpers()`. The new service probes reuse it
  the same way. No new port-detection implementation.
- **The instance readiness probe, claim-file discipline, registry write-after-ready,
  Ollama ownership rules, and `stop --world` verification are done and verified.**
  They are protected, not extended.

### 3.2 Ruled out of scope (with reasons)

- **Multi-target `restart`/`start` (backgrounded instances).** `_instance_start`
  ends in `wait` — a World instance is a foreground process owned by the invoking
  shell. "Restart everything that was running" for N≥2 instances requires a
  supervisor (nohup/launchd-per-instance + log routing + PID adoption). That is a
  sprint of its own. `restart --all` is therefore an **explicit refusal with an
  explanation** (exit 2), not a silent half-feature. Filed as tech debt (§18).
- **`doctor --json`.** Not requested; doctor gets an exit contract (§12) and a
  loop fix, not a machine format.
- **Unifying stage `[6/8]`'s inline readiness poll onto the new shared helper.**
  Behavior-preserving, testable, and correct — but it edits the single most
  load-bearing 40 lines in the repo during a sprint whose mandate is "protect the
  baseline." The new helper is *designed* so stage 6 can adopt it later; the
  duplication is limited to ~15 lines of polling boilerplate (the identity check
  differs anyway — A7). Filed as tech debt with adoption preconditions (§18).
- **`upgrade.sh`'s airgap-blind `pip install`.** Real bug (`LAB_MODE=airgapped`
  does not stop `pip install -q -e ".[tier]"` from reaching PyPI), but it is
  pre-existing and outside this sprint's verbs-and-status mandate. Noted in §18 so
  it has a home.
- **`reset` not touching instance data**, and the `instances/` vs `lab/instances/`
  unification. Both already tracked in `sprints/BACKLOG.md`.

---

## 4. Data flow

### 4.1 `status` — one collector, one document, two renderers

The central architectural property: **the human table and `--json` are rendered
from the same in-memory document**, so they can never disagree. This is the
existing `_status_rows_json` pattern (`status.sh:119`) generalized from the
instance table to the whole view.

```
   .env ──┐                        ┌────────────────────────┐
lab.conf ─┤  config (guarded       │  collect (bash)        │
   tier ──┘  [[ -f ]] source)  ───►│  ────────────────────  │
                                   │  1. instances:         │
lab/instances/registry.d/*.json ──►│     inst_list_slugs    │
   (via instances.sh ONLY)         │     inst_read_record   │
                                   │     inst_alive         │
~/Library/LaunchAgents/io.arail.* ►│     inst_probe_matches │
   (via daemon_active/             │  2. supervision:       │
    daemon_plist_installed ONLY)   │     daemon_active      │
                                   │  3. root services:     │
loopback probes ──────────────────►│     svc_listening      │
  svc_listening  -> _port_in_use   │     svc_http_status    │
  svc_http_status -> curl -m 0.7   │     svc_identity       │
                                   └───────────┬────────────┘
                                               │ TSV lines + JSON fragments
                                               ▼
                                   ┌────────────────────────┐
                                   │ python3: build ONE doc │
                                   │ arail.status/v2        │
                                   │ + compute verdict      │
                                   └───────┬────────┬───────┘
                                           │        │
                        --json / --json=full│        │ default
                                           ▼        ▼
                                   print doc     python3 renderer
                                   (stdout)      (human table)
                                           │        │
                                           └────┬───┘
                                                ▼
                                   inst_prune_all  (after render — §2.5 baseline)
                                                ▼
                                   exit verdict.code   (0 / 3 / 4)
```

### 4.2 `start` — the two paths, now symmetric

```
arailctl start [flags]
   │
   ├─ argv contains --world/--list/--help ──────────────► exec start.sh (always; REVIEW.md B2)
   │
   ├─ daemon_active?
   │     ├─ yes + (--world|--root) ─► refuse, name the slug, exit 1        [NEW: was kickstart]
   │     └─ yes ─► launchctl load + kickstart ─► NEW readiness gate (30s)
   │                                              ✓ print URL, exit 0
   │                                              ✗ log hint, exit 1      [NEW: was blind exit 0]
   └─ no ─► exec start.sh [flags]
              │
              ├─ parse flags (adds --root, --warm)
              ├─ resolve target:  --world X | --root | |W|==0 | |W|==1 | picker/refusal
              │
              ├─ TARGET_SLUG non-empty ─► _instance_start   ◄── PROTECTED, UNCHANGED
              │      [1..8] stages, token+checkout gate, registry write-after-ready
              │      └─ NEW, after the URL banner: optional warm-up report
              │
              └─ TARGET_SLUG empty ─► ROOT PATH
                     ├─ arm cleanup trap FIRST                            [NEW]
                     ├─ spawn portal / memory / [mlx] / ollama / ttyd / jupyter / ide
                     ├─ NEW readiness phase (svc_* helpers, per-service ✓/⚠/✗)
                     │     portal   REQUIRED  60s  /api/instance slug==root && checkout==$REPO_ROOT
                     │     memory   degrade   20s  /health
                     │     mlx      degrade   20s  /health          (iff MODEL_BACKEND=mlx)
                     │     terminal degrade   10s  listen           (iff ttyd installed)
                     │     notebook degrade   10s  listen           (iff jupyter installed)
                     │     ide      degrade   10s  listen           (iff code-server installed)
                     ├─ portal ✗ ─► kill OUR pids only, diagnostics, exit 1
                     ├─ banner: only URLs that answered; "All services running"
                     │            only when nothing degraded
                     ├─ optional warm-up report                           [NEW]
                     └─ wait
```

### 4.3 `install` — phases, with a self-update re-exec

```
arailctl install [--check] [--only/--skip p,..] [--models] [--rebuild-venv] [--yes] [--json]
   │
   ├─ preflight: provisioned? (.venv, .env)      no  ─► exit 1 "run ./arailctl setup"
   │             lab live? (inst_any_alive ||    yes ─► exit 1 "stop it first" (F21/F22)
   │                        root portal answers)          unless --allow-running
   │             LAB_MODE=airgapped?             yes ─► network phases refused, exit 3
   │                                                     unless --force
   ├─ [1/5] source     git pull --ff-only  (clean + tracking + attached only)
   │            └─ if HEAD moved ──► exec self with --_post-source <old-sha>   (F5)
   ├─ [2/5] deps       [--rebuild-venv: rm -rf .venv && recreate] ; pip install -e ".[tier]"
   ├─ [3/5] components delegate: update.sh --apply --non-interactive          (components.json)
   ├─ [4/5] models     detect drift vs model_defaults.yaml/default persona;
   │                   report + exact command; apply only with --models       (A11)
   └─ [5/5] verify     arailctl doctor  (exit contract §12) ─► summary + verdict
```

---

## 5. The verb matrix

Legend — **tty** = `stdin`/`stdout` is a terminal; **non-tty** = piped/redirected
(the CI/daemon contract: deterministic, never prompts, never emits ANSI).
Exit codes are defined in §12. "unchanged" means this sprint does not touch it.

### 5.1 Provisioning and version management

| Verb | Flags | tty | non-tty | Exit | JSON |
|---|---|---|---|---|---|
| `setup` | `--with-coder` / `--no-coder` (existing), **`--yes\|-y`** (= `ARAIL_NONINTERACTIVE=1`), **`--quiet`** (mask passphrase) | 11-step interactive flow, unchanged | already deterministic (`confirm()`/`capture_*` default-yes when `! -t 0`); **passphrase auto-masked** | `0` ok · `1` any `error()` · **`2` unknown flag (new)** | — |
| **`install`** *(new)* | `--check\|--dry-run`, `--only <p>[,<p>]`, `--skip <p>[,<p>]` (p ∈ `source,deps,components,models,verify`), `--models`, `--rebuild-venv`, `--allow-running`, `--force` (override airgap refusal), `--yes\|-y`, `--quiet`, `--json`, `-h\|--help` | per-phase `✓/⚠/✗` + summary; confirms before `--rebuild-venv` | never prompts (`--yes` implied); identical phase lines, no ANSI | `0` all phases ok/no-op · `3` degraded (a phase refused/failed, lab still usable; **also `--check` with pending changes**) · `1` hard failure (deps refresh failed; not provisioned; lab live without `--allow-running`) · `2` bad flags (incl. `install daemon` → "did you mean `install-daemon`?") | `--json` → `arail.install/v1` |
| `update` | all of `install`'s; plus legacy `--component <name>` forwarded to the components phase | **alias for `install`** + one-line notice on stderr | same; notice on stderr keeps stdout clean | same as `install` | same |
| **`tier`** *(new canonical name)* | `minimalist` \| `maximus`, `--with-coder`/`--no-coder`; no arg = print current tier | delegates to `upgrade.sh` unchanged | same | `0` · `1` pip/tier failure · `2` unknown tier | — |
| `upgrade` | unchanged argv | **alias for `tier`** + notice | same | unchanged (`0`/`1`) | — |
| `version` | none | unchanged (`update.sh --version-only`) | unchanged | `0` | — |
| `install-daemon` / `uninstall-daemon` | unchanged | unchanged | unchanged | unchanged | — |

### 5.2 Lifecycle

| Verb | Flags | tty | non-tty | Exit | JSON |
|---|---|---|---|---|---|
| `start` | existing: `--world <slug>`, `--world=<slug>`, `--port <n>`, `--no-browser`, `--list`, `--yes`, `-h`. **New: `--root`, `--warm`** | unchanged instance path; picker when \|W\|≥2 and no target; browser auto-open | picker replaced by exit `2` + the exact `--world`/`--root` commands (existing); **no browser**; ANSI-free | `0` ready (or attached) · `1` failure/refusal (no `.venv`, daemon active, claim held, ceiling, bind conflict, **root portal never came up — new**) · `2` usage (bad flag, unknown slug, `--root` with `--world`, ambiguous picker non-tty) · `130/143` INT/TERM | — |
| `stop` | existing: `--world <slug>`, `--all`. **New: `--root`** | unchanged | unchanged; already deterministic | `0` **including "nothing was running"** (a stop verb's contract is "it is down now") · `1` multiple live instances and no target (existing) / instance support unavailable · `2` invalid slug (existing) | — |
| `restart` | **forwards every `start` flag**; target from `--world` \| `--root` \| the registry | daemon: `kickstart -k` (unchanged) unless `--world`/`--root` given → refuse. Foreground: scoped stop of exactly one target, then `exec start.sh` | identical; never reaches a picker: \|live\|≥2 → exit `2` naming each `restart --world <slug>` | `0`/`1`/`2` inherited from the `start` it `exec`s · `2` ambiguous target · `2` `--all` (explicit refusal) · `1` scoped stop failed (start not attempted) | — |
| `status` | existing: `--json`, `--probe`. **New: `--json=instances`, `--json=full`, `--no-probe`, `--quiet\|-q`, `--no-sizes`** | unified view: Instances → Supervision → Root lab (or one "not started" line) → Scheduler → Runtime state | identical content, ANSI-free; `du` sizes still shown unless `--no-sizes` | **`0`** something expected is up and nothing is wrong · **`3`** up but degraded/foreign/stale/unreadable/checkout-mismatch · **`4`** nothing running · `1` internal failure · `2` bad flag | `--json`/`--json=full` → `arail.status/v2`; `--json=instances` → **byte-compatible v1 rows array** |
| `doctor` | passthrough to `arail.doctor` (`--updates`); **`--strict`** | unchanged output + a findings summary | unchanged | **`0`** healthy (optional binaries/models missing = INFO) · **`3`** degraded (required check failed: `uvicorn` absent, PKB root unwritable, airgap guard expected-but-absent; `--strict` promotes INFO→degraded) · `1` broken (no `.venv`, `import arail` fails) · `2` bad flag | — |
| `reset [mode]` | unchanged | unchanged | unchanged | unchanged | — |
| `logs`, `pkb`, `wiki`, `world`, `kb`, `blueprint`, `deep`, `benchmark_models` | unchanged | unchanged | unchanged | unchanged (`kb help` heredocs deduped — output text preserved) | — |
| `help` / no verb | — | usage banner | ANSI-free banner | `0` (`help`) · `1` (unknown verb, existing) | — |

### 5.3 Cross-cutting flag/env contract (all verbs)

| Control | Meaning |
|---|---|
| `NO_COLOR` set (any value) | ANSI disabled (de-facto standard) |
| `ARAIL_COLOR=always\|never\|auto` | Overrides the tty test; `auto` (default) = colors iff `[[ -t 1 ]]` and `NO_COLOR` unset |
| `! [[ -t 1 ]]` | ANSI disabled everywhere; browser auto-open already suppressed; setup passphrase masked |
| `! [[ -t 0 ]]` | No verb may prompt. Existing: `confirm()`, `capture_*`, the World picker. New verbs inherit the same rule. |
| `ARAIL_NONINTERACTIVE=1` | Same as `! -t 0` for prompts |
| `ARAIL_WARM_TIMEOUT_SEC` | `--warm` cap (default 90) |
| `ARAIL_QUIET=1` | Same as `--quiet` for `setup`/`install` |

---

## 6. Ruling 1 — the `install` / `update` / `upgrade` consolidation

### 6.1 The problem, precisely

Three verbs, three axes, two of them named for the same thing:

| Today | What it actually does | Axis |
|---|---|---|
| `setup` | provision this checkout: platform packages, `.venv`, `.env`/`lab.conf`, ports, PKB, default model, PATH shim, verify. Idempotent (respects existing `.env`), non-tty safe | **provision** |
| `update` | walk `components.json`, check remote versions, apply with confirmation | **version** |
| `upgrade <tier>` | switch feature tier (`minimalist`↔`maximus`), `pip install -e .[tier]`, write `LAB_TIER` | **feature set** |

Nothing owns "refresh the source tree + the venv + the binaries + the model to the
latest, then tell me it still works" — the operator's actual request. And
`upgrade` *reads* like the version axis while being the tier axis, which is why the
trio feels like three overlapping verbs.

### 6.2 The ruling

**Three axes, three verbs, one new name and one rename — with aliases forever.**

1. **`setup` = provision.** Unchanged in scope. It is the only verb that may
   create `.venv`, `.env`, and `lab.conf`, install OS packages, or ask the operator
   questions. Gains only `--yes`, `--quiet`, and unknown-flag rejection.
2. **`install` = refresh everything (new, the operator's verb).** Requires an
   already-provisioned lab; refuses on an unprovisioned one with the exact
   `setup` command (exit 1). Five phases: `source` → `deps` → `components` →
   `models` → `verify`. Non-destructive by default: no model download without
   `--models`, no `.venv` deletion without `--rebuild-venv`, no `git` mutation
   beyond `pull --ff-only` on a clean, attached, tracking branch.
3. **`update` = alias for `install`.** The components-manifest engine
   (`scripts/update.sh`) is *not* deleted — it becomes `install`'s **components
   phase**, invoked as `update.sh --apply --non-interactive` (a new argv mode; the
   existing interactive path stays for `update --component ttyd` muscle memory).
   `update --check` maps to `install --check`.
4. **`tier <minimalist|maximus>` = the canonical name for the feature-set axis;
   `upgrade` becomes its alias.** `tier` with no argument prints the current tier
   instead of dying with usage. `scripts/upgrade.sh` is untouched (same argv).

Why not fold `install` into `setup` with a flag (`setup --refresh`)? Because
`setup` may prompt, may install OS packages, and may rewrite `.env` — three things
a refresh verb must never do. Different blast radius ⇒ different verb.

Why keep `update` at all? It is in `README.md`, `CHANGELOG.md`, the portal's
Updates banner language, and every operator's fingers. Aliasing costs one `case`
arm; breaking it costs trust.

### 6.3 Phase contracts

| Phase | Does | Refuses (→ degraded, exit 3, remaining phases still run) | Never |
|---|---|---|---|
| `source` | `git pull --ff-only`; prints `old…new` short SHAs + commit count; **re-execs `install.sh` if HEAD moved** (F5) | not a git repo · dirty worktree · detached HEAD · no upstream · diverged (non-ff) · `LAB_MODE=airgapped` without `--force` | `stash`, `reset --hard`, `clean`, `merge`, `rebase`, or a branch switch |
| `deps` | `pip install -e ".[$LAB_TIER]"` (idempotent); with `--rebuild-venv`: recreate `.venv` first | airgapped without `--force` | run while a lab is live (preflight already refused, exit 1) |
| `components` | `update.sh --apply --non-interactive` — `components.json` drives it, per-component failures are `warn`+continue (existing) | airgapped without `--force` (already `update.sh`'s own behavior) | fail the whole run for one optional component |
| `models` | compare the expected primary chat model (`model_defaults.yaml:default_a` if present, else the setup default `llama-ai-eng`) against `ollama list`; report drift + the exact two commands; with `--models`, run them | ollama absent / daemon unreachable → `⚠ skipped` (never hangs — reuses `setup.sh`'s 5s `ollama list` fail-fast pattern) | download anything without `--models` (A11) |
| `verify` | `arailctl doctor` (§12 exit contract) | — | mask a doctor failure: doctor `3` ⇒ install `3`, doctor `1` ⇒ install `1` |

### 6.4 Migration and back-compat note

- `arailctl update` → runs `install`. Stderr: `note: 'update' is now an alias for
  'install' (same behavior; see docs/cli.md).` **stdout stays clean** so
  `update --json | jq` works.
- `arailctl update --check` → `install --check`. Exit `3` when changes are pending
  (new; documented — the `git diff --exit-code` convention). `update --check`
  previously exited 0 always.
- `arailctl update --component ttyd` → forwarded verbatim to `update.sh` (the old
  interactive path). No behavior change.
- `arailctl upgrade <tier>` → runs `tier <tier>`, unchanged behavior, one stderr
  note. **No removal date.** ARAIL is a blueprint people have forked; a verb
  removal breaks their scripts silently. Aliases stay.
- `arailctl upgrade` (no arg) → previously `die "usage: …"` (exit 1). Now prints
  the current tier plus the two switch commands, exit 0. Documented as a behavior
  change in CHANGELOG.
- Docs to update in the same commit: `README.md` (command table), `docs/cli.md`
  (new, canonical), `docs/INSTALL.md`, `CHANGELOG.md`, `CLAUDE.md`'s "main verbs"
  list, `arailctl`'s own header comment + `usage()`.

---

## 7. Ruling 2 — the unified status model

### 7.1 What "should be running" means (kills the contradiction, gap 4)

`root.state` is derived, in this order — first match wins:

| Condition | `root.state` | Human line | Verdict contribution |
|---|---|---|---|
| Root portal port answers `/api/instance`, but `slug != "root"` or `checkout != $REPO_ROOT` | `foreign` | `⚠ root portal :8080 is answered by a DIFFERENT checkout: <path>` + `lsof` hint | degraded (3) |
| Portal answers and is ours; **every** expected service listening | `up` | full service list, URLs | ok |
| Portal answers and is ours; ≥1 expected service not listening | `degraded` | `⚠` per missing service | degraded (3) |
| Portal silent **and** `daemon_active` | `down` | `✗ root lab: launchd supervises it but the portal is not answering` + log path | not-running (4), reason recorded |
| Portal silent, no daemon, **≥1 live World instance** | `not-started` | **one line:** `root lab: not started (World instance '<slug>' is running instead)` | neutral — never degrades the verdict |
| Portal silent, no daemon, no live instance | `down` | `root lab: not running — ./arailctl start` | not-running (4) |

Per-service `expected` (the "keyed by what should be running" table):

| Service | Expected iff | Probe |
|---|---|---|
| portal | `root.state != not-started` | HTTP `/api/instance` + identity (always, even without `--probe`: it is the one probe that resolves the contradiction) |
| memory | portal expected | listen; `--probe` adds `/health` |
| mlx | portal expected **and** `MODEL_BACKEND == mlx` | listen; `--probe` adds `/health` |
| terminal (ttyd) | portal expected **and** `command -v ttyd` **and not** `daemon_active` (launchd deliberately does not supervise it — `install-daemon.sh:9-16`) | listen |
| notebook (jupyter) | same shape | listen |
| ide (code-server) | same shape | listen |
| ollama | **never** "expected" — reported under `external` as `reachable` + `managed_by_lab` (pidfile present, i.e. we started it). Honors "never touch an Ollama we didn't start" at the reporting layer too. | HTTP `/api/version` |

A service with `expected=false` renders `state="skipped"` and is **not printed**
in the human view (that is what kills the five dim "not running" rows), but it is
present in `--json` with its reason — scripts still see the whole picture.

### 7.2 Probes, not `pgrep` patterns (gap 5)

- **Verdict source = the probe.** `svc_listening <port>` → `_port_in_use` (loaded
  via `inst_load_port_helpers`, i.e. `setup.sh`'s real implementation — no sixth
  copy). `svc_http_status <url>` → `curl -sf -m 0.7 -w '\n%{http_code}'` (the same
  invocation shape stage `[6/8]` already proved out, including the "`-f` only
  affects the body" trick that keeps a real 4xx/5xx distinguishable from silence).
- **`pgrep` survives as an owner hint, not a verdict.** It runs *only* when the
  port is listening, and only sets `owner: ours|unknown`. The existing
  checkout-scoped patterns (`status.sh:226-230`) are reused verbatim so nothing is
  lost; the port-agnostic footgun is gone because the port answer, not the
  pattern, decides up/down.
- **URLs are printed only when the port answered.** A non-listening service prints
  `:8888  not listening` with no clickable URL. `--json` carries `url` only when
  `listening == true` (null otherwise) so dashboards inherit the same honesty.
- **Bind normalization:** when `BIND_ADDR` is `0.0.0.0` / `::` / empty, probes
  target `127.0.0.1` while the *displayed* URL keeps the configured host (F29).
- **Missing tools:** no `curl` → `http_status: null`, `owner: "unknown"`, state
  from `listening` alone, plus `warnings: ["curl not found — HTTP probes skipped"]`.
  Neither `lsof` nor `ss` → `listening: null`, state `"unknown"`, warning recorded.
  **A missing tool never produces `down` and never degrades the verdict** (A4).
- **Probe levels:** default = portal HTTP + listen checks for the rest (bounded: 1
  curl + ≤6 `lsof`). `--probe` = adds `/health` for memory/mlx **and** the existing
  per-instance token/checkout probe. `--no-probe` = zero HTTP, registry+listen only
  (deterministic CI mode).

### 7.3 `status --json` schema v2 (gap 8)

`--json` / `--json=full` emit exactly one JSON object. Additive-only evolution:
new fields may appear in v2; **removals or type changes require v3**.

```json
{
  "schema": "arail.status/v2",
  "generated_at": "2026-07-29T22:03:11Z",
  "checkout": "/Users/x/ProJects/qukaizen-arail",
  "provisioned": true,
  "lab":  { "name": "Autoresearch AI Lab", "tier": "minimalist", "mode": "airgapped" },
  "bind": "127.0.0.1",
  "probe": { "level": "default", "http_timeout_ms": 700 },
  "warnings": [],
  "supervision": {
    "mode": "foreground",
    "plists_installed": false,
    "agents": [
      { "label": "io.arail.portal", "state": "running", "pid": 4211, "last_exit_status": 0 }
    ]
  },
  "instances": [
    {
      "schema": "arail.instance-registry/v1", "slug": "ai", "display_name": "AI World",
      "checkout": "/Users/x/ProJects/qukaizen-arail",
      "instance_root": "…", "data_dir": "…", "pkb_root": "…",
      "bind": "127.0.0.1", "portal_port": 8090, "lance_port": 8094,
      "launcher_pid": 401, "portal_pid": 402, "memory_pid": 403,
      "token": "…", "started_at": "…", "arailctl_version": "…",
      "state": "live", "data_root_missing": false, "probe_mismatch_checkout": null
    }
  ],
  "root": {
    "state": "not-started",
    "reason": "a World instance is running; the root lab was never started",
    "services": [
      { "name": "portal", "expected": false, "port": 8080,
        "url": null, "listening": false, "http_status": null,
        "owner": "unknown", "state": "skipped",
        "detail": "root lab not started" }
    ]
  },
  "external": {
    "ollama": { "url": "http://127.0.0.1:11434", "reachable": true, "managed_by_lab": false }
  },
  "verdict": { "code": 0, "state": "ok", "reasons": [] }
}
```

- **`instances[]` rows are byte-identical to today's v1 rows** (same keys, same
  `state`/`data_root_missing`/`probe_mismatch_checkout` semantics). `jq
  '.instances'` reproduces today's output exactly.
- **`--json=instances`** prints the bare v1 array — the documented stable form for
  existing scripts (`docs/concurrent-worlds.md:158` updated to name it).
- `--json=<anything-else>` → exit 2.
- `du` sizes are **not** in the JSON: a `du -sh lab/pkb` walk can cost seconds and
  `--json` must stay inside the <2s budget. Human view keeps them (`--no-sizes` to
  skip).
- **`--json` always emits valid JSON, including on failure** (F18): the collector's
  failures land in `warnings[]` and `verdict.code`, never as a bare human error
  line on stdout.
- `verdict.state ∈ {ok, degraded, not-running}`; `verdict.reasons[]` is a list of
  short machine-stable strings (`"instance:ai:stale"`, `"root:foreign:8080"`,
  `"root:service:notebook:down"`, `"registry:unreadable:finance"`).

---

## 8. Ruling 3 — root-lab readiness (gap 6)

### 8.1 How the instance probe generalizes

New `scripts/lib/services.sh`, with a documented boundary in its header:

> `instances.sh` owns the World-instance **registry** and **instance/daemon
> liveness** and remains the single source of truth for both. `services.sh` owns
> **root-lab per-service readiness probing** — a thing `instances.sh` has never
> implemented. It must never re-derive daemon or instance liveness, and it must
> never grow a second `_port_in_use`: it obtains that from
> `inst_load_port_helpers()` (which extracts the real one from `setup.sh`).

| Helper | Contract |
|---|---|
| `svc_probe_host <bind>` | prints the host to *probe* (loopback-normalized); never fails |
| `svc_listening <port>` | 0 = listening, 1 = not, 2 = undetectable (no lsof/ss). Never aborts under `set -e` |
| `svc_http_status <url> [timeout]` | prints `<code>\t<body>`; code `000` = no answer; empty body allowed. Never aborts |
| `svc_wait_listening <port> <deciseconds> [pid]` | poll until listening or cap; early-out if `pid` died. Returns 0/1 |
| `svc_wait_http_ready <url> <deciseconds> [pid]` | poll until HTTP 200; prints the **last non-000 status** on stdout for diagnostics; early-out if `pid` died. Returns 0/1. *(This is the generalized shape stage `[6/8]` can adopt later — §18.)* |
| `svc_identity_root <body> <expect_checkout>` | 0 iff `slug=="root"` **and** `checkout==expect_checkout` (A7). The root analogue of the instance token+checkout gate |

All helpers: pure stdout, always `return 0`-safe inside `$( )` under
`set -euo pipefail`, bash 3.2 only (no arrays in signatures, no `local -n`).

### 8.2 What the root path gains

Insertion points in `scripts/start.sh`'s legacy block (**additions and one moved
line, not a rewrite**):

1. **Arm `cleanup` immediately after `PIDS=()`** (currently armed at line 1059,
   *after* the success banner). Without this, the new "portal failed → exit 1"
   path leaks every spawned child. This is the same lesson `_instance_start`
   already learned as REVIEW.md M4 (the EXIT-trap fix) — applied to the root path.
2. **Per-service readiness phase** after the spawns, before the banner:

```
Readiness:
  ✓ Portal     http://127.0.0.1:8080          (1.9s)
  ✓ Memory     http://127.0.0.1:7414          (0.6s)
  ⚠ Notebook   :8888 did not answer in 10s — the Notebook tab will show help
  ✓ Terminal   http://127.0.0.1:7681          (0.4s)
```

3. **Per-service degradation semantics:**

| Service | Class | Cap | Failure behavior |
|---|---|---|---|
| Portal | **required** | 60s, 0.25s poll, early-out on dead pid | `✗` + `/api/instance answered HTTP <code>, not 200` **or** `portal did not come up`, + "see the uvicorn output above" (the root path logs to *this terminal*, not a file — unlike the instance path's `portal.log`), then `cleanup` (our pids only) and **exit 1** |
| Memory | degrade | 20s | `⚠ memory service did not answer within 20s — chat works, memory features degrade.` (same wording as stage `[7/8]`) |
| MLX (iff `MODEL_BACKEND=mlx`) | degrade | 20s | `⚠` + "MLX API unavailable — chat falls back per router config" |
| Terminal / Notebook / IDE (iff binary present) | degrade | 10s listen | `⚠` + which tab degrades |
| Ollama | degrade | unchanged (existing 10×0.5s `/api/version` loop) | unchanged |

4. **Honest banner:** `All services running.` only when zero degradations;
   otherwise `Lab running — degraded: notebook, ide.` The URL block prints **only
   services that answered** (kills the "URL block can lie" half of gap 6, and the
   MLX/Notebook/IDE lines that print unconditionally today even when the binary
   isn't installed).
5. **Identity, not just liveness:** the portal gate uses
   `svc_identity_root`, so a foreign process squatting `:8080` is reported as
   `port 8080 is answered by a different checkout/process` — the root-path analogue
   of the instance path's M1 token/checkout mismatch — rather than being counted as
   our successful boot.

### 8.3 Interaction with the daemon path

`arailctl`'s daemon `start` branch currently `launchctl load` + `kickstart`s and
prints a URL immediately — the same lie, one level up. It gains:

- `--world`/`--root` present → **refuse** (exit 1) with the slug named, reusing
  `start.sh`'s existing daemon-refusal wording. Today it silently kickstarts the
  root daemon while the operator asked for a World.
- otherwise → after `kickstart`, `svc_wait_http_ready
  http://<bind>:<port>/api/instance 300` (30s) + `svc_identity_root`.
  Ready → `✓` + URL, exit 0. Not ready → `✗ launchd kickstart issued but the
  portal did not answer within 30s — tail lab/logs/portal.err.log`, exit 1.
- `restart` in daemon mode: identical gate after `kickstart -k`.
- `install-daemon` is untouched (it already refuses over a live instance).

---

## 9. Ruling 4 — `restart` (gap 3)

### 9.1 Semantics

**systemd semantics, single target.** `restart` means "make exactly one target
running again," and it starts a stopped target rather than erroring — matching
every operator's muscle memory.

Target resolution (read-only argv scan + registry read; **no flag re-parsing** —
`restart` never becomes a second parser that can drift from `start.sh`):

| argv / state | Stop phase | Start phase |
|---|---|---|
| `--world <slug>` / `--world=<slug>` | `reset.sh stop --world <slug>` (**scoped** — this is the gap-3 fix) | `exec start.sh <original argv>` |
| `--root` | `reset.sh stop --root` (new flag: root services only, never instances) | `exec start.sh <original argv>` |
| neither; `daemon_active` | — | `launchctl kickstart -k` + readiness gate (§8.3) |
| neither; exactly 1 live instance | `reset.sh stop --world <that slug>` | `exec start.sh --world <that slug> <original argv>` (injected first so an explicit later flag would still win) |
| neither; 0 live instances | `reset.sh stop --root` | `exec start.sh <original argv>` (start does its own resolution/picker) |
| neither; ≥2 live instances | — | **exit 2**, printing `./arailctl restart --world <slug>` for each, plus `--root` |
| `--all` | — | **exit 2** + explanation: a foreground start hosts one target; use `stop --all`, then start each in its own terminal (§3.2) |

### 9.2 Invariants

- **The stop phase is always scoped to exactly one target.** `restart` can never
  again stop a sibling World (the motivating bug). A live sibling surviving
  `restart --world a` is a regression test (T12).
- **The registry snapshot is taken before stopping** — `stop_instance` deletes the
  record, so resolution must read it first.
- **Stop failure aborts the restart** (today's `&&` behavior preserved): if the
  scoped stop exits non-zero, `start` is not attempted, exit 1.
- **Loud state change on start failure** (F13): when the stop succeeded and the
  start then failed, print
  `restart: '<target>' was stopped, and the start failed (above) — the lab is now
  DOWN.` A silent "start failed" after a successful stop is how an operator ends
  up with a lab that is down and thinks nothing happened.
- Non-tty determinism: every branch above is decided from argv + the registry —
  no branch reaches `read`.

---

## 10. Ruling 5 — non-interactive root start (gap 2)

- **`--root` is the only spelling.** `start --root` / `stop --root` /
  `restart --root`.
- **`--world root` is deliberately NOT special-cased.** `root` matches
  `INST_SLUG_RE`, so a World literally named `root` must stay startable. `--root`
  and `--world root` therefore mean different things, on purpose, and
  `--root --world <x>` together is exit 2 (`--root and --world are mutually
  exclusive`).
- Implementation in `start.sh`: one new `ROOT_ONLY` flag in the existing `while`
  parser, checked at the top of the target-resolution block so it short-circuits
  the `|W|` counting and the picker entirely (`TARGET_SLUG=""`).
- Picker text gains the flag hints so the non-interactive refusal and the
  interactive menu teach the same vocabulary: option `0` line becomes
  `0) <LAB_NAME> (the root lab on :8080 — non-interactive: --root)`. The existing
  non-tty refusal (exit 2) gains a `./arailctl start --root` line alongside the
  per-World lines — this is the entire fix for "CI/daemons cannot start the root
  lab."
- If a World bundle with slug `root` exists, the picker adds one disambiguating
  line (F11).
- `reset.sh` gains `--root` in its existing `while` parser: dispatch straight to
  `stop_services` (root only), skipping the auto-resolution branch — so
  `stop --root` is well-defined and non-failing even while instances are live.

---

## 11. Ruling 6 — warm-up (gap 7)

### 11.1 Design

**Warm through the portal, never beside it** (A10). Three small pieces:

1. **Portal (Python):** `_warm_primary_router()` gains timing
   (`_MODEL_WARM_MS`) and the backend name it warmed (`_MODEL_WARM_BACKEND`, or a
   skip reason). The boot condition becomes
   `if _autochecks_on or _boot_warm_explicit()` where `_boot_warm_explicit()` is
   **true only when `ARAIL_TIER0_BOOT_WARM` is explicitly set to a truthy value**.
   Quiet boot is preserved exactly: unset + autochecks off ⇒ no warm, `_MODEL_WARM
   = True` immediately (overlay still dismisses). `ARAIL_TIER0_BOOT_WARM=0`
   continues to mean "no completion" in the autochecks-on case.
   **Must stay green:** `tests/test_boot_warm.py`, `tests/test_autochecks_boot.py`.
2. **`GET /api/instance` gains three fields** (both the root and instance
   branches): `"warm": bool`, `"warm_ms": int|null`, `"warm_skipped": str|null`,
   plus `"backend": str` (backend *class* name). Rationale for reusing this
   endpoint rather than adding one: it is already the readiness probe, already
   allow-listed pre-onboarding (A6), already documented as "self-report of the
   process answering," and read-only. **No new anonymous endpoint, therefore no
   new pre-onboarding attack surface, and no endpoint that triggers inference
   anonymously.** Fields are module globals — zero I/O per request. The model
   *identifier* is deliberately **not** added (F16): backend class is already
   visible via the allow-listed `/api/system/health`; a model id is not.
3. **CLI `start --warm` (also reachable as `restart --warm`):**
   - Instance path: pass `ARAIL_TIER0_BOOT_WARM=1` on the portal child's
     invocation line (exactly how `ARAIL_INSTANCE_TOKEN` is already passed) — the
     env pack is **not** touched (`instances.sh` documents the pack's key set as
     fixed; a warm flag is per-invocation, not per-instance state).
   - Root path: same, on the root portal's `uvicorn` line.
   - After the record is written and the URL banner printed (never before), poll
     `GET /api/instance` every 0.5s up to `ARAIL_WARM_TIMEOUT_SEC` (default 90)
     for `warm == true`, then print one line:
     `warm-up: ✓ ai-engineer via ollama_native in 4.2s` /
     `warm-up: ⚠ not complete within 90s — the first chat message will be slower` /
     `warm-up: — not applicable for backend <name> (weights load in-process; the
     portal warms itself on boot)`.

### 11.2 Failure semantics (must degrade, never block)

- `--warm` **never** changes the exit code and **never** gates the readiness
  verdict. It runs strictly after the lab is declared up.
- Timeout, HTTP 401 (onboarded-gate edge), non-JSON body, missing `curl`, absent
  fields (older portal) → one honest line, continue.
- `--warm` under **daemon mode**: the agent's environment is fixed by the plist, so
  print `warm-up: — daemon mode: set ARAIL_TIER0_BOOT_WARM=1 in .env, then
  ./arailctl restart` (the plist's `WorkingDirectory` + the portal's own
  `load_dotenv` make that work) and continue.
- Warming loads weights into a **machine-shared** Ollama, so it can raise memory
  pressure for a sibling instance. That is inherent to warming; the mitigations are
  that it is opt-in per invocation, never default, and never triggered by `status`
  (F15).

---

## 12. Ruling 7 — the exit-code contract (gap 9)

### 12.1 Canonical codes

Deliberately **additive**: no existing non-zero code is renumbered, because
`tests/instance_start_driver.sh` pins `1` for the claim race and the instance
ceiling and `2` for bad flags/unknown slug (A12). Taxonomic purity is not worth
breaking the protected baseline.

| Code | Meaning | Where it already exists |
|---|---|---|
| `0` | success / affirmative verdict | everywhere |
| `1` | failure or refusal — we could not do the thing, or refuse to (no `.venv`, daemon active, claim held, ceiling, bind conflict, multiple live instances with no target) | `start.sh`, `reset.sh`, `arailctl` |
| `2` | usage error — bad flag, missing flag value, invalid slug, ambiguous target that requires an explicit flag | `start.sh`, `reset.sh` |
| `3` | **degraded** (new) — partially up / a phase refused / pending changes (`--check`) | new |
| `4` | **nothing running** (new, `status` only) | new |
| `130` / `143` | SIGINT / SIGTERM | `_instance_cleanup_and_exit` |

`stop` deliberately exits `0` when there was nothing to stop: a stop verb's
contract is the post-condition ("it is down now"), and `restart` chains on it.

### 12.2 Testability

The contract is executable, not prose: `tests/cli/verbs_driver.sh` walks a matrix
of (verb × flags × environment) and asserts the exact code for every row in §5,
including both tty and non-tty invocations (piped stdout/stdin for the non-tty
half). `docs/cli.md` carries the same table for humans, and a cheap test asserts
every verb in `arailctl`'s `case` statement appears in `docs/cli.md` (drift guard).

### 12.3 Behavior changes to announce in CHANGELOG

- `status` now exits `3`/`4` instead of always `0`.
- `arailctl upgrade` with no argument exits `0` (prints tier) instead of `1`.
- `setup` rejects unknown flags (`2`) instead of ignoring them.
- `start` in daemon mode with `--world`/`--root` refuses (`1`) instead of
  kickstarting the root daemon.
- `install --check` exits `3` when changes are pending.
- Root-lab `start` now exits `1` when the portal never comes up (previously it
  printed success and blocked forever).

---

## 13. Ruling 8 — the polish list (gap 10)

| Item | Ruling |
|---|---|
| `doctor`'s `for bin in uvicorn` single-item loop | Replace with a direct `command -v uvicorn` check that feeds the new findings tally (§12) — the loop's disappearance and the exit contract are the same edit |
| shellcheck SC2024 (`sudo cmd >> "$log"`) in `setup.sh` | **Annotate, do not restructure.** The redirect running as the *invoking user* is the correct behavior — `setup.log` must stay user-owned. "Fixing" it with `sudo sh -c '… >> log'` would create a root-owned log that later user-mode appends cannot write (F23). One file-level `# shellcheck disable=SC2024` with that rationale, next to the existing directive block |
| `setup` prints the passphrase to stdout | Mask when `--quiet` **or** `ARAIL_QUIET=1` **or** `! [[ -t 1 ]]`. The non-tty case is the real one: CI redirects setup's stdout to a file and then has a *redaction step* to scrub it — masking at the source makes that belt-and-braces. Masked line still says where it lives (`.env` → `ARAIL_PASSWORD`, `lab.conf` → `IDE_PASSWORD`) so nothing becomes unrecoverable. Builder must grep `tests/setup_ladder/`, `tests/test_setup_extras.py`, `tests/test_qa_airgap_toggle_setup_happy.py` for assertions on the printed passphrase before landing |
| duplicate `kb help` heredocs in `arailctl` | One `kb_usage [<kb_root>]` function; the discovered-root variant just gets the root argument. Output text preserved (it is user-facing documentation) |
| ANSI leaks into non-tty output | **Inline conditional per script — no new lib file.** `if [[ -t 1 && "${ARAIL_COLOR:-auto}" != "never" && -z "${NO_COLOR:-}" ]] || [[ "${ARAIL_COLOR:-auto}" == "always" ]]; then <literal codes>; else <empty strings>; fi`. Rationale: a shared `lib/tty.sh` would add a `source` dependency to `reset.sh`, which is unit-tested as a **standalone sandboxed copy** (`tests/test_reset_paths.py`) — precisely the `source <missing-file>` landmine class this repo has already been bitten by twice (A2). Colors are static presentation, not logic; seven copies of a 4-line conditional carry near-zero drift risk, while seven new `source` sites carry a known one. Applies to `arailctl`, `start.sh`, `status.sh`, `reset.sh`, `setup.sh`, `update.sh`, `upgrade.sh`, and the new `install.sh`. `arailctl:141`'s inline `printf '\033[1m'` inside the usage heredoc is converted to a variable so it participates |
| (found while reading) `status.sh:5` uses logical `pwd` while `start.sh:9` uses `pwd -P` | Align `status.sh` to `pwd -P` with the same REVIEW.md m5 rationale comment. Without it, the new root identity check (`checkout == $REPO_ROOT`) reports `foreign` on any checkout reached through a symlinked path (F2) |

---

## 14. Interface contracts

### 14.1 `arailctl` → subscripts

| Contract | Rule |
|---|---|
| argv | Passed **verbatim**. `arailctl` may *inspect* argv (read-only scan, as `start`'s B2 loop already does) and may *prepend* a resolved target (`restart` only). It must never re-parse, validate, or rewrite flags — that is the subscript's job, and a second parser is how the B2 bug happened |
| exit code | `exec bash scripts/X.sh "$@"` ⇒ the child's code **is** the CLI's code. Where `exec` is impossible (`restart`'s two-phase stop→start), the stop's code is checked explicitly and the start is `exec`'d, so the final code is still the child's |
| env in | `REPO_ROOT` (absolute, symlink-resolved, exported), `INVOCATION_PWD` (exported), plus everything `.env` exports (`arailctl` does `set -a; source .env; set +a`) |
| env NOT in | `lab.conf` is **not** sourced by `arailctl` except inside the daemon `start` branch. Every subscript that needs ports sources it itself, **always** as `[[ -f lab.conf ]] && set -a && source lab.conf && set +a` (the bash-3.2 guard — A2). New scripts must follow this exactly |
| cwd | `$REPO_ROOT` |
| stdout/stderr | Machine output (JSON) → stdout, alone. Notices, deprecations, diagnostics → stderr. `--json` on any verb implies no human decoration on stdout |

### 14.2 `scripts/*` → `scripts/lib/*`

| Contract | Rule |
|---|---|
| `instances.sh` | Remains **the** source of truth for the instance registry, `inst_alive`, `inst_probe_matches`, `daemon_active`, `daemon_plist_installed`. No caller re-derives them. Sourced (never executed), requires `REPO_ROOT` pre-set, side-effect-free on source |
| `services.sh` (new) | Root-lab per-service probing only (§8.1). Requires `REPO_ROOT`; obtains `_port_in_use` via `inst_load_port_helpers` (so `setup.sh` stays the one implementation); never touches the registry, never re-derives daemon liveness; side-effect-free on source; every function safe inside `$( )` under `set -euo pipefail` |
| Sourcing discipline | Mandatory `[[ -f <path> ]] &&` guard, or a hard `die` when the file is genuinely required. `reset.sh`'s optional-source pattern (line 28) is the reference for files that must survive being copied out of the tree by a test |
| bash 3.2 | No associative arrays, no `readarray`/`mapfile`, no `${var,,}`/`${var^^}`, no `local -n`, no `declare -A`. Collections cross function boundaries as newline- or TAB-delimited stdout consumed by `while IFS= read -r`. Every `while read` collector ends with an explicit `return 0` (the errexit-at-EOF landmine already documented at `status.sh:110-116`) |

### 14.3 `install.sh` → `update.sh`

New argv mode on `update.sh` (additive; the existing interactive path is
untouched): `update.sh --apply --non-interactive [--force] [--component <n>]`
⇒ no prompts, no `read`, per-component `warn`+continue, exit `0` (all good / all
recoverable), `3` (≥1 component failed), `1` (manifest unreadable). `install.sh`
maps `3` → its own degraded verdict.

### 14.4 CLI → portal HTTP

| Endpoint | Used by | Contract |
|---|---|---|
| `GET /api/instance` | instance stage `[6/8]` (unchanged), `inst_probe_matches` (unchanged), **new** root readiness gate, **new** root status probe, **new** `--warm` poll | Allow-listed pre-onboarding (A6). Root: `slug=="root"`, `token==null`. Fields added by this sprint (`warm`, `warm_ms`, `warm_skipped`, `backend`) are **additive**; every consumer must tolerate their absence (older portal, mid-upgrade) |
| `GET /health` | root memory + mlx probes (`--probe`), instance stage `[7/8]` (unchanged) | Allow-listed; liveness only |
| `GET /api/jobs/state` | existing scheduler section of `status` | unchanged; not allow-listed pre-onboarding, so its absence must stay non-fatal (it already is — guarded by `curl -sf`) |
| everything else | — | Not used by the CLI. In particular **no new endpoint is added**, and nothing anonymous triggers inference (§11.1) |

---

## 15. Failure modes

| # | Failure | Detection | Recovery |
|---|---|---|---|
| **F1** | Root readiness gate kills a process it does not own (e.g. the foreign squatter on `:8080`) | Kill list is `${PIDS[@]}` — only pids this shell spawned. Test asserts a foreign listener survives a failed root start | Report the port + `lsof -iTCP:<port> -sTCP:LISTEN` hint, exit 1, never signal a non-owned pid |
| **F2** | `status.sh`'s logical `pwd` ≠ portal's physical cwd ⇒ every root probe reports `foreign` on a symlink-reached checkout | Test: run `status` through a symlinked repo path, assert `root.state=="up"` | `pwd -P` in `status.sh` (§13), with the REVIEW.md m5 rationale |
| **F3** | Half-written `lab.conf` (interrupted `setup`) ⇒ non-numeric `PORTAL_PORT`, or a `source` failure | New readers validate `^[0-9]+$` before use; `[[ -f ]]`-guarded source | Warn once, fall back to the documented default, record in `warnings[]`; never abort |
| **F4** | `source <missing-file>` aborts a non-interactive bash 3.2 shell even under `|| true` (regression risk in every new script) | `tests/shell_source_safety_driver.sh` extended to cover `install.sh` and `services.sh`; fresh-checkout scenarios in the CLI harness | Mandatory `[[ -f ]]` guard (§14.2) |
| **F5** | `git pull` during `install` replaces `install.sh`/`arailctl` **while bash is still reading them** ⇒ half-old/half-new execution | HEAD sha compared before/after the source phase | `exec bash "$REPO_ROOT/scripts/install.sh" --_post-source <old-sha> <original argv>` immediately after a moving pull; the marker prevents a re-exec loop, and the remaining phases run entirely from new code |
| **F6** | `install`'s source phase eats local work (dirty tree, detached HEAD, diverged branch, no upstream) | `git status --porcelain`, `rev-parse --abbrev-ref @{u}`, `symbolic-ref -q HEAD`, `pull --ff-only` exit | Refuse the phase with the named reason, continue other phases, verdict `3`. **Never** `stash`/`reset`/`clean`/`merge`/`rebase` |
| **F7** | `brew`/`apt`/`npm` absent or failing during the components phase | `update.sh`'s existing per-component `warn`+continue; its new `--apply` mode returns `3` | Degraded verdict, exit 3, named components listed. Never exit 1 for an optional component |
| **F8** | A new verb prompts with no tty ⇒ a CI job hangs forever | Harness runs **every** verb with stdin `</dev/null` and stdout piped, under a hard `_timeout`, asserting no hang | `! [[ -t 0 ]]` ⇒ default-yes (mutating confirmations) or exit 2 (ambiguous target). No `read` outside a `[[ -t 0 ]]` branch |
| **F9** | Daemon-mode edge cases: (a) `restart --world X` kickstarts the root daemon instead of the World; (b) plists installed but unloaded routes to the wrong path | `daemon_active` (both plist **and** live PID) is the only predicate; new refusal branch for `--world`/`--root` in `arailctl`'s daemon arms | (a) refuse, exit 1, naming the slug + `uninstall-daemon` path; (b) `daemon_plist_installed`-only ⇒ foreground with the existing notice |
| **F10** | Probe race: `status` samples a port mid-stop/mid-start and reports a transient `down`/`foreign` | Inherent to snapshots | No destructive action is ever keyed on an HTTP probe. `inst_prune_all` remains keyed on the PID predicate only (`inst_alive`), never on a probe result |
| **F11** | A World whose slug is literally `root` collides with `--root` semantics | `--root` never consults the catalog; `--world root` never means the root lab | Picker prints a disambiguation line when such a bundle exists; `docs/cli.md` states the rule |
| **F12** | `restart` with ≥2 live instances silently picks one | Explicit branch | exit 2 listing `restart --world <slug>` per live instance + `--root` |
| **F13** | `restart` stops the target, then the start fails ⇒ the lab is down and the operator does not realize the state changed | Non-zero from the `exec`'d start is the process's code; the pre-`exec` notice is printed unconditionally | Print `'<target>' was stopped; the start failed — the lab is now DOWN` **before** `exec`, so it survives the exec |
| **F14** | `--warm` hangs or blocks the start | Hard `ARAIL_WARM_TIMEOUT_SEC` cap; runs strictly after the record + banner | One `⚠` line, exit code untouched |
| **F15** | Warm-up pressures a sibling instance's memory via the shared Ollama | Inherent to warming a shared daemon | Opt-in per invocation, never default, never from `status`; documented in `docs/cli.md` |
| **F16** | The new `/api/instance` fields leak something | Fields are booleans/ints/backend-class only; no model id, no path, no secret. `tests/test_instance_isolation_audit.py`'s token-is-not-a-credential invariant still applies | Reviewer checklist item; test asserts the field set exactly |
| **F17** | New `status` exit codes break an unknown consumer | Grep found none in `.github/`, `tests/`, `scripts/`, `src/` (A9); CI's only CLI calls are `setup`, `doctor`, `start --world`, `stop \|\| true` | CHANGELOG behavior-change entry; `--json=instances` preserves the old *output* shape for scripts that only parsed stdout |
| **F18** | `--json` prints a human error line ⇒ downstream `jq` explodes | Harness runs `status --json` with a `chmod 000` `registry.d`, a corrupt record, and no `.venv`, asserting `python3 -m json.tool` succeeds every time | Collector failures land in `warnings[]` + `verdict.code`; the document is always emitted |
| **F19** | bash 3.2 trap: someone reaches for an associative array for the service table, or `readarray` for the collector | Harness runs every driver under `/bin/bash` explicitly (macOS 3.2 where available) | TAB-delimited stdout + `while IFS= read -r`; one `python3` pass builds the document |
| **F20** | `while read` collector returns non-zero at EOF and aborts a `$( )` assignment under `set -e` (the exact bug documented at `status.sh:110`) | Zero-instance / zero-service scenarios in the harness | Every collector ends `return 0` |
| **F21** | `install --rebuild-venv` deletes `.venv` out from under a running lab | Preflight: `inst_any_alive` **or** the root portal answers | Refuse, exit 1, name what is live and the stop command; `--allow-running` for an operator who insists |
| **F22** | `install`'s deps phase `pip install`s under a running uvicorn ⇒ half-imported modules in a live process | Same preflight as F21 | Same refusal |
| **F23** | The "obvious" SC2024 fix (`sudo sh -c '… >> log'`) creates a root-owned `setup.log` that later user-mode appends cannot write | Reasoned, not detected | Annotate the warning, do not restructure (§13) |
| **F24** | Passphrase masking hides a secret the operator genuinely needs | Masked line names both files that store it | Documented recovery: `grep ARAIL_PASSWORD .env` |
| **F25** | Color gating breaks someone's colored logs, or `NO_COLOR` fights an operator who wants color | `ARAIL_COLOR=always\|never\|auto` overrides both tests | Documented in `docs/cli.md` |
| **F26** | The test harness binds real ports and collides with CI parallelism or the developer's own lab | Harness allocates a per-run random high port (≥18000), verifies it free via `lsof` before use, and **never** uses 8080/8090 | Hard harness requirement; asserted by a self-check inside `tests/cli/lib.sh` |
| **F27** | The test harness kills the developer's real lab (`reset.sh stop`'s pre-upgrade fallback pattern matches port-only) | Fallback only matches argv **without** `--app-dir`, and only on the fake repo's randomized port (F26) | Randomized ports are load-bearing for safety, not just isolation — stated in the harness header; a driver self-check refuses to run if `PORTAL_PORT` resolves to 8080 |
| **F28** | `install` run inside a **git worktree** (this sprint's own environment) pulls the wrong thing | `git rev-parse --git-dir` / `--show-toplevel` reported in the phase output | Print branch + toplevel before pulling; `--ff-only` cannot cross branches |
| **F29** | `BIND_ADDR=0.0.0.0` ⇒ probing `http://0.0.0.0:<port>` is unreliable on macOS ⇒ false `down` | `svc_probe_host` normalizes `0.0.0.0`/`::`/empty → `127.0.0.1` | Probe loopback, display the configured URL |
| **F30** | Missing `curl`/`lsof`/`ss` reported as "service down" ⇒ a false alarm on a minimal box | Helpers return a distinct "undetectable" state (`2` / `null`) | `state: "unknown"` + a `warnings[]` entry; **never** contributes to the degraded verdict (A4) |
| **F31** | Root portal readiness passes because a *previous* root lab from this same checkout is still listening (double-start) | Identity check passes (same checkout!), so the gate would say ✓ while our new uvicorn actually failed to bind | The gate early-outs when **our** spawned pid dies; additionally the pre-spawn `_port_in_use` check on `PORTAL_PORT` refuses before spawning, with the "already running — `./arailctl status`" message. (The instance path already has this at stage `[5/8]`; the root path has never had it — added) |
| **F32** | `install daemon` (typo for `install-daemon`) starts refreshing the whole lab | Positional-argument rejection in `install.sh` | exit 2 + `did you mean: ./arailctl install-daemon?` |
| **F33** | `docs/cli.md` drifts from the real verb list | Test asserts every `case` arm in `arailctl` appears in `docs/cli.md` | Cheap grep test in the same WP as the doc |

---

## 16. Test strategy

QA allocation for this sprint (per repo `CLAUDE.md`, with the Buddy share
reallocated — no Buddy surface is touched; record the reallocation in
TEST_REPORT.md): **35 % setup/lifecycle · 20 % security · 30 % regression
(protected baseline) · 10 % happy path · 5 % performance**.

### 16.1 The `tests/cli/` harness

Modeled directly on `tests/instance_start_driver.sh` (real scripts, throwaway repo,
stub PATH, portable `_timeout` via the venv python, isolated `HOME` so a
developer's real launchd plist cannot leak in). One shared library plus one driver
per concern, each with a thin pytest wrapper that skips when no venv is available
(the `tests/test_instance_start.py` pattern).

```
tests/cli/
  lib.sh                # make_fake_repo / make_stub_bin / _timeout / random port
                        # allocator (F26,F27) / registry-record builder / run_ctl
  stub_uvicorn_serving  # NEW capability: a stub that ACTUALLY BINDS and serves
                        #   /api/instance (JSON from a fixture file, so slug /
                        #   checkout / warm can be dialed per scenario) and
                        #   /health 200; dies cleanly on SIGTERM
  verbs_driver.sh       # the §5 exit-code matrix, tty and non-tty
  status_driver.sh      # unified status model + schema v2 + v1 rows compat
  root_start_driver.sh  # root readiness gate, crash detection, no pid leak
  restart_driver.sh     # scoped stop, registry-aware target, refusals
  install_driver.sh     # phases against a local bare git "remote"
  color_driver.sh       # ANSI-free piped output, NO_COLOR, ARAIL_COLOR
tests/test_cli_verbs.py  test_cli_status.py  test_cli_root_start.py
tests/test_cli_restart.py  test_cli_install.py  test_cli_color.py
```

The **serving** stub is the enabling piece: without it, gaps 4/5/6 are untestable
without a real portal. It is ~30 lines of `python3 -m http.server`-style code and
it is what turns "the URL only prints when it answers" into an assertion.

### 16.2 Numbered tests

Regression / protected baseline (must be green before **and** after every WP):

- **T1** `tests/instance_start_driver.sh` and `tests/instance_qa_driver.sh` pass
  unchanged — the 8-stage boot, claim race, ceiling, bind conflict, slug jail,
  port-override validation. *(baseline; guards every WP)*
- **T2** `tests/test_instance_readiness_probe.py`, `test_instance_stop_scope.py`,
  `test_instance_isolation*.py`, `test_daemon_predicate.py`,
  `test_reset_paths.py`, `test_shell_source_safety.py` pass unchanged.
  *(baseline; F4, F19)*
- **T3** `status`'s instance table still renders `live`/`stale`/`unreadable`, still
  detects `--probe` checkout mismatch, still prunes **after** rendering, still
  distinguishes daemon-active from plist-installed-inactive. *(baseline, gap 4/8
  regression net)*
- **T4** Fresh checkout (no `.venv`, no `lab.conf`): `status`, `status --json`,
  `start`, `install` all produce a helpful named message and **do not** crash
  under bash 3.2. *(baseline + F3, F4)*
- **T5** `stop --world <slug>` still stops verified processes only and cleans the
  record; an unverified pid is still skipped, not killed. *(baseline)*
- **T6** `setup`'s 11 steps, port-bump pinning into `lab.conf`, PATH shim, and
  final summary unchanged (existing `tests/setup_ladder/`, `test_setup_extras.py`).
  Plus: the passphrase does **not** appear on stdout when stdout is a pipe.
  *(baseline + gap 10, security)*

Exit-code contract:

- **T7** Every row of §5's exit-code column, asserted for both tty and non-tty
  invocation. *(gap 9, F8)*
- **T8** `status` verdicts: nothing running → `4`; one live instance → `0`; live
  instance + stale record → `3`; foreign process on the root portal port → `3`;
  bad flag → `2`; unreadable `registry.d` → valid JSON + `1`. *(gap 9, F18)*
- **T9** `doctor`: healthy → `0` **with `ttyd`/`code-server`/model absent** (the CI
  invariant, A8); `uvicorn` removed from PATH → `3`; `.venv` absent → `1`;
  `--strict` with an optional binary missing → `3`. *(gap 9/10, A8)*

Unified status:

- **T10** With a live World instance and no root lab: exactly one `root lab: not
  started` line, **zero** "not running" service rows, verdict `0`. *(gap 4)*
- **T11** URL honesty: a service whose port is not listening prints no URL and has
  `url: null` in JSON; a listening one prints both. Serving stub on the portal port
  with a foreign `checkout` ⇒ `root.state == "foreign"` + `lsof` hint + `3`.
  *(gap 5, F2, F29)*
- **T12** `--json` schema: validates against the §7.3 key set; `jq .instances`
  equals `--json=instances` output byte-for-byte; `--json=bogus` → `2`; sizes
  absent from JSON. *(gap 8)*

Root readiness:

- **T13** Serving stub ⇒ per-service `✓` lines, `All services running`, exit path
  reaches `wait`. *(gap 6)*
- **T14** Crashing stub uvicorn ⇒ `✗` on portal, the last-HTTP-status diagnostic
  when the stub answers 401, **no** `All services running`, exit `1`, and **no
  orphaned children** (`pgrep` against the fake repo's randomized ports is empty
  after exit). *(gap 6, F1, F31)*
- **T15** Portal ✓ but notebook port silent ⇒ `⚠`, banner says `degraded:
  notebook`, the Notebook URL is **absent** from the URL block, process still runs.
  *(gap 6)*
- **T16** A pre-existing listener on `PORTAL_PORT` ⇒ refusal **before** any uvicorn
  is spawned, with the "already running — `./arailctl status`" message; the foreign
  listener survives. *(F31, F1)*
- **T17** Daemon-active `start`: readiness gate reports `✓`+URL when the stub
  answers, `✗`+`1` and the log hint when it does not; `start --world x` under an
  active daemon refuses (`1`) naming the slug. *(gap 6, F9)*

`--root` / restart:

- **T18** With ≥2 Worlds and no tty: `start --root` starts the root lab
  (previously impossible); bare `start` still exits `2` and its refusal now lists
  `--root`. `start --root --world x` → `2`. *(gap 2)*
- **T19** `restart --world a` with `a` and `b` both live: `b` survives (registry
  record intact, pid alive) — the gap-3 regression net. *(gap 3, F12)*
- **T20** Bare `restart`: 1 live instance → that instance; 0 live → behaves like
  `start`; ≥2 live → `2` listing each command; `--all` → `2` with the explanation.
  All non-tty. *(gap 3)*
- **T21** `restart` whose stop phase fails ⇒ start not attempted, `1`; whose start
  fails after a successful stop ⇒ the "lab is now DOWN" line appears. *(F13)*

Warm-up:

- **T22** Python: `_warm_primary_router` records `warm_ms` and backend; boot runs
  the warm when `ARAIL_TIER0_BOOT_WARM=1` with autochecks **off**, and does **not**
  when both are unset (quiet boot preserved); `=0` still disables. `/api/instance`
  exposes exactly `warm`, `warm_ms`, `warm_skipped`, `backend` and **no** model id.
  *(gap 7, F16)*
- **T23** CLI: `--warm` against a stub reporting `warm=false` forever ⇒ one `⚠`
  line after the cap, exit code **unchanged**; against `warm=true` ⇒ the `✓` line
  with a duration; absent fields (old portal) ⇒ graceful line, no crash.
  *(gap 7, F14)*

`install`:

- **T24** Clean tracking branch behind a local bare remote ⇒ ff pull, sha range
  printed, and the re-exec actually happens (assert a marker only the *new*
  script prints). *(gap 1, F5)*
- **T25** Refusals: dirty tree · detached HEAD · no upstream · diverged ·
  `LAB_MODE=airgapped` — each names its reason, continues other phases, exits `3`,
  and leaves the worktree byte-identical (no stash/reset). *(gap 1, F6)*
- **T26** Live-lab preflight: with a fake live instance record, `install` and
  `install --rebuild-venv` refuse with `1` and `.venv` still exists;
  `--allow-running` proceeds. *(F21, F22)*
- **T27** `install --check` with a pending component ⇒ `3`, nothing mutated;
  up-to-date ⇒ `0`. `install daemon` ⇒ `2` + the `install-daemon` hint. Unprovisioned
  lab ⇒ `1` + the `setup` command. *(gap 1, F32)*
- **T28** Aliases: `update` runs the install phases with its notice **on stderr**
  (stdout stays valid JSON under `--json`); `update --component ttyd` still reaches
  the old interactive path; `upgrade maximus` still switches tier; `upgrade` with no
  arg prints the tier and exits `0`; `tier` prints the tier. *(gap 1, §6.4)*

Security (20 %):

- **T29** No new pre-onboarding endpoint: assert `onboarding_gate`'s allow-list is
  unchanged by this sprint (exact tuple comparison) — the warm signal rides on the
  already-allowed `/api/instance`. *(F16)*
- **T30** No `secrets.env` is ever read, copied, linked, or referenced by any new
  code path (`install.sh`, `services.sh`, the status collector) — grep-based
  assertion, mirroring the existing per-instance secrets invariant.
- **T31** No new code path signals a pid it did not spawn or verify: assert every
  `kill` in `start.sh`'s root path targets `${PIDS[@]}` only, and that
  `services.sh` contains no `kill`/`pkill`/`pgrep` at all. *(F1)*
- **T32** Ollama untouched unless we started it: `install`, `status`, and the root
  readiness gate never `kill`/`brew services stop` ollama; the pidfile rule is
  unchanged.
- **T33** Passphrase never on stdout in non-tty `setup`; no secret in
  `status --json` beyond the already-audited instance `token` (whose
  not-a-credential invariant test stays green).

Performance (5 %):

- **T34** `status` (default, 3 registered instances, none live) completes in < 2 s
  — the existing win condition, now with probes added. `status --no-probe` and
  `status --json` measured separately; `--json` must not run `du`. *(gap 5 cost
  control)*

Happy path (10 %):

- **T35** Golden path on a clean fake repo: `setup`-equivalent fixture →
  `start --root --no-browser` → `status` (`0`) → `restart --root` → `stop --root`
  → `status` (`4`). Every step non-tty, every exit code asserted.
- **T36** `.github/workflows/blueprint-smoke.yml` still passes: `doctor` exits `0`
  on the runner, `start --world ai --port 8080` still boots, `stop || true` still
  works. (Run the workflow logic locally where feasible; otherwise this is a
  reviewer checklist item before merge.)

---

## 17. Work packages

Each is independently buildable, independently reviewable, and lands as one atomic
commit. Ordered so that every WP leaves `main` shippable.

| WP | Title | Touches | Depends on | Gates |
|---|---|---|---|---|
| **WP1** | Foundations: color gating, exit-code doc, polish list | `arailctl` (colors, `kb_usage`, doctor loop + findings tally), `scripts/{setup,start,status,reset,update,upgrade}.sh` (color blocks), `setup.sh` (`--yes`/`--quiet`/unknown-flag/passphrase mask/SC2024 note), `src/arail/doctor.py` (findings tally + `--strict`), **new** `docs/cli.md`, `tests/cli/lib.sh`, `tests/cli/{color,verbs}_driver.sh` | — | T6, T7, T9, T33, T35 partial, F33 |
| **WP2** | `scripts/lib/services.sh` + root-lab readiness gate | **new** `scripts/lib/services.sh`, `scripts/start.sh` (root block: early trap, pre-spawn port check, readiness phase, honest banner), `arailctl` (daemon-branch readiness) | WP1 | T13–T17, F1, F31, F30, F29 |
| **WP3** | `--root` for start / stop | `scripts/start.sh` (`ROOT_ONLY`, picker text), `scripts/reset.sh` (`--root` arm) | WP2 | T18, F11 |
| **WP4** | `restart` redesign | `arailctl` (restart branch: target resolution, scoped stop, daemon refusal, DOWN notice) | WP3 | T19–T21, F9, F12, F13 |
| **WP5** | Unified `status` + schema v2 + verdict codes | `scripts/status.sh` (collector → doc → renderer, probes, flags, `pwd -P`), `docs/concurrent-worlds.md` (`--json=instances`) | WP2 | T3, T8, T10–T12, T34, F2, F18, F20 |
| **WP6** | Warm-up | `src/arail/portal/app.py` (`_warm_primary_router` timing + explicit gate, `/api/instance` fields), `scripts/start.sh` (`--warm` both paths), `arailctl` (daemon hint) | WP2 | T22, T23, T29, F14–F16 |
| **WP7** | `install` verb + consolidation | **new** `scripts/install.sh`, `scripts/update.sh` (`--apply --non-interactive` mode), `arailctl` (dispatch: `install`, `update`→alias, `tier`, `upgrade`→alias, usage/header rewrite) | WP1, WP5 (uses the live-lab preflight built on the status collector) | T24–T28, F5–F7, F21, F22, F28, F32 |
| **WP8** | Docs + CHANGELOG | `docs/cli.md` (final), `README.md`, `docs/INSTALL.md`, `CLAUDE.md` verb list, `CHANGELOG.md` (§12.3 behavior changes), `AGENTS.md` if the setup flag surface changed | WP1–WP7 | F33, §6.4 migration note |

Recommended commit sequence: **WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → WP7 → WP8.**
WP6 and WP7 are the only pair that could be reordered; WP7 last-but-one is
preferable because its live-lab preflight reuses WP5's collector rather than
growing a second liveness check.

---

## 18. Tech debt assessment

### Added (each with a home)

| Debt | Why accepted | Follow-up |
|---|---|---|
| Two readiness-poll implementations: stage `[6/8]`'s inline loop and `svc_wait_http_ready` (~15 lines of overlap; identity logic differs by design — A7) | The mandate is to protect the verified baseline, not refactor its most load-bearing 40 lines | Backlog item: "adopt `svc_wait_http_ready` in `_instance_start` stage `[6/8]`". Preconditions: `tests/instance_start_driver.sh` + `tests/test_instance_readiness_probe.py` green, and stage output byte-identical |
| `install.sh` learns the expected default model name (a 4th place after `setup.sh`, `models/ai-eng/Modelfile.default`, `model_defaults.yaml`) | Extracting a single source means restructuring `setup.sh`'s 200-line Ollama block — a separate, riskier change | Backlog item: "one source of truth for the shipped default model id" (candidate: `[tool.arail.models]` in `pyproject.toml`, read by both) |
| Two names for the tier axis (`tier` + `upgrade`) and two for refresh (`install` + `update`), indefinitely | Removing a verb from a blueprint people have forked breaks their scripts silently | None — deliberate, documented, permanent |
| `docs/cli.md` is a hand-maintained mirror of the verb matrix | Generating it from the `case` statement is more machinery than it is worth | Mitigated now by the drift test (F33) |
| Color-gating conditional duplicated in 8 scripts | A shared `lib/tty.sh` would add a `source` dependency to `reset.sh`, which is tested as a standalone copy — the known `source <missing-file>` landmine class (A2) | None; revisit only if a `lib/` source becomes mandatory for other reasons |

### Unanticipated (found during the review-fix pass, required action #9)

REVIEW.md's original pass (§8) and its re-review (§R6.1) both required these be
filed as the condition of a clean PASS rather than a WEAK_PASS. All seven now
have a home in `sprints/BACKLOG.md` (one entry each, named below):

| Debt | Why accepted | Follow-up |
|---|---|---|
| `status.sh` runs under `set -uo pipefail` — no `-e` — an undocumented posture change from a 782-line rewrite (m4) | Probe helpers return nonzero as DATA (down/unreadable/unknown), not failure; running the whole file under `-e` would turn every expected-degraded state into an undiagnosed abort (F20's exact bug class). Documented as a landmine note in the file header | `sprints/BACKLOG.md` — "`status.sh`'s deliberate `set -e` omission" |
| `install`'s live-lab preflight shells out to `status.sh --json=full`, whose read path (`inst_list_slugs`/`inst_prune_all`) prunes stale registry records as a side effect — a "read-only" preflight that mutates state | Correct-ish (`inst_prune`'s own contract: only removes provably-dead records) but surprising for a preflight check | `sprints/BACKLOG.md` — "`install`'s preflight silently mutates the registry" |
| `scripts/lib/services.sh`'s `[[ -f ]]`-guarded source (in `start.sh`/`status.sh`/`arailctl`) degrades WITHOUT crashing when the file is missing (F4 holds — confirmed by this pass's own driver extension), but the degrade is not USEFUL — every root start still fails, just with a worse message (n6) | A real hard-dependency-vs-honest-degrade design decision, not a fix-if-trivial line change | `sprints/BACKLOG.md` — "`services.sh`/`setup.sh`: hard dependency or a real degrade" |
| `install --json` emits no JSON on its three early exits (unprovisioned, lab live, bad flag) — unlike `status --json`'s F18 doctrine (n4) | A documented scope trim (§5.1 names the schema; no numbered test requires early-exit JSON); the two `--json` verbs now behave differently under failure | `sprints/BACKLOG.md` — "`install --json`'s early-exit paths emit no JSON" |
| `start --warm`/`restart --warm` `export ARAIL_TIER0_BOOT_WARM=1` leaks into every subsequently spawned child (memory service, ttyd, jupyter, code-server), not just the portal (n7) | Harmless today (only the portal reads it); an inline per-invocation prefix instead of `export` would need touching every spawn call site for one cosmetic tightening | `sprints/BACKLOG.md` — "`ARAIL_TIER0_BOOT_WARM`'s export blast radius" |
| `stop --root`/`restart --root` can still stop a live World instance during ITS OWN `[6/8]`→`[8/8]` boot window if it shares the root's configured port — the review-fix pass's B2 exclusion set is built from WRITTEN registry records only, and write-after-ready (`start.sh:948`, after the portal spawns at `:807`) is a protected invariant from the Concurrent-Worlds sprint that must not change | Much narrower than the shipped B2 bug (which fired unconditionally); requires a same-port collision AND a concurrent boot. The cheap close (consulting the pre-spawn `.claim` file) is real but is itself a change adjacent to a protected write-ordering invariant — deserves its own review cycle, not a rider on this fix pass | `sprints/BACKLOG.md` — "B2's residual: `stop --root` during a same-port World's boot window" |
| `tests/test_reset_stop_scope.py`'s 2 pre-existing failures (`_ollama_pid_if_we_started_it: command not found`, an unrelated awk-extraction gap) mean the *unit*-level test of `stop_services`'s scoping does not exercise the review-fix pass's new instance-exclusion clause — only the driver-level B2 scenarios do | Pre-existing, unrelated to this sprint's own changes (confirmed: the new code is correctly outside the extracted range); the driver-level coverage is real (confirmed fail-pre-fix), just not doubled at the unit level | `sprints/BACKLOG.md` — "`test_reset_stop_scope.py`'s pre-existing failure leaves B2 unit-untested" |

### Repaid

- The `pgrep`-pattern service check (port-agnostic, cross-checkout-fragile) stops
  being a verdict source.
- The "Portal not running" contradiction and the lying URL block are gone.
- The root-lab path gains failure detection it has never had, plus a cleanup trap
  armed before anything can fail, plus a pre-spawn port check.
- `restart` stops being able to kill a sibling World.
- The whole CLI gains a documented, executable exit-code contract where there was
  none.
- Polish: single-item loop, duplicate heredocs, ANSI in pipes, passphrase in
  redirected logs, SC2024 noise.
- `status.sh`'s logical-vs-physical `pwd` inconsistency with `start.sh` (a latent
  false-`foreign` bug the moment identity checking arrives).

### Deliberately NOT fixed by this sprint (named so nobody assumes otherwise)

- Multi-instance / backgrounded `restart --all` and per-instance supervision
  (needs a supervisor — §3.2).
- `upgrade.sh` runs `pip install` without honoring `LAB_MODE=airgapped`.
- `reset` still does not touch instance data; repo-root `instances/` vs
  `lab/instances/` remain unreconciled (both already in `sprints/BACKLOG.md`).
- `doctor --json`.
- No shellcheck job exists in CI, so the SC2024 annotation is local hygiene only;
  adding a lint workflow is out of scope.
- Windows/PowerShell parity for any of the new verbs.

### Net

**Negative** (debt reduced). The two structural additions (a second readiness-poll
shape, a fourth model-name reader) are both small, both fenced by tests, and both
carry a named follow-up — against which the sprint retires one wrong verdict
source, two dishonest outputs, one sibling-killing bug, and an entire undefined
exit-code surface.
