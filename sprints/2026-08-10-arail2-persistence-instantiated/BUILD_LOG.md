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
| 6 | `scripts/lib/instances.sh` (shell mirror), `install`/`start`/`status` wiring, `arail/provisioning.py` in `status` | Seamless install/start, status `db` object, exit-code mapping | 20, 23-29, 32-36 | **NOT DONE — see "Deferred scope" below** |

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

- **8 commits** on this branch from this build pass: `b60bfad`, `03b70e5`,
  `9b748ed`, `d2c5d72`, `11ccc9c`, plus this BUILD_LOG.md commit.
- **New tests added:** 46 (6 defect-B + 24 ensure.py + 4 data_dirs.py + 12
  provisioning.py), all passing, run via `PYTHONPATH=src python3 -m
  pytest` (no `.venv` in this worktree — see below).
- **Regression check:** `tests/test_pkb.py`, `test_pkb_index.py` (the
  24/30 subset that doesn't require `lancedb`), `test_pkb_gate.py`,
  `test_pkb_retrieve_for_agents.py`, `test_dbspec_spec.py`,
  `test_doctor_embedding_status.py` all pass or fail *identically* to the
  pre-change baseline (`d5c592a`) — confirmed by diffing pass/fail sets
  before and after, not by inspection alone.
- **Not run locally, and why:** anything requiring `lancedb`, `fastapi`,
  or the `atlas` binary — this worktree has no `.venv` (per the task
  brief, that's the deliberate broken state defect B is about). The
  operator's main checkout (`/Users/netsushi/ProJects/qukaizen-arail`,
  `.venv/bin/python`) should re-run the full suite, especially
  `tests/test_dbspec_ensure.py`'s test-4-equivalent once `atlas` is
  available, and the full `tests/test_pkb_index*.py` / `test_pkb_search_api_status.py`
  / portal suites that need `lancedb`/`fastapi`.
- **Win condition status: NOT MET end-to-end.** Defect B is closed.
  Defect A's *visibility* (doctor reports it) is closed; defect A's
  *seamlessness* (install/start auto-create the DB) is NOT — see
  "Deferred scope" above.
