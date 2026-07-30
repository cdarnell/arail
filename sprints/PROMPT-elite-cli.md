# Prompt: plan the "Elite CLI" sprint for arailctl

> Feed this to `/sprint` (or the architect subagent directly) in the ARAIL
> repo. It captures the 2026-07-29 live review of `arailctl
> setup/start/restart/status` — what already works (don't regress it) and
> what to build. Verified on a clean worktree: fresh `.venv` build, full
> 8-stage `start --world ai` boot, token/checkout readiness probe,
> attach-on-running, `status`/`status --probe`/`status --json`, clean
> `stop --world`, registry prune. All green.

## Mission

Make `./arailctl` an elite operator CLI: one obvious verb for every
lifecycle moment (install → setup → start → status → restart → stop →
update), every verb non-interactive-safe, machine-readable, honest about
ports/URLs, and fast. ARAIL is a blueprint others run on clean machines —
the CLI *is* the product's first impression.

## Verified baseline (protect with regression tests, do not redesign)

- `start --world <slug>`: 8-stage launch with per-stage ✓/✗, token+checkout
  readiness probe on `/api/instance`, memory `/health` probe, Ollama
  shared-daemon ownership rules, claim file with EXIT-trap cleanup,
  registry record written only after readiness. Attach-on-running works.
- `status`: instance table (live/stale/unreadable), `--probe` checkout
  mismatch detection, `--json` rows-only output, stale-record prune after
  render, daemon vs plist-installed-inactive distinction.
- `stop --world <slug>`: verified-process stop, registry cleanup.
- `setup`: 11-step flow, port-bump pinning into `lab.conf`, PATH shim,
  final summary with next steps.
- Fresh-checkout grace: `status` and `start` fail helpfully with no
  `.venv`/`lab.conf` (bash-3.2 `source` landmines already guarded).

## Gaps found in the live review (the plan must address each)

1. **New verb: `arailctl install`** (operator request, 2026-07-29): a
   single command that gets/refreshes the latest version of everything —
   `git pull` (or release fetch), `.venv` rebuild/`pip install -e .`
   refresh, service binaries (ollama/ttyd/jupyter/code-server), model
   re-pull if the default changed, then a `doctor`-style verify.
   Decide its relationship to the existing `update`/`upgrade` verbs —
   three overlapping verbs is not elite; propose a consolidation
   (e.g. `install` = first-time + refresh, `update` becomes an alias or
   is absorbed) with back-compat aliases.
2. **No non-interactive way to start the root lab** when ≥2 Worlds exist:
   the picker's "0) root lab" option has no flag equivalent. Add
   `--root` (or `--world root`) so scripts/daemons/CI can start it.
3. **`restart` asymmetries**: `restart --world <slug>` runs an
   *unscoped* `reset.sh stop` (stops everything) before starting one
   World; bare `restart` in a multi-World repo dies at the picker
   non-interactively. Make restart accept and forward the same flags as
   start/stop, scope its stop phase, and restart-what-was-running by
   default (read the registry).
4. **Status double-bookkeeping**: with a World instance live, the root-lab
   section still prints "Portal not running" — technically true, reads as
   contradiction. Unify into one services view keyed by what *should* be
   running (registry + supervision mode + tier), with an explicit
   "root lab: not started" line instead of five dim "not running" rows.
5. **Status port checks are pgrep-pattern, not connectivity**: `check()`
   proves a process exists, not that the port answers. Add a cheap HTTP
   probe (like `--probe` does for instances) or fold ports into a single
   "listening?" column; report the URL only when it actually answers.
6. **Root-lab start has no readiness gate**: unlike the instance path, the
   legacy root path prints "All services running" immediately, before
   uvicorn binds; the URL block can lie for a few seconds and there's no
   failure detection at all (a crashed portal still prints success). Port
   the instance path's probe (readiness + last-HTTP-status diagnostics)
   to the root path, per service, with per-service ✓/✗ lines.
7. **Warm-up**: nothing warms the model after start. Add an opt-in
   `--warm` (or post-ready hook) that fires one tiny inference through
   the default backend so first chat isn't cold; report warm-up time.
8. **`status --json` covers instances only** — root-lab services,
   supervision mode, ports, and tier are absent. Emit one complete JSON
   document (keep the bare rows array behind `--json=instances` or a
   schema version bump) so dashboards/scripts get everything.
9. **Exit-code contract**: document and test exit codes for every verb
   (0 running/ok, distinct codes for not-running, degraded, bad flags) —
   `status` currently always exits 0 even when nothing is running.
10. **Small polish**: `doctor`'s single-item `for bin in uvicorn` loop;
    shellcheck SC2024 sudo-redirect warnings in setup.sh; setup prints the
    passphrase to stdout (offer `--quiet`/mask); duplicate `kb help`
    heredocs in arailctl; ANSI codes leak into non-tty output (gate colors
    on `[[ -t 1 ]]`).

## Constraints

- Keep `scripts/lib/instances.sh` the single source of truth for liveness;
  no sixth implementation.
- bash 3.2 compatible (macOS /bin/bash); `set -euo pipefail` landmines
  documented in start.sh/status.sh comments must not regress.
- Never auto-copy/share per-instance `secrets.env`; never touch an Ollama
  we didn't start.
- Non-interactive (no tty) behavior must be deterministic for every verb —
  that's the CI/daemon contract.
- QA allocation per repo CLAUDE.md: 30% setup / 30% Buddy / 20% security /
  10% happy / 10% regression; the regression suite must include the
  verified-baseline behaviors above (a `tests/cli/` harness that runs the
  8-stage boot against a throwaway data root would be ideal).

## Deliverable of the planning phase

ARCHITECTURE.md covering: verb matrix (verb × flags × exit codes ×
tty/non-tty behavior × JSON output), the install/update/upgrade
consolidation ruling, the unified status model, root-lab readiness design,
and a migration/back-compat note for renamed or absorbed verbs.
