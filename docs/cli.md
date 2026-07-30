# `arailctl` CLI reference

> Canonical, hand-maintained reference for every `./arailctl <verb>`. This
> is the doc `tests/cli/verbs_driver.sh` checks against (a drift guard: every
> `case` arm in `arailctl` must appear somewhere below — F33 in
> `sprints/2026-07-29-elite-cli/ARCHITECTURE.md`). If you add or rename a
> verb, update this file in the same commit.
>
> This file is being built incrementally across the
> `2026-07-29-elite-cli` sprint's work packages (see
> `sprints/2026-07-29-elite-cli/ARCHITECTURE.md` §17 for the plan). What's
> below reflects the verbs and behavior that exist **today** — it grows as
> later work packages land (`--root`, the redesigned `restart`, the
> unified `status --json` schema, `--warm`, and the new `install`/`tier`
> verbs). Don't infer unshipped behavior from the architecture doc; this
> file is the source of truth for what's actually built.

## Cross-cutting conventions

| Control | Meaning |
|---|---|
| `NO_COLOR` (any value) | Disables ANSI color codes everywhere in the CLI |
| `ARAIL_COLOR=always\|never\|auto` | Overrides the tty test; `auto` (default) = colors iff stdout is a tty and `NO_COLOR` is unset |
| `! [[ -t 1 ]]` (stdout not a tty) | ANSI disabled; `setup`'s passphrase banner is masked |
| `! [[ -t 0 ]]` (stdin not a tty) | No verb prompts; `ARAIL_NONINTERACTIVE=1` has the same effect |
| `ARAIL_QUIET=1` | Same as `setup --quiet` — masks the passphrase in the end-of-setup banner |

### Exit-code contract (built incrementally — see `ARCHITECTURE.md` §12)

Codes are **additive only**: an existing non-zero code never gets
renumbered or reused for a different meaning.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Failure or refusal (e.g. no `.venv`, daemon already active, a required check failed) |
| `2` | Usage error — bad flag, missing flag value, invalid slug |
| `3` | Degraded — a required check failed, or `--strict` promoted an optional one (`doctor` only, so far) |
| `130` / `143` | Killed by SIGINT / SIGTERM (`start --world <slug>`) |

## Verbs

### `setup`

First-time provisioning: platform packages, `.venv`, `.env`/`lab.conf`,
ports, PKB, default model, PATH shim, verify. Idempotent — respects an
existing `.env`.

| Flag | Effect |
|---|---|
| `--with-coder` / `--no-coder` | Download the Qwen2.5-Coder starter model, or don't |
| `--yes` / `-y` | Same as `ARAIL_NONINTERACTIVE=1` — never prompts, default-yes everything |
| `--quiet` | Masks the passphrase in the end-of-setup banner (also: `ARAIL_QUIET=1`, or automatically whenever stdout isn't a tty) |

Exit: `0` success · `1` any `error()` (e.g. no Python 3.10+ and install
declined) · `2` unknown flag (new — previously silently ignored).

### `start`

Launch the lab: foreground `scripts/start.sh`, or (if `install-daemon` has
been run and launchd is actively supervising) drive `launchctl` instead.

| Flag | Effect |
|---|---|
| `--world <slug>` / `--world=<slug>` | Start (or attach to) one Concurrent-Worlds instance |
| `--port <n>` | Override the allocated/default portal port |
| `--no-browser` | Suppress auto-opening the dashboard |
| `--list` | Print configured Worlds and exit (side-effect free) |
| `--yes` | Non-interactive default for the World picker |
| `-h` / `--help` | Usage |

`--world`/`--list`/`--help` always reach `scripts/start.sh` directly, even
when a daemon is active — daemon-mode refusal is `start.sh`'s own job so it
can name the World slug in the message.

**Root-lab readiness (new):** the foreground root-lab path (no World
configured, or the operator picked the root lab) now has a real readiness
gate, ported from the Concurrent-Worlds instance path's own probe:

- A pre-spawn check refuses immediately (before anything is started) if
  the portal port is already answering — `Root lab already running — try:
  ./arailctl status`.
- After every service is spawned, each is polled: **Portal is required** —
  if it never answers `/api/instance` with HTTP 200 from *this* checkout,
  every process this invocation spawned is stopped and `start` exits `1`.
  Memory, MLX (when `MODEL_BACKEND=mlx`), Terminal, Notebook, and IDE are
  **degrade-only** — a missing one prints `⚠` and is left out of the final
  URL block, but never aborts the launch.
- The closing banner says `All services running.` only when nothing
  degraded; otherwise `Lab running — degraded: <services>.`
- Daemon mode gained the identical honesty: after `launchctl kickstart`,
  `start` polls `/api/instance` for up to 30s before reporting success. If
  the portal never answers, `start` exits `1` with `tail
  lab/logs/portal.err.log` instead of printing a URL it hasn't verified.

Exit: `0` ready (or attached to an already-running instance/daemon) · `1`
failure or refusal (no `.venv`, daemon active with `--world`, claim held,
instance ceiling, bind conflict, **root portal never came up — new**,
**daemon kickstart never answered within 30s — new**) · `2` usage (bad
flag, unknown slug, ambiguous picker when non-interactive) · `130`/`143`
SIGINT/SIGTERM (World-instance path).

### `stop`

Stop lab services (unloads launchd agents in daemon mode).

| Flag | Effect |
|---|---|
| `--world <slug>` | Stop one World instance |
| `--all` | Stop every configured World instance |

Exit: `0` (including "nothing was running" — a stop verb's contract is
the post-condition) · `1` multiple live instances with no target · `2`
invalid slug.

### `restart`

Stop then start. In daemon mode: `launchctl kickstart -k`. Unchanged in
this sprint so far — see `ARCHITECTURE.md` §9 for the redesign planned in
a later work package (scoped stop, registry-aware target resolution).

### `upgrade <tier>`

Switch install tier (`minimalist` | `maximus`). `min`/`max`/`med` legacy
names accepted with a deprecation warning.

Exit: `0` success · `1` pip/tier failure (or missing argument today —
unchanged in this sprint so far).

### `deep <op>`

AeroLLM 2nd-inference control: `rebuild` (from source) | `update`
(published wheel) | `status`.

### `update`

Check for and apply component updates from `components.json`.

| Flag | Effect |
|---|---|
| `--check` | Dry run — report only |
| `--yes` | Skip confirmation |
| `--component <name>` | Update a single component |

### `version`

Print installed component versions (alias for `update --version-only`).

### `reset [mode]`

Wipe state: `models`\|`data`\|`pkb`\|`plugins`\|`env`\|`full`\|`destroy`.
See `./arailctl reset help`.

### `status`

Show what's running and where — World-instance table, `.venv`/service
checks, supervision mode, scheduler state, `lab/` disk usage.

| Flag | Effect |
|---|---|
| `--json` | Print only the instance-registry row array (machine-readable) |
| `--probe` | Add the `/api/instance` token+checkout mismatch check per instance |

Exit: `0` (unchanged in this sprint so far — the unified verdict model
with `3`/`4` is planned for a later work package; see `ARCHITECTURE.md`
§7).

### `doctor`

Explicit environment checkup — passthrough to `python -m arail.doctor`
plus a `.venv`/import/`uvicorn` preflight.

| Flag | Effect |
|---|---|
| `--updates` | Also run the remote component-update check (hybrid mode only) |
| `--strict` | Promote optional/info findings (a missing optional binary, no model installed) to degraded |

**Findings tally:** `uvicorn` absent, the egress guard failing to
install, or the PKB root being unwritable are **required** checks — any
of them failing degrades the run. `ttyd`/`jupyter`/`code-server` and "no
model installed" are **info** — reported, but only degrade the exit code
under `--strict`. This is deliberate: CI
(`.github/workflows/blueprint-smoke.yml`) runs plain `./arailctl doctor`
on a runner that legitimately lacks `ttyd`, `code-server`, and any pulled
model, and must keep exiting `0`.

Exit: `0` healthy · `1` broken (no `.venv`, `import arail` fails) · `3`
degraded (a required check failed, or `--strict` promoted an info one).

### `logs [component] [lines]`

Tail `lab/data/activity.jsonl`, optionally filtered by component
(`browser`\|`system`\|`researcher`\|`goal`\|`wiki`\|`pkb`\|`chat`\|`consent`).

### `pkb <op>`

`ingest`\|`compile`\|`browse` — ARAIL lab knowledge-base content ops.

### `wiki <op>`

`build`\|`info`\|`new <title>`\|`serve` — ARAIL docs-as-code.

### `world <op>`

DaC WorldBundle ops — passthrough to `python -m arail.world_mount`.

### `benchmark_models` (aliases: `benchmark`, `aerollm`)

Measure local model TPS for autoresearch routing. Defaults to `--all`
when no args are given.

### `kb <op>`

QuKaiZen Karpathy LLM Wiki ops (`status`\|`compile`\|`lint`\|`validate`\|
`query`\|`search`\|`ingest`\|`index`\|`where`). Auto-discovers `KB_ROOT` —
never hardcoded. `kb help` (and the in-repo `kb` help shown once `KB_ROOT`
is known) share one `kb_usage()` function.

### `install-daemon` / `uninstall-daemon`

Supervise the lab with launchd (starts at login, respawns on crash) /
remove that supervision.

### `blueprint <op>`

Configuration-as-Code: `list`\|`catalog`\|`show`\|`create`\|`apply`\|`destroy`.

### `help` (also: `-h`, `--help`, no verb)

Usage banner.

Exit: `0` (`help`) · `1` (an unrecognized verb).
