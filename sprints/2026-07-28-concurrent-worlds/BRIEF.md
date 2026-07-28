# BRIEF — concurrent Worlds as independent instances

> The orchestrator's briefing artifact for every persona in this sprint. All
> file:line anchors below were verified on disk 2026-07-28 on branch
> `qukaizen/arailctl-concurrent-worlds-33db65`; re-verify any anchor you build
> an argument on.

## The operator's ask, verbatim

> "I want arailctl retrofitted to be able to start multiple worlds. Maybe even a
> case statement on start, 'which world to load' and take time loading those
> worlds for the user. This will allow the ability to jump from one world to
> another cleaner than selecting from a dropdown. Maybe have both but I feel like
> that doesn't work as well, and I want the instances to feel completely
> independent if a new world is selected."

Today ARAIL has exactly ONE mounted World at a time, live-swapped via `/worlds`'
Mount/Unmount buttons (`POST /api/worlds/select`) inside a single running portal
process. The operator wants e.g. the debt-finance World and the AI/ML World both
fully up at once, in separate places, without one's state/data root touching the
other's — and wants starting a World to feel like a deliberate launch with
visible progress, not an instant dropdown flip.

## The motivating incident (observability requirements)

While manually verifying the debt-finance World build, `./arailctl start`
refused to run in the foreground because a launchd plist *file existed*
(`~/Library/LaunchAgents/io.arail.portal.plist`) — the check is file existence
(`arailctl:195`), not "is the daemon running" or "is it pointed at this
checkout". The daemon itself was silently crash-looping (ModuleNotFoundError)
and resolving `arail` to a *different checkout* via the venv's editable install.
Diagnosis required `ps`/`launchctl list`/`arail.__file__`. Any multi-instance
design must make "is instance X up, serving which World, which checkout, which
data root, which port" a first-class fast answer — that debugging path must not
be the normal path for standing up a second instance.

## Open questions the visionary MUST answer concretely

1. **What does "independent" mean?** Separate port only? Separate `lab/pkb/` and
   `lab/data/` roots (almost certainly yes)? Separate model process per instance
   (resource-heavy — actually wanted?), or shared model backend with per-instance
   data roots?
2. **Does the dropdown mount/unmount still earn its place?** The operator is
   skeptical ("maybe have both but I feel like that doesn't work as well"). Give
   a real answer, not a hedge — replace (plan the deprecation) or name the
   specific surviving use case.
3. **What is the start UX?** Interactive picker on bare `./arailctl start`
   (scanning the same set `/worlds` lists)? `--world <slug>` for scripting?
   Both? What happens when the requested World is already running — attach/focus
   or error?
4. **What does "take time loading… for the user" imply?** Staged progress during
   instance boot (model warm, World mount, PKB index) instead of today's silent
   backgrounded spawn.
5. **Resource ceiling:** a concrete number of concurrent instances and why;
   eviction policy or not.
6. **Naming/discovery:** how instances are told apart at a glance (per-instance
   banner via the existing `LAB_NAME` rebrand keyed to the World?).

## Hard constraints (carried from the debt-finance sprint)

- Per-World data isolation must be **structural** (different directories), not
  logical (a filter that could have a bug). Sensitive/personal World data never
  lives under a shared, cross-instance-visible `lab/pkb/` path.
- Fully world-generic: every World (video games, AI/ML, horticulture, physics,
  finance) gets the same capability. Nothing finance-specific.
- Plus the standing repo conventions: airgapped default untouched; internal
  package name stays `arail`; secrets `0600`, never echoed/logged; no
  auto-checks at boot (`ARAIL_AUTOCHECKS` defaults off); no hardcoded machine
  paths (ARAIL is a blueprint others run).

## Grounding facts (verified 2026-07-28)

### Start flow (`arailctl` + `scripts/start.sh`)

- `arailctl:92` sources `.env` (`set -a`); `lab.conf` is NOT sourced there.
  `start` dispatch at `arailctl:210-229`: if `daemon_installed()` (`arailctl:195`
  — plist file existence only) → launchd branch (kickstart, exit); else
  `exec scripts/start.sh "$@"` — and **`start.sh` discards all arguments**.
- Four inconsistent "is it running" checks: `arailctl:195` (plist exists),
  `start.sh:35` (`launchctl list io.arail.portal`), `status.sh:42` (plist+uname),
  `install-daemon.sh:76-79` (pgrep + not-launchctl). After `arailctl stop`
  (unloads, keeps plists) `arailctl start` still takes the launchd branch — the
  operator's trap.
- `start.sh` backgrounds up to 7 services into a `PIDS` array — portal uvicorn
  (`PORTAL_PORT`→8080), Ollama (only if unreachable; the sole PID file
  `.ollama-started-by-arail.pid`), MLX API (11435), memory service
  (`LANCE_PORT`→7414), ttyd (7681), jupyter (8888), code-server (8443). **No
  lock file, no port pre-check, no already-running detection** — a second start
  spawns a uvicorn that fails to bind silently. Cleanup trap kills `PIDS`.
- `start.sh:21` sources `lab.conf` **without `set -a`** → uvicorn gets the port
  via argv but the Python process reads stale `.env` values via
  `os.getenv("PORTAL_PORT")` (`portal/services/opencode.py:588,1036`,
  `portal/app.py:9498,9727`, `agents/_builtin_sre.py:271`).
- `reset.sh stop` kills by `pgrep -f` module patterns — the three uvicorn
  patterns are **port-agnostic** (kills every ARAIL portal/memory/mlx on the
  box); ttyd/jupyter/code-server patterns are port-scoped but `reset.sh` never
  sources `lab.conf`.
- launchd: fixed labels `io.arail.{portal,memory,mlx}`, one set per machine;
  plist bakes host+port into argv; `WorkingDirectory` = repo root; env only
  PATH + `PYTHONPATH=<REPO>/src`.
- Python paths: `src/arail/config.py:84-89` — `_resolve()` = env var else bare
  relative default (CWD-relative!): `LAB_ROOT`→`lab`,
  `ARAIL_DATA_DIR`→`$LAB_ROOT/data`, `ARAIL_MODELS_DIR`, `ARAIL_WORLDS_DIR`,
  `LAB_PKB`→`$LAB_ROOT/pkb`. `ARAIL_ENV_FILE` (`config.py:26-30`) pins which
  `.env` loads — exists because worktrees otherwise find the parent checkout's
  `.env`. `reset.sh:44-90` re-implements resolution in bash (pinned by
  `tests/test_reset_paths.py`); `start.sh:71-83` is a third partial copy.
  `egress.py:92` bypasses config, re-reads `os.getenv("ARAIL_DATA_DIR")`.
- Latent bug: `start.sh:139-140` calls undefined `warn` (ttyd present, tmux
  absent) → command-not-found under `set -euo pipefail`.

### Blueprint instances (the reuse candidate)

- `scripts/blueprint.sh` (321 lines; nothing in `src/arail/` touches
  `instances/`): `create <name> --from <bp>` scaffolds
  `instances/<name>/{.env,lab.conf,log/,blueprint.toml}`. "Render" = string
  interpolation of five `.env` vars (`LAB_NAME/SHORT_NAME/TAGLINE/TIER/INTENT`)
  + five ports into `lab.conf` (base = max existing instance `PORTAL_PORT`+10,
  default 9100, offsets portal 0/terminal 1/notebook 2/ide 3/mlx 5; no bind
  test; ignores root `lab.conf`). `blueprint.toml`'s `agents[]`, `runtime.*`,
  `telemetry.sinks` are inert. `apply` overwrites instance `.env` wholesale.
  Instance `lab.conf` lacks `IDE_PASSWORD` and `LANCE_PORT` (7414 collision).
  `instances/<n>/blueprint.toml` and `log/` NOT gitignored. Only test coverage:
  shell-injection safety of rendered `.env`
  (`tests/shell_source_safety_driver.sh:34-48`).
- **Config-only: nothing launches an instance.** No `--instance` flag anywhere;
  `start.sh` hardcodes repo-root `.env`/`lab.conf`. Instance `.env` sets **no
  data roots** — every instance would share one `lab/` tree. Known drift:
  `sprints/2026-07-23-clean-experience/reports/report-docs-drift.md:30`.
- `LAB_INTENT` mismatch: blueprint writes prose `goal_prompt`; `identity.py:80`
  treats it as an enum slug.
- Aspirational precedent: `docs/REPOSITORY_LAYOUT.md:34-78` proposes
  `ARAIL_HOME` defaulting to `instances/default/` — designed, unbuilt.

### Worlds machinery

- Bundle `dac.world-bundle/v1`: flat dir, 6 sealed sha256-pinned JSON files
  (`manifest/terms/spec/face/roster/agenda` + `drift-report`); seal-exempt
  `SKILL.md`, `capabilities.json`, `model.json`; runtime sidecars written into
  the bundle dir (`review.json`, `evolution.json`, `librarian-scout.json`).
  A world = terms + categories + face/theme + agenda; only a model *hint*.
- Catalog: `lab/worlds/` scanned (`ai` 331 terms, `qukaizen` 32,
  `video-games` 69); `examples/worlds/` importable by path (4 more).
  `list_available_worlds()` (`world_mount.py:714-821`) never raises.
- `mount()` (`world_mount.py:1433-1512`): verify seal in memory → stage term
  markdown into `PKB_ROOT/sources/world-<slug>/` → **`_sweep_other_worlds`
  rmtree's every other `sources/world-*/`** (`:1343-1372`, "A World IS the
  lab's dataset") → LanceDB upsert → write `DATA_DIR/world-mount.json` pointer
  (atomic, last) → capabilities + model-hint sidecars into `DATA_DIR`. No
  process restart, no `.env` write; consumers read `current_mount()`
  (`:679-690`) fresh per request; `identity.effective_identity()` resolves
  per request, no cache. **One mounted World per DATA_DIR ⇒ concurrent Worlds ≡
  concurrent DATA_DIRs.**
- **The loader is already parameterizable**: `mount/unmount/swap` accept
  `pkb_root=`/`data_dir=`/`worlds_dir=` kwargs (CLI + tests use them); every
  portal call site passes none.
- Portal coupling: all forge/review/grow/terms endpoints (`world_routes.py`)
  operate on `_mounted_catalog_dir()` (no world param, 409 unmounted) with
  module-level state (`_forge_state` etc.) — one forge/review/grow per process.
- A mount reaches: PKB staged markdown, LanceDB (`PKB_ROOT/.cache/lancedb`, one
  shared index), wiki graph, Buddy (`SKILL.md` + face framing), Researcher,
  Librarian, Curator, chat model chip, capabilities gating (STT/OCR/mic),
  identity/theme in ~25 templates.
- Scoping that exists: exclusive staging dirs; wiki brain-scope IS world-gated
  (`wiki_routes.py:52-115`, tested); machinery-file exclusion.
  **`pkb.search`/`_iter_pkb_files` (`pkb.py:391-411`) walk all of `lab/pkb/`
  with no world scoping and no approval gate** (backs ungated
  `GET /api/pkb/search`). The debt-finance sprint (branch
  `qukaizen/modern-finance-world-plan-a34437`,
  `sprints/2026-07-26-world-of-debt-finance/`, read via `git show`) relocated
  sensitive output to `lab/data/`, never `lab/pkb/`, and deferred cross-World
  scoping to "a separate, cross-World vision pass" — this sprint is arguably
  that pass.
- `/worlds` and `/dac` are ungated every-tier surfaces.
- Stale docs: `arailctl:170` advertises removed `world mount --apply-face`;
  `2026-06-14-world-switcher/ARCHITECTURE.md`'s "mount never touches other
  worlds' staged dirs" predates `_sweep_other_worlds`.

## Prior art to read (from files, not memory)

- `BLUEPRINTS.md`, `blueprints/README.md` — instance philosophy
- `sprints/2026-06-14-world-switcher/` — built the dropdown this may replace
- `sprints/2026-06-27-dac-world-mount/` — mount/seal/staging semantics
- `sprints/2026-07-08-world-forge/` — world authoring
- `docs/REPOSITORY_LAYOUT.md` — the unbuilt `ARAIL_HOME` proposal
- `ROADMAP.md` — no conflicting track; closest are "Multi-user mode" (Later)
  and "Phase 2 inference worker isolation" (Next)
