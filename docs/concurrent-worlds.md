# Concurrent Worlds — running more than one lab at once

> Design record: `sprints/2026-07-28-concurrent-worlds/` (`VISION.md`,
> `ARCHITECTURE.md`, `BUILD_LOG.md`). This doc is the operator-facing
> summary; the sprint folder is the full rationale, failure-mode table,
> and test strategy.

## What changed

Before this sprint, ARAIL ran exactly one portal against exactly one
`lab/` tree, and mounting a second World would **delete** the first one's
staged knowledge base out from under it (`_sweep_other_worlds`). "Two
Worlds at once" and "two data roots at once" were the same sentence.

Now they're the same sentence in the other direction: `./arailctl start
--world <slug>` launches a **second process**, rooted at its own data
tree, on its own ports, sharing only the machine's model weights and the
Ollama daemon. Two (or three) Worlds can run side by side, each with its
own knowledge base, chat memory, and secrets — genuinely isolated, not
filtered.

```
./arailctl start --world finance    # Finance World, its own process, its own data
./arailctl start --world ai         # AI & ML World, side by side with the above
./arailctl status                   # one row per instance — world, port, pid, data root
./arailctl stop --world finance     # stop just that one
./arailctl stop --all               # stop every instance, then the root lab
```

## On-disk layout

```
<repo>/
  lab/                          ← the ROOT lab (unchanged, port 8080)
    pkb/  data/  models/  worlds/
    instances/                  ← NEW, gitignored — one tree per running World
      registry.d/                 the liveness truth — one JSON file per instance
        finance.json
      finance/
        instance.env             ports, roots, identity — written once at first boot
        data/                    ARAIL_DATA_DIR (secrets.env lives HERE, per-instance)
        pkb/                     LAB_PKB (this instance's knowledge base)
        log/
      ai/
        instance.env  data/  pkb/  log/
```

**Shared, read-mostly:** `lab/models/` (weights — duplicating per World
was never sane) and `lab/worlds/` (the World *library*, read-write, safe
only because at most one live instance can serve a given World slug at a
time). **Shared, machine-level:** the Ollama daemon. **Per-instance,
never shared:** everything else — `pkb/`, `data/`, chat memory, LanceDB,
`secrets.env`.

## Ports

Each instance gets a 10-port block starting at `8090` (portal at
`+0`, memory service at `+4`); the block is allocated once on first boot
and pinned in `instance.env` forever after — the Finance World is always
on `:8090` once it's been started there. The allocator refuses at or
above `:9100` and never collides with the root lab (`:8080`) or
`blueprint.sh`'s instance range (`:9100+`, see the naming note below).

## Secrets are per-instance, on purpose

Each instance gets its own `secrets.env` (`0600`, in its own data dir),
created only when you first save a provider key via that instance's ⚙
Manage providers. **Nothing is auto-copied** from the root lab or from a
sibling instance — a shared or symlinked `secrets.env` would mean your
personal-finance instance could read your work instance's cloud API keys,
invisibly. If you want the same key in two instances, add it twice.

## The ceiling, and what happens at it

`LAB_MAX_INSTANCES` defaults to **3**. At the ceiling, `start` refuses and
prints the running roster plus the exact `stop` command to free a slot —
it never auto-stops a lab for you (stopping a lab is a data-loss-shaped
decision the operator makes, not software).

## What a World instance does NOT start

An instance runs only the portal and the memory service (+ Ollama if it's
not already reachable). It never starts its own terminal, notebook, or
IDE — those stay singletons on the root lab (`:7681`/`:8888`/`:8443`);
an instance's nav tiles for those link out to the root lab's copy rather
than 404ing.

## Daemon mode (launchd) is still single-instance

If you've run `./arailctl install-daemon`, that supervises the ROOT lab
only. `./arailctl start --world <slug>` refuses while the daemon is
active and tells you the two options: `./arailctl uninstall-daemon` first
(to run Worlds side by side), or keep using the daemon-served lab as-is.

## The in-place World switcher is being deprecated

`/worlds`' Mount button and the nav dropdown's per-World select still
work this release, but a World that's running as its own live instance
now shows **Open** instead of **Mount** — clicking it takes you to the
running instance rather than trying to remount it here (which the server
now refuses with `409 instance_live`, to stop an in-place mount from
sweeping a live instance's data out from under it). A World that isn't
live, but you already have something else mounted in the current lab,
shows **Launch** — a copy-to-clipboard `./arailctl start --world <slug>`
command, not a one-click spawn (turning a loopback endpoint into a
process-execution surface was a threat-model line this sprint declined to
cross). In-place Mount/Unmount is removed entirely in the next release;
use instances.

## `status` reference

```
./arailctl status            # human-readable table, no network calls
./arailctl status --json     # the same rows, for scripts
./arailctl status --probe    # adds a GET /api/instance check per row —
                              #   catches "this port is answering, but from
                              #   a DIFFERENT checkout" (a crash-looped
                              #   daemon serving stale code), at the cost
                              #   of a per-row network round trip
```

A record whose PID is gone renders `stale (pid N gone)` and is pruned
automatically (the data directory is never touched by pruning — only the
registry entry). A record whose data directory has vanished out from
under a still-running process renders `⚠ data root missing` and is left
alone — the operator decides what to do, `status` never guesses.

## `./arailctl reset` does NOT touch instance data — yet

**This is a real gap, not a cosmetic one — read this before you assume
`reset pkb`/`reset data`/`reset env` wipes a World instance.** Every
`./arailctl reset <mode>` (`pkb`, `data`, `env`, `full`, …) operates on the
ROOT lab's `lab/pkb/`, `lab/data/`, `.env`/`lab.conf` only. A running or
stopped World instance's own tree —
`lab/instances/<slug>/{pkb,data}/` (its knowledge base, chat memory,
LanceDB index, and `secrets.env`) — is **not reached by any reset mode**.
`reset env` in particular does not remove a World instance's
`secrets.env`, even though it removes the root lab's.

If you need to wipe a World instance's data today, do it directly:

```
./arailctl stop --world <slug>          # stop it first
rm -rf lab/instances/<slug>              # then remove its tree by hand
```

A `--world`-aware `reset` (or an explicit refusal naming the untouched
instance roots) is filed as backlog work — see `sprints/BACKLOG.md`:
*"`./arailctl reset` should be instance-aware."* Until that lands, this
gap is the one place "wipe the PKB = wipe memory" (CLAUDE.md's stated
contract) is not yet true for a World instance.

## Naming note: two things called "instances"

`lab/instances/` (this sprint, real, gitignored runtime state) and the
repo-root `instances/` directory `./arailctl blueprint create` scaffolds
(config-only, never itself instantiated into a running process) are
**unrelated**. This is a known, tracked point of future confusion — see
`sprints/BACKLOG.md`: *"Unify blueprint instances with runtime instances
(+ decide `ARAIL_HOME`)"*. Until that lands, if you see `instances/` at
the repo root, that's the blueprint config namespace; `lab/instances/` is
where running Worlds actually live.

## Non-goals (this sprint)

- No per-instance model processes — Ollama/MLX stay machine-shared.
- No launchd multi-instance — daemon mode stays single-instance.
- Nothing cross-instance: no shared corpus, no cross-World search, no
  instance-to-instance messaging or auth.
- No eviction, quotas, or auto-shutdown of instances.
