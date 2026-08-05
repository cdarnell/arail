# `arailctl` CLI reference

> Canonical, hand-maintained reference for every `./arailctl <verb>`. This
> is the doc `tests/cli/verbs_driver.sh` checks against (a drift guard: every
> `case` arm in `arailctl` must appear somewhere below — F33 in
> `sprints/2026-07-29-elite-cli/ARCHITECTURE.md`). If you add or rename a
> verb, update this file in the same commit.
>
> Finalized at the end of the `2026-07-29-elite-cli` sprint (WP8), against
> the complete, shipped CLI — every verb, flag, and exit code below is
> real. `sprints/2026-07-29-elite-cli/ARCHITECTURE.md` is the design
> record (rationale, failure modes, the WP-by-WP build order); this file
> is the day-to-day reference.

## Cross-cutting conventions

| Control | Meaning |
|---|---|
| `NO_COLOR` (any value) | Disables ANSI color codes everywhere in the CLI |
| `ARAIL_COLOR=always\|never\|auto` | Overrides the tty test; `auto` (default) = colors iff stdout is a tty and `NO_COLOR` is unset |
| `! [[ -t 1 ]]` (stdout not a tty) | ANSI disabled; `setup`'s passphrase banner is masked |
| `! [[ -t 0 ]]` (stdin not a tty) | No verb prompts; `ARAIL_NONINTERACTIVE=1` has the same effect. `install`'s one guarded confirmation (`--rebuild-venv`) treats a non-tty stdin as `--yes` |
| `ARAIL_QUIET=1` | Same as `--quiet` for `setup` and `install` — masks the passphrase banner / suppresses decorative narration |
| `ARAIL_WARM_TIMEOUT_SEC` | Caps how long `start --warm` / `restart --warm` polls for warm-up completion (default `90`) |

### Exit-code contract

Codes are **additive only**: an existing non-zero code never gets
renumbered or reused for a different meaning (`sprints/2026-07-29-elite-cli/ARCHITECTURE.md` §12.1).

| Code | Meaning | Where it applies |
|---|---|---|
| `0` | Success / affirmative verdict | every verb |
| `1` | Failure or refusal — couldn't do the thing, or refuse to (no `.venv`, daemon active with `--world`/`--root`, claim held, instance ceiling, bind conflict, root portal never came up, multiple live instances with no `restart` target, lab not provisioned, lab live without `--allow-running`, deps refresh failed, doctor broken) | `start`, `restart`, `stop`, `install`, `doctor` |
| `2` | Usage error — bad flag, missing flag value, invalid slug, ambiguous non-interactive target, unknown `--json` value, `install daemon` (typo) | every verb with flags |
| `3` | **Degraded** — partially up, a phase refused/failed but the lab is still usable, `--check` pending changes | `status`, `doctor`, `install`, `update` |
| `4` | **Nothing running** | `status` only |
| `130` / `143` | Killed by SIGINT / SIGTERM | `start --world <slug>` (foreground instance/root path) |

`stop` deliberately always exits `0` when there was nothing to stop — a
stop verb's contract is the post-condition ("it is down now"), and
`restart` chains on it.

## Verbs

### `setup`

First-time provisioning: platform packages, `.venv`, `.env`/`lab.conf`,
ports, PKB, default model, PATH shim, verify. Idempotent — respects an
existing `.env`. The **only** verb that may prompt, install OS packages,
or create/rewrite `.env`/`lab.conf`.

| Flag | Effect |
|---|---|
| `--with-coder` / `--no-coder` | Download the Qwen2.5-Coder starter model, or don't |
| `--yes` / `-y` | Same as `ARAIL_NONINTERACTIVE=1` — never prompts, default-yes everything |
| `--quiet` | Masks the passphrase in the end-of-setup banner (also: `ARAIL_QUIET=1`, or automatically whenever stdout isn't a tty) |

Exit: `0` success · `1` any `error()` (e.g. no Python 3.10+ and install
declined) · `2` unknown flag.

### `install`

Refresh an already-provisioned lab: `source` → `deps` → `components` →
`models` → `verify`, in that order. Requires a provisioned lab (refuses
with the exact `setup` command otherwise) and requires the lab to be
**stopped** (refuses with `./arailctl stop`, naming what's live, unless
`--allow-running`). Non-destructive by default: no model download without
`--models`, no `.venv` deletion without `--rebuild-venv`, no `git`
mutation beyond `pull --ff-only` on a clean, attached, tracking branch
(never `stash`/`reset`/`clean`/`merge`/`rebase`). Honors
`LAB_MODE=airgapped` on every network-touching phase (`source`, `deps`,
`components`, and `models`' `--models` apply step) — refuses with a named
reason unless `--force`.

| Flag | Effect |
|---|---|
| `--check` / `--dry-run` | Detect-only: reports what would change, mutates nothing |
| `--only <phase>[,<phase>]` | Run only the named phases (`source`,`deps`,`components`,`models`,`verify`) |
| `--skip <phase>[,<phase>]` | Run every phase except the named ones (mutually exclusive with `--only`) |
| `--models` | Actually apply the detected model drift fix (default: report only, per the metered-link doctrine) |
| `--rebuild-venv` | Delete and recreate `.venv` before `pip install`; asks for confirmation on a tty unless `--yes` |
| `--allow-running` | Proceed even though the lab is currently live (normally refused, exit 1) |
| `--force` | Override the `LAB_MODE=airgapped` refusal on network-touching phases |
| `--yes` / `-y` | Non-interactive is implied already; this only affects the `--rebuild-venv` confirmation on a tty |
| `--quiet` | Suppress decorative narration (also: `ARAIL_QUIET=1`) |
| `--json` | Emit `arail.install/v1` on stdout only; all narration moves to stderr |
| `-h` / `--help` | Usage |

**Phases:**

| Phase | Does | Refuses (→ degraded, remaining phases still run) |
|---|---|---|
| `[1/5] source` | `git pull --ff-only`; prints `old…new` short SHAs + commit count; **re-execs itself if HEAD moved** so a self-update never runs on stale bytes | not a git repo · dirty worktree · detached HEAD · no upstream · diverged (not a fast-forward) · airgapped without `--force` |
| `[2/5] deps` | `pip install -e ".[$LAB_TIER]"` (idempotent); with `--rebuild-venv`, recreates `.venv` first (**failure here is a hard failure, exit 1** — not degraded) | airgapped without `--force` |
| `[3/5] components` | `scripts/update.sh --apply --non-interactive` — `components.json` drives it; a single component's failure warns and continues | airgapped without `--force` (`update.sh`'s own check) |
| `[4/5] models` | Compares the expected primary chat model (`model_defaults.yaml`'s `default_a` if present, else `llama-ai-eng`) against `ollama list`; reports drift + the exact commands; applies only with `--models` | ollama absent / daemon unreachable → skipped (never hangs); the apply step also honors the airgap refusal |
| `[5/5] verify` | `./arailctl doctor` — its exit code folds straight through (`3`→degraded, `1`→hard failure) | — |

Exit: `0` all phases ok/no-op · `3` degraded (a phase refused or failed,
lab still usable; also `--check` pending changes) · `1`
hard failure (deps refresh failed, not provisioned, lab live without
`--allow-running`, verify broken) · `2` bad flags (including
`install daemon`, a typo for `install-daemon` — hinted, not run).

### `update` (alias for `install`)

Permanent alias — no removal date (ARAIL is a forked blueprint; removing
a verb breaks other people's scripts silently). Prints a one-line notice
on **stderr** (`update --json | jq` still works — stdout stays clean) and
runs exactly what `install` would with the same flags. The one carve-out:
**`update --component <name>`** is forwarded verbatim to the old,
interactive `scripts/update.sh` path (unchanged behavior, no notice —
nothing about it is aliased). `update --check` behaves exactly like
`install --check` (exit `3` when changes are pending; previously always
exited `0`, an intentional behavior change).

### `tier [<minimalist|maximus>]`

The canonical name for the feature-set axis. No argument prints the
current tier plus the two switch commands and exits `0`. With an
argument, delegates to `scripts/upgrade.sh` unchanged — `pip install -e
".[<tier>]"`, writes `LAB_TIER` to `.env`. Downgrading doesn't uninstall
anything; the extra tabs just hide until you upgrade again.

| Flag | Effect |
|---|---|
| `--with-coder` / `--no-coder` | Also (or don't) download the Qwen2.5-Coder starter model |

Exit: `0` success (or bare `tier` printing the current one) · `1`
pip/tier failure · `2` unknown tier.

### `upgrade` (alias for `tier`)

Permanent alias — same no-removal-date rationale as `update`/`install`.
Prints a one-line notice on stderr, then behaves exactly like `tier`.
`upgrade` with no argument used to `die "usage: ..."` (exit `1`); it now
prints the current tier and exits `0`, matching `tier`'s own behavior —
an intentional, documented change.

### `version`

Print installed component versions (`scripts/update.sh --version-only`).
Unchanged.

### `start`

Launch the lab: foreground `scripts/start.sh`, or (if `install-daemon` has
been run and launchd is actively supervising) drive `launchctl` instead —
with a real readiness gate either way, not a print-and-hope.

| Flag | Effect |
|---|---|
| `--world <slug>` / `--world=<slug>` | Start (or attach to) one Concurrent-Worlds instance |
| `--root` | Start the root lab explicitly, even with Worlds configured. Mutually exclusive with `--world` (exit 2 if both given). **Not** the same thing as `--world root` — a World can validly be named `root`; the picker names the distinction when that's the case |
| `--port <n>` | Override the allocated/default portal port |
| `--no-browser` | Suppress auto-opening the dashboard |
| `--list` | Print configured Worlds and exit (side-effect free) |
| `--pick` | Force the interactive picker even with fewer than 2 Worlds configured (which would otherwise auto-select the single World, leaving no way to reach the root lab but `--root`). Mutually exclusive with `--world`, `--root`, and `--yes` (exit 2). Needs a tty — exit 2 without one. This is what `switch` uses |
| `--yes` | Take the picker's default — the lab you launched last, or the root lab if this checkout has never launched one — without asking, and print which. Works with or without a tty (its whole audience is scripts). Mutually exclusive with `--pick` |
| `--warm` | After the lab is up, poll for the boot-time model warm-up to finish and print one honest line (`✓ via <backend> in N.Ns` / `⚠ not complete within Ns` / `— not applicable for backend <name>`). Never gates readiness, never changes the exit code. Daemon mode prints a hint instead of polling (its env is fixed by the launchd plist) |
| `-h` / `--help` | Usage |

`--world`/`--root`/`--list`/`--help` always reach `scripts/start.sh`
directly, even when a daemon is active — daemon-mode refusal is
`start.sh`'s own job so it can name the World slug (or `--root`) in the
message.

**Root-lab readiness:** a pre-spawn check refuses immediately (before
anything is started) if the portal port is already answering
(`Root lab already running — try: ./arailctl status`). After every
service is spawned, each is polled: **Portal is required** — if it never
answers `/api/instance` with HTTP 200 from *this* checkout, every process
this invocation spawned is stopped and `start` exits `1`. Memory, MLX
(when `MODEL_BACKEND=mlx`), Terminal, Notebook, and IDE are
**degrade-only** — a missing one prints `⚠` and is left out of the final
URL block, but never aborts the launch. The closing banner says
`All services running.` only when nothing degraded; otherwise
`Lab running — degraded: <services>.` Daemon mode gets the identical
honesty: after `launchctl kickstart`, `start` polls `/api/instance` for
up to 30s before reporting success; if the portal never answers, `start`
exits `1` naming `lab/logs/portal.err.log` instead of printing an
unverified URL.

**The picker.** With 2+ Worlds configured and no target given, an
interactive tty picker appears. Option `0` is always the root lab
(non-interactively `--root`) — and when a World is *mounted* into the root
lab, option `0` names it (`Autoresearch AI Lab — Debt Finance World
mounted (:8080)`), because otherwise that World and its own catalog row
are two indistinguishable names for two different labs. Each World row
shows its liveness (`● running :8090` / `○ not running`).

Non-interactive with no target still exits `2`, listing every
`./arailctl start --world <slug>` command plus `--root` — VISION §3's
"never guess" ruling is what CI, daemons, and scripted callers depend on,
and no memory overrides it. A running World/root lab is attached to (URL
printed, browser opened), never respawned.

**The picker remembers.** Every *successful* start — root lab, World
instance, or an attach to one already running — records its target in
`lab/instances/last-target.json` (schema `arail.last-target/v1`). The next
picker marks that row `← last` and makes it the Enter-default, so pressing
Enter returns you to the lab you were last in. A checkout that has never
launched anything defaults to option `0`. The write happens only *after*
readiness passes, so a World that crash-loops on boot never becomes the
sticky default; a remembered World later deleted from the catalog degrades
to option `0` with one line saying so. The file is a preference, not
state: corrupt, empty, or hand-edited-hostile content is treated as
absent, and a failure to write it can never fail a start.

With exactly one World configured the picker still does not appear
(VISION §3 — it must not tax the single-World user), but the memory is
honored: if you last ran the root lab, bare `start` returns you there and
says so. `--pick` forces the prompt in either case.

Exit: `0` ready (or attached) · `1` failure/refusal (no `.venv`, daemon
active with `--world`/`--root`, claim held, instance ceiling, bind
conflict, root portal never came up, daemon kickstart never answered
within 30s) · `2` usage (bad flag, unknown slug, `--root` with `--world`,
ambiguous picker non-interactively) · `130`/`143` SIGINT/SIGTERM
(foreground instance/root path).

### `stop`

Stop lab services (unloads launchd agents in daemon mode).

| Flag | Effect |
|---|---|
| `--world <slug>` | Stop one World instance |
| `--root` | Stop only the root lab's services — never touches a live World instance, even while one is running |
| `--all` | Stop every configured World instance, then the root lab |

Exit: `0` always (including "nothing was running" — a stop verb's
contract is the post-condition) · `1` multiple live instances with no
target (bare `stop`, neither flag given) / instance support unavailable ·
`2` invalid slug, unknown/malformed flag (including a value-less
`--world`) — a usage mistake is always reported as one and never
silently widens the stop's scope.

### `restart`

Stop then start — **scoped to exactly one target**, never a sibling
World (the bug this sprint's redesign retires: an unscoped stop used to
be able to kill a live sibling instance mid-write). Forwards every flag
`start` accepts, including `--warm`; never re-parses them itself (a
second parser is how the original scoping bug happened).

| Target resolution (no flags reparsed — read-only argv scan + registry read) | Behavior |
|---|---|
| `--world <slug>` given | Stops exactly that World, then starts it |
| `--root` given | Stops only the root lab's services, then starts the root lab |
| Neither; daemon active | `launchctl kickstart -k` + the same readiness gate `start`'s daemon branch uses |
| Neither; exactly 1 live instance | Stops and restarts that instance |
| Neither; 0 live instances | Stops the root lab, then `start` does its own resolution/picker |
| Neither; ≥2 live instances | **Exit 2** — lists `restart --world <slug>` for each, plus `--root` |
| `--all` | **Exit 2** — explicit refusal with an explanation (a foreground start hosts exactly one target; multi-instance restart needs a supervisor this sprint does not build). Use `stop --all`, then start each in its own terminal |
| `--world`/`--root` while a daemon is active | **Exit 1** — refuses by name rather than silently kickstarting the root daemon instead of the thing actually asked for |

If the scoped stop phase fails, the start is never attempted (exit `1`).
If the stop succeeds but the subsequent start fails, `restart` prints
`'<target>' was stopped, and the start failed (above) — the lab is now
DOWN.` before propagating the start's own exit code — a silent "start
failed" after a successful stop is how an operator ends up with a down
lab and no idea why.

Exit: inherited from the `start` it drives (`0`/`1`/`2`/`130`/`143`),
plus its own `2` (ambiguous target, `--all`) and `1` (scoped stop
failed).

### `switch`

Jump from one World to another in one command: stop whatever is running,
then pick. This is the verb for the way most operators actually use
Worlds — one at a time, switching between them — which `restart` cannot
be, because `restart` deliberately pins to the *current* target.

```bash
./arailctl switch                  # stop what's live, then the picker
./arailctl switch --world finance  # …or go straight there, no prompt
./arailctl switch --root           # …or back to the root lab
```

| Target | Behavior |
|---|---|
| No flags | Stops **every** live World instance, then the root lab, then hands off to `start.sh --pick` — the picker, forced even with a single World configured |
| `--world <slug>` | Same scoped stop, then `start --world <slug>`; no prompt |
| `--root` | Same scoped stop, then `start --root`; no prompt |
| `--root` with `--world` | **Exit 2** — usage error |
| Daemon active | **Exit 1** — daemon mode is single-instance, so there is nothing to switch between; names `uninstall-daemon` as the fix |

The deliberate difference from `restart`: with ≥2 live instances `restart`
exits `2` (it cannot know which one you meant), whereas `switch` stops all
of them and then asks — collapsing to exactly one lab *is* what switching
means. Each stop is scoped (`reset.sh stop --world <slug>`), never an
unscoped stop that could take out a sibling mid-write.

`switch` owns no picker of its own — it forces `start.sh`'s. The lab you
land in is recorded the same way any other successful start is, so the
next bare `start` returns you there.

If a stop fails, the start is never attempted (exit `1`). If a stop
succeeds and the start then fails, `switch` prints `the previous lab was
stopped, and the start failed (above) — the lab is now DOWN.` before
propagating the start's exit code — the same F13 discipline `restart` uses,
for the same reason.

Exit: inherited from the `start` it drives (`0`/`1`/`2`/`130`/`143`), plus
its own `2` (`--root` with `--world`) and `1` (scoped stop failed, daemon
active).

### `deep <op>`

AeroLLM 2nd-inference control: `install` (bundled prebuilt binary) |
`rebuild` (from source) | `update` (published wheel) | `status`.

Three install channels, dispatched by `scripts/build-aerollm.sh auto`
(what `setup.sh` and a bare `./arailctl deep install` with no forced
channel both use):

| Channel | Op | Requires | Who it's for |
|---|---|---|---|
| BUNDLED | `deep install` | network to `github.com` (or a local tarball via `AEROLLM_BUNDLE_FILE`) | outside users — no source repo, no credentials |
| DEV | `deep rebuild` | the aeroLLM sibling repo checked out at `$ARAIL_AEROLLM_REPO` | maintainers with local aeroLLM changes |
| RELEASE | `deep update` | `pypi.qukaizen.com` index credentials | maintainers on the private index |

`auto` picks DEV if the sibling repo is present, RELEASE if
`AEROLLM_CHANNEL=release` or index credentials are configured, and
BUNDLED otherwise. Force any channel with `AEROLLM_CHANNEL=dev|release|bundle`
regardless of what's on disk.

**Bundled-channel env knobs** (all optional):

| Var | Default | Meaning |
|---|---|---|
| `AEROLLM_CHANNEL` | unset (auto) | force `dev` \| `release` \| `bundle` |
| `AEROLLM_BUNDLE_URL` | derived from repo/tag below | full asset URL override (mirrors, forks) |
| `AEROLLM_BUNDLE_REPO` | `cdarnell/qukaizen-arail` | which GitHub repo carries the release asset |
| `AEROLLM_BUNDLE_TAG` | pinned in `pyproject.toml` `[tool.arail.package-sources] aerollm_bundle_tag` | which ARAIL release carries the bundle |
| `AEROLLM_BUNDLE_FILE` | unset | use a local tarball instead of downloading — the offline / airgapped install path |
| `AEROLLM_BUNDLE_SHA256` | read from the `.sha256` sidecar | pin/override the expected digest |

`./arailctl deep status` reports a `channel:` line (`dev` \| `release` \|
`bundled` \| `none`) and, when bundled, an `aerollm <version> (<short-sha>,
built <date>)` provenance line read from `aerollm_api.bundle.json`.

See `sprints/2026-08-05-arail-bundled-aerollm/ARCHITECTURE.md` for the
full design and `docs/releasing.md` for the maintainer-side bundle
refresh checklist.

### `reset [mode]`

Wipe state: `models`\|`data`\|`pkb`\|`plugins`\|`env`\|`full`\|`destroy`.
See `./arailctl reset help`. Unchanged.

### `status`

One collector, one `arail.status/v2` document, two renderers (the human
table and `--json`) — they can never disagree. HTTP/port probes
(`scripts/lib/services.sh`), not `pgrep` patterns, are the verdict
source; `pgrep` survives only as an "owner" hint, run only after a port
is already known to be listening.

| Flag | Effect |
|---|---|
| `--json` / `--json=full` | The whole `arail.status/v2` document |
| `--json=instances` | The bare instance-registry rows array — byte-compatible with the pre-sprint `--json` output (the documented stable form for scripts; see `docs/concurrent-worlds.md`) |
| `--probe` | Extended: adds a `/health` check for memory/MLX and the per-instance token+checkout mismatch probe |
| `--no-probe` | Zero HTTP calls — registry + port-listen only, fully deterministic (CI mode) |
| `--quiet` / `-q` | Suppress the top banner and the `Runtime state` (`du`) section |
| `--no-sizes` | Skip the `lab/` disk-usage walk (never in the JSON regardless — a `du` walk can cost real seconds on a large PKB, outside the <2s budget) |

Renders, in order: the World-instance table (`live`/`stale`/`unreadable`,
data-root-missing warnings), `.venv`/supervision status, the root lab
(one line — `root lab: not started (a World instance is running
instead)` — when a World is up and the root lab never was, replacing five
previously-dim "not running" rows; per-service `✓`/`⚠` lines when the
root lab IS up, with a URL printed **only** for a service that actually
answered), a foreign-checkout warning if a different process answers the
portal port, external Ollama reachability, then (human mode only) the
scheduler window and `lab/` disk usage. Stale registry records are pruned
**after** rendering, in every mode — a status command that silently
deletes what it just reported would be surprising.

Exit: `0` something expected is up and nothing is wrong · `3` degraded
(up but a service is down, a registry record is stale/unreadable, or a
foreign checkout answers the portal port) · `4` nothing running · `1`
internal failure (registry directory unreadable) · `2` bad flag.

### `doctor`

Explicit environment checkup — `.venv`/import/`uvicorn` preflight plus
`python -m arail.doctor` (models, KB index, components, egress).

| Flag | Effect |
|---|---|
| `--updates` | Also run the remote component-update check (hybrid mode only) |
| `--strict` | Promote optional/info findings (a missing optional binary, no model installed) to degraded |

**Findings tally:** `uvicorn` absent, the egress guard failing to
install, or the PKB root being unwritable are **required** checks — any
of them failing degrades the run. `ttyd`/`jupyter`/`code-server` and "no
model installed" are **info** — reported, but only degrade the exit code
under `--strict`. Deliberate: CI (`.github/workflows/blueprint-smoke.yml`)
runs plain `./arailctl doctor` on a runner that legitimately lacks
`ttyd`, `code-server`, and any pulled model, and must keep exiting `0`.

Exit: `0` healthy · `1` broken (no `.venv`, `import arail` fails) · `3`
degraded (a required check failed, or `--strict` promoted an info one).

### `logs [component] [lines]`

Tail `lab/data/activity.jsonl`, optionally filtered by component
(`browser`\|`system`\|`researcher`\|`goal`\|`wiki`\|`pkb`\|`chat`\|`consent`).
Unchanged.

### `pkb <op>`

`ingest`\|`compile`\|`browse` — ARAIL lab knowledge-base content ops.
Unchanged.

`prune` — reconcile the **Compiled KB** (the approved layer agents build
on) with what is actually on disk: drop approvals whose raw file no longer
exists.

| Flag | Effect |
|---|---|
| `--dry-run` | List what would be dropped, change nothing |

Why this exists: the Compiled KB is a *manifest of pointers* into the raw
corpus, not a second copy. Mounting a World runs
`world_mount._sweep_other_worlds()`, which deletes the previous World's
staged `sources/world-<slug>/` term files — deliberately, because a World
IS the lab's dataset. The approvals for those terms used to outlive their
files, and since the retrieval gate is a query-time intersection (approved
paths ∩ live search hits), a dangling pointer matches nothing. Enough of
them and `search_for_agents()` returns zero hits for **every** query in
**every** World, with no error raised anywhere — the gate fails closed, and
"no approved truth" is indistinguishable from "nothing approved yet."

Mount, swap, and `unmount --remove-staged` now prune automatically. This
verb is the manual door for a lab that already drifted. `./arailctl doctor`
reports the dangling count (and warns when a World is mounted but nothing
is approved, so agents would find nothing).

Exit: `0` pruned or already clean · `3` pkb root missing/unreadable — the
prune deliberately refuses there rather than treating "every path looks
deleted" as 556 revocations.

### `wiki <op>`

`build`\|`info`\|`new <title>`\|`serve` — ARAIL docs-as-code. Unchanged.

### `world <op>`

DaC WorldBundle ops — passthrough to `python -m arail.world_mount`.
Unchanged.

### `benchmark_models` (aliases: `benchmark`, `aerollm`)

Measure local model TPS for autoresearch routing. Defaults to `--all`
when no args are given. Unchanged.

### `kb <op>`

QuKaiZen Karpathy LLM Wiki ops (`status`\|`compile`\|`lint`\|`validate`\|
`query`\|`search`\|`ingest`\|`index`\|`where`). Auto-discovers `KB_ROOT` —
never hardcoded. `kb help` (and the in-repo `kb` help shown once `KB_ROOT`
is known) share one `kb_usage()` function. Unchanged.

### `install-daemon` / `uninstall-daemon`

Supervise the lab with launchd (starts at login, respawns on crash) /
remove that supervision. Unchanged.

### `blueprint <op>`

Configuration-as-Code: `list`\|`catalog`\|`show`\|`create`\|`apply`\|`destroy`.
Unchanged.

### `help` (also: `-h`, `--help`, no verb)

Usage banner.

Exit: `0` (`help`) · `1` (an unrecognized verb).
