# Sprint backlog — named revisits

Items filed here are deliberate deferrals from a completed sprint: known,
scoped, not forgotten. Each entry names the sprint that found the gap and
the tech-debt tradeoff that justified deferring it. Pull from this list
when scoping the next sprint in the relevant area — don't let it become a
second, competing TODO list.

---

## Unify blueprint instances with runtime instances (+ decide `ARAIL_HOME`)

**Filed by:** `sprints/2026-07-28-concurrent-worlds/` (WP8), per
ARCHITECTURE.md §12 "Tech debt assessment — Added #1".

**The gap.** This sprint introduced `lab/instances/` as the real,
gitignored runtime home for concurrently-running World instances
(registry, per-instance data/pkb/env-pack — see
`docs/concurrent-worlds.md`). The repo also already has a repo-root
`instances/` directory that `./arailctl blueprint create` scaffolds
(`instances/<name>/{.env,lab.conf,log/,blueprint.toml}`) — config-only,
never itself instantiated into a running process, and nothing under
`src/arail/` reads it. Two directories both named "instances", meaning
different things, is a real future-confusion cost — flagged explicitly
in `docs/concurrent-worlds.md`'s naming note so it isn't silently
stumbled into.

**Why it wasn't done now.** VISION.md scoped this sprint against
unifying with `blueprint create`'s namespace or the
`docs/REPOSITORY_LAYOUT.md:34-78` `ARAIL_HOME` proposal explicitly — both
are separate, load-bearing design questions (does a "blueprint instance"
become a runtime instance? does `ARAIL_HOME` replace `REPO_ROOT`-relative
`lab/` entirely, and if so what happens to every existing path resolver
in `config.py`/`reset.sh`/`scripts/lib/instances.sh`?) that deserve their
own VISION pass, not a rider on this one.

**What a future sprint needs to decide:**
1. Does `blueprint create` start producing REAL runtime instances (i.e.
   converge on `lab/instances/`), or stay a pure scaffolding/config tool
   with a renamed directory to stop the collision?
2. Does `ARAIL_HOME` (an env var naming where "the lab" lives,
   independent of the checkout) get adopted, and if so, does
   `lab/instances/<slug>/` move under it too, or stay checkout-relative
   the way this sprint left it?
3. Whatever is decided, `scripts/lib/instances.sh`'s `inst_root_dir()` is
   the single choke point that would need to change — by design, nothing
   else re-derives that path.

**Mitigation until this is scheduled:** the naming distinction is
documented in `docs/concurrent-worlds.md`'s "Naming note" section and in
`scripts/blueprint.sh`'s own header comment.

---

## `./arailctl reset` should be instance-aware

**Filed by:** `sprints/2026-07-28-concurrent-worlds/REVIEW.md` finding
M6 (architect-review pass).

**The gap.** `reset pkb`, `reset data`, `reset env`, and `reset full` all
operate on the ROOT lab's `config.py`-resolved paths (`lab/pkb/`,
`lab/data/`, `.env`/`lab.conf`). `lab/instances/<slug>/{pkb,data}/` —
which holds a World instance's own knowledge base, chat memory, LanceDB
index, and `secrets.env` — is untouched by every one of them. CLAUDE.md
states the privacy contract flatly ("wipe the PKB = wipe memory");
that contract is not yet true for a World instance. Minimum mitigation
shipped this sprint: documented loudly in `docs/concurrent-worlds.md`
and `CHANGELOG.md`, with a manual `rm -rf lab/instances/<slug>` workaround
named. No code change to `reset.sh`'s destructive paths — REVIEW.md M6
ruled that in scope for documentation only, not a redesign, this pass.

**What a future sprint needs to decide:**
1. Does `reset pkb`/`reset data`/`reset env` grow a `--world <slug>` flag
   that targets one instance's tree instead of (or in addition to) the
   root lab's?
2. Should `reset full`/`reset pkb` at minimum REFUSE and list the
   untouched instance roots when any exist, rather than silently
   completing as if the whole lab were wiped?
3. Whatever is decided must not let a reset command delete instance data
   for a WORLD THAT IS CURRENTLY RUNNING out from under a live process —
   the same "verify before touching" discipline `stop_instance()` already
   applies to killing PIDs should extend to any future data-deleting path.

**Mitigation until this is scheduled:** documented in
`docs/concurrent-worlds.md`'s "`./arailctl reset` does NOT touch instance
data — yet" section, with the manual two-command workaround.
