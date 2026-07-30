# Vision: Concurrent Worlds as independent instances

**Date:** 2026-07-28
**Product:** arail
**Wedge size:** one sprint

---

## The six questions, answered

### 1. What does "independent" mean?

**Independent state, not independent silicon.** Three levels were on the table;
the answer is the middle one, and the other two are wrong for specific reasons.

| Level | What it isolates | Verdict |
|---|---|---|
| L1 | Port only; shared `lab/` tree | **Reject — actively destructive** |
| L2 | Port + `LAB_ROOT` (⇒ `pkb/`, `data/`, LanceDB, `world-mount.json`, `secrets.env`); **shared** model weights + inference daemon | **This one** |
| L3 | L2 + a dedicated model process per instance | **Reject — not this sprint** |

**Why L1 is not merely insufficient but harmful:** `_sweep_other_worlds`
(`src/arail/world_mount.py:1343-1372`, re-verified on disk) `shutil.rmtree`s
every other `sources/world-*/` directory on every mount. Two portals sharing one
PKB root would have instance B silently delete instance A's staged World. One
PKB root can hold exactly one World *by design*, not by accident — the docstring
says so: "A World IS the lab's dataset." Structural isolation isn't a nicety
here; it's the only shape the existing loader permits.

**Why L3 is wrong for this sprint — measured, not assumed.** On the operator's
36 GB box right now: portal uvicorn **254 MB** RSS, memory service **52 MB**,
`ollama serve` **60 MB** idle with model runners shared across clients. An
additional instance on the shared-backend design costs **~300 MB**. A dedicated
7B per instance costs 5–8 GB — which caps you at two instances on a 36 GB
machine and *one* on the 16 GB machine the `minimalist` tier explicitly targets.
Shared backend is the difference between concurrent Worlds being a feature and
being a luxury for people with workstations. ARAIL is a blueprint others run;
the friction profile has to hold on the small machine.

So, concretely, an instance owns: its `LAB_ROOT` (and therefore its `pkb/`,
`data/`, LanceDB index, wiki cache, `world-mount.json`, `secrets.env`,
`egress.jsonl`), its portal port, its memory-service port. An instance *shares*:
`ARAIL_MODELS_DIR` (weights are the expensive artifact — duplicating a 5 GB GGUF
per World is absurd) and the machine-level Ollama daemon, which `start.sh`
already treats as machine-level (it starts one only if 11434 is unreachable).

**The sharp edge, named on purpose.** Separate PKB roots mean the user's own
non-World material does not follow them across instances. This box has
`lab/pkb/sources/{papers,articles,datasets,images,bookmarks.md}` sitting
alongside `world-ai`. Under this model, those live in exactly one instance. That
is correct — it is the isolation the hard constraint demands — and it is also the
single most likely surprise. The UI must say it. We must **not** paper over it
with a shared-corpus mechanism in this sprint (see Scope boundary).

### 2. Does the dropdown mount/unmount still earn its place?

**No. Replace it. Plan the deprecation.** No hedge, and the reason isn't taste.

The `/worlds` Mount button reads as "switch view." What it actually does is
`rmtree` every other World's staged directory and drop its LanceDB rows.
Switching from AI (331 curated terms) to Finance destroys the AI World's staged
layer; switching back re-indexes from scratch. When the operator says jumping
between Worlds should be "cleaner than selecting from a dropdown," they are
describing a **correctness** problem they have felt, not an ergonomic
preference. There is no design in which one-PKB-root-many-Worlds has a
non-destructive dropdown, because the sweep is the deliberate expression of the
dataset invariant, not a bug to fix.

Keep the invariant. One mounted World per data root is *right*. The consequence
is simply that two live Worlds require two data roots, which requires two
instances. The dropdown's entire job — "put me in a different World" — is
subsumed.

**The one surviving use case, stated precisely so it can't expand:** the *first*
bind, and unbind-to-default. A fresh lab has no World. The `/worlds` surface must
still let a user go from "AI Lab (default)" into their first World inside the
instance they're already in, and back out. That operation is non-destructive by
construction — there is nothing else in that root to sweep. It is the degenerate
case of launch, not a second mechanism.

So the deprecation is precise and it is not "have both":

- `POST /api/worlds/select` survives **only** when the target root has no other
  World bound. Picking a World owned by a different instance stops offering
  "Mount" and offers **Launch / Open** instead.
- The nav dropdown becomes a **World roster with liveness** — which Worlds
  exist, which are running, on which port. A viewer, not a mutator.
- One release of overlap, announced. Then the roster is all that's left.

One mechanism (an instance owns a World). One surface (`/worlds`). The mount
button survives as a special case of launch, not as an alternative to it.

### 3. What is the start UX?

- **Bare `./arailctl start`, more than one World configured → interactive
  picker.** Same set `/worlds` lists, annotated with liveness (running on :8090 /
  not running). Deliberate, legible, one keystroke.
- **Bare `./arailctl start`, exactly one World configured → just start it.** No
  picker. The picker must not tax the single-World user, who is most of the fork
  audience.
- **`--world <slug>`** for scripting and muscle memory. Non-interactive, same
  semantics, non-zero exit if the slug doesn't exist. (Today `scripts/start.sh`
  parses *no* arguments at all — verified: no `$1`, no `getopts`, no `shift`.)
- **Requested World already running → attach, never error, never respawn.**
  Print the URL, offer to open it, exit 0. Today there is no port pre-check and
  no lock file anywhere in `start.sh` (verified: no `lsof`, no lock, no
  already-running detection), so a double start spawns a uvicorn that fails to
  bind and dies silently. That failure mode dies this sprint. Erroring on "it's
  already up" would be the same species of hostility as the plist trap that
  motivated this sprint.

### 4. What does "take time loading… for the user" imply?

It implies the launch should be **legible**, not that it should be slow. Nobody
wants a progress bar for its own sake; the operator wants to know it worked.

Today `start.sh` backgrounds up to seven services and hands back the prompt with
no readiness signal — you find out it worked by loading a page and seeing if it
answers. Instead: a staged, one-line-per-step launch that reports each outcome —
resolve data root → bind ports → portal up (**readiness-checked, not `sleep`**) →
model backend reachable → World bound → index ready → URL. The prompt does not
come back claiming success until the portal actually answers.

**The real content of this question is the corollary.** The motivating incident
cost a `ps` / `launchctl list` / `arail.__file__` archaeology session because
four files disagree about what "running" means — `arailctl:195` (plist file
exists), `start.sh:35` (`launchctl list`), `status.sh:42` (plist + uname),
`install-daemon.sh:76-79` (pgrep and *not* launchctl). With N instances that
archaeology multiplies by N and becomes the *normal* path for standing up a
second World. So: **`./arailctl status` must answer "which instances are up,
serving which World, from which checkout, on which port, against which data
root" in one command.** Instance liveness becomes a recorded, queryable fact —
one source of truth, checked once, not four heuristics that disagree.

### 5. Resource ceiling

**Three concurrent instances. Soft-warn at 4. No automatic eviction.**

The number comes from the measurement above: ~300 MB per additional instance on
the shared-backend design, so three instances ≈ 0.9 GB of ARAIL plus one shared
model runner. Comfortable on the 16 GB floor; trivial on 36 GB.

**RAM is not the binding constraint — attention is.** Concurrent chat across
three Worlds against one Ollama daemon serializes; the second and third response
will feel slow. You cannot meaningfully *work* in more than about two Worlds at
once. Three is one more than anyone will actually use, which is the correct
ceiling for a tool: high enough to never be the thing in your way, low enough to
catch a runaway script.

**No eviction, deliberately.** Auto-stopping a lab instance is a data-loss-shaped
action, and the operator would be right never to trust it. Above the limit:
refuse to launch, print what's running and how to stop it. Refusal that names the
fix beats cleverness. `LAB_MAX_INSTANCES` as an env override for the person on a
128 GB workstation — blueprint, not product.

### 6. Naming and discovery

Two levels. Both are required; neither substitutes for the other.

- **Terminal:** `./arailctl status` lists every instance as a row — World slug,
  display name, port, PID, checkout path, data root, up/down. This is the direct
  fix for the motivating incident and it is not optional.
- **Browser:** the instance's identity must be unmistakable *before you read
  anything*. Use the seam that already exists — `identity.effective_identity()`
  resolves per request from the mount sidecar, and the World's `face.json`
  carries a theme the world-identity-flip sprint already wired through ~25
  templates. So the Finance instance is slate-violet and reads "Finance World"
  in the nav; the AI instance is blue-cyan and reads "AI & ML World." Port in the
  page title so browser tabs are distinguishable. **Do not invent a new naming
  mechanism** — `LAB_NAME` keyed to the World is exactly the existing rebrand
  seam.

The thing that must never happen: two identical-looking tabs on 8080 and 8090
where the operator acts on the wrong lab. With personal finance data in one of
them, that's a harm, not a papercut.

---

## User

**The operator.** Charlie, running ARAIL from a git checkout on a 36 GB Mac. He
has just built a personal debt/finance World (`sprints/2026-07-26-world-of-debt-finance/`)
and already runs an AI/ML World with 331 curated terms. He wants to do a
Friday-afternoon finance review *and* keep his research lab intact. Today,
mounting Finance `rmtree`s the AI World's staged layer, and he re-indexes 331
terms to get back. Worse: his finance data lands in the same `lab/pkb/` tree
that `GET /api/pkb/search` walks with no world scoping and no approval gate
(`pkb.py:391-411`).

**The fork audience.** Someone who cloned ARAIL because BLUEPRINTS.md promised
"here is a lab you can run," on a 16 GB laptop, who wants a *work* lab and a
*personal* lab that cannot see each other — and who expects that separation to be
true because of directories, not because of a filter that could have a bug.

## Problem

ARAIL can hold only one World at a time and switching destroys the other one's
state, so anyone with two subjects — especially when one of them is personal —
has to choose between them instead of running both.

## Win condition

Pre-committed thresholds:

1. **Isolation is provable, not asserted.** Two Worlds up simultaneously on
   different ports with different data roots; the AI World's
   `sources/world-ai/` and its LanceDB rows are byte-identical before and after
   the Finance instance is launched, used, and stopped. This is the falsifiable
   core.
2. **One command replaces the archaeology.** `./arailctl status` answers what's
   running / which World / which port / which checkout / which data root in
   under 2 seconds. The incident that motivated this sprint becomes one line of
   output.
3. **No silent failures.** Launching a second instance is under 60 s of legible
   staged progress on a warm machine. A port collision or a double start prints
   a named error — never a background uvicorn that dies quietly.
4. **Witnessed.** The operator runs both Worlds for a full week and does not once
   reach for `ps` to work out what is up.

## Wedge

One sprint. The smallest thing that proves the model:

> `./arailctl start --world <slug>` launches an instance rooted at a per-World
> `LAB_ROOT`, on a deterministic port, recorded in a registry, with staged
> readiness-checked progress — and `./arailctl status` lists every live
> instance with its World, port, checkout, and data root.

Two Worlds, two ports, two data roots, one shared Ollama. The interactive picker
is in the wedge only because bare `start` must not become a new trap. Everything
else — nav roster liveness, executing the mount deprecation, eviction, blueprint
unification — is later.

Runnable on the developer's own machine with no cloud account, by construction.

## Disconfirming evidence

Pre-committed, so we can't rationalize afterward:

1. **The need was switching, not concurrency.** If after two weeks the registry
   shows the operator has never had two instances up simultaneously for more
   than a single session, then what he wanted was non-destructive *switching*
   inside one root. Shelve the multi-instance work; keep `status`.
2. **The shared backend doesn't hold.** If a second instance on a 16 GB machine
   makes chat in the first visibly worse (>2× first-token latency under normal
   single-user load), the shared-backend premise is wrong, the honest ceiling is
   1, and concurrency becomes a maximus-only affordance rather than a blueprint
   capability.
3. **We drew the isolation boundary in the wrong place.** If per-instance roots
   make the operator's own corpus feel *lost* rather than *isolated* — concretely,
   if he starts symlinking or copying `sources/papers` between roots within the
   first month — then the unit of isolation should have been the World's staged
   layer, not the whole PKB.
4. **"Deliberate" collapses into "slow."** If launching an instance takes more
   than 3 minutes on a warm machine, the framing fails and the dropdown wins on
   ergonomics regardless of its correctness problems.

## Displacement

**Inside ARAIL,** two ROADMAP "Now" tracks lose the sprint: **Chat Studio M2**
(loader strip + blocking send) and **Build/Model-Mgmt Phase 1**. Chat Studio is
the honest casualty — it is the more visible user-facing win and it slips a
sprint. Say that out loud rather than pretending this is free.

**Across QuKaiZen,** aerollm and aerollm-distill get nothing this cycle. Since
aeroLLM is arail's `maximus` deep-mode backend and this sprint touches nothing
in the inference path, that is a clean deferral rather than a blocking one.

**A positive displacement worth naming:** this largely retires the "separate,
cross-World vision pass" the debt-finance sprint deferred. Structural isolation
answers the ungated-`pkb.search` exposure *between* Worlds without a scoping
filter. It does **not** answer sensitivity *within* one instance — `GET
/api/pkb/search` stays ungated inside a root, and that remains open.

**And one thing we are choosing not to displace yet.** The `instances/`
blueprint scaffolding is config-only, unused, and aimed at this exact problem:
`instances/` has never existed on this machine, `git log -- instances/` is empty,
and nothing under `src/arail/` reads it. Building a second multi-instance
mechanism next to a dead first one would normally be the wrong call — but
unifying them (plus the unbuilt `ARAIL_HOME` proposal in
`docs/REPOSITORY_LAYOUT.md:34-78`) is more than one sprint holds. So: build the
wedge on the runtime side, and put reconciliation explicitly out of scope with a
named revisit. Do not let it drift in.

## Notes for the architect

Observed while grounding this vision. **Not designs — hazards to route around.**

1. **Four disagreeing liveness checks** — `arailctl:195` (plist exists),
   `start.sh:35` (launchctl), `status.sh:42` (plist+uname),
   `install-daemon.sh:76-79` (pgrep). With N instances this multiplies. One
   source of truth is needed and it is the heart of the sprint.
2. **launchd is machine-global and conflicts head-on** — fixed labels
   `io.arail.{portal,memory,mlx}`, one set per machine, host+port baked into the
   plist argv. Daemon mode and multi-instance cannot both be naive; something
   must give, explicitly.
3. **`reset.sh stop` would kill every instance on the box** — its uvicorn
   `pgrep -f` patterns are port-agnostic, and `reset.sh` never sources
   `lab.conf`. A data-adjacent footgun the moment instance #2 exists.
4. **Path resolution is implemented three times** — `config.py:84-89` (Python),
   `reset.sh:44-90` (bash, pinned by `tests/test_reset_paths.py`),
   `start.sh:71-83` (partial third copy) — and `egress.py:92` bypasses config to
   re-read `os.getenv("ARAIL_DATA_DIR")`. Per-instance roots turn divergence from
   untidiness into a correctness bug.
5. **`config.py` resolves bare relative defaults CWD-relative**, and
   `ARAIL_ENV_FILE` (`config.py:26-30`) exists precisely because worktrees
   otherwise find the parent checkout's `.env`. Instances make this sharper.
6. **`start.sh:21` sources `lab.conf` without `set -a`** — uvicorn binds the argv
   port while the Python process reads a stale `PORTAL_PORT` from `.env`
   (`opencode.py:588,1036`, `app.py:9498,9727`, `_builtin_sre.py:271`). Cosmetic
   with one instance; cross-instance misrouting with N.
7. **`world_routes.py` module-level state** (`_forge_state` et al.) means one
   forge/review/grow per process. Per-instance processes *fix* this — note it as
   a benefit, not a hazard.
8. **Instance `lab.conf` from `blueprint.sh` omits `LANCE_PORT`** — every
   instance would collide on 7414. Also omits `IDE_PASSWORD`.
9. **The loader is already parameterized** — `mount`/`unmount`/`swap` accept
   `pkb_root=` / `data_dir=` / `worlds_dir=`; no portal call site passes them.
   The seam exists.
10. **Latent break:** `start.sh:139-140` calls an undefined `warn` (ttyd present,
    tmux absent) under `set -euo pipefail`.
11. **Secrets need a decision, not a default.** `secrets.env` per data root means
    N `0600` copies of the same provider key. That is a real call about sprawl vs
    isolation, and it is not obvious either way.

## Recommended next step

**Proceed to `/architect` with this as the spec.**

The isolation requirement is not a preference — `_sweep_other_worlds` makes
concurrent Worlds and concurrent data roots the *same thing*, so the only
question was whether to pay for it, and the measured cost (~300 MB per instance
on a shared backend) says yes.

### Scope boundary — explicitly OUT of this sprint

- **Per-instance model processes.** Shared Ollama/MLX only.
- **Unifying with `blueprint create` / `instances/` / the `ARAIL_HOME`
  proposal.** Revisit named, not now.
- **launchd / daemon-mode multi-instance.** Foreground `start` only. Daemon mode
  stays single-instance and must *say so* out loud.
- **Anything cross-instance.** No shared corpus, no cross-World search, no
  instance-to-instance messaging.
- **Removing `POST /api/worlds/select`.** Deprecation announced this sprint,
  executed the next.
- **Eviction, quotas, auto-shutdown.**
- **The ungated `GET /api/pkb/search` *within* an instance.** Still open; still
  not this sprint.
- **Windows/WSL parity** beyond not regressing it.
