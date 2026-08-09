# Review: Compiled-KB bootstrap (QA-6)

**Date:** 2026-08-09
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `7a663ae`
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at `6bef72c`
**Diff reviewed:** `6bef72c..7a663ae` (8 commits)
**Tests run by reviewer:** `PYTHONPATH=src python3 -m pytest tests/test_compiled_kb.py
tests/test_compiled_kb_bootstrap.py tests/test_pkb_gate.py
tests/test_pkb_retrieve_for_agents.py tests/test_world_mount.py
tests/test_world_mount_auto_approve.py tests/test_compiled_kb_sweep_prune.py -q`
→ **80 passed**. The builder's claim reproduces.

## Verdict: BLOCK

The security half of this sprint is good work and I found no way to widen the
gate. The sprint is blocked on the *convenience* half — specifically, the
mechanism is hooked to a code path the operator does not use, and the backfill
verb cannot reach five of the six roots it was written to fix. The win
condition ("Buddy can read the knowledge base") is not met on the operator's
machine by any documented single command. Two of the three required actions are
small.

---

## 1. The scope invariant — HOLDS

Read `compiled_kb.auto_approve_world_terms` line by line rather than trusting
test names. Both conditions are enforced, and the enforcement is structural
rather than filter-based, which is the right shape:

- The candidate path is **constructed**, never accepted: the loop iterates over
  `bundle_slugs` (derived from `terms.json`) and synthesizes
  `f"sources/world-{world_slug}/terms/{slug}.md"`. There is no path input from
  the filesystem side at all. Condition (1) and condition (2) are therefore the
  *same* operation — a path cannot satisfy one without the other. This is
  stronger than the architecture asked for.
- `world_slug` is regex-gated `^[a-z0-9][a-z0-9-]*$` before use.
- `_safe_term_slug` (`[^a-z0-9-]+` → `-`, `.strip("-")`, `[:80]`) is verified
  byte-identical to `world_mount._TERM_SLUG_SAFE_RE` (`world_mount.py:1146` vs
  `compiled_kb.py:581`). Parity confirmed, and the builder documented the
  requirement in a comment.
- Every write still goes through `approve()`, so `_clean_rel`'s traversal
  rejection, `_is_candidate`, `is_file()`, and sha256 stamping apply unchanged.
  No second write path was introduced.

Attacks I actually walked:

| Attack | Result |
|---|---|
| `slug: "../../../notes/personal"` | `.` and `/` are outside `[a-z0-9-]` → collapses to `-notes-personal` → `strip("-")` → `notes-personal` → path is `sources/world-<slug>/terms/notes-personal.md`, which does not exist. Not approved. |
| `slug: "/etc/passwd"` | → `etc-passwd`, same containment. |
| Hand-dropped `terms/not-in-bundle.md` | Unreachable: the loop never enumerates the directory. Tested. |
| Slug collision (two terms → same sanitized slug) | Same single file approved once. Harmless. |
| Unicode slug (`"café"`) | → `caf` (non-ASCII stripped). Deterministic and identical to what `world_mount._write_term_pages` used to name the file, so it either matches the real staged page or matches nothing. No normalization skew between writer and approver because they share the sanitizer. |
| macOS case-insensitive FS (`terms/FOO.md`, bundle slug `foo`) | `is_file()` succeeds, `foo.md` gets approved; but `pkb.search`'s approved-set intersection uses the rglob-reported real case `FOO.md`, so the entry never matches. Fails **closed**, not open. |
| Symlink in `terms/` whose name is in `terms.json` | `is_file()` follows it and `approve()` would hash the target. See [ASK-4]. |
| Empty / malformed / non-dict `bundle_terms` | `[]`, no write. Tested. |

**No BLOCK findings here.**

## 2. debt-finance stays gated — HOLDS

`notes/`, `inbox/`, `conversations/`, `agents/**`, `sources/scout/`,
`sources/seeds/`, `research/`, `skills/` are unreachable by construction (see
above) — not by a deny-list that could be incomplete. The `_is_candidate` and
`_kind_of` classifiers are untouched. I confirmed by reading the matching
logic, not the test names: there is no filesystem enumeration anywhere in the
auto-approval path.

The one thing I want QA to still prove is the *retrieval*-level assertion the
architecture specified as S1(c)(d), which the builder's tests do not cover:
plant a personal note with a unique token, bootstrap, then assert
`search_for_agents("<token>") == []` **and**
`retrieve_for_agents("<token>")["empty_reason"] == "no_match"` — i.e. the
search ran and still did not surface it. The builder's
`test_never_reaches_notes_inbox_or_agent_output` proves only the approval-set
half. That is a QA gap, not a builder defect.

## 3. Fail-closed — HOLDS

- `manifest_present()` returns False on missing / unreadable / truncated /
  non-dict-non-list. Five tests, including truncated JSON and `null`. Correct.
- `gate_state()` derives `state` in the specified order and its outer
  `except` returns a complete dict with `state="unbootstrapped"`. Verified
  there is no branch producing a superset of the manifest — `approved_paths`
  and `_approved_map` are untouched by this diff, and `gate_state` only ever
  *narrows* (`approved_paths(root) if present else set()`).
- The bootstrap path is not an error path: `bootstrap()` has a total
  try/except returning `skipped_reason`, and each failure sub-case
  (`FileNotFoundError` on catalog, generic resolve failure, missing root) sets
  a reason and still returns a well-formed dict. `mount()`'s step 3.5 is
  wrapped and logs a warning; `test_mount_still_succeeds_if_auto_approve_raises`
  proves a mount survives it.
- Atomicity: `_save_json` is unchanged `tmp.write_text` → `tmp.replace(path)`.
  `replace` is atomic within a filesystem, so a crash mid-write leaves the
  previous manifest intact. One residue note: a crash between write and replace
  leaves an `approved.json.tmp`; nothing reads `.tmp`, and `_is_candidate`
  excludes `compiled/`, so it is inert. Acceptable.
- Corrupt manifest + `bootstrap` → `approve([])` reads `_approved_map` as `{}`
  and overwrites the corrupt file with an empty manifest. Fail-closed and
  self-healing. Correct.

**No BLOCK findings here.**

## 4. Sticky revocation — HOLDS, with a trap

Mechanism verified: `revoke()` adds to `unapproved.json`,
`auto_approve_world_terms` skips any path in that set, `approve()` discards
from it. `prune_dangling` does **not** touch `unapproved.json` — I checked this
specifically, because if it did, a World switch (which sweeps other Worlds'
staged dirs and dangles their approvals) would have permanently poisoned every
term of the World you switched away from. It doesn't. Good.

Survives a bootstrap re-run too: `bootstrap()` delegates to
`auto_approve_world_terms`, which consults the same set. Tested
(`test_sticky_revocation_survives_remount`,
`test_explicit_approve_after_revoke_persists_across_remount`).

The trap: `revoke_auto()` calls `revoke()`, so the architecture's documented
one-step rollback marks **every** auto-approved path sticky. There is no
`./arailctl pkb approve` verb and no un-stick command, so "roll back the
sprint" is a one-way door whose only exit is 351 individual clicks on `/dac`.
See [ASK-1].

## 5. Empty-state contract — HOLDS

`search_for_agents` is now `retrieve_for_agents(...)["hits"]`. Shape is
unchanged for all nine callers; `tests/test_pkb_gate.py` is untouched and
passes. `retrieve_for_agents`'s four `empty_reason` values are each tested,
and the internal-error branch is monkeypatch-tested to fail closed and loud.

`gate_state(cheap=True)` genuinely does not walk the tree —
`test_gate_state_cheap_skips_pending_walk` monkeypatches `pending_count` to
raise. Correct. One perf note: `cheap=True` still calls `dangling_paths()`,
which `stat()`s every approved path — 351 stats per Buddy turn on the `ai`
root. That is not an `rglob` and will not show up as a hang, but it is not
free, and the architecture's `< 5 ms` threshold is untested. See [ASK-3].

---

## BLOCK findings

### [BLOCK-1] The hook is on the path the operator does not take

The builder was right to stop and ask rather than improvise, and the ruling is:
**extend the hook to `swap()`. `swap` is not out of scope; it is the primary
path.** Evidence, from the code rather than from intuition:

```
src/arail/portal/world_routes.py:452
    rec = wm.swap(catalog) if wm.current_mount() is not None else wm.mount(catalog)
```

The World switcher UI calls `mount()` **only on a lab that has never mounted a
World**. Every subsequent World change — the operator's stop-and-switch
workflow, which the workspace record identifies as how they actually run
Worlds — goes through `swap()`. `_reseal_and_swap` (`world_routes.py:547`,
also `librarian_routes.py:155`) routes the term-editor and world-forge flows
through `swap()` as well, meaning **a freshly-edited-and-resealed World never
gets its new terms auto-approved either**.

So as shipped: the mount hook fires approximately once per lab, ever. The
sprint's forward-looking guarantee ("every future World is correct without
operator action") is false for every path except a first mount.

`swap()` already does the work that makes the hook safe — `load_bundle`,
`verify_seal`, `SealMismatch` refusal, `check_compat`, `check_categories`,
`_stage_files`, `_sweep_other_worlds`, `_write_record` — so this is the same
try/except block after `_write_record(record, dd)` at `world_mount.py:1693`,
with `seal.computed_sha256` in hand. Roughly ten lines plus a test mirroring
`test_mount_auto_approves_all_term_pages`.

**Required:** add step 3.5 to `swap()`; add a test that a swap into a second
bundle approves the incoming World's terms; update ARCHITECTURE.md's data-flow
diagram to name both entry points.

### [BLOCK-2] The backfill cannot reach five of the six roots

The sprint exists to fix six PKB roots. What shipped can reach one of them.
`./arailctl pkb bootstrap` resolves `PKB_ROOT` per-process from `arail.config`,
and `scripts/install.sh` calls it for the root lab only. `--all-instances` and
`--world <slug>` were deferred, so backfilling `ai`, `debt-finance`, `finance`,
`qukaizen`, and `video-games` requires the operator to reconstruct each
instance's env pack by hand — a procedure that appears in no doc, including the
`docs/cli.md` section this sprint added.

I accept the builder's other deferrals. I do not accept this one, because it is
the difference between "the bug is fixed" and "the bug is fixable by someone
who reads the source." `scripts/lib/instances.sh` and `lab/instances/` already
carry the registry; the Python side needs to enumerate instance roots and loop
`bootstrap(root)` per root, reporting per-root `skipped_reason` (the
architecture already specified this behavior).

**Required:** implement `--all-instances` and `--world <slug>`, and document
in `docs/cli.md` how a multi-World lab gets fully backfilled.

### [BLOCK-3] `approved_by="world-seal:<sha12>"` is not a seal in the bootstrap path

`mount()` passes `seal.computed_sha256` — a real, verified seal. `bootstrap()`
passes `sha256(WORLDS_DIR/<slug>/terms.json bytes)`, computed after
`resolve_world_bundle()`, which **does not call `verify_seal`** (I read it:
`build/world_corpus.py:65-84` is a bare `json.loads` of `terms.json` and
`spec.json`). The BUILD_LOG's claim that this "matches what `verify_seal` would
compute at a real mount" is incorrect — the bundle seal covers the whole
bundle, not `terms.json` alone.

Two consequences:

1. **Provenance is wrong.** Identical content approved by two paths carries two
   different `world-seal:` values, and one of them refers to no seal. The
   `auto: True` audit trail the architecture depends on for revocability is
   therefore misleading about *what was verified*.
2. **The stated invariant is weakened in the bootstrap path** from
   "seal-verified `terms.json`" to "whatever `terms.json` is in the catalog."
   `docs/cli.md` as written ("present in the seal-verified bundle's
   `terms.json`") overstates what the code does.

I am **not** treating this as a privilege escalation: an attacker who can edit
`WORLDS_DIR/<slug>/terms.json` and drop a matching file under `terms/` can
already edit `approved.json` directly. The manifest is an unprotected local
file; the gate defends against agent-initiated content promotion, not against
an attacker with lab write access. But shipping a provenance string that
asserts a verification that did not occur is exactly the kind of quiet untruth
this gate exists to prevent.

**Required (choose one):** either call `verify_seal` on the catalog bundle in
`bootstrap()` and pass the real `computed_sha256`, or stamp
`approved_by=f"world-terms:{sha12}"` and correct the `docs/cli.md` wording to
say what is actually checked.

## ASK findings (fix now or file as tickets)

- **[ASK-1] The rollback is one-way.** `revoke_auto()` makes every auto path
  sticky, and nothing un-sticks it short of per-item re-approval in the UI.
  Either exempt `revoke_auto` from the sticky write (it is a mechanism
  rollback, not a per-term human judgment), or add
  `./arailctl pkb bootstrap --force` that clears `unapproved.json` entries
  carrying no explicit-revocation provenance. Also note `./arailctl pkb revoke
  --auto` from ARCHITECTURE.md's "Rollback" section was never wired —
  `revoke_auto()` is Python-only today.
- **[ASK-2] `revoke()` does not normalize through `_clean_rel`.** It writes
  `str(raw_rel).replace("\\","/").strip().lstrip("/")` into `unapproved.json`.
  A caller passing a `./`-prefixed or `..`-containing rel writes a junk sticky
  entry that never matches anything. Fails harmless (toward *more* approval,
  which is why it is an ASK and not a BLOCK), but the two path normalizers
  should be one function.
- **[ASK-3] `gate_state(cheap=True)` still stats every approved path** via
  `dangling_paths()`. Add the architecture's `< 5 ms` assertion on a
  351-approval root, or drop `live_count` from the cheap variant.
- **[ASK-4] No `is_symlink()` guard** on the approval read. A symlink under
  `terms/` whose name appears in `terms.json` would be approved and hashed
  through to its target. Requires local write access to exploit and the
  indexer already follows symlinks, so this is pre-existing surface — but
  `approve()` is the right chokepoint to add `full.is_symlink() → skip`.
- **[ASK-5] `approve([])` rewrites `rejected.json` from `_rejected_set()`.**
  If `rejected.json` is corrupt, the bootstrap silently replaces it with an
  empty set and previously-dismissed items resurface in the review queue. Not
  a security issue (it widens the *queue*, not the approved set), but it is a
  silent data loss on a corruption path.
- **[ASK-6] Two weak test assertions.**
  `test_traversal_paths_never_approved` asserts `X == set() or all(...)`, which
  passes under both outcomes and proves little; assert the exact expected set.
  `test_sentinel_unreadable_treated_as_present` documents that it cannot
  actually exercise the contract on POSIX and asserts a subset instead — the
  real test is monkeypatching `Path.exists` to raise `OSError`.

## INFO

- `bootstrap()` picks the **first** `sources/world-*` directory alphabetically.
  Post-`_sweep_other_worlds` there should only ever be one, so this is correct
  today — but it is an undocumented assumption in a function whose whole job is
  repairing roots that are in an unexpected state. One comment would fix it.
- `bootstrap --dry-run` reports a count derived from `terms.json` alone, before
  the existence / `rejected` / `unapproved` filters. It will over-report
  relative to what a real run approves. Harmless (writes nothing) but the flag
  is advertised as "print the exact path list."
- `scripts/install.sh` change is correct and genuinely non-fatal (`|| rc=$?`,
  both branches print). `bash -n` clean.
- The builder's `python-dotenv` environment note is real and worth carrying to
  QA: this worktree has no `.venv`, and tests only run under
  `PYTHONPATH=src python3`.

## Test coverage assessment

47 new cases across four files, all passing, plus `test_pkb_gate.py` (13) and
`test_world_mount.py` (12) unchanged and green — the back-compat contracts held.

Failure-mode table coverage: 11 of 17 rows have a corresponding test. Uncovered
rows, all of which trace to deferred scope rather than to missing tests for
shipped code: `compiled/kb/` unwritable during mount (F3), `ARAIL_APPROVED_ONLY=off`
banner, `pending_count` perf benchmark, bulk-approve race, `--all-instances`
unreadable root, world-corpus build behavior change. Genuinely missing for
*shipped* code: F3 (unwritable `compiled/kb/` during mount) and the S1(c)(d)
retrieval-level debt-finance assertion.

## Performance assessment

No benchmark was run. None of the three thresholds in the architecture
(`gate_state(cheap=True) < 5 ms`, `bootstrap` on `ai` `< 3 s`, `mount()`
regression `< 10%`) has a number behind it. `retrieve_for_agents` adds one
`gate_state(cheap=True)` per agent retrieval, which is one manifest read plus
N stats. Assign to QA rather than blocking on it.

## Tech debt delta

Matches the architecture's prediction, plus one item it did not anticipate:

- **Predicted and incurred:** `auto: True` provenance class; third manifest
  file `unapproved.json` (the stated ceiling — a fourth forces a schema-versioned
  state file); the transitional `retrieve_for_agents` / `search_for_agents`
  pair; the sentinel-file convention (documented in `docs/cli.md`, as required).
- **Unanticipated:** a fourth `_safe_term_slug` copy now exists
  (`world_mount`, `world_corpus`, `compiled_kb`, and DaC's own). The copies are
  currently identical and the builder documented the parity requirement in a
  comment, but nothing enforces it — a one-character divergence silently
  un-approves an entire World's terms with no error anywhere. File as a
  follow-up: single sanitizer with a parity test.
- **Repaid:** the silent-zero gate, only partially — retrieval is repaired, but
  every surface that would *tell a human* about it (doctor, `/dac`, lab brief,
  `/api/pkb/review`, Buddy's own note) is deferred.

## Ruling on the deferrals

**Acceptable to defer:** `promote_bulk` + the `/dac` bulk-select UI; the goal
drafter, researcher, and `lab_brief` wiring; the `ARAIL_APPROVED_ONLY=off`
banner. None are load-bearing for the win condition and each is a real,
independent surface. Log as follow-ups.

**Not acceptable:** `swap()` (BLOCK-1) and `--all-instances` (BLOCK-2), for the
reason stated — without them, the fix does not reach the operator's lab.

**On the win condition, honestly:** "Buddy can read the knowledge base" *is*
mechanically achieved by this diff — once `approved_paths()` is non-empty,
`search_for_agents` returns hits and `lab_brain` needs no edit to benefit. The
caller wiring is about *legibility when the gate is empty*, not about
retrieval. So the deferral of §6 does not sink the sprint. What sinks it is
that on this operator's machine, after this diff, `approved_paths()` is still
empty on five of six roots and will stay empty through every World switch.

## Required actions before merge

1. **[BLOCK-1]** Hook `auto_approve_world_terms` into `world_mount.swap()`
   after `_write_record` (`world_mount.py:1693`), with a test; update
   ARCHITECTURE.md's data flow to name `swap` alongside `mount`.
2. **[BLOCK-2]** Implement `./arailctl pkb bootstrap --all-instances` and
   `--world <slug>` with per-root `skipped_reason`; document the multi-World
   backfill procedure in `docs/cli.md`.
3. **[BLOCK-3]** Either verify the seal in `bootstrap()` or rename the
   provenance stamp and correct the `docs/cli.md` "seal-verified" claim.
4. Resolve or ticket [ASK-1] (one-way rollback) — my preference is to fix it
   now; it is a trap with no exit.
5. Ticket [ASK-2] through [ASK-6] and the `_safe_term_slug` parity debt.

Re-review scope on return: the `swap` hook and its test, the multi-root
bootstrap, the provenance stamp. The scope invariant does not need
re-litigating unless `auto_approve_world_terms` itself changes.
