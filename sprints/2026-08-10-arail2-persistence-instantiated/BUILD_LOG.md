# Build log: arail2-persistence-instantiated

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `4f8ae97`
**Started:** 2026-08-10
**Repo:** `qukaizen-arail` worktree `eloquent-lederberg-6aeb3b`
**Branch:** `qukaizen/arail2-persistence-instantiated`

## Plan

Following ARCHITECTURE.md §9's recommended implementation order:

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/pkb.py`, `src/arail/pkb_index.py`, `src/arail/doctor.py` | Defect B fix: `_semantic_search`'s backend-absent branch calls `set_degraded("backend", ...)` | 16-19 | (below — landed first, out of §9 order since it's small/independent and closes a live honesty hole) |
| 2 | `src/arail/dbspec/ensure.py` (new) | Atlas-free replay of the migration ledger | 1-12 | (below) |
| 3 | `src/arail/data_dirs.py` (new) | `resolve_data_dirs()` Python mirror | 13-15 | (below) |
| 4 | `src/arail/provisioning.py` (new), `src/arail/doctor.py` | The class check + doctor wiring | 30-31 | (below) |
| 5 | `sprints/BACKLOG.md` | File the two required follow-up tickets | — | (below) |
| 6 | `scripts/lib/instances.sh` (shell mirror), `install`/`start`/`status` wiring, `arail/provisioning.py` in `status` | Seamless install/start, status `db` object, exit-code mapping | 20, 23-29, 32-36 | **DONE in the continuation pass — see below** |

## Continuation (resumed per coordinator: finish steps 6-9, do not descope)

The coordinator's ruling: "seamless" is the operator's headline requirement
and is not optional scope. This section covers everything landed after
the initial handoff, finishing ARCHITECTURE.md §9 steps 6-9.

### Step 6 — `install`/`start` wiring

`src/arail/dbspec/ensure.py` gained a thin CLI (`python -m
arail.dbspec.ensure <data_dir> [--apply] [--quiet-ok] [--json]`) — the
shell integration point, matching the existing `python -m
arail.compiled_kb bootstrap` pattern already in `install.sh`. Exit 0 for
ok/created/updated/pending, 3 for blocked/ahead/diverged/unavailable.

- **`scripts/install.sh`**: new `_install_db_ensure`, called from `[5/5]
  verify`, loops `inst_resolve_data_dirs()` and applies (SAFE-FORWARD
  only) to every resolved root. Never hard-fails install — a
  blocked/ahead/diverged root sets the existing `PHASE_DEGRADED` flag.
- **`scripts/start.sh`**: new `_instance_db_ensure <data_dir>`, called for
  exactly one data_dir at a time — the booting instance's own, never a
  sibling's. Wired into both the World-instance path (`_instance_start`,
  right after the env pack is sourced and before port-binding) and the
  root-lab boot path (before the port-conflict check/spawn). Quiet when
  already `ok`; one line when it created/applied; a warning (never a
  refusal) naming the exact verb when blocked/ahead/diverged, per §4.5's
  deliberate "nothing reads `arail.db` at runtime yet" call.

Commit: `a56124f` — `feat(cli): wire ensure_db into install and start`

### Step 7 — `status` wiring

New `DB_JSON` bash variable in `scripts/status.sh`, built by piping
`inst_resolve_data_dirs()`'s TSV into a one-shot in-process Python script
that calls `ensure_db(apply=False)` per root (never creates what it
checks). Merged into the python doc-builder:

- `root.db` / `root.origin`, and per-instance-row `db`/`origin` —
  additive only, **only** in `--json`/`--json=full`. `--json=instances`
  is untouched — proven by a driver-level contract check (stripping
  `db`/`origin` from `--json`'s `.instances` must reproduce
  `--json=instances` exactly; neither key may ever appear there).
- An on-disk-unregistered instance (found via `resolve_data_dirs` but
  absent from the registry-driven `instances` rows) gets its own
  synthetic row (`"state": "unregistered"`, `"origin": "ondisk"`) in
  `--json=full` and the human table only — never in `--json=instances`,
  never counted toward the verdict.
- Exit-code mapping: a db state in `{pending, blocked, ahead, diverged}`
  degrades the verdict **only if the owning root/instance is actually
  live**. Deliberately excluded from the degrading set: `"unavailable"`
  (no `spec/schema/migrations` at all — e.g. a stripped-down fork per
  `BLUEPRINTS.md`, or this sprint's own test fixtures before `spec/` was
  copied in) — that state means "this feature doesn't apply here," not
  "a live service is down," and treating it as degrading would have
  broken every pre-existing `status_driver.sh` scenario that never
  touches `spec/`. This is a real, considered interpretation of §4.4's
  table (which never names `"unavailable"` explicitly) — flagged here for
  the architect review pass, not silently assumed.
- Verified functionally in isolation before wiring: fed the extracted
  Python doc-builder real `FACTS_JSON`/`INSTANCES_JSON`/`DB_JSON` env
  vars by hand and confirmed (a) root live + db pending → exit 3, reason
  `root:db:pending`; (b) a healthy instance's `db: ok` does not degrade;
  (c) **nothing running + db absent → exit 4, never promoted to 3** — the
  load-bearing rule, confirmed directly against the real code the shell
  script runs, not a reimplementation.
- Human renderer: a `db:` line per lab, printed only when that lab is
  up/live and its db state isn't already `ok`/`created`/`updated`.

`tests/cli/status_driver.sh` (the existing self-skipping, real-`.venv`-
required driver) gained three new scenarios — T28a (nothing running, db
absent → exit 4, never promoted; also asserts `status` creates no
`arail.db`), T28b (root live, db pending → exit 3, reason names
`root:db:pending`), T28c/T29 (root live, db pre-applied via a real
`ensure_db --apply` call → exit 0, `root.db.state == "ok"`,
`root.origin == "root"`) — and T12's byte-compatibility assertion was
rewritten from strict equality (no longer true, by design, once `db`/
`origin` are additive) to the strip-and-compare contract check described
above. `bash -n` clean; the driver **self-skips** in this worktree (no
`.venv`) exactly as it already does for every other scenario in the
file — confirmed by running it directly (`SKIP: no usable .venv found`).

Commit: `b3be6a5` — `feat(cli): wire db visibility into status`

### Step 8 — shell mirror of `resolve_data_dirs`

`scripts/lib/instances.sh` gained `inst_ondisk_slugs()` and
`inst_resolve_data_dirs()` — the shell-side mirror, same union (root,
`registry.d`, on-disk-unregistered), same origin tags, TSV output. No
associative arrays (`services.sh`'s existing portability rule: macOS
system bash is 3.2) — dedup via a plain newline list + `grep -Fxq`
instead. Manually smoke-tested against a hand-built fixture (registry
with one slug, two on-disk-unregistered dirs) and confirmed correct
before writing the parity test.

A new shared-fixture test, `tests/test_data_dirs_resolve_shell_parity.py`,
shells out to `bash` and asserts the shell and Python resolvers agree on
slug+origin for the same fixture — this **did** run locally (bash is
present) and passes. `ARCHITECTURE.md §8`'s "two implementations of one
rule" tech debt is now guarded by a real test, not left to drift.

Commit: `9f5cb64` — `feat(instances): shell mirror of resolve_data_dirs`

### Step 9 — Docs

- `docs/cli.md`: `install`'s `[5/5] verify` phase description now names
  the `ensure_db(apply=True)` sweep; `start`'s readiness section gained a
  subsection on the per-instance db-ensure step and its deliberate
  warn-and-continue behavior; `status`'s section gained the `db` object
  shape, the `origin` field, the on-disk-unregistered synthetic row, and
  the exit-code table's new db-driven degrade row plus the explicit
  "never promotes 4 to 3" rule.
- `CHANGELOG.md`: one `[Unreleased]` entry in the existing format
  covering the whole sprint (db instantiation, status/doctor visibility,
  the defect-B honesty fix).

Commit: `047e91c` — `docs: document the seamless DB path`

### Additional tests landed in the continuation pass

- `tests/test_win_condition_honest_failure.py` — tests 21 (the
  honest-failure inverse half; the win-condition-succeeds half still
  needs a real seeded PKB + embedder, not run locally), 22 (the
  agent-facing `retrieve_for_agents` entry point, three natural-language
  queries), and 35 (egress: defect B's fix makes zero network calls,
  proven by making `socket.socket.connect`/`urllib.request.urlopen`
  raise). **All ran locally and pass** — this worktree's actual
  LanceDB-absent state is exactly the fixture these tests need, no
  mocking of the interesting part required.
- `tests/test_seamless_db_integration.py` — test 20's DB-creation half:
  a real subprocess run of `python -m arail.dbspec.ensure` (the same CLI
  `install.sh`/`start.sh` call) against a from-scratch fixture tree,
  proving install-then-start yields a genuinely queryable database
  (`schema_version`/`worlds` tables present, not just a file that
  exists), and that the `apply=False` path creates nothing. **Ran
  locally and passes.**

Commit: `f9bf3a5` — `test: land tests 20-22, 35`

### What is still NOT run locally, and why (unchanged reason: no `.venv`)

- **Test 4** (schema fidelity via the `atlas` binary) — dev-only per the
  spec itself; `atlas` is not installed anywhere available to this build.
- **The shell-level halves of tests 20, 23-29** (actually invoking
  `bash arailctl install`/`start`/`status` against a real `.venv`) — the
  `status_driver.sh` scenarios exist and are believed correct (syntax-
  checked, and the underlying Python doc-builder logic they exercise was
  verified in isolation with real env vars), but the driver itself
  self-skips here exactly as its pre-existing scenarios already do.
  Steps 6 (install.sh/start.sh) have no equivalent self-skipping pytest
  wrapper at all — they were verified via `bash -n` (syntax) and by
  invoking the underlying `python -m arail.dbspec.ensure` CLI directly
  (proven working), but the shell control flow around it (the
  `_install_db_ensure`/`_instance_db_ensure` functions themselves) was
  only smoke-tested with the `.venv`-absent guard path, never against a
  real `.venv`.
- **Test 21's full (win-condition-succeeds) half, and test 26** — need a
  real seeded PKB with a real or deterministic-stub embedder at 768 dims
  and LanceDB; this worktree cannot import `lancedb`.
- **Test 33** (start boot-time delta ≤150ms, measured over 5 runs) — needs
  an actual `start` invocation.

**The operator's provisioned checkout (`.venv/bin/python` present)
should re-run:** `pytest tests/cli/status_driver.sh`'s wrapper
(`tests/test_cli_status.py`), a real `./arailctl install` then
`./arailctl start` on a scratch checkout to confirm test 20/26/33
end-to-end, and test 21's full win-condition-succeeds half against a
real seeded World.

## Deferred scope — NOT completed in this pass (updated)

~~This build did not reach ARCHITECTURE.md §9 steps 4-9.~~ **Superseded
by the continuation section above** — steps 6-9 are now done. What
remains genuinely deferred, unchanged from the original pass:

1. Test 4 (atlas-bearing schema fidelity) — needs the `atlas` binary; the
   CI-job follow-up ticket is filed in `sprints/BACKLOG.md`.
2. Full shell-level execution of `install.sh`/`start.sh`/`status.sh`
   against a real `.venv` — everything is wired and syntax-clean, and the
   underlying Python logic each shells out to is independently tested,
   but nobody has run the actual bash control flow end-to-end in this
   pass. This is the single largest remaining risk and should be the
   first thing `/architect review` or `/qa` does on a provisioned
   machine.
3. Test 33 (boot-time delta) — needs a real `start`.

I deviated from §9's literal order by landing the defect-B fix (§9 step 3)
first: it's small, independent of the DB work, and it closes a live
honesty hole that was already shipped and measured broken (§0 of
ARCHITECTURE.md). Everything else follows §9's order.

## Execution

### Step 1 — Defect B fix

`pkb.py:717-718`'s `if not available(): return []` was the only early
return in `_semantic_search` that never called
`pkb_index.set_degraded(...)`. Added a new `"backend"` degraded code, set
on that branch, naming `sys.executable` and the fix
(`./arailctl install`). Cleared only by a later successful `available()`
observation in the same process or a full rebuild (`clear_degraded(None)`)
— never by a successful embed call (BLOCK-1 discipline, per the existing
module docstring's pattern). Promoted `"backend"` to `doctor`'s required
tier alongside `"dimension"`/`"provenance"`, since LanceDB is a hard dep in
both tiers.

No deviation from ARCHITECTURE.md §4.7.

Commit: `b60bfad` — `fix(pkb): defect B — backend-absent branch was the
only silent early return`

Tests: `tests/test_pkb_semantic_backend_absent.py` (tests 16-19, plus one
extra covering the available()-becomes-True-again clear path). 6/6 pass.

### Step 2 — `arail.dbspec.ensure`

Implemented per ARCHITECTURE.md §4.1/§4.2 exactly, with one documented
interpretation choice on the divergence check — see "Architect feedback
requested" below; I did not stop the build over it because it doesn't
touch the safe/lossy line itself, only how divergence is *detected*.

- `EnsureReport` dataclass matches the spec's field list exactly.
- `apply=False` never creates a file, directory, or writes a byte —
  verified by a directory-snapshot test (test 1) and the truncated-DB
  test (test 11), which asserts the garbage file is byte-identical after
  the call. Uses `sqlite3.connect("file:...?mode=ro", uri=True)` rather
  than `db.connect()` for the read path specifically because
  `db.connect()`'s default `sqlite3.connect(path)` call creates a
  zero-byte file as a side effect of merely opening it — the exact class
  of bug this sprint calls out (§4.1: "A read-only check that creates the
  thing it is checking is the exact bug `doctor` hit in the previous
  sprint").
- Static SQL classifier (`classify_migration`) is a single regex over raw
  text — deliberately does not strip comments or string literals, so a
  `DROP TABLE` mentioned inside either false-positives as LOSSY. Test 5
  pins this as required behavior ("fails closed, never open"), not a bug.
- Migration eligibility is gated by `MIGRATION_NAME_RE =
  ^\d{14}_[a-z0-9_]+\.sql$` (test 36) — any other filename in the
  directory is silently ignored, never executed.
- `PRAGMA user_version` is the cursor, per Assumption 4. No new SQLite
  table added to the schema.
- Concurrency (F17/test 12): a thread-level lock keyed by `data_dir`
  covers the realistic case (concurrent Worlds are one-process-per-World);
  an `flock` on a `.arail_ensure.lock` sidecar file extends the same
  guarantee across processes on POSIX (best-effort elsewhere — `fcntl` is
  imported defensively). The cursor is re-read *after* the lock is
  acquired, not reused from the earlier read-only pre-check, to close the
  TOCTOU window between the two.
- Failure isolation (F2/test 8): each migration file applies inside its
  own `dbmod.transaction()`; a mid-file SQL error rolls back that file
  only, `user_version` stays at the last fully-applied migration, and the
  report's `state="blocked"` names `./arailctl doctor`.

Commit: `03b70e5` — `feat(dbspec): ensure.py — Atlas-free replay of the
migration ledger`

Tests: `tests/test_dbspec_ensure.py`, 24/24 pass. Covers tests 1-3, 5-12,
plus the migration-name-regex and no-migrations-dir contract checks (test
36's regex half; the path-traversal-name half is covered by construction
— `MIGRATION_NAME_RE` is anchored and the iteration only globs `*.sql`
then filters by the regex, so a `../` name can never even reach
`Path.iterdir()`'s matches in a way that escapes `migrations_dir`).
Performance (test 32): measured ~1.9ms per `apply=False` call against the
real repo spec tree — well under the 20ms budget (see the note under
"Not run locally" for what I could NOT measure: `status` over 6 roots,
since `status` itself isn't wired yet).

**Test 4 (schema fidelity via `atlas schema diff`) was not run.** It's
explicitly dev-only/skipped-if-`atlas`-absent per ARCHITECTURE.md itself,
and neither this worktree nor (per the task brief) any environment
available to me has the `atlas` binary installed. This is exactly the gap
ARCHITECTURE.md §8 calls out as requiring a CI follow-up ticket — filed in
`sprints/BACKLOG.md` (commit `11ccc9c`).

### Step 3 — `resolve_data_dirs` (Python mirror only)

Implemented `src/arail/data_dirs.py`: `resolve_data_dirs(repo_root) ->
list[DataDirRecord]`, unioning the root lab's data dir, every
`registry.d/*.json` slug, and every on-disk `lab/instances/<slug>/` dir
(has `data/` or `instance.env`) with no registry record. Each record
carries `origin ∈ {root, registry, ondisk}`.

Commit: `9b748ed` — `feat(instances): resolve_data_dirs — the six-roots
fix (Python mirror)`

Tests: `tests/test_data_dirs_resolve.py`, 4/4 pass, covering tests 13-15
plus a union-dedup check (registry wins over ondisk when a slug has both).

**Deviation from plan: the shell mirror
(`scripts/lib/instances.sh`) was not implemented.** ARCHITECTURE.md §4.3
and §8 call for both a shell and Python implementation "mirrored," with a
shared-fixture test asserting they agree. I implemented only the Python
side. This is a genuine scope gap, not a design disagreement — see
"Deferred scope" below.

### Step 4 — `arail.provisioning` (the class check)

Implemented per ARCHITECTURE.md §5 exactly: `Assertion` dataclass with a
`.finding` property (`declared and not instantiated`), a registry keyed by
mechanism name, and the five seeded checks
(`relational_store`/`vector_backend`/`kb_gate`/`embedding_provenance`/
`instance_registry`). `evaluate_all()` never lets one mechanism's checker
raising an exception crash the whole run — it becomes an info-tier finding
naming the exception instead.

Wired into `./arailctl doctor` as a new "Provisioning" section
(`check_provisioning()`), required tier maps onto the existing `_record()`
mechanism and therefore the existing exit-3 contract — no new exit-code
path invented. Confirmed by hand on this actual worktree: `python -m
arail.doctor` now reports `relational_store` and `vector_backend` as
`MISSING` (previously both were invisible to doctor) and exits `3` where
it previously exited `0` — this is the sprint's headline "declared but
never instantiated" defect made visible, demonstrated on the exact
environment ARCHITECTURE.md's §0 measured it in.

Commit: `d2c5d72` — `feat(provisioning): the class check — declared-but-
uninstantiated as a standing assertion`

Tests: `tests/test_provisioning.py`, 12/12 pass. Covers tests 30 (partial
— see below) and 31, including the required synthetic "instance four"
mechanism proving generalization.

**Test 30 partial.** ARCHITECTURE.md's test 30 is "doctor on a healthy
clean machine still exits 0; doctor with a declared-but-uninstantiated
mechanism exits 3 for required tiers." I tested the second half directly
(`check_relational_store` returns a required finding when uninstantiated)
and confirmed the exit-code wiring by hand (`python -m arail.doctor`
above). I did NOT construct a "healthy clean machine" fixture that exits
0 end-to-end through the real `main()` — this worktree has no `.venv`, so
`doctor`'s other sections (models, embedding provider reachability) are
themselves in various non-clean states unrelated to this sprint's code,
and building a fully-isolated "clean machine" harness for `main()` was out
of scope for the time available. QA should construct this fixture
explicitly (mocking every doctor section to a known-healthy state,
including the new provisioning section) as part of its pass.

### Step 5 — BACKLOG.md

Filed both required follow-up tickets from ARCHITECTURE.md §8: the
atlas-bearing CI job for the schema-fidelity test, and the `start`
hard-gate promotion for when `arail.db` gets its first runtime reader.

Commit: `11ccc9c` — `docs(backlog): file the two required follow-up
tickets from ARCHITECTURE.md §8`

## Deferred scope — NOT completed in this pass

This build did not reach ARCHITECTURE.md §9 steps 4-9. Concretely, still
undone:

1. **`install`/`update` wiring** (`ensure_db(apply=True)` over every
   resolved root, test 25) — `ensure_db` and `resolve_data_dirs` exist and
   are tested in isolation, but nothing in `scripts/install.sh` or
   `arailctl` calls either yet.
2. **`start` wiring** (readiness step before the portal binds, tests 20,
   23, 24, 33) — same story; `scripts/start.sh` does not call `ensure_db`
   for the booting instance's own data dir.
3. **`status`'s additive `db` object, `origin` field, and the exit-code
   mapping table in §4.4** (tests 21-22, 26-29) — `scripts/status.sh` is
   871 lines and untouched. The byte-compatibility golden for
   `--json=instances` (test 27) does not exist yet because there is
   nothing new to be compatible with.
4. **The shell mirror of `resolve_data_dirs`** in
   `scripts/lib/instances.sh`, and the shared-fixture parity test between
   it and `src/arail/data_dirs.py`.
5. **Tests 21-22 (the win-condition / Buddy-level checks) and test 35
   (egress)** — these exercise the wired `start`/`status`/`install` paths
   and a real seeded PKB; without item 1-3 above there is nothing
   end-to-end to exercise them against. `retrieve_for_agents`/
   `search_for_agents` themselves are unchanged by this sprint (only the
   `_semantic_search` backend-absent branch changed), so the *existing*
   win-condition behavior ARCHITECTURE.md §0 already measured as working
   on a provisioned machine is not expected to have regressed, but I have
   not re-run that measurement.
6. **Docs**: `docs/cli.md` (the `status` `db` object, `origin` field,
   `install`/`start` behavior), a note that `arail.db` has no runtime
   reader yet, and `CHANGELOG.md` — not updated because the behavior they
   would document does not exist yet (items 1-3).

**Why I stopped here rather than pushing further:** the wiring work
touches three large, live, hand-maintained shell scripts
(`scripts/install.sh` 584 lines, `scripts/start.sh` 1654 lines,
`scripts/status.sh` 871 lines) plus the documented `arail.status/v2` JSON
contract and its byte-compatibility golden. That is real risk surface —
exactly the kind ARCHITECTURE.md §4.4 is precise about (additive-only,
`--json=instances` byte-identical, the `4`-must-never-promote-to-`3` rule)
— and I judged it needed more care than the time remaining in this pass
allowed to do safely. Landing the three new, fully-tested, callerless
modules (`ensure.py`, `data_dirs.py`, `provisioning.py`) plus the
defect-B fix and doctor wiring is real, shippable progress on its own
(defect B is closed; defect A is now *visible* to `doctor` even though the
seamless auto-create path isn't wired into `start`/`install` yet) — but
the sprint's stated win condition ("a user who runs `install` then `start`
never has to know `arail.db` exists") is **not yet met**. This should go
back through `/architect review` scoped explicitly as "steps 1-5 done,
steps 6 (wiring) pending" rather than being represented as sprint-complete.

## Architect feedback requested

**Divergence detection does not use Atlas's own hash format.**
ARCHITECTURE.md §4.2 defines SAFE-FORWARD as (among other things) "hash
matches `atlas.sum`." I implemented divergence detection instead as
*self-consistency*: `ensure_db` records a plain `sha256` of each migration
file's bytes, the first time it applies that file, into a JSON sidecar
(`<data_dir>/.arail_ensure_state.json`) — not a new SQLite table, per
Assumption 4's constraint against adding an unspecced one. Every later
call re-hashes the file and compares against the sidecar. This is
*not* literal parity with `atlas.sum`'s own hash algorithm, which is
undocumented outside the `atlas` binary itself (Assumption 1 says that
binary is explicitly not available to this module or to users). I could
not find a way to verify a migration file's hash against `atlas.sum`
without either vendoring Atlas's hash algorithm (risk: silently getting it
wrong and creating false confidence) or shelling out to `atlas` itself
(forbidden by Assumption 1 and F1's test). I judged self-consistency
sufficient to satisfy the actual safety property in play (test 7: "an
already-applied migration file gets mutated → DIVERGED") without
introducing an unverified reimplementation of a third-party hash format,
and documented the choice prominently in `ensure.py`'s module docstring.
**This is a real interpretation, not a rubber-stamp** — if the architect
wants literal `atlas.sum` parity, that needs either the `atlas` binary
made available at `ensure` time (which contradicts Assumption 1) or an
explicit, verified port of Atlas's hash algorithm as its own reviewed
piece of work. I did not silently pick a side of this; flagging it here
per the builder protocol's "when the architect's plan is wrong" step,
even though I judged it did not block continuing (the safety property the
line exists to protect — never auto-applying a migration whose committed
bytes changed — holds either way).

## Operational incident (not a code change, worth recording)

Mid-build, while comparing pre/post-change test baselines with `git
stash` / `git stash pop`, a `git stash pop` popped an **old, unrelated**
stash entry (`stash@{0}`, "On qukaizen/arail-model-defaults:
pre-bundled-aerollm-round2-switch", from a different branch's WIP,
unrelated to this sprint) because the plain `git stash` immediately before
it found nothing to save (my own edits at that point were untracked new
files, which plain `git stash` does not capture) and so `pop` fell through
to the next entry in the stack. This left ~350 unrelated `lab/pkb/` and
`lab/worlds/ai/` files in a conflicted/deleted state in the worktree.
Recovered via `git checkout HEAD -- lab/pkb/sources/world-ai
lab/worlds/ai` — confirmed via `git diff --stat HEAD -- src/ tests/`
showing zero unexpected diff and `git stash list` showing `stash@{0}`
still present (never dropped, so nothing was lost). A handful of
harmless, purely-additive untracked directories from that same errant pop
likely remain in the worktree (`experiments/`,
`lab/pkb/conversations/`, `lab/pkb/sources/world-debt-finance/`,
`lab/worlds/debt-finance/`, `lab/worlds/photography/`,
`sprints/2026-07-26-semantic-retrieval/`) — none of these were staged or
committed by me, so they cannot appear in any commit I made, but the
operator should `git status`/`git clean -n` this worktree before treating
it as pristine. **Lesson for future sessions: never run bare `git stash` /
`git stash pop` in a worktree with a pre-existing stash stack — use `git
stash push -u -- <specific paths>` (scoped, and captures untracked files
so `pop` can't silently fall through) or just `git diff`/copy-compare
instead of stashing at all.**

## Final state

- **14 commits** on this branch across both passes: `b60bfad` (defect B),
  `03b70e5` (ensure.py), `9b748ed` (data_dirs.py), `d2c5d72`
  (provisioning.py), `11ccc9c` (BACKLOG tickets), `141a35f` (BUILD_LOG,
  first pass) — then the continuation: `9f5cb64` (shell mirror), `a56124f`
  (install/start wiring), `b3be6a5` (status wiring), `047e91c` (docs), and
  `f9bf3a5` (tests 20-22, 35), plus this BUILD_LOG.md update.
- **New tests added:** 58 total (6 defect-B + 24 `ensure.py` + 4
  `data_dirs.py` + 1 shell-parity + 12 `provisioning.py` + 3 win-
  condition/egress + 2 seamless-DB-integration = 52 pure-Python, all
  passing, run via `PYTHONPATH=src python3 -m pytest`; plus 3 new
  `status_driver.sh` scenarios that self-skip in this worktree — see
  below), plus `test_cli_status.py`'s existing self-skipping wrapper.
- **Regression check (repeated after the continuation pass):**
  `tests/test_pkb.py`, `test_pkb_index.py` (the 24/30 subset that doesn't
  require `lancedb`), `test_pkb_gate.py`, `test_pkb_retrieve_for_agents.py`,
  `test_dbspec_spec.py`, `test_doctor_embedding_status.py`,
  `test_cli_status.py` all pass or fail *identically* to the pre-change
  baseline (`d5c592a`) — confirmed by diffing pass/fail sets, not by
  inspection alone. `bash -n` clean on every modified shell script
  (`install.sh`, `start.sh`, `status.sh`, `lib/instances.sh`,
  `status_driver.sh`, `arailctl`). `git diff --stat -- lab/` empty at
  every commit in the continuation pass — nothing in `lab/` was ever
  staged or touched, per the coordinator's explicit instruction.
- **Not run locally, and why:** anything requiring `lancedb`, `fastapi`,
  the `atlas` binary, or actually invoking `bash arailctl
  install`/`start`/`status` against a real `.venv` — this worktree has no
  `.venv` (per the task brief, that's the deliberate broken state defect
  B is about). See "What is still NOT run locally" in the continuation
  section above for the precise list and what the operator's provisioned
  checkout should re-run.
- **Win condition status: MET in code, NOT YET VERIFIED shell-level
  end-to-end in this worktree.** All four of the operator's required
  scope items are now implemented: seamless (install/start wire
  `ensure_db`), status visibility (the `db` object + exit-code mapping),
  startup love (start's readiness step, reported not silent), and doctor
  (the provisioning class check). Defect B is closed and tested directly.
  What remains is verification, not implementation: the shell control
  flow in `install.sh`/`start.sh`/`status.sh` has never been run against
  a real `.venv` in this pass (self-skipping test harnesses exist and are
  believed correct — syntax-checked, and the Python logic underneath each
  was independently verified — but "believed correct" is not "run and
  passed"). This is the right next gate for `/architect review` and/or
  `/qa` on a provisioned machine, not a reason to withhold the build.

## Round 2 (fixing REVIEW.md's BLOCK verdict — commit 6328112)

Architect's review round 1: **BLOCK**, 3 findings, all on the boot-time
auto-apply safety boundary, all verified by execution rather than by
reading. Full review at `sprints/2026-08-10-arail2-persistence-instantiated/REVIEW.md`.
The review confirmed the exit-code contract, `apply=False` write-freedom,
provisioning generalization, and defect B's fix were all correct and
should not be redone.

### BLOCK-1 — the lossy classifier could not fail closed

The classifier was a denylist of six regex patterns. Four verified-
executable SQLite bypasses classified SAFE-FORWARD and would have been
auto-applied at `start`: `ALTER TABLE t DROP c` (no `COLUMN` keyword —
the idiomatic short form and the single most likely destructive migration
anyone actually writes), `REPLACE INTO`, `INSERT OR REPLACE INTO`,
`UPDATE OR REPLACE`, plus `DROP VIEW`/`DROP TRIGGER`.

**Fix:** inverted to an ALLOWLIST keyed on leading statement keywords
(`CREATE TABLE`, `CREATE [UNIQUE] INDEX`, `CREATE VIEW`, `CREATE TRIGGER`,
`ALTER TABLE ... ADD COLUMN`, bare `INSERT INTO`). Classification moved
from whole-file-regex to per-statement (after `_split_statements`); a
migration is SAFE-FORWARD only if every statement matches the allowlist,
LOSSY otherwise — including anything unrecognized. Leading SQL comments
(Atlas's own generated migrations prefix nearly every statement with
one) are stripped before the allowlist match, since comments cannot be
"escaped" early and this reopens no bypass — verified the real committed
baseline still classifies SAFE-FORWARD (`test_real_baseline_migration_classifies_safe_forward`).

Test table rewritten with all four verified bypasses, `DROP VIEW`/
`DROP TRIGGER`, and unparseable/unrecognized-statement cases — all
correctly LOSSY. `test_lossy_classifier_table_driven` now has 22 cases
(was 10).

### BLOCK-2 — migrations executed with zero integrity check on first apply

My round-1 architect-feedback item (a) asserted Atlas's digest was
"undocumented, binary-only" — the review reproduced it exactly:
`base64(sha256(filename_bytes + content_bytes))`, three lines of pure
Python, no `atlas` binary, verified byte-for-byte against this repo's
real `atlas.sum`. The premise was false. Consequence: the sidecar only
records a hash *after* a file has been applied, so on a fresh clone
`ensure_db(apply=True)` executed migration SQL having verified nothing
at all — and deleting `.arail_ensure_state.json` silently turned
`diverged` back into `ok`.

**Fix:** `ensure_db` now verifies every committed migration against
`atlas.sum` (parsed in pure Python, matching the algorithm above) BEFORE
any SQL executes — on `apply=False` too, so `status`/`doctor` catch a
tampered ledger as early as possible. A file missing from the ledger or
whose hash disagrees makes the whole call `state="diverged"`, zero
statements executed. The sidecar is kept as the complementary post-apply
check (it still catches "someone edited an already-applied file," which
`atlas.sum` alone can't express since it only ever describes the current
checkout, not a given database's history) — it's no longer the *only*
gate.

Six new tests: the hash reproduction pinned against the real `atlas.sum`,
fresh-clone-verifies-before-executing, unlisted-file-diverges,
sidecar-deletion-no-longer-defeats-detection (the exact bypass the
review reproduced live), ledger-check-runs-on-apply=False-too, and
missing-atlas.sum-blocks-everything.

Also fixed as part of the same change: **ASK-4** (removed the dead
`if True:` scaffolding in `_apply_locked`) and **ASK-5** (`record_version`
being silently skipped when the spec fails to load — now reported in
`detail` instead of leaving `state="created"` with an empty
`schema_version` table silently).

Commit: `d78aa69` — `fix(dbspec): BLOCK-1/BLOCK-2 — allowlist classifier, ledger verification before execution`

**Collateral fix required by BLOCK-1/2's stricter checking:**
`test_failure_isolation_bad_migration`'s synthetic migration files now
need real `atlas.sum` entries (ledger verification runs before
classification/execution) — added via `ensure.py`'s own `_atlas_file_hash`
so the test can't silently drift from what the module actually checks.
Its "broken" migration also switched from a classification-rejected typo
(`CREATE TBLE`, caught by the new allowlist before ever reaching
execution) to a real execution-time SQL error (`CREATE TABLE ... (;` —
valid leading keywords, malformed body), preserving the original F2
per-file-transaction-rollback intent the allowlist would otherwise have
short-circuited before it could be exercised.

### ASK-1 — `spec_dir`/`repo_root` resolved from CWD, not the package location

`ensure_db`'s `spec_dir` default was the relative `Path("spec")`; a
caller with the wrong CWD got a silent, non-degrading `unavailable` on a
perfectly healthy database. Latent everywhere shell callers `cd
"$REPO_ROOT"` first, but exposed: `doctor.check_provisioning` passes
`repo_root=os.getcwd()`.

**Fix:** `DEFAULT_SPEC_DIR = Path(__file__).resolve().parents[3] / "spec"`
— derived from the package location, matching the editable-install
assumption already relied on elsewhere. `check_relational_store` now
defaults from this constant instead of re-deriving from `repo_root`;
`doctor.check_provisioning` derives `repo_root` the same way instead of
`os.getcwd()`. Verified by hand: `python -m arail.doctor` run from `/tmp`
now correctly reports `relational_store: pending` (the true state), not
`unavailable`.

Commit: `ee797bf` — `fix(provisioning): ASK-1 — resolve spec_dir/repo_root from package location, not CWD`

### BLOCK-3 — `status.sh`'s DB collector swallowed every failure

The collector ended in `2>/dev/null || echo '{}'`. Any failure became
`{}`, rendering `"db": null` with no warning, no `verdict.reasons` entry,
no exit-code effect. The architect reproduced this live by accident: the
DB subsystem failed to import entirely and `status` exited 3 for an
unrelated memory reason, saying nothing about the dead subsystem — this
sprint's own thesis ("declared and not instantiated is always a finding,
never silence") broken three files from where it's stated.

**Fix:** stderr is captured to a temp file instead of discarded; a
non-zero exit, empty output, or unparseable JSON is a collector failure.
`DB_COLLECTOR_FAILED`/`DB_COLLECTOR_ERROR` feed the python doc-builder,
which appends a `db: status could not check the relational store: ...`
warning, adds `db:collector-failed` to `verdict.reasons` unconditionally,
and degrades a currently-live root/instance to exit 3 — gated on the
same liveness check every other db-driven degrade already uses, so a
collector failure on a lab that was never started still exits 4, never
promoted to 3.

**Verified functionally** (not just read) against the extracted python
doc-builder with real env vars simulating both cases:
- root live + `DB_COLLECTOR_FAILED=1` → exit 3, `verdict.reasons =
  ['db:collector-failed']`, warning present naming the captured error —
  reproduces the architect's exact live finding, now loud instead of
  silent.
- nothing running + `DB_COLLECTOR_FAILED=1` → exit 4 (never promoted),
  `db:collector-failed` still present in `reasons` (non-degrading, but
  not silent either).

Also required: `tests/cli/status_driver.sh`'s T28c asserted `RC == 0` on
a fixture whose stub portal never spawns memory/MLX/etc, so root
legitimately degrades for an unrelated reason — could never pass. Fixed
to the narrower, correct claim the scenario actually needs: no
`db:`-prefixed reason appears in `verdict.reasons` on a healthy db,
regardless of what else is degraded.

**Deliberately NOT added:** a driver scenario that breaks the collector
end-to-end (QA's explicit assignment per REVIEW.md's "What QA should
hammer," not a builder requirement this round). I attempted one and
caught my own mistake before committing it: `tests/cli/lib.sh`'s
`make_fake_venv` symlinks `.venv/lib` straight into the **real** venv's
site-packages, so a scenario that renames/edits anything under it (e.g.
"rename `ensure.py` so the import fails") would mutate the operator's
actual installation — exactly what the coordinator's constraints forbid.
I built and then discarded that version before running it against
anything. A safer alternative (a malformed registry record designed to
crash the collector's own TSV parsing) turned out not to reach the
vulnerable code path (`inst_resolve_data_dirs` computes `data_dir` from
the slug/filename, not from JSON field content, so the injected
malformed field was never read) and I judged building a *verified*
correct crash-fixture without a real `.venv` to test against, under this
constraint, not worth the risk of shipping a broken or — worse — falsely
reassuring scenario. Left as a clearly-marked comment in the driver
pointing QA at exactly this gap, plus the functional verification above
as the evidence for the fix itself.

Commit: `8905a17` — `fix(cli): BLOCK-3 — status.sh's DB collector no longer swallows failures`

### ASK-2 — install and status disagreed about `unavailable`

`_install_db_ensure` degraded install on ANY non-zero CLI exit, including
`unavailable`; `status.sh` deliberately excludes that state. Cheap fix
per the coordinator's ruling: the `ensure.py` CLI's exit code now matches
`status.sh`'s `_DB_DEGRADING_STATES` exactly — 0 for
ok/created/updated/pending/unavailable, 3 for blocked/ahead/diverged.

Commit: `2add0c2` — `fix(dbspec): ASK-2 — install and status now agree on "unavailable"`

### ASK-3 — filed, not fixed (non-blocking, per the review)

`--json=instances`'s byte-compatibility guard (T12/T27) is an
internal-consistency check (strip `db`/`origin` from `--json`'s
`.instances`, must equal `--json=instances`), not the committed golden
ARCHITECTURE.md's test 27 originally specified. Real property, but
self-referential — a change that broke both modes identically would
pass. Filed in `sprints/BACKLOG.md` per the review's explicit
instruction ("not worth blocking; file it").

### Item 5 (add unanticipated debt to ARCHITECTURE.md §8) — deferred to the architect

The review's required-action item 5 asks for the round-1 unanticipated
debt (the denylist→allowlist inversion and ledger verification hiding
behind "hash-verified committed migration" in §4.2; ASK-2's two-sources-
of-truth; the CLI-contract layer's total self-skip without a `.venv`) to
be added to ARCHITECTURE.md §8. I did not edit ARCHITECTURE.md directly
— it is the architect's own artifact from the design phase, and this
sprint's round-1 build already respected that boundary (BUILD_LOG raised
the divergence-hash interpretation as an "architect feedback requested"
item rather than editing the spec to match). This round's debt delta is
recorded here instead; the architect's own next pass should fold it into
§8 alongside their PASS/BLOCK verdict, consistent with "the architect
doesn't build code; the builder doesn't redesign."

### Full regression sweep after round 2

```
PYTHONPATH=src python3 -m pytest tests/test_dbspec_ensure.py \
  tests/test_data_dirs_resolve.py tests/test_data_dirs_resolve_shell_parity.py \
  tests/test_provisioning.py tests/test_pkb_semantic_backend_absent.py \
  tests/test_win_condition_honest_failure.py tests/test_seamless_db_integration.py \
  tests/test_cli_status.py tests/test_pkb.py tests/test_pkb_gate.py \
  tests/test_pkb_retrieve_for_agents.py tests/test_dbspec_spec.py \
  tests/test_doctor_embedding_status.py -q
```
123 passed, 1 skipped (test_cli_status.py's self-skip, no `.venv` here —
unchanged reason from round 1), 3 pre-existing failures in
`test_doctor_embedding_status.py` that require `lancedb` and fail
identically on the pristine `d5c592a` baseline (re-confirmed this round,
not a regression). `bash -n` clean on every modified shell script.
`git diff --stat -- lab/` empty at every commit — zero `lab/`
contamination held across both rounds, confirmed after every commit in
this pass per the coordinator's explicit constraint. No bare `git
stash` used this round (explicit paths only, per the constraint — the
round-1 incident is not repeated).

### What round 2 did NOT touch, and why

Per the coordinator's explicit constraints: `install.sh`/`start.sh` were
NOT run against the operator's real lab, and no authorization was sought
for that (the architect's review explicitly ruled this acceptable to
pass to QA, using `tests/cli/lib.sh`'s existing fake-venv/fake-repo
harnesses rather than the operator's lab). `status.sh`'s own control flow
WAS exercised live by the architect in their review (T28a/T28b/T27
passing, T28c a test bug) — this round's `status.sh` changes were
verified against the same extracted-doc-builder technique used in round
1, not a live `bash arailctl status` run, since no `.venv` is available
in this worktree. The operator's provisioned checkout should re-run
`tests/cli/status_driver.sh` in full (all scenarios, including the new
T28c fix) to confirm live, not just via the extracted-logic verification
recorded here.

### Final state, round 2

- **6 additional commits**: `d78aa69` (BLOCK-1/BLOCK-2), `ee797bf`
  (ASK-1), `8905a17` (BLOCK-3), `2add0c2` (ASK-2), plus the BACKLOG.md
  ASK-3 filing and this BUILD_LOG update — 20 commits total across both
  rounds.
- **All three BLOCKs addressed** with the review's required fixes,
  verified either by full local test suite (BLOCK-1, BLOCK-2, ASK-1) or
  by direct functional verification of the extracted logic against real
  env vars matching the architect's own reproduction technique (BLOCK-3,
  since the shell control flow itself can't run without a `.venv` here).
- **Win condition status: the data-safety boundary now actually holds**
  under the adversarial cases the review found. What remains, unchanged
  from round 1: live end-to-end verification of `install.sh`/`start.sh`/
  `status.sh`'s shell control flow against a real `.venv` — ruled
  acceptable by the architect to pass to QA, not a builder gap.

## Round 3 (REVIEW2.md — commit e7efcc5, verdict BLOCK, narrow)

All three round-1 BLOCKs verified genuinely fixed by execution (not
re-touched this round, per the review's own instruction): the allowlist
held under a fresh, different attack surface (semicolons in strings,
CTEs, BEGIN/COMMIT wrappers, unterminated comments — 19 new adversarial
cases, all correct); the ledger-ordering claim was verified by checking
the DB file doesn't exist after any of seven failure modes; the
collector is loud (traceback printed, `db:collector-failed` in
`verdict.reasons`, exit 3, 4-never-promoted preserved) across 16 driver
scenarios with a working collector; ASK-1 verified from `/tmp`; ASK-2/4/5
fixed; ASK-3 filed. The architect also closed their own required action
5 by folding both rounds' debt into ARCHITECTURE.md §8 themselves
(commit `e7efcc5`) — correctly not something I should have edited.

Two new findings, both fixed this round.

### BLOCK-4 — a leading keyword does not bound what a statement does

`INSERT INTO worlds VALUES (...) ON CONFLICT(id) DO UPDATE SET status=...`
classified SAFE-FORWARD — the allowlist admitted bare `INSERT INTO`, and
SQLite's upsert suffix turns it into a row-rewriting statement while the
prefix still matches. Verified by the review to mutate real data
(`('w1','active')` → `('w1','WIPED')`). The review named a second,
structurally identical gap: `CREATE TRIGGER ... BEGIN DELETE FROM y; END`
classified LOSSY, but only by accident — the naive `;`-split fragments
the trigger body and the leftover pieces usually (not by any rule) fail
to parse.

**Checked the committed baseline first**, as instructed: zero `INSERT`
or `TRIGGER` statements anywhere in `spec/schema/migrations/*.sql`.
**Chose to drop both keywords from the allowlist entirely**, not guard
them — the review's stated preference, and consistent with BLOCK-1's own
lesson: a negative guard against `ON CONFLICT`/`RETURNING` only protects
against the suffixes named today, the same denylist failure mode BLOCK-1
already replaced once. Neither keyword is missed: schema migrations
don't need data DML or triggers, and either can go through the
non-seamless `./arailctl db apply` path like any other change this
module refuses to auto-apply.

Applied the structural lesson beyond the two named cases: reviewed every
remaining allowlisted keyword (`CREATE TABLE`, `CREATE [UNIQUE] INDEX`,
`CREATE VIEW`, `ALTER TABLE ... ADD COLUMN`) against the question "is
this statement's entire effect on existing data bounded by its prefix,
or can something after the prefix change what it does to rows that
already exist?" All four are pure schema DDL with no form that rewrites
or deletes an existing row — none have a destructive suffix or an
unbounded body the way `INSERT` (a suffix) and `CREATE TRIGGER` (a body)
do. Documented this as the standing test for anyone re-adding a keyword
in the future, directly in `_ALLOWLIST_RE`'s own comment.

Added both upsert forms and the `CREATE TRIGGER`-body case to the test
table (24 cases, was 22), asserted LOSSY for the stated structural
reason. Verified directly against a live `sqlite3` connection that the
exact exploit the review found now classifies LOSSY.

Commit: `eff30f7` — `fix(dbspec): BLOCK-4 — a leading keyword does not bound what a statement does`

### BLOCK-5 — T10 regressed silently (0 → 3) when the db object landed

A pre-existing, long-standing driver scenario (T10: live `ai` instance,
missing data root — `cli_test_fabricate_live_instance` registers a
record without ever creating the data directory) flipped from exit 0 to
3 once round 2's db object started reporting the derived "pending" state
against a directory that doesn't exist.

**Decision: suppress the derived db object when `data_root_missing` is
true, rather than update T10's expectation to 3.** Reasoning (also in
the commit message and `docs/cli.md`): "pending" is the wrong word for a
database that can't exist because its whole containing directory
doesn't — the actionable fact is the missing data root itself, which is
already reported as a deliberately non-degrading warning
(`data_root_missing`/"⚠ data root missing"). A second, derived
`db:`-prefixed complaint about the same underlying fact would be noise
pointing at the wrong subsystem, and — the deciding factor — it would
silently change a documented, pre-existing exit-code contract for a
scenario this sprint never set out to touch. The alternative (updating
T10 to expect 3) was rejected because a live instance whose data
directory is simply not there yet (a timing window during boot, or an
operator who hasn't run `install` yet) is a materially different,
already-triaged condition from "the db subsystem itself is unhealthy,"
and conflating them would make `status`'s exit code less diagnostic, not
more.

Applied symmetrically: the verdict computation (no db-degrade
candidate/reason when `data_root_missing`), the `--json`/`--json=full`
augmentation (`"db": null`, not the derived state), and the human
renderer (no `db:` line). T10 now asserts the chosen behavior explicitly
— `data_root_missing is True`, `db is None`, no "db pending" line in the
human view — rather than merely continuing to pass by accident, per the
review's explicit instruction not to "absorb the change" silently.

Commit: `9173c2a` — `fix(cli): BLOCK-5 — suppress derived db state when a live instance's data root is missing`

### The `make_fake_venv` footgun note — moved to the symlink site

The warning about `.venv/lib` being a live symlink into the real venv's
site-packages was at the tail of `status_driver.sh`, where the person
who repeats the mistake (editing `lib.sh`, or writing a new driver) will
never read it. Moved and expanded directly above the `ln -s
"$REAL_VENV/lib" ...` line in `tests/cli/lib.sh`, naming the concrete
incident from round 2 by sprint reference.

**Hardening (per-package symlinks or a read-only tree) was filed, not
implemented** — the review's own fallback for "if it isn't cheap and
self-contained." It isn't: it touches shared test-harness infrastructure
used by every CLI driver, and verifying a change to it doesn't break
anything requires a real `.venv` to run against, which this worktree
doesn't have. Filed in `sprints/BACKLOG.md`, along with a second entry
(also from the review, "the meta-pattern... the shell layer's only real
test hid something ... twice") for giving the CLI-driver layer an actual
CI-runnable path instead of universal self-skip.

Commit: `cc66b1d` — `docs(tests): move the make_fake_venv footgun note to the symlink site; file hardening + CI-runnable-driver tickets`

### What round 3 did NOT do

Per the same standing constraints: did not run `install.sh`/`start.sh`
against the operator's real lab, did not seek authorization to. Did not
build a collector-kill test (QA's explicit assignment per REVIEW2.md,
reiterated this round: "don't pre-empt it by writing through that
symlink yourself"). Did not implement `make_fake_venv` hardening (filed,
reasoning above). Did not touch `lab/` — confirmed empty diff after
every commit.

### Full regression sweep after round 3

```
PYTHONPATH=src python3 -m pytest tests/test_dbspec_ensure.py \
  tests/test_data_dirs_resolve.py tests/test_data_dirs_resolve_shell_parity.py \
  tests/test_provisioning.py tests/test_pkb_semantic_backend_absent.py \
  tests/test_win_condition_honest_failure.py tests/test_seamless_db_integration.py \
  tests/test_cli_status.py tests/test_pkb.py tests/test_pkb_gate.py \
  tests/test_pkb_retrieve_for_agents.py tests/test_dbspec_spec.py -q
```
124 passed, 1 skipped (unchanged self-skip reason, no `.venv`). `bash -n`
clean on every modified shell script (`status.sh`, `status_driver.sh`,
`lib.sh`). `git diff --stat -- lab/` empty at every commit this round —
zero `lab/` contamination held across all three rounds. No bare `git
stash` used.

### Final state, round 3

- **4 additional commits**: `eff30f7` (BLOCK-4), `9173c2a` (BLOCK-5),
  `cc66b1d` (footgun note + 2 BACKLOG tickets), plus this BUILD_LOG
  update — 24 commits total across three rounds.
- **Both new BLOCKs fixed and verified**: BLOCK-4 by the full local test
  suite plus a direct live-sqlite3 reproduction of the exact exploit
  (now LOSSY); BLOCK-5 by the extracted doc-builder verification
  technique (matching the architect's own reproduction) plus updated
  driver assertions.
- **Data-safety boundary status**: both rounds of adversarial review
  (round 2's fresh-attack-surface pass, round 3's structural
  "does the prefix bound the effect?" question) are now closed with
  fixes, not just patches to the specific cases named. What remains
  unchanged from prior rounds: live end-to-end shell verification of
  `install.sh`/`start.sh`/`status.sh` against a real `.venv` — ruled
  acceptable by the architect to pass to QA in round 2, not revisited
  as a builder gap in round 3.

## Round 4 (TEST_REPORT.md — commits d161ac3/ca6b43a, verdict FAIL, 4 blocking findings + ASK-6)

QA's full report read in full. All six failing QA tests left over from a
crashed QA pass were independently adjudicated real defects, not bad
tests — nothing was weakened to go green. What held (not touched this
round, per instruction): the 600-candidate statement-safety fuzz corpus
(zero third bypass found), collector-kill 7/7 from the caller side,
ledger tampering, six-roots/empty-registry install, F4/F5/F10,
cross-process `_apply_lock`, defect-B honesty surfaces, no `secrets.env`
touched.

### QA-1 (HIGH) — `apply=False` was not actually write-free

`_read_user_version_readonly`'s `sqlite3.connect("file:...?mode=ro",
uri=True)` was not write-free on a WAL-journaled database (`dbmod.connect`
always sets `journal_mode=WAL`), breaking in opposite directions by
SQLite version: >=3.53.4 materializes `-wal`/`-shm` sidecars (a write on
the contractually write-free path); <=3.51.0 fails outright with
`state="blocked"`, a DEGRADING state, so a perfectly healthy database in
an unwritable/version-mismatched data dir degraded a live lab to exit 3.
QA's three independent confirmations (the builder's own
`test_user_version_ahead_of_ledger` failing under the operator's `.venv`;
`qa_db_seamless_driver.sh` S5 showing five new `-wal`/`-shm` pairs at the
CLI; a healthy DB in a `0o500` dir reporting `blocked`) all match what I
reproduced independently before fixing.

**Applied QA's suggested fix as-is, and I agree with it.** Read
`PRAGMA user_version`'s value directly from the SQLite file header
(bytes 60-63, big-endian signed int32) via a plain `open(path,
"rb").read(100)` — genuinely zero-write on every SQLite version, since
it never asks SQLite to open anything. I checked the one thing that
could make this wrong (staleness against an open WAL) before trusting
it: correctness depends on every `apply=True` caller closing its
connection before returning, which it already does (`ensure_db`'s
`finally: conn.close()`) — SQLite's checkpoint-on-last-close flushes the
true `user_version` into the header before any later `apply=False` call
reads it. Documented this as a load-bearing invariant directly in the
function so a future edit removing that `close()` doesn't silently
reintroduce staleness. `immutable=1` was correctly avoided per QA's own
note (licenses stale reads of a concurrently written file) — the header
read has no such license since it re-reads fresh bytes every call.

Verified: all 5 of `test_qa_ensure_write_free.py`'s cases pass on the
system interpreter (SQLite 3.51, the "fails outright" direction) — the
read-only-data-dir case now correctly reports `ok`, not `blocked`. Full
`ensure.py` suite (46) + the 600-candidate fuzz corpus + concurrency
suite (695 tests) pass with no regressions.

Commit: `07080fe` — `fix(dbspec): QA-1 — read user_version from the SQLite header, never open the file`

### QA-5 (MEDIUM) — the class check only ever looked at one root

`doctor.check_provisioning` passed a single `data_dir` (the root lab's
own), so with five of six roots having no database — the operator's
measured usage pattern — `relational_store` reported
`instantiated=True`. `check_relational_store` now calls
`resolve_data_dirs(repo_root, root_data_dir=data_dir)` and checks EVERY
resolved root; `instantiated` is True only if all of them are `ok`, and
the finding names which root(s) are missing. Verified live:
`python -m arail.doctor` in this worktree now correctly names a real,
previously-invisible second root (`finance`).

Fixed `test_provisioning.py`'s `test_healthy_registry_has_no_required_findings`
to use its own isolated `repo_root` rather than the shared worktree
`REPO_ROOT` — with the fix above, the real `REPO_ROOT` would pull in
this worktree's actual `lab/instances/` state into the check, which is
test-isolation maintenance, not a weakened assertion (the underlying
claim — a healthy single DB reports no finding — is unchanged, just
correctly isolated from machine state the test doesn't control).

### QA-6 (MEDIUM) — a crashing `required` check silently demoted to `info`

`evaluate_all`'s except-handler hardcoded `tier="info"`, so a mechanism
registered `required` whose predicate raised (a broken import, an
unreadable data dir, a bug in the predicate itself) became an `info`
finding that `doctor`'s exit code doesn't read — exactly the mechanism
most likely to be genuinely broken. `register()` now takes a `tier`
parameter (default `"required"` — a predicate that's never successfully
run isn't proven safe to demote); the crash fallback in `evaluate_all`
uses the mechanism's *registered* tier, never a hardcoded constant. The
success path is unaffected (a successful call's own returned
`Assertion.tier` still wins).

### QA-7 (LOW) — `register()` silently replaced a built-in

Was a bare `_REGISTRY[key] = fn`. Now refuses a duplicate key by
default (logs a warning, keeps the existing registration active) unless
the caller passes `overwrite=True` — a 2.1 mechanism, a plugin, or a bad
merge reusing a key can no longer silently replace a real check with one
that always reports healthy.

Commit (QA-5/6/7 together, one file): `43a9cde` — `fix(provisioning): QA-5/QA-6/QA-7 — six-roots blind spot, crash demotion, silent overwrite`

### ASK-6 — real, reproduced by execution (`qa_db_ledger_driver.sh` A2)

BLOCK-5's round-2 fix (suppress the derived db object when a live
instance's data root is missing) was keyed on the `data_root_missing`
FLAG, not the db STATE — so it swallowed `"diverged"` (a fact about the
*checkout*, BLOCK-2's tampered-ledger condition) along with the benign
`"pending"`/`"unavailable"` it was meant to cover. An operator running
altered committed SQL, with the only live lab's data root also missing,
was told everything is fine: exit 0, no `verdict.reasons` entry, silent
human view.

Fixed by keying the suppression on state: a new
`_DB_SUPPRESSIBLE_WHEN_ROOT_MISSING = {"pending", "unavailable"}` set
and a shared `_suppress_for_missing_root()` helper, applied identically
in the verdict computation and the `--json=full`/human augmentation.
`"diverged"`/`"blocked"`/`"ahead"` now survive a missing data root
unconditionally.

Verified functionally against the extracted doc-builder (the same
technique used throughout this sprint, since no `.venv` is available
here to run `qa_db_ledger_driver.sh` directly): a live instance with
`data_root_missing=True` and `db.state="diverged"` now correctly
produces exit 3 with `reason="instance:ai:db:diverged"` and the db
object intact — previously exit 0, no reason, `db=None`. The original
BLOCK-5 case (`data_root_missing=True`, `db.state="pending"`) is
unchanged: exit 0, `db` suppressed to `null`.

Commit: `59947f4` — `fix(cli): ASK-6 — key the missing-data-root db suppression on state, not the flag`

### QA-8 (HIGH, harness) — reviewed QA's already-committed fix, kept it, checked for other instances

QA's finding: `make_fake_venv` symlinks the *discovered* venv's
site-packages, and in a worktree that venv is the operator's main
checkout's `.venv`, whose editable install points at the main checkout's
`src/` — a different branch with no `ensure.py`. Every DB assertion in
every driver was reachable in a state where it could pass or fail for
reasons having nothing to do with the code under review. QA's fix (one
line in `tests/cli/lib.sh`: `export PYTHONPATH="$CLI_TEST_REPO/src..."`,
prepended so a driver that deliberately shadows a module still wins) was
already committed (`ca6b43a`) before this round started.

**Reviewed and kept, no changes needed.** Checked the rest of the
harness for other places that resolve `arail` against the wrong tree:
two other direct `$REAL_VENV/bin/python` invocations exist
(`cli_test_make_world`'s inline `PYTHONPATH="$CLI_TEST_REPO/tests"`
override, and the stub-uvicorn spawn) — both invoke scripts
(`world_bundle_builder.py`, `stub_uvicorn_serving.py`) that import only
the Python standard library, never `arail`, so neither is exposed to
QA-8's blind spot regardless of which venv `REAL_VENV` resolves to.
`status.sh`'s own `source .venv/bin/activate && python3 -c ...`
collector invocations inherit the shell's exported `PYTHONPATH`
unchanged (`activate` only prepends `PATH`), so QA's fix at the top of
`lib.sh` covers every DB-relevant subprocess in the harness. No further
harness changes made.

### What round 4 did NOT do

Did not touch `lab/` (confirmed empty diff after every commit). Did not
run `install.sh`/`start.sh` against the operator's real lab, did not
seek authorization to. Did not use a bare `git stash`. Did not write
through `make_fake_venv`'s `.venv/lib` symlink. Did not re-verify QA's
findings that "held" (fuzz corpus, collector-kill, ledger tampering,
seamless/six-roots, concurrency, defect-B honesty, secrets) — the
coordinator's instruction was explicit not to redo any of it, and I
didn't. Did not chase the reported `instance.env` mtime anomaly — noted,
not reproducible, likely a concurrent session per QA's own honest
assessment; kept using explicit paths as instructed.

### Full regression sweep after round 4

```
PYTHONPATH=src python3 -m pytest tests/test_dbspec_ensure.py \
  tests/test_data_dirs_resolve.py tests/test_data_dirs_resolve_shell_parity.py \
  tests/test_provisioning.py tests/test_qa_provisioning_generalize.py \
  tests/test_pkb_semantic_backend_absent.py tests/test_win_condition_honest_failure.py \
  tests/test_seamless_db_integration.py tests/test_cli_status.py tests/test_pkb.py \
  tests/test_pkb_gate.py tests/test_pkb_retrieve_for_agents.py tests/test_dbspec_spec.py \
  tests/test_qa_ensure_write_free.py tests/test_qa_ensure_concurrency.py \
  tests/test_qa_ensure_statement_safety.py tests/test_qa_retrieval_honesty.py -q
```
779 passed, 2 skipped (both the standing, unchanged no-`.venv` self-skip
reasons). `bash -n` clean on every modified shell script.
`git diff --stat -- lab/` empty after every commit — zero `lab/`
contamination held across all four rounds. No bare `git stash` used.

### Final state, round 4

- **4 additional commits**: `07080fe` (QA-1), `43a9cde` (QA-5/6/7),
  `59947f4` (ASK-6), plus this BUILD_LOG update — 28 commits total
  across four rounds. QA-8's fix was already committed by QA
  (`ca6b43a`) and required no further change, only review.
- **All four blocking findings plus ASK-6 fixed and verified**: QA-1 by
  the full local suite (695 tests, including the previously-failing
  system-interpreter cases now passing) plus the header-read's
  correctness argument checked explicitly (the WAL-checkpoint-on-close
  dependency); QA-5/6/7 by the QA test suite plus a live `doctor` run
  showing the previously-invisible second root; ASK-6 by the same
  extracted-doc-builder verification technique used throughout this
  sprint, reproducing both the bug (before) and the fix (after)
  side-by-side.
- **Agreement with QA's suggested fix for QA-1: yes, applied as given.**
  I verified the one property that would have made it wrong (staleness
  against an unflushed WAL) rather than trusting "verified equivalent"
  at face value, and confirmed the module's existing connection-close
  discipline already makes it safe — documented that dependency
  explicitly so it can't be silently broken by a future edit.
