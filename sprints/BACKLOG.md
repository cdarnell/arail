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

---

## Canonicalize the mount record's `bundle_dir` on adopted Worlds

**Filed by:** `sprints/2026-07-28-worlds-select-removal/REVIEW.md` ASK-1.

**The gap.** `mount()` records the SOURCE path a World was mounted/imported
from (`world_mount.py`), then `_adopt_into_catalog()` copies it into
`WORLDS_DIR/<slug>`. For an externally-imported World those are two
different strings for the same World, so the `in_place_switch_removed`
guard's `cur.bundle_dir != str(bundle_dir)` comparison alone would wrongly
refuse that World re-binding to itself via its catalog slug. This sprint
shipped the narrow fix: the guard also allows when `cur.world ==
target_slug`. That is correct but is a second, string-slug-based notion of
"same World" living alongside the path-based one — a future path/slug
divergence (two dirs sharing a slug, ASK-1's own F7 fixture pattern) could
reintroduce an asymmetry.

**The real fix (not done this sprint):** have `mount()` write the ADOPTED
catalog dir into the mount record when `_adopt_into_catalog()` succeeds, so
one World has exactly one canonical `bundle_dir` regardless of which door
(select/import/import-zip) it arrived through. Touches mount-record
semantics — deserves its own sprint, not a rider fix.

---

## Extract `_refuse_in_place_switch()` — third guard-body copy

**Filed by:** `sprints/2026-07-28-worlds-select-removal/REVIEW.md` INFO.

**The gap.** The `in_place_switch_removed` refusal body is now duplicated
three times (`api_worlds_select`, `api_worlds_import`,
`api_worlds_import_zip`) — ARCHITECTURE.md accepted two copies and named
three as the threshold for extracting a shared helper
(`_refuse_in_place_switch(cur, target_slug) -> Optional[JSONResponse]`).
Not done this pass to keep the review-fix commits minimal and reviewable;
worth doing the next time any of these three endpoints is touched.

---

## De-duplicate `showLaunchCommand()` (welcome.html / worlds.js)

**Filed by:** `sprints/2026-07-28-worlds-select-removal/BUILD_LOG.md` /
`REVIEW.md` INFO.

**The gap.** `welcome.html` and `src/arail/portal/static/js/worlds.js` each
carry their own copy of `showLaunchCommand(slug)` (copy the `./arailctl
start --world <slug>` command to the clipboard + alert). The two templates
don't currently share a JS module, so extracting a common helper means
introducing that sharing mechanism first — out of scope for a UI-removal
sprint. Worth doing if a third copy appears (`nav.js`'s `reveal()` posture
is close but not identical).

---

## `status.sh`'s deliberate `set -e` omission

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` m4 / §8 unanticipated
debt #2 / re-review §R6.1 item 1 (required action #9).

**The gap.** `scripts/status.sh` runs under `set -uo pipefail` — no `-e` —
unlike every other `scripts/*.sh` in this repo, which all run under
`set -euo pipefail`. This is deliberate: the probe helpers this file calls
(`scripts/lib/services.sh`'s `svc_listening`/`svc_http_status`/etc., and
this file's own instance-record readers) use a nonzero return as DATA
("down"/"unreadable"/"unknown" are legitimate outcomes on the way to
building the status document), not a failure that should abort the
collector. Running the whole file under `-e` would turn every one of those
expected-degraded states into an immediate, undiagnosed exit — the same
class of bug F20 already names for `while read` loops. Documented as a
20-line LANDMINE note in the file header (`status.sh:12`) during the
review-fix pass, but the file's error-handling posture itself was not
changed.

**Why it wasn't done now.** The narrower alternative — scope `set +e`/
`set -e` tightly around just the probe-calling block, rather than omitting
`-e` for the whole 782-line file — was considered during the review-fix
pass and rejected as out of scope: no numbered test currently pins where
that boundary should sit, and retrofitting it means auditing every one of
this file's ~15 probe call sites for what CURRENTLY relies on `-e` being
off globally (a materially larger, riskier change than a documentation
fix).

**What a future sprint needs to decide:**
1. Is the `set +e`/`set -e` scoped-block form worth building, or does the
   file-level `set -uo pipefail` posture stay permanent (matching the
   comment's own "next maintainer" framing)?
2. If scoped, what is the exact boundary — one block per probe, or one
   block wrapping the whole collector phase?
3. A numbered test (`status --json` under a probe helper forced to return
   an unexpected nonzero) should pin whichever boundary is chosen, so this
   doesn't regress silently a second time.

**Mitigation until this is scheduled:** the landmine comment at
`status.sh:12` explains the omission and the road not taken, so the next
maintainer does not have to rediscover the reasoning from scratch.

---

## `install`'s preflight silently mutates the registry

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` §8 unanticipated debt
#4 / re-review §R6.1 item 2 (required action #9).

**The gap.** `install.sh`'s live-lab preflight (F21/F22) shells out to
`scripts/status.sh --json=full --no-probe` to check whether anything is
running before allowing a mutating phase (`--rebuild-venv`, `deps`). As a
side effect of that read, `status.sh`'s collector calls
`inst_list_slugs`/`inst_prune_all`, which deletes any registry record whose
liveness predicate fails — so a preflight an operator would reasonably
expect to be read-only actually mutates `lab/instances/registry.d/` on
every `install` invocation.

**Why it wasn't done now.** The mutation is correct-ish on its own terms
(`inst_prune`'s documented contract is "remove a record iff it is
provably stale" — never live data, never a data directory, ARCHITECTURE.md
§2.5) and reusing WP5's status collector rather than growing a fourth
liveness check was itself an explicit architecture instruction
(§17: "use WP5's status collector for the liveness preflight — do NOT
grow a new liveness check"). Making the preflight genuinely read-only would
mean either a `status.sh --no-prune` flag (a new flag on a protected file,
with its own test surface) or duplicating the liveness read without the
prune — both larger than a review-fix-pass rider.

**What a future sprint needs to decide:**
1. Is a silent prune during an unrelated verb's preflight actually
   surprising enough to fix, or is "stale records get cleaned up
   opportunistically" an acceptable, even desirable, side effect worth
   documenting explicitly instead (in `docs/cli.md`'s `install` section)?
2. If it should be read-only, does `status.sh` gain a `--no-prune` flag
   that `install`'s preflight passes, or does `install.sh` grow its own
   narrower liveness check (re-opening the "one liveness check" mandate
   this sprint's architecture explicitly closed)?

**Mitigation until this is scheduled:** the mutation is confined to
pruning genuinely-dead records (never live data), and is the same prune
`status`'s own bare invocation already performs on every call — `install`
does not introduce a NEW kind of mutation, just an additional trigger for
an existing, narrowly-scoped one.

---

## `services.sh`/`setup.sh`: hard dependency or a real degrade

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` n6 / re-review §R6.1
item 3 (required action #9, accepted "on condition it is filed").

**The gap.** `scripts/start.sh`'s root path calls
`inst_load_port_helpers` (which extracts `_port_in_use` from
`scripts/setup.sh` via `awk`) under `set -e` with no guard — if
`scripts/setup.sh` is absent (a copied-out fixture, or a corrupted
checkout), the root path aborts with no message rather than degrading.
Separately, `scripts/lib/services.sh`'s `[[ -f ]]`-guarded `source` (used
by `start.sh`, `status.sh`, and `arailctl`) does NOT crash when
`services.sh` is missing (F4 holds — confirmed by this sprint's own driver
extension, `tests/shell_source_safety_driver.sh` cases #7/#8), but the
degrade it produces is not USEFUL: every root start still fails, just with
a worse message ("✗ Portal did not come up" instead of a named "readiness
probes unavailable" warning).

**Why it wasn't done now.** This is a genuine hard-dependency-vs-honest-
degrade DESIGN decision — not a fix-if-trivial line change. Two real
options exist (make the dependency hard and say so plainly in an error
message, or make the degrade real by having the root path continue with
readiness detection disabled and a loud warning), and picking between them
changes user-facing failure behavior for a case (a `setup.sh`/`services.sh`
missing from an otherwise-checked-out repo) that has no existing numbered
test either way.

**What a future sprint needs to decide:**
1. Is `scripts/setup.sh` / `scripts/lib/services.sh` presence a hard
   precondition for `start`/`status` to run at all (in which case both
   should fail loudly and immediately, naming the missing file), or should
   the root path degrade to "readiness detection unavailable" and continue?
2. Whichever is chosen needs a numbered test (a fresh-checkout-with-a-file-
   deleted scenario) so the choice is pinned, not just documented in
   prose.

**Mitigation until this is scheduled:** none beyond the current (silent
but non-corrupting) failure modes — a missing `setup.sh`/`services.sh` is
an unusual-enough checkout state that it has not been reported in
practice.

---

## `install --json`'s early-exit paths emit no JSON

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` n4 / re-review §R6.1
item 4 (required action #9).

**The gap.** `status --json` follows F18's doctrine: the document is
ALWAYS emitted, even on a collector failure (an unreadable
`registry.d`, a corrupt record) — errors land in `warnings[]` /
`verdict.code`, never as a bare non-JSON error line. `install --json` does
not follow the same doctrine: its three early exits (unprovisioned lab,
lab live without `--allow-running`, a bad flag) print a plain human error
line to stderr and exit, with no JSON on stdout at all. A caller piping
`install --json | jq` through one of those three paths gets a `jq` parse
error instead of a machine-readable verdict.

**Why it wasn't done now.** This is a documented scope trim, not an
oversight: §5.1 names `arail.install/v1`'s schema (`{"schema", "check",
"verdict": {"code", "state"}}`) but no numbered test (T24-T28, F5-F7,
F21/F22, F28, F32) requires early-exit JSON, and `install`'s own stderr
narration already carries the same information for an operator running
`--json` interactively (§14.1: "no human decoration on stdout" moves it to
stderr, it doesn't delete it). Adding early-exit JSON emission is a small
but real behavior change across three distinct refusal paths, each needing
its own test.

**What a future sprint needs to decide:**
1. Should all three early exits gain a minimal `arail.install/v1` JSON
   emission (`verdict.code` + a `reason` field), matching `status --json`'s
   F18 doctrine?
2. If so, does the schema need a version bump, or is a new optional
   `reason` field additive enough to stay `v1`?

**Mitigation until this is scheduled:** the three early-exit paths are
narrow and well-named on stderr; a caller that checks the exit code before
parsing stdout (the documented, correct usage) is unaffected.

---

## `ARAIL_TIER0_BOOT_WARM`'s export blast radius

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` n7 (accepted as-is).

**The gap.** `scripts/start.sh:801` and `:1050`'s `export
ARAIL_TIER0_BOOT_WARM=1` (set when `--warm` is passed to `start`/`restart`)
leaks into every subsequently spawned child process on that path — the
memory service, ttyd, jupyter, code-server — not just the portal process
that actually reads it.

**Why it wasn't done now.** Harmless today: nothing besides the portal's
own `_warm_primary_router()` reads `ARAIL_TIER0_BOOT_WARM`, so the leak has
no observable effect. Fixing it means replacing the blanket `export` with
an inline per-invocation env prefix on the ONE `uvicorn` spawn line that
needs it — a small change in isolation, but one that touches a spawn call
site shared with several other env vars, for a purely cosmetic tightening
with no bug behind it.

**What a future sprint needs to decide:** worth doing opportunistically the
next time `start.sh`'s spawn block is touched for an unrelated reason; not
worth a dedicated pass on its own.

**Mitigation until this is scheduled:** the `export` choice and its blast
radius are explained in an inline comment at both call sites.

---

## B2's residual: `stop --root` during a same-port World's boot window

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` re-review §R6.3
(required action #9).

**The gap.** The review-fix pass's B2 fix
(`scripts/reset.sh`'s `stop_services()`) excludes a live World instance's
portal/memory pids from the QA-17 fallback match by consulting
`lab/instances/registry.d/`'s WRITTEN records
(`inst_list_slugs`/`inst_alive`/`inst_read_record`). But `_instance_start`
spawns the portal at stage `[6/8]` (`start.sh:807`) and does not WRITE the
registry record until stage `[8/8]` (`start.sh:948`) — write-after-ready is
a protected invariant from the Concurrent-Worlds sprint and must not
change. Consequence: a `stop --root`/`restart --root` fired while another
World is mid-boot, on the SAME port as the root lab's configured
`PORTAL_PORT`, can still take it via the fallback — the exclusion set
simply doesn't know about an instance that hasn't finished registering
yet.

**Why it wasn't done now.** Much narrower than the shipped B2 bug (which
fired unconditionally on any same-port collision, live or not): this
residual needs a same-port collision AND a concurrent boot, a much smaller
window. The cheap close the re-reviewer named — `stop_services` refusing
the fallback while any FRESH `.claim` file exists
(`lab/instances/registry.d/<slug>.claim`, written with the launcher pid at
`start.sh:658`, i.e. before the spawn, so it IS available during the
`[6/8]`→`[8/8]` window) — is real, but touches code adjacent to the
protected write-ordering invariant and was explicitly filed as a follow-up
by the reviewer, not implemented in the same review-fix pass that found it
(deliberately — it deserves its own review cycle, not a rider commit).

**What a future sprint needs to decide:**
1. Confirm the `.claim`-file read in `stop_services` cannot itself
   introduce a new hazard (e.g. a stale/orphaned claim file from a crashed
   boot blocking a legitimate `stop --root` indefinitely — needs a TTL or
   a liveness check on the claim's own launcher pid).
2. Add a numbered test that reproduces this exact residual (a live claim,
   no registry record yet, same-port collision) failing before the fix and
   passing after.

**Mitigation until this is scheduled:** the window is narrow (a same-port
collision during the ~1-2 second `[6/8]`→`[8/8]` boot span) and requires an
operator to have already chosen to run a World on the root lab's own
configured port — an unusual, non-default configuration.

**Addendum (QA pass, `sprints/2026-07-29-elite-cli/TEST_REPORT.md` §8):**
the residual has a SECOND, non-timing route to the same outcome. The
exclusion set `stop_services` builds is populated only from **readable**
live registry records (`inst_read_record` succeeding). A **corrupt**
registry record — the same "unreadable/truncated JSON" shape `status
--json` already has to tolerate elsewhere in this sprint (QA-4) — makes
`inst_read_record` fail for that slug, so the record's pids are silently
absent from the exclusion set even though the instance itself may be
genuinely alive and matched by the fallback pattern. No concurrent boot or
same-port timing is required to hit this route — a corrupt-on-disk record
is sufficient by itself. Same narrow blast radius as the boot-window
residual above (still requires the fallback's other preconditions: a
same-port collision and no `--app-dir` in the process's argv), and the
same `.claim`-file-based remedy proposed above would not close this second
route on its own — a corrupt *record* is a different failure shape than a
*missing* one, and the fix would need to treat "registry entry exists but
is unreadable" as itself grounds to withhold the fallback (fail closed)
rather than silently proceeding as if no instance were there at all. Filed
here rather than as a new entry since it shares the same root component,
the same fallback mechanism, and the same recommended review-cycle
treatment as the timing residual above.

---

## `test_reset_stop_scope.py`'s pre-existing failure leaves B2 unit-untested

**Filed by:** `sprints/2026-07-29-elite-cli/REVIEW.md` re-review §R6.4
(required action #9).

**The gap.** `tests/test_reset_stop_scope.py::test_foreign_uvicorn_survives`
and `::test_port_scoped_helpers` fail with
`_ollama_pid_if_we_started_it: command not found` — the test's own awk-based
extraction of `stop_services()`'s body does not pull in
`_ollama_pid_if_we_started_it` (a separately-defined helper `stop_services`
calls), so the extracted, re-sourced copy the test drives aborts before
reaching any assertion. This predates the `2026-07-29-elite-cli` sprint
entirely (reproduced identically at `42e87f4`, before the sprint's own
first commit) and is unrelated to the sprint's `reset.sh` changes — the
review-fix pass's new `_stop_services_pid_is_instance_owned` exclusion
clause is confirmed to sit correctly OUTSIDE the awk-extracted range (its
closing brace is indented, never at column 0), so it isn't the cause.

Consequence: this file is the natural home for a *unit*-level test of
`stop_services`'s scoping (real fixtures, no real processes, fast), but
because it's broken, `stop_services`'s new instance-exclusion logic (B2)
is exercised ONLY at the driver level
(`tests/cli/restart_driver.sh`'s two sibling-survival scenarios, which spawn
real processes and are confirmed to fail without the fix). That coverage is
real, just not doubled at the faster, more isolated unit level a maintainer
would normally reach for first when touching this function again.

**Why it wasn't done now.** Fixing the awk extraction is a small, focused
change, but it is to a PRE-EXISTING test bug entirely unrelated to the
BLOCK/minor findings this review-fix pass was scoped to address — fixing
it here would be scope drift into a different, older gap.

**What a future sprint needs to decide:** extend the awk range (or switch
to a smarter extraction, e.g. pulling every function `stop_services`
transitively calls) so `_ollama_pid_if_we_started_it` is included, then
add a unit-level scenario for B2's exclusion clause (a fabricated live
instance record, no real process, asserting the fallback pattern match is
suppressed) alongside the existing `test_foreign_uvicorn_survives`/
`test_port_scoped_helpers` cases.

**Mitigation until this is scheduled:** the driver-level B2 coverage
(`tests/cli/restart_driver.sh`) is real and independently confirmed to
fail without the fix — this gap is about test-pyramid shape (missing the
faster, more isolated layer), not about missing coverage entirely.

---

## agenda_watch.py — 4 non-blocking follow-ups from round-11 review

**Filed by:** `sprints/2026-07-26-world-of-debt-finance/` (deals/education/
tracking capability upgrade), REVIEW.md addendum 10, round 11, verdict
WEAK_PASS. None of these are reachable from the World as shipped (the
shipped `scout-patterns.json` has tightly numeric patterns), which is why
round 11 didn't block on them — but a future World author with a looser
pattern could reach all four.

**ASK-19 — candidate-value markdown injection risk in the finding
document.** `src/arail/research/agenda_watch.py` (near the "Candidate
values" section writer) wraps each matched value in a single backtick with
no length cap, while the excerpt directly above it in the same finding is
deliberately fenced as untrusted content. A candidate value containing a
backtick or a newline could break out of that inline-code wrapping and
inject markdown into a document a human reviews and approves. Needs an
operator-authored loose pattern (not any of the shipped ones) to reach.
**Fix shape:** fence candidate values the same way the excerpt above them
already is, plus a length cap consistent with `_MAX_PATTERN_MATCHES`'s
spirit.

**ASK-20 — candidate-extraction result payload has no size cap.**
Round 10 (BLOCK-12's neighborhood) fixed the *misdiagnosis* of a large
result as a killed backtracking pattern (queue-then-join reordering), but
never capped how large a result can actually be. A pattern with a huge
`max_matches` × long per-match text could still produce an very large
payload — no longer misreported as a hang, but still a large read/write
and a large "Candidate values" section in the finding document.
**Fix shape:** cap total serialized candidate bytes in
`_extract_candidates`, truncate with a "(truncated)" marker, same spirit
as the existing per-pattern `max_matches` cap.

**ASK-21 — a slow-but-successful child can be misreported as
backtracking.** In `_extract_candidates_bounded`, if the child is slow to
exit after writing its result (but not stuck matching), the current logic
can discard a valid result and log a "possible catastrophic-backtracking
pattern" warning that doesn't match what actually happened.
**Fix shape:** once `queue.get()` has returned a real result, treat exit
lag as a benign reap-timing detail, not a backtracking signal — only log
the backtracking warning on the path where `queue.get()` itself timed out.

**INFO-23 — BLOCK-12's empty-extraction guard is warn-only, not a
fallback (deliberate, not a gap).** When visible-text extraction empties a
genuinely non-empty fetch, the fix added a loud `_log.warning` rather than
falling back to hashing `raw_text` directly. This is a considered
divergence, not an oversight: falling back to raw bytes would reintroduce
BLOCK-11/BLOCK-9's original problem (a rotating CSRF token or analytics ID
buried in markup counting as "the page changed" on every tick) for the one
World whose extractor happens to have a residual gap, silently
reintroducing noise instead of loudly surfacing a parser bug to fix.
Recorded here so a future reader doesn't "fix" this into a regression.

**Why not done now:** none of the four is reachable from the debt-finance
World's shipped `scout-patterns.json` (tightly numeric APR/percent
patterns), and this sprint's scope was the deals/education/tracking
capability upgrade, not a general hardening pass on `agenda_watch.py`'s
scouting internals for hypothetical future Worlds with looser patterns.

**What a future sprint needs to decide:** whether to fix ASK-19/20/21
proactively (cheap, isolated, no behavior change for existing Worlds) the
next time `agenda_watch.py` is touched, or wait for a concrete World that
actually needs a loose extraction pattern to force the issue.

---

## agenda_watch.py — 2 non-blocking follow-ups from round-13 QA re-verification

**Filed by:** `sprints/2026-07-26-world-of-debt-finance/` (deals/education/
tracking capability upgrade), TEST_REPORT.md "QA round 13", verdict PASS.
Found while adversarially re-verifying the QA-1/QA-2/QA-3 fixes from round
12 (commit `0cdadf1`).

**INFO-24 — the QA-2 slug-hashing fix is an un-migrated rename for a lab
that already ran the pre-fix code.** `_slugish`'s new content-hash suffix
changes every snapshot filename and finding stem. A lab that ran the old
code has `state.json` entries keyed by the old sha with an orphaned
snapshot file under the old name — `_read_snapshot` returns `None` on the
first post-upgrade change. Confirmed non-broken, just non-ideal: the
finding degrades honestly to an **Excerpt** section instead of a unified
diff (not silent, not a crash), and the `Change: <old> → <new>` line stays
correct. The orphaned old-named `.txt` files under
`DATA_DIR/agenda-watch/` are inert residue, never cleaned up.
**Fix shape:** either a one-time migration pass that renames existing
snapshot files to the new slug scheme on first tick after upgrade, or
accept the one-time diff-quality degradation as the cost of the fix (it
self-heals on the very next change per feed) and just clean up the
orphaned files opportunistically.

**INFO-26 — `_safe_write_atomic`'s tmp-file name is fixed per destination,
which is a concurrency assumption, not yet a rule.** The ``.tmp`` staging
name is derived deterministically from the destination path
(``path.with_suffix(".tmp")``), so two concurrent writers to the same
destination could in principle interleave and corrupt each other's write.
Checked and confirmed safe *today*: `agenda_watch.tick()` has exactly one
caller in `src/` (the Librarian's `watch_horizon`, awaited via
`asyncio.to_thread`), so writes are serialized by construction, not by
this file's own locking.
**What a future sprint needs to decide:** if a future feature ever calls
`tick()` from a second call site (e.g. an on-demand "run this watch now"
portal action), either add real locking around the tmp-file write or
derive the tmp name per-call (e.g. a pid/uuid suffix) before that second
caller ships — this is a load-bearing assumption to revisit, not
something to rediscover the hard way.

**Why not done now:** neither is reachable under this sprint's actual
shape (single caller, in-place upgrades are the exception not degrading
unsafely) — filed so a future sprint that changes either assumption
(adds a second `tick()` caller, or needs snapshot continuity across an
upgrade) finds this written down instead of rediscovering it.

---

## PDF text extraction → PKB → librarian scout

**Filed by:** `sprints/2026-08-06-deep-research-world-forge/VISION.md`
(reject-as-scoped verdict on a proposed "Deep Research World Forge"
source mode).

**The gap, independent of the rejected feature.** A PDF dropped into
`lab/pkb/inbox` (the Knowledge tab's drag-drop zone) is filed by `pkb.py`
under the `"papers"` category and then **never read by anything.**
`_PKB_TEXT_SUFFIXES` (`pkb.py:376`) is `.md/.txt/.rst/.csv/.json/.html`;
`librarian_scout._TEXT_SUFFIXES` (line 53) is narrower still —
`.md/.txt/.markdown`. `grep` for `pypdf|PyPDF|pdfminer|fitz|pdftotext`
across `src/` and `pyproject.toml` returns nothing — there is zero PDF
text extraction anywhere in ARAIL. The user-visible surface (a drag-drop
zone, a folder-reveal button, a `"papers"` filing category) implies PDFs
are used. They are not. This is arguably already a defect, not just a
missing feature.

**Why it surfaced now.** An operator asked for a "Deep Research World
Forge" mode (live web research via the Browser agent, feeding a new
World's starting term base) to build a "Quantum" World with current
post-quantum cryptography jargon. VISION.md rejected that proposal — the
Browser agent is a `subprocess.run(["agent-browser", ...])` call the
egress guard structurally cannot see (it patches `requests`/`urllib`/
`httpx`, all in-process), so routing forge through it would make the
existing forge banner's audit promise (`worlds.html:92`) false. Separately,
the actual motivating sources (NIST FIPS 203/204/205, the PQC standards)
are PDFs — so a web-research mode wouldn't have reached the right content
anyway.

**The better wedge, once (if) the need is confirmed.** Add a PDF-to-text
step at PKB ingest (`pypdf` — pure Python, no system deps, no network),
extend both text-suffix allowlists above to cover the extracted text, and
let the existing machinery do the rest: `librarian_scout.mine_candidates()`
already scans `pkb/inbox`/`pkb/sources` for capitalized multi-word phrases
and standalone acronyms — precisely the shape of `ML-KEM`, `SLH-DSA`,
`Module-Lattice-Based Key-Encapsulation Mechanism` — and already routes
mined candidates through evidence accumulation, the ubiquity threshold,
and the Compiled-KB approval gate. No new egress surface (the operator
downloads the PDF themselves), no new consent gate, no Node/npm/Chromium
dependency, and it generalizes past one World: every future World forged
from a specialized corpus (a standards body, a textbook, a paper set) is
served, not just Quantum.

**Why not done now.** VISION.md's reject verdict was contingent on a
pre-registered, falsifiable experiment (three-arm forge coverage test —
local dream / frontier-brain dream / Wikipedia fetch — against a
~20-term PQC checklist) that had not yet been run at time of filing. If
Arm B (frontier brain) scores ≥70% coverage, the existing "Frontier API"
forge-brain toggle already solves the operator's stated problem and this
item drops in priority to "fix the PDF-ingest defect" without the
World-forge framing. Revisit alongside that experiment's result — see
`sprints/2026-08-06-deep-research-world-forge/VISION.md` for the full
decision tree and thresholds.
