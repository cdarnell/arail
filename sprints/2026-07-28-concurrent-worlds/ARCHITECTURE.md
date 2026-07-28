# Architecture: Concurrent Worlds as independent instances

**Date:** 2026-07-28
**Spec:** [VISION.md](./VISION.md) at `a2bb7f8` · [BRIEF.md](./BRIEF.md) at `25efe24`
**Branch:** `qukaizen/arailctl-concurrent-worlds-33db65`
**Mode:** design

> Every `file:line` anchor below was re-verified on disk on 2026-07-28 in this
> worktree. Where I found something the BRIEF did not name, it is flagged
> **[NEW FINDING]**. Where I refined or overruled a VISION ruling, it is flagged
> **[REFINEMENT]** with the reason.

---

## Restatement

ARAIL today runs exactly one portal process against exactly one `lab/` tree, and
that tree can hold exactly one mounted World — not by accident but by design,
because `_sweep_other_worlds` (`world_mount.py:1343-1372`, verified) `rmtree`s
every other `sources/world-*/` directory on every mount. So "two Worlds live at
once" and "two data roots live at once" are the same sentence. This sprint makes
that sentence executable: `./arailctl start --world <slug>` launches a *second
process* rooted at a per-World `LAB_ROOT`, on its own portal and memory port,
sharing the machine's model weights and Ollama daemon, recorded in a registry
that becomes the one true answer to "what is running." `./arailctl status` reads
that registry and prints one row per instance — world, port, PID, checkout, data
root — replacing the four mutually-contradicting liveness heuristics that cost
the operator a `ps`/`launchctl`/`__file__` archaeology session. The isolation is
structural (different directories), never a filter.

---

## Assumptions

Each is falsifiable; each has a test in §Test strategy.

1. **A32.1 — Process separation is sufficient isolation.** Two uvicorn processes
   with disjoint `LAB_ROOT`/`ARAIL_DATA_DIR`/`LAB_PKB` cannot observe each
   other's PKB. Rests on there being no absolute path baked anywhere in
   `src/arail/`. Verified for the five config paths (`config.py:84-89`); the
   one known bypass (`egress.py:92`) re-reads `os.getenv("ARAIL_DATA_DIR")`,
   which the env pack exports — so it resolves correctly. See §6.
2. **A32.2 — Weights are shared safely.** `ARAIL_MODELS_DIR` is read-mostly;
   concurrent readers of a GGUF/MLX checkpoint are safe. Only setup writes it.
3. **A32.3 — The Worlds catalog is a single-writer-per-bundle store.** Runtime
   sidecars *are* written into bundle dirs (`.gitignore:122` pins
   `lab/worlds/*/librarian-scout.json`; also `review.json`, `evolution.json`).
   Sharing the catalog read-write is only safe because the registry enforces
   **one live instance per World slug** (§2). That uniqueness constraint is not
   cosmetic — it is what makes a shared catalog sound.
4. **A32.4 — Ollama multiplexes.** One `ollama serve` answers N portals; the
   measured cost of an extra instance is ~300 MB (VISION §1). Disconfirming
   evidence #2 in VISION is the check on this.
5. **A32.5 — `python-dotenv` and `bash source` agree on the env pack.** We write
   it in the strict `KEY=value` subset both accept, with the same shell-safety
   discipline `tests/shell_source_safety_driver.sh:34-48` already pins.
6. **A32.6 — The operator's machine has `lsof` or `ss`.** `setup.sh:298-306`
   already assumes this and degrades to "assume free"; we inherit that and
   backstop with a real bind test.
7. **A32.7 — launchd stays single-instance.** No plist templating per World this
   sprint (VISION scope boundary).

---

## Data flow

```
./arailctl start --world finance
        │
        │  arailctl: parse argv, source .env, resolve REPO_ROOT (absolute)
        │  daemon_active()?  ── yes ──▶ refuse w/ named error (§4 guard)
        ▼
scripts/start.sh  ──sources──▶  scripts/lib/instances.sh   (THE single truth)
        │
        │ 1. resolve slug ──▶ lab/worlds/<slug>/  (jailed, seal-verified)
        │ 2. instance root ──▶ lab/instances/<slug>/
        │ 3. claim  O_EXCL   ──▶ lab/instances/registry.d/<slug>.claim
        │ 4. env pack (create on first boot, else read)
        │        lab/instances/<slug>/instance.env
        ▼
   set -a; source instance.env; set +a     ◀── ports, roots, identity, token
        │
        ├──▶ uvicorn arail.portal.app  --port $PORTAL_PORT
        │         │  ARAIL_ENV_FILE=<abs instance.env>  ──▶ config.py:26-30
        │         │  load_dotenv(pack) ──▶ LAB_ROOT / ARAIL_DATA_DIR / LAB_PKB
        │         │                        ARAIL_MODELS_DIR (SHARED, abs)
        │         │                        ARAIL_WORLDS_DIR (SHARED, abs)
        │         ▼
        │    GET /api/instance ──▶ {slug, token, port, data_root, checkout}
        │         ▲                         │
        │         └── readiness probe ──────┘  (token must match — anti PID-reuse,
        │                                       anti wrong-checkout)
        ├──▶ uvicorn arail.memory_service --port $LANCE_PORT
        │
        ├──▶ ollama serve   (machine-shared; started only if :11434 unreachable)
        │
        └──▶ world mount ──▶ <instance>/pkb/sources/world-finance/
                             <instance>/data/world-mount.json
                             <instance>/pkb/.cache/lancedb
        │
        ▼ (only after portal answers with matching token)
   registry.d/<slug>.json   ◀── atomic tmp + os.replace; claim removed
        │
        ├──▶ ./arailctl status   (glob registry.d/*.json → liveness → rows)
        ├──▶ ./arailctl stop --world <slug>  (kill by recorded PID, cmdline-verified)
        └──▶ GET /api/instances  (portal A reads the same dir → roster liveness)
```

**What is NOT in the flow, deliberately:** no instance ever reads another
instance's `LAB_ROOT`; no portal endpoint spawns a process; no instance writes
another instance's registry record except `status`'s stale-prune.

---

## 1. Instance model & on-disk layout

### 1.1 Where instance roots live

```
<repo>/
  lab/                          ← the ROOT LAB (unchanged, legacy, port 8080)
    pkb/  data/  models/  worlds/
    instances/                  ← NEW. gitignored.
      registry.d/               ← NEW. the liveness truth (§2)
        finance.json
        finance.claim           ← transient, O_EXCL race guard
      finance/                  ← one World instance
        instance.env            ← the env pack (0644; no secrets in it)
        data/                   ← ARAIL_DATA_DIR  (secrets.env 0600 lives here)
        pkb/                    ← LAB_PKB  (sources/world-finance/, .cache/lancedb)
        log/
      ai/
        instance.env  data/  pkb/  log/
```

**Why `lab/instances/` and not repo-root `instances/`.** Repo-root `instances/`
is `blueprint.sh`'s namespace (`blueprint.sh` scaffolds
`instances/<name>/{.env,lab.conf,log/,blueprint.toml}`, verified; nothing under
`src/arail/` reads it; the directory has never existed on this machine).
VISION's scope boundary forbids unifying with it *and* forbids colliding with
it. `lab/instances/` satisfies both: disjoint path, and it sits under `lab/`
where all other runtime state already lives — so `reset.sh`'s mental model
("runtime state is under `lab/`") stays true, and `du -sh lab/` still totals the
lab. **Nesting is safe:** the root lab's PKB walker scans `lab/pkb/`, never
`lab/` (`pkb.py:391-411` roots at `PKB_ROOT`), so instance trees are invisible
to the root lab's search.

### 1.2 What the env pack pins

`lab/instances/<slug>/instance.env` — written once on first boot, read verbatim
after. **Every path absolute.** Format: strict `KEY=value`, values double-quoted
only when they contain no `$`, backtick, or `"` (reuse the
`shell_source_safety_driver.sh:34-48` discipline; a slug is `_SLUG_RE`-jailed
`^[a-z0-9][a-z0-9-]*$` — `world_mount.py:141`, verified — so slugs cannot inject).

| Key | Value | Why |
|---|---|---|
| `ARAIL_INSTANCE` | `<slug>` | marks the process as instance-scoped; gates the boot assertion (§6) |
| `ARAIL_ENV_FILE` | `<abs>/lab/instances/<slug>/instance.env` | **the load-bearing line.** `config.py:26-30` — pins which `.env` python-dotenv reads, so the process cannot walk up and find the repo (or a parent worktree's) `.env` |
| `LAB_ROOT` | `<abs>/lab/instances/<slug>` | absolute — defeats the CWD-relative `_resolve()` hazard (`config.py:57-61`) |
| `ARAIL_DATA_DIR` | `<LAB_ROOT>/data` | explicit, not derived |
| `LAB_PKB` | `<LAB_ROOT>/pkb` | explicit |
| `ARAIL_EXPERIMENTS_DIR` | `<LAB_ROOT>/data/experiments` | explicit |
| `ARAIL_MODELS_DIR` | `<abs>/lab/models` (**shared**) | **[NEW FINDING] must be set explicitly.** `config.py:86` defaults `MODELS_DIR` to `LAB_ROOT/models`. Moving `LAB_ROOT` silently forks the weights dir per instance and every instance would re-download 5 GB. Not in the BRIEF. |
| `ARAIL_WORLDS_DIR` | `<abs>/lab/worlds` (**shared**) | the World *library* is shared; see A32.3 |
| `PORTAL_PORT` | allocated, see §3.4 | in the pack ⇒ python and argv agree ⇒ the `lab.conf` drift bug cannot recur for instances |
| `LANCE_PORT` | allocated, see §3.4 | closes the 7414-collision gap the BRIEF flagged for `blueprint.sh` |
| `BIND_ADDR` | inherited from root `.env`, default `127.0.0.1` | |
| `LAB_NAME`/`LAB_SHORT_NAME` | from the World's `face.json` display name | VISION §6 — reuse the existing rebrand seam, invent nothing |
| `LAB_THEME`/`LAB_INTENT` | from `face.json` | `identity.py:70-87` reads these for the *unmounted* fallback; once the World is mounted `effective_identity()` derives them from the mount sidecar anyway. Setting them makes the instance legible **even before the first mount completes**. |

**Not in the pack:** `LAB_MODE` (inherits root `.env` ⇒ airgapped default
untouched — hard constraint), `ARAIL_AUTOCHECKS` (absent ⇒ off — hard
constraint), any secret, any token. `ARAIL_INSTANCE_TOKEN` is generated per boot
and exported into the child env **only** (never written to the pack) — see §2.3.

### 1.3 Shared vs per-instance — the ruling

| Resource | Shared? | Justification |
|---|---|---|
| `lab/models/` (`ARAIL_MODELS_DIR`) | **Shared** | 5 GB artifacts; read-mostly (A32.2). Duplicating per World is the thing VISION explicitly calls absurd. |
| `lab/worlds/` (`ARAIL_WORLDS_DIR`) | **Shared, read-write** | Sole store of World bundles; `_adopt_into_catalog` (`world_mount.py:1494`) writes into it on mount, and sidecars are written into bundle dirs. Safe **only** under the one-live-instance-per-slug constraint (§2.4). |
| Ollama `:11434` | **Shared, machine-level** | `start.sh:85-99` already treats it this way (starts one only if unreachable; owns it via `.ollama-started-by-arail.pid`). Unchanged. |
| `pkb/`, `data/`, LanceDB, wiki cache, `world-mount.json`, `secrets.env`, `egress.jsonl` | **Per-instance** | VISION L2. This is the isolation. |
| ttyd / jupyter / code-server / MLX | **Neither** — not started for instances (§3.6) | |

### 1.4 gitignore additions

Append to `.gitignore` (which already has `lab/data/`, `lab/models/`,
`lab/worlds/*/librarian-scout.json`):

```
# Per-World instance runtime (concurrent Worlds)
lab/instances/
```

One line covers roots, env packs, registry, logs, and per-instance secrets. Do
**not** add a negation for `registry.d/` — a registry is machine state and must
never be committed (it carries absolute checkout paths and PIDs).

---

## 2. The instance registry — the single liveness truth

### 2.1 Format and location

**A directory of one JSON file per instance**, not a single JSON file:
`lab/instances/registry.d/<slug>.json`.

**Why a directory.** A single shared file needs a lock for concurrent
`start`/`stop`/`status` across processes, and bash has no portable file locking
(`flock` is Linux-only; macOS ships no `flock(1)`). One file per instance gives
per-record atomicity for free: writer does `tmp + mv` (POSIX rename is atomic
within a filesystem — the same technique `_write_record`,
`world_mount.py:692-699`, already uses for `world-mount.json`), and readers glob.
No lock, no partial read, no lost update.

```json
{
  "schema": "arail.instance-registry/v1",
  "slug": "finance",
  "display_name": "Finance World",
  "checkout": "/abs/path/to/repo",
  "instance_root": "/abs/path/to/repo/lab/instances/finance",
  "data_dir":  "/abs/.../lab/instances/finance/data",
  "pkb_root":  "/abs/.../lab/instances/finance/pkb",
  "bind": "127.0.0.1",
  "portal_port": 8090,
  "lance_port": 8094,
  "launcher_pid": 41221,
  "portal_pid": 41223,
  "memory_pid": 41224,
  "token": "c1f0…(uuid4, per boot)",
  "started_at": "2026-07-28T14:03:11Z",
  "arailctl_version": "<git describe or version string>"
}
```

### 2.2 Write / read discipline

- **Write:** `python3 -c` one-liner (python3 is a hard dep already — `status.sh:69`
  uses it) serialising the record to `<slug>.json.tmp` then `os.replace`. Never
  hand-rolled `echo >` JSON.
- **Read:** `for f in registry.d/*.json` → parse with python3. Missing dir, empty
  glob, and corrupt JSON must all be non-fatal (mirror
  `list_available_worlds()`'s never-raises contract, `world_mount.py:714-821`).
- **The record is written only after the portal answers with a matching token.**
  A record's existence therefore means "this instance was, at some point,
  actually serving" — never "we tried."

### 2.3 Liveness predicate — precisely

`inst_alive <slug>` returns 0 iff **all four** hold. This is the definition that
replaces all four legacy checks.

1. `registry.d/<slug>.json` exists and parses.
2. `kill -0 <portal_pid>` succeeds.
3. **Anti-PID-reuse:** `ps -p <portal_pid> -o command=` matches
   `uvicorn.*arail\.portal\.app` **and** contains `--port <portal_port>`. A
   recycled PID belonging to an unrelated process fails here. (Cheap; no network.)
4. **Anti-wrong-checkout (`--probe`, and always during `start`'s attach check):**
   `GET http://<bind>:<portal_port>/api/instance` (timeout 0.7 s) returns JSON
   whose `token` equals the record's `token` **and** whose `checkout` equals the
   record's `checkout`.

Steps 1–3 are the default for `status` (no network, well under the 2 s win
condition for 3 instances). Step 4 runs for `start`'s attach decision, for
`stop`'s confirmation, and on `status --probe`. **Step 4 is the direct kill of
the motivating incident**: a daemon crash-looping against a *different checkout*
answers with the wrong `checkout`, and `status` says so by name instead of
requiring `arail.__file__` archaeology.

`GET /api/instance` is the new endpoint that makes step 4 possible (§5.1).

### 2.4 Uniqueness constraint

**One live instance per World slug**, enforced at claim time (§3.5). This is what
licenses the shared read-write Worlds catalog (A32.3) and what makes "attach,
never respawn" (VISION §3) well-defined.

### 2.5 Staleness and pruning

A record failing predicate step 2 or 3 is **stale**. `status` prints it as
`stale (pid <n> gone)` and removes it — pruning is a `status` side effect
because `status` is the command the operator reaches for after a crash, and a
stale record must never block a restart. `start` also prunes the target slug's
stale record before claiming. Pruning removes only the record; it never touches
`lab/instances/<slug>/` data. (Deleting user data as a side effect of a status
command would be exactly the "data-loss-shaped action" VISION forbids.)

### 2.6 Reconciling the four disagreeing checks

All four are replaced by helpers in a **new** `scripts/lib/instances.sh`, sourced
by `arailctl`, `start.sh`, `status.sh`, `reset.sh`.

| Site (verified) | Today | Becomes |
|---|---|---|
| `arailctl:195` `daemon_installed()` | `[[ -f ~/Library/LaunchAgents/io.arail.portal.plist ]]` | `daemon_active()` = plist exists **AND** `launchctl list io.arail.portal` prints a numeric `"PID" =` line. **This is the plist trap's death.** After `./arailctl stop` (which unloads but keeps plists, `arailctl:222-228`), `daemon_active` is false ⇒ `start` runs in the foreground as the operator expects. |
| `start.sh:35` | `launchctl list io.arail.portal >/dev/null` (true when *loaded but crash-looping*) | `daemon_active()` — same function, one definition |
| `status.sh:42` | plist file exists + `uname` | `daemon_active()` for the verdict; plist-exists only to print "installed, inactive" |
| `install-daemon.sh:76-79` | `pgrep -f uvicorn.*arail\.portal\.app && ! launchctl list` | `inst_any_alive()` (registry-driven) `|| pgrep` fallback for a legacy root lab; message names which instance blocks |
| `status.sh:32-39` `check()` | **[NEW FINDING]** takes `$port` but only *prints* it — the match is `pgrep -f <pattern>`, port-agnostic. With N instances it reports "Portal running on :8080" while looking at the :8090 process. | Port-scoped pattern (`--port <p>`) for the root lab; registry rows for instances |

**Rule for the builder: after this sprint, the strings
`~/Library/LaunchAgents/io.arail.portal.plist` and `launchctl list io.arail.portal`
appear in exactly one place each — inside `scripts/lib/instances.sh`.** A grep
proving that is WP2's verification gate.

---

## 3. `./arailctl start` retrofit

### 3.1 Argument parsing

`arailctl:229` already does `exec bash "$REPO_ROOT/scripts/start.sh" "$@"`
(verified) — the args reach `start.sh`, which then discards them. Parsing lands
in `start.sh` (keeps `arailctl` a thin dispatcher).

```
./arailctl start [--world <slug>] [--port <n>] [--no-browser] [--list] [--yes]
```

- `--world <slug>` — non-interactive. Unknown slug ⇒ exit **2** with the list of
  known slugs (VISION §3: "non-zero exit if the slug doesn't exist").
- `--port <n>` — override the allocated portal port; re-pinned into the pack.
- `--list` — print the roster and exit 0 (scriptable, no side effects).
- `--yes` — never prompt; with >1 World and no `--world`, exit 2 rather than
  block on a picker. Required for CI and for the shell test driver.
- Unknown flag ⇒ exit 2 with usage. (Silently ignoring argv is the bug we are
  fixing; do not re-introduce it in a new place.)

### 3.2 Bare `./arailctl start` — picker rules (VISION §3, verbatim)

Let `W` = worlds in `ARAIL_WORLDS_DIR` via `list_available_worlds()`.

| Condition | Behaviour |
|---|---|
| `|W| == 0` | **Legacy root lab.** Start `lab/` on 8080 exactly as today, all seven services. No instance, no registry record beyond a `root` pseudo-row. Preserves every existing user. |
| `|W| == 1` | Start that World's instance. No picker. (VISION: the picker must not tax the single-World user.) |
| `|W| >= 2`, TTY | Interactive picker: numbered rows, each annotated with liveness from the registry — `2) Finance World  finance   ● running :8090` / `3) AI & ML World  ai   ○ not running`. Plus a `0) AI Lab (default — the root lab on :8080)` row so the legacy lab stays reachable. One keystroke. |
| `|W| >= 2`, no TTY or `--yes` | exit 2, print the roster and the exact `--world` command to use. Never guess. |

Selecting a **running** instance from the picker is an attach (§3.3), not an error.

### 3.3 Attach-on-running

Before anything is spawned: if `inst_alive <slug>` (all four steps, including
the token probe):

```
Finance World is already running.
  URL:        http://127.0.0.1:8090
  Data root:  /…/lab/instances/finance
  Started:    2026-07-28T14:03:11Z (pid 41223)
Opening in your browser… (suppress with ARAIL_NO_BROWSER=1)
```

**exit 0.** Never respawn, never error. This is VISION §3's explicit ruling and
it removes today's silent-death failure (a second `start` spawns a uvicorn that
cannot bind and dies with no message — verified: `start.sh` has no `lsof`, no
lock file, no already-running detection).

### 3.4 Port allocation

**Layout:** each instance owns a 10-port block. Block `k` base `B_k = 8090 + 10k`.
Within a block: portal `B_k+0`, memory/Lance `B_k+4`. Offsets 1–3 and 5–9 are
reserved for the per-instance ttyd/notebook/IDE/MLX we are *not* starting (§3.6)
so a future sprint needs no renumbering.

**Range safety:** 8090 is above the root lab's 8080 and below `blueprint.sh`'s
9100 base (verified: `blueprint.sh` base = max existing instance `PORTAL_PORT`+10,
default 9100). With the ceiling of 3 (§3.7) the top port used is 8114 — a clean
25-port corridor that touches neither neighbour. **Hard stop: refuse any
allocation at or above 9100**, even under a raised `LAB_MAX_INSTANCES`, and say
why. Also excluded: 8443 (IDE), 8888 (notebook), 7681 (ttyd), 7414 (root Lance),
11434/11435 (Ollama/MLX) — none fall in 8090–8114, but the exclusion list is
explicit in code so a future range change can't silently collide.

**Allocation is once-and-pinned, not re-derived.** First boot walks `k = 0,1,2…`
and takes the first block where both ports are free (`_port_in_use()` from
`setup.sh:298-306` — reuse it, do not write a fourth copy) **and** unclaimed by
any registry record. The result is written into `instance.env` and reused
forever after.

> **[REFINEMENT of VISION §Wedge "a deterministic port."]** VISION says
> deterministic *per World*. A pure function of the slug (e.g. a hash) is
> deterministic but cannot guarantee the port is free, and would silently move
> the user's bookmarked URL if we ever changed the hash or if they used
> `--port`. Allocate-once-then-pin is deterministic **from the operator's point
> of view** — the Finance World is always on 8090 — while remaining collision-safe.
> This is the same contract `setup.sh:329-345` already gives for the root ports
> ("pinned in lab.conf — future runs reuse the bumped values"), so it is the
> behaviour the operator already knows.

**Bind test, not just a scan.** `_port_in_use` is a TOCTOU check. Belt and braces:
(a) scan at allocation, (b) treat the portal readiness probe (§3.5 stage 5) as
the authority — if the port was stolen between scan and bind, uvicorn dies and
the probe times out, and we report `port 8090 taken (bind failed)` with the
`lsof -iTCP:8090` line to run. Never claim success on an unbound port.

### 3.5 The staged launch

Ordered stages, one line each, each with a real check. `start.sh` prints
`[1/8] …` prefixes and a `✓`/`✗` per stage. **The prompt does not return
claiming success until stage 6 passes** (VISION §4).

| # | Stage | Check | On failure |
|---|---|---|---|
| 0 | Preflight | `daemon_active()` false (§4.4); `.venv/bin/activate` exists; `LAB_MAX_INSTANCES` not exceeded (§3.7) | exit 1, named error, nothing spawned |
| 1 | Resolve World | slug matches `_SLUG_RE`; dir under `ARAIL_WORLDS_DIR` (jail: reuse the `_resolve_world_dir` prefix-check shape from `app.py:3126-3156`); `verify_seal` passes | exit 2 — **refuse before creating an instance root** |
| 2 | Claim | `set -o noclobber` + `> registry.d/<slug>.claim` (O_EXCL); stale record pruned first; trap removes the claim on any exit | exit 1 "another start for `<slug>` is in progress (pid N)" |
| 3 | Instance root | first boot: mkdir `data/`, `pkb/{sources,notes}`, `log/`; write `instance.env`; allocate ports. Re-boot: read pack, assert all paths absolute | exit 1 |
| 4 | Bind ports | both ports free per `_port_in_use` | exit 1, print the `lsof` line |
| 5 | Portal up | spawn uvicorn; poll `GET /api/instance` every 0.25 s to 60 s; require token **and** checkout match | kill the child, exit 1, tail `log/portal.log` |
| 6 | Memory up | spawn memory service; poll its port to 20 s | **warn, continue** — chat works without it; degradation is honest |
| 7 | Model backend | Ollama `/api/version` (start one iff unreachable — reuse `start.sh:85-99` verbatim, incl. the pidfile ownership rule) | **warn, continue** — airgapped labs may intend no backend |
| 8 | World bound + index | if `<data>/world-mount.json` absent or names another slug ⇒ mount; then report staged term count | mount failure ⇒ warn + leave instance up unmounted (the portal is usable; `/worlds` can retry) |
| — | Record + URL | write `registry.d/<slug>.json`, remove claim, print the URL, open browser unless `ARAIL_NO_BROWSER=1` / not a TTY | |

**How stage 8 mounts — [REFINEMENT of VISION note 9].** The BRIEF frames the
`pkb_root=`/`data_dir=`/`worlds_dir=` kwargs (`world_mount.py:1433-1438`,
verified) as "the seam." They are *a* seam, for in-process multi-root work. We do
not need them: because the env pack exports `LAB_PKB`/`ARAIL_DATA_DIR`/
`ARAIL_WORLDS_DIR` and pins `ARAIL_ENV_FILE`, `_default_pkb_root()` /
`_default_data_dir()` (`world_mount.py:655-665`) already resolve to the instance
in that process. So stage 8 runs the **existing** `./arailctl world mount <dir>`
under the instance environment, and `api_worlds_select` (`app.py:3172`, which
calls `mount(bundle_dir)` with no kwargs — verified) is correct as-is inside an
instance process. **Process-level isolation is the mechanism; the kwargs stay
for tests.** This is a strictly smaller change than threading kwargs through
every call site, and it means the portal code path is identical in root and
instance labs — one code path, not two.

### 3.6 What a World instance does NOT start

**Not started:** ttyd (7681), jupyter (8888), code-server (8443), MLX
(11435). Rationale, per service:

- **ttyd/jupyter/code-server** are single-user developer conveniences bound to
  the *checkout*, not the World; all three are already port-scoped singletons,
  and running three code-servers is 3× the memory of the entire instance we just
  budgeted at 300 MB. The root lab keeps all three; the instance's nav links to
  the root lab's terminal/notebook/IDE. **Honesty requirement:** those nav tiles
  in an instance must say "served by the root lab on :7681", not silently 404.
- **MLX** is a model process. VISION's scope boundary: "Per-instance model
  processes. Shared Ollama/MLX only." — out of scope, unambiguous.
- **Ollama** stays machine-shared, unchanged (`start.sh:85-99`).

`start.sh`'s existing seven-service block is therefore gated: `if [[ -z
"${ARAIL_INSTANCE:-}" ]]` for the four above. Root-lab behaviour is untouched.

### 3.7 Ceiling

`LAB_MAX_INSTANCES` default **3** (VISION §5). At the limit: refuse, print the
live roster and the exact `./arailctl stop --world <slug>` line. At
`LAB_MAX_INSTANCES >= 4`: proceed but soft-warn once. **No eviction, ever** —
VISION is explicit that auto-stopping a lab is data-loss-shaped.

---

## 4. `./arailctl status` / `stop` retrofit

### 4.1 `status`

Registry-driven table first, then the existing root-lab sections (venv, runtime
state) unchanged. Target: <2 s for 3 instances (win condition #2) — achieved by
defaulting to the no-network predicate steps 1–3.

```
Arail — Instances                              (checkout: /Users/…/qukaizen-arail)

  ●  finance   Finance World     :8090  pid 41223  up 2h14m
                 data  lab/instances/finance
  ●  ai        AI & ML World     :8100  pid 41500  up 6d01h
                 data  lab/instances/ai
  ○  root      AI Lab (default)  :8080  not running

  Supervision: foreground.  launchd plists installed but inactive.
```

- `--probe` adds predicate step 4 and a `checkout` column; a mismatch renders
  `⚠ serving from a DIFFERENT checkout: /other/path` — the motivating incident,
  as one line.
- `--json` for scripting and for QA assertions.
- Stale rows print `✗ stale (pid 41223 gone)` and are pruned (§2.5).

### 4.2 `stop`

```
./arailctl stop [--world <slug>] [--all]
```

| Situation | Behaviour |
|---|---|
| `--world <slug>` | Stop that instance only. |
| `--all` | Stop every live instance, then the root lab. |
| No args, 0 instances live | Today's behaviour: `reset.sh stop` for the root lab. |
| No args, exactly 1 instance live | Stop it (and the root lab if also live), after naming it. |
| No args, ≥2 instances live | **Refuse.** Print the roster and require `--world` or `--all`. Refusal that names the fix beats guessing which lab to kill — VISION §5's principle applied to stop. |

**Instance-scoped kill — the exact mechanism.** For the target record:

1. Candidate PIDs = `portal_pid`, `memory_pid`, `launcher_pid` from the record.
2. **Verify before killing:** for each, `ps -p <pid> -o command=` must match the
   expected pattern **and** contain `--port <that instance's port>`. A PID that
   fails verification is skipped and reported — never killed. This is the PID-reuse
   guard applied to the destructive path, where it matters most.
3. `TERM` → 2 s grace → `KILL`, reusing `reset.sh:126-141`'s existing loop shape.
4. Remove the registry record. Do **not** touch `lab/instances/<slug>/`.
5. Ollama: only if this was the last live instance *and* the pidfile in **that
   instance's** data dir says we started it (`_ollama_pid_if_we_started_it`,
   `reset.sh:154-169`). Never pattern-match Ollama — that rule stands.

**Fixing `reset.sh`'s kill-everything.** Verified: `reset.sh:104-106`'s three
uvicorn patterns are port-agnostic, so `reset.sh stop` today kills *every* ARAIL
portal/memory/mlx on the box — the moment instance #2 exists, `./arailctl stop`
in the root lab silently kills the Finance instance mid-write. Fix:
`stop_services()` takes an optional port set; when instances exist it kills only
verified registry PIDs; the legacy path appends `.*--port <PORTAL_PORT>` to the
three uvicorn patterns. `tests/test_reset_stop_scope.py` (exists, verified) must
stay green and gains instance cases.

### 4.3 What `stop` no longer does

`stop` never unloads launchd plists as a side effect of stopping an instance.
Daemon control stays `./arailctl stop` with no `--world` on a daemon-active
machine, exactly as today (`arailctl:220-228`).

### 4.4 Daemon-mode guard — the exact predicate

launchd is machine-global with fixed labels `io.arail.{portal,memory,mlx}` and
host+port baked into the plist argv (verified). Multi-instance under launchd is
out of scope. The guard, in `start.sh` stage 0:

```
if daemon_active; then
    if [[ -n "$WORLD_SLUG" ]]; then
        # refuse — exit 1
        "Daemon mode is active (launchd supervises the lab on :$PORTAL_PORT)."
        "Daemon mode is single-instance: it cannot host a second World."
        "  To run Worlds side by side:  ./arailctl uninstall-daemon && ./arailctl start --world $WORLD_SLUG"
        "  To keep the daemon:          use the lab it already serves at http://…"
    else
        <existing launchd kickstart branch, arailctl:211-219>
    fi
fi
```

If the plist exists but `daemon_active` is **false**, foreground start proceeds
and prints one dim line: `launchd plists installed but inactive — starting in the
foreground.` That single behaviour change retires the trap that motivated the
sprint. `install-daemon.sh` gains a symmetric refusal: if any instance is live,
die with "stop instance(s) first: `./arailctl stop --all`" (today's check at
`:76-79` would not see them, because its pgrep matches the *root* pattern and its
message names the wrong remedy).

---

## 5. Portal / UI deltas

Deliberately minimal — the centre of gravity is the CLI runtime.

### 5.1 `GET /api/instance` (new)

Self-report of the process answering. **Load-bearing for §2.3 step 4.**

```json
{"slug":"finance","token":"c1f0…","portal_port":8090,
 "checkout":"/abs/repo","data_root":"/abs/…/lab/instances/finance",
 "world":"finance","display_name":"Finance World","started_at":"…"}
```

- Read-only, no side effects, airgap-safe (local state only).
- `token` from `ARAIL_INSTANCE_TOKEN` (child env only, never on disk in the
  pack). It is a **liveness nonce, not a credential** — it grants nothing, so
  serving it on a loopback-bound endpoint is not a secret disclosure. Document
  that in the docstring so a future reader doesn't "harden" it into uselessness.
- Root lab (no `ARAIL_INSTANCE`) returns `{"slug":"root", …}`.

### 5.2 `GET /api/instances` (new)

Portal A learns about instance B **by reading `registry.d/`** — the same single
truth the CLI uses. No cross-instance HTTP, no discovery protocol, no state
shared in memory. Returns the roster with liveness computed by predicate steps
1–3 (no probe — an HTTP fan-out from a request handler is a stall risk). Read-only.

### 5.3 `/worlds` — Mount button semantics

Per VISION §2, the button's label is a pure function of two facts:

| Target World's state | Current root's state | Button |
|---|---|---|
| no live instance | **no** World mounted here | **Mount** — the surviving first-bind case. Non-destructive by construction: nothing to sweep. |
| no live instance | a World **is** mounted here | **Launch** |
| live instance | any | **Open** → `http://<bind>:<port>` (new tab) |
| currently mounted here | — | **Unmount** (→ default) — the surviving unbind case |

**Launch shows a copyable command; it does not spawn.**

> **[REFINEMENT / partial overrule of VISION §2.]** VISION says the button
> "offers **Launch / Open**." Open is a link — fine. Launch, if it actually
> spawned a process, would turn a loopback HTTP endpoint into a
> process-execution surface: a CSRF-reachable `POST` that forks a long-lived
> server with an operator-controlled slug. The CSRF envelope on
> `api_worlds_select` (`app.py:3193-3205`, verified) is a same-origin heuristic,
> not an authenticator, and the product CLAUDE.md's paranoid checklist names
> "code-execution surfaces without sandboxing" explicitly. So **Launch renders
> the exact command** (`./arailctl start --world finance`) with a copy button
> and a one-line "run this in your terminal." Same user outcome, one keystroke
> more, no new RCE-adjacent surface. If a real one-click launch is wanted later,
> it needs its own threat model and its own sprint.

`POST /api/worlds/select` keeps working this sprint (removal is next sprint per
the scope boundary) but returns **409 `instance_live`** when the requested slug
has a live instance — otherwise mounting it here would `_sweep_other_worlds` a
World that another process is actively serving. **[NEW FINDING — this is a
genuine data-loss path the VISION did not enumerate]**: without this check, the
deprecation-window dropdown in instance A can delete instance B's staged layer
out from under it. Non-negotiable; it ships with the registry, not with the
deprecation.

### 5.4 Nav dropdown → roster viewer

`nav.js:633-895` (verified: builds the menu from `/api/worlds`, `change-world`
navigates to `/welcome?step=world`, and `POST /api/worlds/select` fires at
`:885`). Change: fetch `/api/instances` alongside `/api/worlds`, render a
liveness dot + `:port` per row, and route clicks to **Open** (live) or a
disabled row with the launch command (not live). The mutating `select` POST stays
only for the first-bind/unbind rows. Keep the existing theme-swatch painting
(`nav.js:737-750`) — it is exactly VISION §6's "tell them apart at a glance."

### 5.5 Deprecation notice + title

- One dismissible line on `/worlds`: *"Switching Worlds in place is being
  replaced by instances — one World per lab, side by side. `./arailctl start
  --world <slug>`. In-place Mount is removed in the next release."* Placement:
  above the World grid; not a modal.
- **Page title:** `{{ identity.name }} · :{{ portal_port }}` in `base.html`, so
  two tabs are never identical. VISION §6 calls the two-identical-tabs case a
  harm, not a papercut; the title is the cheapest place to fix it. The port must
  come from the same env the process bound (§6.2), or the title lies.

---

## 6. Python config plumbing

### 6.1 How the env pack reaches uvicorn

Two mechanisms, deliberately redundant, because they cover different consumers:

1. `set -a; source "$INSTANCE_ENV"; set +a` in `start.sh` → the values are in the
   child's environment → `os.getenv` consumers (`egress.py:92`,
   `opencode.py:588,1036`, `app.py:9498,9727`, `_builtin_sre.py:271` — all
   verified as os.getenv readers) see the right values.
2. `ARAIL_ENV_FILE=<abs pack>` → `config.py:26-30` calls
   `load_dotenv(ARAIL_ENV_FILE)` → any process started *without* the shell
   wrapper (a test, a `python -m arail…` in the instance dir) still resolves
   correctly. `load_dotenv` does not override already-set env vars, so (1) and
   (2) cannot disagree.

### 6.2 The `lab.conf`-without-`set -a` fix

Verified: `start.sh:21` is `source lab.conf 2>/dev/null || true` — no `set -a`.
So `PORTAL_PORT` reaches uvicorn's argv (shell-local expansion works) but is
**not exported**, and the Python process falls back to `.env`/default 8080 for
`os.getenv("PORTAL_PORT")`. `arailctl:213-218` already gets this right in the
launchd branch (`set -a && source lab.conf && set +a`). **Ruling: fix it —
IN SCOPE.** One line in `start.sh` and one in `status.sh:16`, bringing both into
line with `arailctl`. Cosmetic today; with instances it is cross-instance
misrouting (the SRE agent probing the wrong lab's port), and we are restructuring
these exact lines anyway. Leaving a known port-drift bug in a file we rewrite is
not a defensible omission.

### 6.3 `egress.py:92`

**Ruling: do not touch.** It re-reads `os.getenv("ARAIL_DATA_DIR")` instead of
importing `config.DATA_DIR`. Untidy, but the env pack exports `ARAIL_DATA_DIR`
explicitly (never leaving it to be derived), so the bypass lands in the right
instance dir. Refactoring it would touch the egress-honesty path — a
high-blast-radius, zero-benefit change in this sprint. **Cover it with a
regression test** (`test_instance_isolation.py`) asserting `egress.jsonl` is
written under the instance's data dir; if the test ever fails, the refactor
becomes justified.

### 6.4 The CWD-relative `_resolve()` hazard

`config.py:57-61` returns a bare `Path(default_rel)` when the env var is unset —
CWD-relative. `start.sh:5` does `cd "$REPO_ROOT"`, which is why this has been
survivable. Instances make it sharp. Two guards:

1. **The env pack sets all five paths explicitly and absolutely** — the bare
   default never fires in an instance.
2. **Boot assertion (new, ~8 lines in `arail/portal/app.py` startup):** if
   `ARAIL_INSTANCE` is set, assert each of `LAB_ROOT`, `DATA_DIR`, `PKB_ROOT`,
   `MODELS_DIR`, `WORLDS_DIR` `.is_absolute()`; otherwise raise at startup with
   the offending key named. Fail loud at boot, never silently write an instance's
   PKB into the CWD. Cheap, and it converts the entire class of "instance wrote
   to the wrong tree" bug into a startup error.

`_resolve()` itself is **not** changed — `tests/test_reset_paths.py` pins the
bash resolvers against the Python ones, and altering the Python semantics would
require changing `reset.sh:44-90` in lockstep for no gain here.

---

## 7. Secrets decision (VISION note 11)

**Ruling: per-instance `secrets.env` at `<instance>/data/secrets.env`, `0600`,
never auto-copied from the root lab or from any sibling instance.**

Reasoning, since VISION correctly says this is not obvious:

- A shared file (or a symlink into the root lab) means the **personal-finance
  instance can read the work instance's provider keys**, and vice versa. The
  fork audience's stated expectation (BRIEF, "a *work* lab and a *personal* lab
  that cannot see each other") is violated by a symlink in a way that is invisible
  from the UI. Isolation that has an exception is not isolation.
- Auto-copying on first boot is worse than sharing: it silently propagates
  credentials into a root the user believes is clean, and it does so at a moment
  (instance creation) when the user is not thinking about keys. Credentials must
  move only by an explicit act.
- The sprawl cost is real but small and bounded: a handful of provider keys × ≤3
  instances, and `LAB_MODE=airgapped` (the untouched default) means many
  instances never get a key at all.

**Mechanics.** First boot creates `<instance>/data/` mode `0700` and no
`secrets.env`. When the user first opens ⚙ Manage providers in the instance, the
existing save path writes `secrets.env` `0600` in that data dir — unchanged code,
correct dir, because `ARAIL_DATA_DIR` is exported. Stage 3 prints one line if the
root lab has a `secrets.env`: *"Provider keys are per-instance — add this
instance's keys via ⚙ Manage providers."* It names **no key and no value**. The
existing never-echo/never-log rule is untouched, and no new code reads a secret.

`.gitignore` line 11 pins `lab/data/secrets.env`; the new `lab/instances/`
blanket line covers every instance copy. Verify with `git check-ignore`.

---

## 8. Failure modes

| # | Failure | Detection | Recovery / behaviour |
|---|---|---|---|
| F1 | Port stolen between allocation scan and bind | Stage 5 readiness probe times out (60 s cap); uvicorn child already dead | Kill any survivors, remove the claim, no record written, exit 1: `port 8090 was taken during startup` + the `lsof -iTCP:8090 -sTCP:LISTEN` line. **Never a silently dead background uvicorn** (win condition #3). |
| F2 | Registry says up, PID is dead | Predicate step 2 (`kill -0`) | `status` prints `✗ stale (pid N gone)`, prunes the record, leaves data untouched. `start` prunes then proceeds. |
| F3 | PID reused by an unrelated process | Predicate step 3 (cmdline must match module **and** `--port`) | Treated as stale, not as live. **`stop` never kills an unverified PID** — it skips and reports. |
| F4 | Instance serving from a *different checkout* (the motivating incident) | Predicate step 4: `/api/instance`'s `checkout` ≠ record's | `status --probe` prints `⚠ serving from a DIFFERENT checkout: /other/path`. One line replaces the archaeology. |
| F5 | World slug invalid / unsealed / not in catalog | Stage 1: `_SLUG_RE` (`world_mount.py:141`), jail prefix-check, `verify_seal` | exit 2 **before any directory is created**. No half-built instance root. Slug list printed. |
| F6 | Two `start --world X` racing | Stage 2 O_EXCL claim (`set -o noclobber`) | Loser exits 1: `another start for X is in progress`. Winner's `trap … EXIT` removes the claim on every exit path, including SIGINT — so a Ctrl-C'd start does not wedge the slug. A claim older than 120 s is treated as abandoned and broken with a printed note. |
| F7 | Instance root deleted while running | Portal I/O errors; `status` shows the row live but `data_dir` missing | `status` prints `⚠ data root missing` and does **not** prune (the process is real). Operator decides. We never recreate a deleted root under a live process — that would silently resurrect a tree the user deliberately removed. |
| F8 | launchd daemon active + `start --world` | §4.4 `daemon_active()` | Refuse, exit 1, print the two-line remedy (uninstall-daemon, or use the served lab). Nothing spawned. |
| F9 | Plist installed but *not* loaded (today's trap) | `daemon_active()` false | Foreground start proceeds + one dim informational line. **The trap is gone.** |
| F10 | Ceiling reached | Stage 0 counts live records | Refuse; print the roster and the exact stop command. No eviction. `LAB_MAX_INSTANCES` documented as the override. |
| F11 | Same World mounted in-place while an instance serves it | `api_worlds_select` checks the registry (§5.3) | 409 `instance_live`. Prevents `_sweep_other_worlds` deleting a live instance's staged layer. |
| F12 | Memory service fails to bind | Stage 6 probe (20 s) | **Warn, continue.** Instance is usable; status shows memory down. Honest degradation beats refusing a working lab. |
| F13 | Ollama unreachable / not installed | Stage 7 probe | Warn, continue. Airgapped labs may intend this. Existing pidfile ownership rule unchanged. |
| F14 | Instance path resolves relative (config regression) | §6.4 boot assertion | Startup error naming the key. Cannot write to the wrong tree. |
| F15 | `reset.sh stop` in the root lab kills instances | `test_instance_stop_scope.py` | Port-scoped patterns + registry-verified PIDs (§4.2). |
| F16 | Corrupt / partial registry JSON | Parse failure on read | Non-fatal: row rendered `✗ unreadable`, file quarantined to `<slug>.json.bad`. Never crashes `status`, never blocks `start`. |
| F17 | Crash leaves ports bound (zombie uvicorn) | Stage 4 scan finds the port busy but no record | Named error listing the PID holding the port, plus the kill command. No auto-kill (we cannot prove it is ours). |

---

## 9. Test strategy

Product allocation for arail is 30 setup / 30 Buddy / 20 security / 10 happy /
10 regression. Buddy is not on this sprint's path; **that 30 % moves to
isolation-correctness**, which is this sprint's falsifiable core (VISION win
condition #1). QA's brief: 30 start/setup · 30 isolation · 20 security · 10
happy · 10 regression.

### New tests

| File | Kind | Covers (failure modes) |
|---|---|---|
| `tests/test_instance_registry.py` | pytest | Record schema, atomic tmp+replace, stale detect, PID-reuse rejection via stubbed `ps`, corrupt-JSON quarantine. **F2, F3, F16** |
| `tests/test_instance_paths.py` | pytest | Env pack → `config.py` resolution; all five paths absolute; `ARAIL_MODELS_DIR` stays shared (**the `config.py:86` trap**); `ARAIL_ENV_FILE` beats a parent-dir `.env`; boot assertion fires on a relative path. **F14** |
| `tests/test_instance_ports.py` | pytest | Block allocation determinism; pinned-on-reboot; never 8080/7414/8443/8888/7681; hard stop below 9100; `LANCE_PORT` always allocated. |
| `tests/instance_start_driver.sh` + `tests/test_instance_start.py` | shell driver + pytest wrapper (same pattern as `test_reset_stop_scope.py`, verified to exist) | Arg parsing incl. unknown-flag exit 2; picker rules for \|W\| = 0/1/≥2; `--yes` non-TTY refusal; attach-on-running exit 0; claim race; stage failure paths with stubbed `uvicorn`/`curl`/`pgrep`. **F1, F5, F6, F10, F17** |
| `tests/test_instance_stop_scope.py` | shell-driven pytest | `stop --world X` kills only X's verified PIDs; root-lab stop leaves instances alive; unverified PID skipped not killed. **F3, F15** |
| `tests/test_instance_isolation.py` | pytest — **the falsifiable core** | Mount World A in root A, then mount B in root B; assert A's `sources/world-a/` tree is byte-identical (sha256 per file) and its LanceDB dir untouched. Assert `egress.jsonl` lands per-instance (§6.3). Assert instance PKB is invisible to the root lab's `pkb.search`. |
| `tests/test_instance_api.py` | pytest | `/api/instance` shape + token; `/api/instances` roster from registry; **both read-only — assert no process-spawn path exists**; `select` → 409 `instance_live` (**F11**); CSRF envelope preserved. |
| `tests/test_daemon_predicate.py` | shell-driven pytest | plist-exists ≠ running; `daemon_active` true only with a launchctl PID line; `start --world` refused when active; foreground allowed when installed-but-inactive. **F8, F9** |
| `tests/test_instance_secrets.py` | pytest | `secrets.env` created 0600 in the instance data dir; **not** copied/symlinked from root; `git check-ignore` covers it; no secret value in any stdout/log fixture. |

### Existing suites that MUST stay green (non-negotiable)

`test_world_switcher.py`, `test_world_reset.py`, `test_reset_paths.py`,
`test_reset_stop_scope.py`, `test_shell_source_safety.py`,
`test_world_mount.py`, `test_world_identity_flip.py`, `test_default_worlds_catalog.py`.

### Performance

Win condition #2: `./arailctl status` < 2 s with 3 registered instances —
assert with a timed test using stubs. Win condition #3: instance launch < 60 s
warm — measured by QA manually and recorded in TEST_REPORT.md (a real-launch
timing test is too flaky for CI).

### Security (the 20 %)

1. Slug injection into the env pack (`; rm -rf`, `$(…)`, backticks) — blocked by
   `_SLUG_RE` **and** by the shell-source-safety writer; test both layers.
2. Path traversal in `--world ../../etc` — jail prefix-check.
3. No HTTP endpoint spawns a process (§5.3) — assert by grep + by test.
4. Secrets: 0600, not shared, not logged.
5. Registry files contain no credential (assert the key set).
6. Airgapped default unchanged in an instance — assert `LAB_MODE` resolves
   `airgapped` with no `.env` edit.

---

## 10. Ordered work packages

Each WP ends with a gate the builder runs **before** starting the next. Commit
per WP.

**WP1 — `scripts/lib/instances.sh`: paths, registry, liveness.**
Files: `scripts/lib/instances.sh` (new), `tests/test_instance_registry.py`,
`tests/test_instance_paths.py`, `.gitignore`.
Scope: path helpers (instance root, env pack, registry dir), record write
(python3 tmp+replace), record read, `inst_alive` (4-step predicate), `inst_list`,
`inst_prune`, `daemon_active`. No caller changes yet.
**Gate:** new tests pass; `bash -n` + `shellcheck` clean; `git check-ignore
lab/instances/registry.d/x.json` exits 0.

**WP2 — Retire the four liveness checks.**
Files: `arailctl` (`:195`, start/stop branches), `scripts/start.sh:35`,
`scripts/status.sh:42`, `scripts/install-daemon.sh:76-79`.
Scope: every site calls `daemon_active`/`inst_*`. No behaviour change beyond the
plist-trap fix (F9).
**Gate:** `grep -rn 'LaunchAgents/io.arail.portal.plist\|launchctl list io.arail.portal'
arailctl scripts/` returns hits in `scripts/lib/instances.sh` **only**;
`test_daemon_predicate.py` passes.

**WP3 — Env pack, first-boot scaffold, port allocation.**
Files: `scripts/lib/instances.sh`, `scripts/setup.sh` (export `_port_in_use`/
`_find_free_port` for reuse — do not copy them).
Scope: pack writer (shell-safe quoting), first-boot mkdir tree, block allocation
+ pinning, exclusion list, sub-9100 hard stop.
**Gate:** `test_instance_ports.py` + `test_instance_paths.py` pass; a
hand-written pack sources cleanly under `set -euo pipefail` **and** loads via
`python -c "import arail.config"` yielding absolute paths.

**WP4 — `start.sh` retrofit.**
Files: `scripts/start.sh`, `arailctl` (usage text).
Scope: arg parsing; picker; attach; the 8 stages; claim/trap; instance-service
gating (§3.6); **define `warn()`** (see below); `set -a` around `lab.conf`.
**Gate:** `instance_start_driver.sh` suite passes; real manual launch of two
Worlds on 8090/8100 with both `/api/instance` tokens matching; root-lab
`./arailctl start` with zero Worlds behaves byte-identically to today.

**WP5 — `status` / `stop` / `reset.sh` scoping.**
Files: `scripts/status.sh`, `scripts/reset.sh`, `arailctl`.
Scope: instance table (+`--json`, `--probe`), stale prune, `stop --world/--all`
with verified-PID kill, port-scoped legacy patterns, `check()`'s port-agnostic
match fixed.
**Gate:** `test_instance_stop_scope.py` **and** the pre-existing
`test_reset_stop_scope.py` + `test_reset_paths.py` all green; timed `status`
< 2 s with 3 stub records.

**WP6 — Portal endpoints + boot assertion.**
Files: `src/arail/portal/app.py`.
Scope: `GET /api/instance`, `GET /api/instances`, the absolute-path boot
assertion, `select` → 409 `instance_live`.
**Gate:** `test_instance_api.py` passes; `test_world_switcher.py` and
`test_world_mount.py` still green.

**WP7 — UI: roster, button semantics, notice, title.**
Files: `src/arail/portal/static/nav.js`, `templates/worlds.html`,
`templates/base.html`.
Scope: liveness dots + port in the nav roster; Mount/Launch/Open/Unmount matrix;
copy-the-command Launch; deprecation line; `· :<port>` in the title.
**Gate:** `test_world_switcher.py` + `test_world_identity_flip.py` green; manual
two-tab check that the two labs are visually unmistakable.

**WP8 — Docs, isolation proof, changelog.**
Files: `docs/concurrent-worlds.md` (new), `README.md`, `CHANGELOG.md`,
`CLAUDE.md` (conventions), `tests/test_instance_isolation.py`,
`tests/test_instance_secrets.py`.
Scope: the falsifiable-core test; operator docs; deprecation announcement.
**Gate:** full `pytest` green; the byte-identical isolation assertion passes.

### Ruling on the two latent fixes

- **Undefined `warn` at `start.sh:139-140` — IN SCOPE (WP4).** Verified: `start.sh`
  defines only `info()` (`:27`); `warn` is called at `:139-140` on the
  ttyd-present/tmux-absent path under `set -euo pipefail`, so a
  command-not-found aborts the start mid-launch. We are restructuring that exact
  file; shipping a rewrite that leaves a known `set -e` landmine in it is not
  defensible. Fix = define `warn()` beside `info()`. Two lines.
- **`lab.conf` without `set -a` — IN SCOPE (WP4/WP5).** See §6.2. One line in
  `start.sh:21`, one in `status.sh:16`, matching `arailctl:213-218`'s existing
  correct form.

Both are one-line-class fixes inside files the sprint already rewrites. Nothing
else latent gets adopted — in particular the stale `--apply-face` help text at
`arailctl:170` and the outdated `2026-06-14-world-switcher/ARCHITECTURE.md`
sweep claim are **out** (docs-only, no runtime effect, and touching the old
sprint artifact rewrites history we didn't live).

---

## 11. Non-goals (restated from VISION so the builder cannot drift)

- **No per-instance model processes.** Shared Ollama only; MLX not started per
  instance.
- **No unification with `blueprint create` / repo-root `instances/` / the
  `ARAIL_HOME` proposal** (`docs/REPOSITORY_LAYOUT.md:34-78`). Named revisit,
  not now. Do not "while I'm here" the blueprint renderer.
- **No launchd multi-instance.** Foreground `start` only; daemon stays
  single-instance and says so.
- **Nothing cross-instance.** No shared corpus, no cross-World search, no
  instance-to-instance messaging, no cross-instance auth.
- **Do not remove `POST /api/worlds/select`.** Deprecation is *announced* this
  sprint, executed next.
- **No eviction, quotas, or auto-shutdown.**
- **The ungated `GET /api/pkb/search` *within* an instance stays open.** Still
  not this sprint.
- **No Windows/WSL work** beyond not regressing it (guard `ps`/`lsof` usage
  behind the same capability checks `setup.sh` already uses).
- **No portal redesign.** WP7 is four surgical edits.
- **No change to `_sweep_other_worlds`.** It encodes the dataset invariant; the
  whole design accepts it rather than fighting it.

---

## 12. Tech debt assessment

**Added**

1. **A second instance mechanism beside `blueprint.sh`'s dead one.** `lab/instances/`
   (runtime, real) now coexists with repo-root `instances/` (config-only, unused,
   never instantiated). Two directories named "instances" meaning different
   things is a genuine future-confusion cost. **Named revisit:** file
   `sprints/BACKLOG.md` item *"Unify blueprint instances with runtime instances
   (+ decide `ARAIL_HOME`)"* as a WP8 deliverable. Mitigation now: a comment at
   the top of `blueprint.sh` and in `docs/concurrent-worlds.md` stating which is
   which.
2. **A fourth path-resolution site** — `scripts/lib/instances.sh` joins
   `config.py:84-89`, `reset.sh:44-90`, `start.sh:71-83`. Mitigated by making it
   the only *new* one and by having it consume the pack's explicit absolute
   values rather than re-deriving defaults, so there is nothing to drift.
3. **A liveness nonce (`token`) is a new concept** in a codebase that had none.
   Small, documented, non-credential.
4. **Root-lab nav tiles for terminal/notebook/IDE become cross-instance links.**
   Slightly odd UX until a future sprint decides whether instances get their own.

**Repaid**

1. **Four disagreeing liveness checks → one predicate.** The single largest
   correctness debt named in the BRIEF, retired.
2. **The launchd plist-existence trap** (`arailctl:195`) — the incident that
   started this sprint — is gone.
3. **`reset.sh`'s port-agnostic kill-everything** (`:104-106`) is scoped.
4. **`status.sh:32-39`'s print-a-port-but-match-anything `check()`** fixed
   (found during this design; not previously tracked).
5. **`lab.conf` `set -a` port drift** (`start.sh:21`) fixed.
6. **Undefined `warn` at `start.sh:139`** — a live `set -e` abort — fixed.
7. **Silent double-start** (uvicorn that can't bind and dies quietly) replaced by
   attach or a named error.
8. **`LANCE_PORT` is allocated per instance**, closing the 7414 collision the
   BRIEF flagged as latent in `blueprint.sh`.
9. **`world_routes.py` module-level state** (`_forge_state` et al., one
   forge/review/grow per process) is *fixed as a side effect* — separate
   processes mean separate state. VISION note 7 called this a benefit; it is.
10. **`start.sh` silently discarding argv** — fixed.

**Net: strongly negative (debt repaid).** Ten concrete defects retired, four of
them latent data-loss or silent-failure paths, against one genuine structural
duplication with a named revisit and a filed backlog item.

---

## Recommended implementation order

WP1 → WP2 → WP3 → WP4 → WP5 → WP6 → WP7 → WP8, gated as above.

WP1–WP2 are safe to ship even if the sprint stalls: they retire the four-checks
debt and the plist trap with no behaviour change to the root lab, which alone
satisfies VISION win condition #2. WP4 is the riskiest package; do not begin it
until WP3's gate proves a hand-written env pack round-trips through both `bash`
and `arail.config`.
