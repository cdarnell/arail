# Architecture: KB incremental persistence

**Date:** 2026-05-01
**Spec:** [VISION.md](./VISION.md) at commit `4b617f2`
**Sprint:** [SPRINT.md](./SPRINT.md)
**Branch:** `qukaizen/arail-kb-incremental-persistence`

## Restatement

Today the chat-RAG path (`build_chat_messages` →
`retrieve_chat_context` → `pkb.search` →
`_semantic_search` → `VectorIndex.search` over `pkb_pages`) reads from
a LanceDB table that is built by a wholesale `index_all()` over every
file under `lab/pkb/`. Agent write helpers
(`write_agent_research`, `write_agent_experiment`,
`write_agent_experiment_rollup`, `write_agent_synthesis`,
`write_agent_recommendation`, `write_teacher_qa` —
[src/arail/pkb.py:534-654](../../src/arail/pkb.py#L534)) drop markdown
on disk but never touch the index, so the chat tab keeps returning
"nothing useful" until the operator manually triggers a full rebuild.
This sprint closes the loop by making every write helper push a
**single-row upsert** into the existing `pkb_pages` LanceDB table
through an in-process debouncer, so a Researcher write becomes
findable in chat in under 10 seconds with no human action and no new
service. Cold start with an existing schema-compatible table reuses
it; only a missing-or-mismatched table triggers a full rebuild.

## Assumptions

- **The on-disk corpus is small.** PKB today is hundreds-to-low-thousands
  of files; one row per file is correct (no per-chunk splitting needed
  in this sprint). Confirmed by reading
  [src/arail/pkb.py:395-425](../../src/arail/pkb.py#L395) — `index_all`
  builds one row per file with the first 4 KB embedded.
- **The embedder is deterministic and local.** `hash_embedding` at
  [src/arail/vector_index.py:35](../../src/arail/vector_index.py#L35)
  is a SHA1-based 128-dim projection — no torch, no
  sentence-transformers, no model weights, no network. Airgapped-safe
  by construction. We reuse it; this sprint MUST NOT introduce a new
  embedder.
- **LanceDB ≥ 0.13.0 is a hard dep.** Declared in
  [pyproject.toml:32](../../pyproject.toml#L32). The `available()` guard
  in `vector_index.py` is defensive for stale envs and stays.
- **Single Python process.** The portal is a single uvicorn process;
  the researcher loop, the buddy loop, and the chat handler all share
  it. No multi-process writers across one PKB. (Sub-process tests of
  the CLI are the exception — they run, exit, and the next process
  reads the on-disk LanceDB.)
- **LanceDB handles its own on-disk durability.** We do not need to
  fsync or transaction-wrap; LanceDB's transaction log under
  `pkb_pages.lance/_transactions/` is the durability primitive.
  Verified: SPRINT.md notes `lab/pkb/.cache/lancedb/pkb_pages.lance/`
  contains transactions + version manifest already.
- **`asyncio.get_running_loop()` is available at write-call time when
  the call comes from the portal or researcher.** Buddy/SRE write paths
  (`state.json`, `dreams/<date>.md`) are not in scope for this sprint
  — see § Pip and SRE wiring.
- **No watchdog/file-watcher in scope.** The win condition is
  closed-loop on the helper boundary; a watcher would be a strictly
  larger surface (handles for non-helper writes too) and the visionary
  explicitly excluded heavy components. Helper-only is the wedge.

## Data flow

```
┌─────────────────┐                     ┌────────────────────────┐
│  Researcher     │── write_agent_*() ──▶  pkb.write_agent_*     │
│  (and portal    │                     │  ([src/arail/pkb.py:   │
│  teacher write) │                     │   534-654])            │
└─────────────────┘                     └─────────┬──────────────┘
                                                  │
                                       (1) markdown to disk
                                       (2) pkb_index.schedule_upsert(path)
                                                  │
                                                  ▼
                                  ┌─────────────────────────────────┐
                                  │  arail.pkb_index (new module)   │
                                  │                                 │
                                  │  in-process coalescer:          │
                                  │    pending: set[Path]           │
                                  │    lock: threading.Lock         │
                                  │    timer: threading.Timer       │
                                  │      (debounce 2s)              │
                                  │                                 │
                                  │  on flush():                    │
                                  │    snapshot pending under lock  │
                                  │    for each path:               │
                                  │      build row {path, name,     │
                                  │      mtime, source_kind, vec}   │
                                  │    table.merge_insert(           │
                                  │      "path").when_matched_      │
                                  │      update_all().when_not_     │
                                  │      matched_insert_all()       │
                                  │      .execute(rows)              │
                                  └────────────┬────────────────────┘
                                               │
                                               ▼
                          ┌──────────────────────────────────────┐
                          │ LanceDB pkb_pages table              │
                          │ lab/pkb/.cache/lancedb/              │
                          │   pkb_pages.lance/                   │
                          └──────────────┬───────────────────────┘
                                         │
                       (chat path, unchanged surface)
                                         │
              ┌──────────────────────────▼──────────────────────────┐
              │  retrieve_chat_context                              │
              │   ([src/arail/lab_brain.py:387])                    │
              │  → pkb.search                                       │
              │   ([src/arail/pkb.py:498])                          │
              │  → _semantic_search                                 │
              │   ([src/arail/pkb.py:448])                          │
              │  → VectorIndex.search (pkb_pages)                   │
              └─────────────────────────────────────────────────────┘
```

## Schema — exact LanceDB table layout for `pkb_pages`

**Today** ([src/arail/pkb.py:395-425](../../src/arail/pkb.py#L395)) the
table is created by `index_all()` from rows shaped:

```python
{ "path": str,        # relative to pkb_root, e.g. "agents/research/2026-05-01_x_report.md"
  "name": str,        # basename
  "vector": list[float] }  # hash_embedding(name + path + first 4 KB body), dim=128
```

LanceDB infers the Arrow schema from the first batch on
`create_table(..., mode="overwrite")` (see
[src/arail/vector_index.py:162](../../src/arail/vector_index.py#L162)).
There is no SQL-level migration in scope.

**This sprint** widens the row to:

| Column        | Type            | Why                                                                         |
|---------------|-----------------|-----------------------------------------------------------------------------|
| `path`        | string (PK)     | Relative path from `pkb_root`. Identity for upsert; LanceDB merge key.      |
| `name`        | string          | Basename, kept for read-side compatibility with `_semantic_search`.         |
| `vector`      | fixed_size_list<float, 128> | Same `hash_embedding` projection as today. **Unchanged.**       |
| `mtime`       | double          | `os.path.getmtime(path)` at upsert time. Used for staleness detection on cold start. |
| `source_kind` | string          | One of `"agent_research" \| "agent_experiment" \| "agent_rollup" \| "agent_synthesis" \| "agent_recommendation" \| "teacher_qa" \| "user"`. Lets future filtering (e.g. "draft/published") attach without another migration. |

`mtime` and `source_kind` are **additive**. They are written by the
new upsert path and by a refreshed `index_all()`. They are read only
by the schema/staleness check on cold start and by future
draft/published filtering — `_semantic_search` ignores them.

**Migration on cold start:** `pkb_index.ensure_ready()` opens the
table and inspects its schema (Arrow `Table.schema`). If `path` and
`vector` are present **and** `mtime` and `source_kind` are present
**and** the dim matches, reuse. Otherwise drop the table and call
`index_all()` once. This is one-time, idempotent, and bounded — the
corpus is small and the rebuild already exists. We do **not** ship a
runtime migrator; the rebuild *is* the migration.

`agent_id` is **not** added in this sprint (we don't need it to close
the loop and YAGNI prevents over-fitting the schema). A `published`
boolean is **not** added — see § Draft/published flag.

## Upsert semantics

**Definition.** A call to `pkb_index.schedule_upsert(path)` is a
promise that within the debounce window the LanceDB row whose
`path` column equals `str(path.relative_to(pkb_root))` will reflect
the on-disk file at that path: replaced if it existed, inserted if
it did not, removed if the file no longer exists at flush time.

**Mechanism.** True upsert via LanceDB's `merge_insert` API
(`table.merge_insert("path").when_matched_update_all().when_not_matched_insert_all().execute(rows)`).
This is a single LanceDB transaction per flush. Available since
LanceDB 0.5; we require ≥ 0.13.0 so it's safe to assume.

**Compatibility shim.** If `merge_insert` is unavailable on a
pinned-down env (the same defensive posture
`vector_index.py:_existing_tables` takes for `list_tables`), fall
back to delete-then-add per row inside one transaction:
`table.delete(f"path = '{escaped}'")` then `table.add([row])`. Both
paths are in `pkb_index._flush()` behind a feature probe.

**Keying.** One row per file, keyed on the relative path string.
**No chunking** in this sprint — the embedding input cap (`text[:4096]`)
already trims long files; chunk-level granularity is a follow-up
that pairs with a real embedder, not the hash projection.

**File deletion.** When a flush snapshots a pending path and
`(pkb_root / path).exists()` is False, that path is enqueued as a
**delete** (`table.delete(f"path = '{escaped}'")`), not an upsert.
This avoids stale rows when an agent rewrites a rollup file by
unlink-then-write or when an operator manually removes a file
between the helper call and the flush. Path-deletion via the helpers
themselves is not currently a code path; this is a forward-compat
guarantee, not a feature.

**Path normalization.** Paths are normalized to POSIX-style
relative-from-pkb_root (`p.relative_to(root).as_posix()`) before they
are used as the merge key. Mixed separators on Windows would
otherwise create duplicate rows for the same file.

**Idempotency.** Two `schedule_upsert(path)` calls inside the
debounce window collapse to one row in `pending` (it's a `set`); the
flush does one merge per unique path.

## Trigger surface

**Primary: explicit `pkb_index.schedule_upsert(path)` calls inside
the write helpers.** No watchdog. No filesystem watcher. No new
thread besides the single debounce timer.

Justification:
- **Complexity floor.** A watchdog adds (a) a new dep, (b) a daemon
  thread that must be torn down on portal shutdown, (c) noise from
  editor/temp/.swp files, (d) handling for atomic-rename writes vs
  in-place writes, (e) per-OS quirks (FSEvents on macOS, inotify on
  Linux, polling on Windows). The visionary explicitly forbade heavy
  components; helper-trigger is the smallest thing that works.
- **Failure detection.** If a helper forgets to call
  `schedule_upsert`, the operator notices because the chat answer
  doesn't include their content; we surface a clear escape hatch
  (`POST /api/pkb/reindex` already exists via `index_all()` and
  `pkb compile` from the CLI) and an activity-log line on every flush
  (`pkb_index: upserted 3 rows in 12 ms`) so missed calls are visible
  in the activity stream.
- **Recovery.** If the in-process timer is killed mid-flight (process
  crash mid-write), the next process boot detects via mtime-vs-table
  scan in `ensure_ready()` (described in § Cold-start) that some
  files are newer than the table and re-upserts them. This makes the
  durability test pass even with crashes.

**Wrapper helpers** to keep the call sites tidy. Every write helper
in `pkb.py` ends with:

```python
try:
    from arail.pkb_index import schedule_upsert
    schedule_upsert(path)
except Exception:
    pass  # never break the file write on index failure
```

Wrapped exactly once per helper (six call sites:
`write_agent_research`, `write_agent_experiment`,
`write_agent_experiment_rollup`, `write_agent_synthesis`,
`write_agent_recommendation`, `write_teacher_qa`).

**Debounce timer.** `threading.Timer(debounce_sec, _flush)` started on
the first `schedule_upsert` after a quiet period; subsequent calls
inside the window cancel and re-arm. `LAB_PKB_UPSERT_DEBOUNCE_SEC`
env, default `2.0`. Win-condition budget is 10 s; 2 s leaves
breathing room for the `merge_insert` transaction (~tens of ms on a
small table) and for the chat poller's grace period.

**Why threading, not asyncio** (the wiki module uses asyncio for its
debouncer): the write helpers are sync functions called from
multiple contexts (the researcher's async loop, the portal's sync
teacher endpoint, the future CLI). A `threading.Timer` works from
any caller without requiring a running loop. This deliberately
diverges from `wiki.schedule_rebuild`'s asyncio pattern; the wiki
debouncer can stay as it is because it's only called from
already-async surfaces.

## Concurrency

**One `threading.Lock`** in `pkb_index._lock` serializes (a) reads of
`_pending`, (b) the timer arm/cancel, (c) the merge-insert call, and
(d) cold-start initialization. The lock is held for the duration of
each flush, which means at most one writer is inside LanceDB at a
time per process. LanceDB itself uses a transaction log for
multi-writer cases but inside a single process we serialize
explicitly so we don't depend on its semantics.

**Two agents write the same file simultaneously.** The set-dedupe
collapses the writes to one entry; the **second on-disk write wins**
(filesystem semantics) and the flush picks up whichever bytes are on
disk at flush time. This matches the existing rollup helper which is
already last-writer-wins on `_rollup.md`. Documented as
expected behavior; no test required to "fail" this scenario, but
there is a regression test asserting that the index reflects the
final on-disk content.

**Process crash during flush.** LanceDB's transaction log either
commits the merge atomically or rolls it back; the next process boot
sees a consistent table. Files newer than the table on cold start
are picked up by `ensure_ready`'s staleness sweep.

**Multiple processes writing to the same PKB.** Out of scope. The
portal is single-process; the CLI is short-lived and exits before
the portal restarts. We do not claim multi-process write safety; if
this becomes a problem (it won't in this sprint), document and
defer.

## Cold-start vs hot-start branching

`pkb_index.ensure_ready()` is called once from the portal startup
hook and lazily on the first `schedule_upsert`. Its job: decide
whether to reuse the existing `pkb_pages.lance` table or rebuild it.

**Detection logic** (executes in this order):

1. `db_path = _vector_db_path(root)` — same path as today
   ([src/arail/pkb.py:391](../../src/arail/pkb.py#L391)).
2. If `not VectorIndex(name="pkb_pages", db_path=db_path)._table()`
   (table missing), call `pkb.index_all(root)` and return. This
   matches the existing lazy-build branch at
   [src/arail/pkb.py:461-464](../../src/arail/pkb.py#L461).
3. Otherwise open the table, check the Arrow schema:
   - required cols `{path, name, vector, mtime, source_kind}` all
     present?
   - `vector` is `fixed_size_list<float, 128>`?
   If either check fails, drop and call `index_all(root)`.
4. Otherwise the table is reusable. Run a **bounded staleness
   sweep**: iterate `_iter_pkb_files(root)`; for each on-disk file,
   compare its `mtime` to the row's `mtime` in the table; if the
   file is newer or absent from the table, enqueue it for upsert.
   For each row in the table whose path no longer exists on disk,
   enqueue it for deletion. Cap this sweep at 200 files per startup;
   anything beyond that triggers a full `index_all` instead. (The
   PKB is currently well below 200 files; the cap exists so a
   pathological growth doesn't quietly slow boot.)

**Hot start (no restart, just a write).** `schedule_upsert(path)` is
the only path. `ensure_ready` is a no-op after first call (gated by
a module-level boolean `_initialized`).

**Backwards compatibility with the legacy table.** Today's table has
`{path, name, vector}`. On the first boot after this sprint lands,
step 3 detects the missing columns and triggers `index_all` once.
The user sees a one-time "Rebuilding KB index for upgrade" activity
log line and the rebuild completes in seconds for the current
corpus size. This is acceptable; no offline migration tool needed.

## Embedding

**Reuse `arail.vector_index.hash_embedding`** unchanged. Same call
site as today
([src/arail/pkb.py:419](../../src/arail/pkb.py#L419)):

```python
hash_embedding(f"{p.name} {rel} {snippet_for_embedding}")
```

Rationale:
- Deterministic — identical input produces identical vectors;
  the staleness sweep can compare without re-reading old vectors.
- Local — no model weights, no torch, no network; airgapped-safe by
  construction.
- Already shipping — every install has it
  ([src/arail/vector_index.py:35](../../src/arail/vector_index.py#L35));
  no install delta.
- Same projection as `index_all()`, so a row written by the upsert
  path is interchangeable with a row written by a full rebuild.

**Embedding cost on the write path.** ~tokens-of-the-first-4-KB
SHA1 hashes per call. Sub-millisecond on any machine. The debouncer
exists to coalesce bursts, not to amortize embedder cost.

`pkb_index` does **not** import or instantiate sentence-transformers
or any other ML embedder. If a future sprint replaces
`hash_embedding` with a real embedder, the `pkb_index` upsert path
gets the upgrade for free because both paths go through the same
function.

## Failure modes

| Failure                                                | Detection                                                                                          | Recovery                                                                                                                                                            |
|--------------------------------------------------------|----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `lancedb` import fails (stale env)                     | `vector_index.available()` returns False; `pkb_index.schedule_upsert` returns early.               | File still on disk. `pkb.search()` regex fallback path ([pkb.py:516-528](../../src/arail/pkb.py#L516)) finds it by exact-token. Activity log warns once per process. |
| Disk full at flush time                                | LanceDB raises in `merge_insert`; caught in `_flush`, logged at WARN.                              | Pending set NOT cleared on failure; next `schedule_upsert` re-arms the timer; eventually flushes once disk frees. Operator-visible via activity log line.            |
| Embedder unavailable in airgapped mode                 | Cannot happen — `hash_embedding` is pure-stdlib (hashlib).                                         | N/A.                                                                                                                                                                |
| Schema mismatch on cold start (legacy table)           | `ensure_ready` step 3 detects missing columns.                                                     | Drop + `index_all` once. Activity log: "Rebuilding KB index for schema upgrade".                                                                                    |
| Process crash mid-flush                                | Next boot's `ensure_ready` finds files with `mtime > row.mtime`.                                   | Staleness sweep enqueues them; debounce flushes within seconds of boot.                                                                                             |
| Helper call from a thread with no running event loop   | Not applicable — `pkb_index` uses `threading.Timer`, not asyncio.                                  | N/A by design.                                                                                                                                                      |
| Two helpers write same file simultaneously             | Set-dedupe in `_pending`; one merge fires.                                                         | Last on-disk write wins. Documented; matches existing rollup behavior.                                                                                              |
| File deleted between helper call and flush             | `(root / path).exists() == False` at flush.                                                        | Enqueue as `table.delete(f"path = '{escaped}'")`. No stale row.                                                                                                     |
| Path traversal (helper called with `../../etc/passwd`) | `path.relative_to(pkb_root)` raises `ValueError`; caught in `schedule_upsert`, logged.             | Reject the upsert. The file write itself is gated by helper-internal `pkb_root / "agents"/...` joins, but we add the guard at the index boundary too.               |
| Bounded staleness sweep cap (>200 files newer)         | Counter in `ensure_ready` exceeds threshold.                                                       | Fall back to full `index_all`. One-time, logged.                                                                                                                    |
| `merge_insert` API not available on pinned LanceDB     | `getattr(table, "merge_insert", None) is None`.                                                    | Fall back to per-row `delete + add` inside one acquired lock. Slower but functionally identical.                                                                    |
| `_pkb_root()` returns a path that doesn't exist        | `pkb.search` already returns `[]` ([pkb.py:509](../../src/arail/pkb.py#L509)); upsert short-circuits. | No-op. Upstream agent loop should have created the dir; if not, the helper's `dest.mkdir(parents=True, exist_ok=True)` will.                                       |

The contract: **the file write to disk is never blocked or
broken by an indexing failure.** Every `schedule_upsert` call in
the helpers is wrapped in `try/except Exception: pass`. The chat
fallback to regex still works in every degraded mode because
`pkb.search` falls back to `_iter_pkb_files` when `_semantic_search`
returns empty.

## Pip and SRE wiring

**Verified by reading the actual code:**

- **Pip / Buddy** (`src/arail/agents/_builtin_buddy.py`) writes only to
  `state.json` ([line 192-193](../../src/arail/agents/_builtin_buddy.py#L192))
  and `dreams/<date>.md` ([line 1151](../../src/arail/agents/_builtin_buddy.py#L1151)).
  The dream file is markdown, lives under `lab/pkb/agents/buddy/dreams/`,
  has YAML frontmatter, and is exactly the kind of thing chat would
  benefit from retrieving ("what did Buddy notice yesterday?").
- **SRE** (`src/arail/agents/_builtin_sre.py`) writes only to
  `state.json` ([line 47](../../src/arail/agents/_builtin_sre.py#L47),
  [line 333](../../src/arail/agents/_builtin_sre.py#L333)) — JSON state
  for cooldowns/fingerprints. **Not chat-shaped** and not in the
  `_PKB_TEXT_SUFFIXES` allowlist
  ([pkb.py:374](../../src/arail/pkb.py#L374)) anyway. Wiring SRE up
  to write narrative postmortems is a future sprint, not this one.
- **Researcher** ([src/arail/agents/researcher.py:735](../../src/arail/agents/researcher.py#L735))
  is the canonical caller — already calls four helpers.
- **Portal teacher endpoint** at
  [src/arail/portal/app.py:6347-6349](../../src/arail/portal/app.py#L6347)
  calls `write_teacher_qa`. Already in scope because it goes through
  the helper.

**Action for this sprint:** Add a single new helper
`pkb.write_buddy_dream(date_str, body, pkb_root=None)` and refactor
`BuddyAgent.dream` ([_builtin_buddy.py:1116-1160](../../src/arail/agents/_builtin_buddy.py#L1116))
to call it instead of `target.write_text(body)` directly. The new
helper is wrapped in `schedule_upsert` like the others. This wires
Pip into the index loop with one call site and zero behavioral
change to the dream content.

**SRE is intentionally NOT wired** in this sprint. Justification:
SRE writes JSON state, not chat-shaped narrative. Wiring it up would
either (a) require SRE to write a new markdown surface (scope creep),
or (b) put `state.json` rows into the chat-RAG index (noise). Defer
to a follow-up that decides whether SRE should produce
human-readable incident notes.

## Test strategy

QA allocation for this sprint: **40% correctness / 25% setup / 20%
security / 15% regression** (per SPRINT.md decisions log). The plan
below distributes accordingly.

### Unit tests — `tests/test_pkb_index.py` (new)

- `test_schedule_upsert_dedupes_same_path` — two calls inside debounce
  window result in one row, one flush.
- `test_schedule_upsert_normalizes_paths` — Windows-style `\\`
  separator is stored as POSIX `/`.
- `test_path_traversal_rejected` — `schedule_upsert(Path("../etc/passwd"))`
  does not insert and does not raise.
- `test_flush_handles_missing_file_as_delete` — schedule a file, then
  unlink before debounce fires, assert no row exists for that path.
- `test_ensure_ready_legacy_table_triggers_rebuild` — pre-populate a
  legacy `{path, name, vector}` table, call `ensure_ready`, assert
  schema is upgraded with `mtime` and `source_kind` columns.
- `test_ensure_ready_compatible_table_reuses` — pre-populate a
  schema-compatible table with N rows, call `ensure_ready`, assert
  no rebuild and row count unchanged.
- `test_ensure_ready_staleness_sweep` — write a file with a newer
  mtime than its table row, call `ensure_ready`, assert the row is
  re-upserted.
- `test_lancedb_unavailable_is_silent` — patch
  `vector_index.available` to return False, call `schedule_upsert`,
  assert no exception, assert helper still wrote the file.

### Integration tests — `tests/test_pkb_index_integration.py` (new)

- **Round-trip** (covers win condition #1): call
  `pkb.write_agent_research("test", "the answer is forty-two")`,
  poll `pkb.search("forty-two")` for up to 10 seconds, assert the
  agent file is in the result and `source == "semantic"`.
- **Restart durability** (covers win condition #2): write via the
  helper, force a flush, simulate a process restart by tearing down
  the in-memory `pkb_index` state and re-importing, assert
  `pkb.search` finds the content **without** rebuilding (assert
  `index_all` was not called — instrument with a counter).
- **Cold-start fallback** (covers win condition #2 fallback): start
  with no `.cache/lancedb` dir, call `pkb.search("anything")`,
  assert `index_all` was called once, assert the table now exists.
- **Concurrent writes**: spawn two threads, each calling a different
  write helper for a different path, both find both contents within
  10 seconds.
- **Hot-write during cold-start**: kick `ensure_ready()` and call
  `schedule_upsert` from another thread mid-rebuild, assert the
  upserted file appears in the final table.

### Regression tests

- `tests/test_pkb.py::test_search_falls_back_to_regex_when_no_lancedb`
  — verify the fallback path
  ([pkb.py:516-528](../../src/arail/pkb.py#L516)) still works after
  this sprint's changes (we're adding to `_iter_pkb_files`'s peer
  paths, not removing).
- Existing `tests/test_vector_index.py` must continue to pass — we
  do not change `VectorIndex.replace` or `.search`.
- Existing `tests/test_wiki.py` must continue to pass — `wiki.py`
  is untouched.

### Performance tests — `tests/test_pkb_index_perf.py` (new, smoke-only)

- **Burst coalescing**: enqueue 50 upserts in a tight loop, assert
  exactly one `merge_insert` call (mock the table) within a 5 s
  window, total wall-clock < 7 s.
- **Single-write latency**: from `schedule_upsert(path)` to the row
  being queryable, p95 ≤ 4 s on a default debounce (2 s).

### Security tests

- **Path traversal at the index boundary** (already in unit list):
  `schedule_upsert(pkb_root / ".." / ".." / "etc" / "passwd")` is
  rejected with no row written and no file read.
- **Airgapped mode**: with `LAB_MODE=airgapped`, end-to-end write →
  search test passes (no network calls; verified by patching
  `socket.socket` to raise on connect during the test).
- **Symlink escape**: a symlink under `lab/pkb/` pointing outside
  the root is read by `_iter_pkb_files` today; we do not regress.
  This sprint's `schedule_upsert` only operates on paths that are
  already inside `pkb_root` (the helpers construct them from
  `_pkb_root()`); no new symlink surface introduced. Documented.
- **Secrets**: `secrets.env` lives at `lab/data/secrets.env`, NOT
  under `lab/pkb/`, so it is out of `_iter_pkb_files`'s scope and
  cannot be indexed. Verified by reading
  [pkb.py:374-388](../../src/arail/pkb.py#L374).

### End-to-end witness scenario (covers win condition #3)

A scripted `tests/test_kb_loop_e2e.py` (or a `pytest -m e2e` lane):

1. Start a real lab process in a temp PKB.
2. Trigger a Researcher write (call
   `write_agent_research("topic-x", "Aerollm reduces latency by 40%.")`
   directly — we are testing the loop, not the Researcher's reasoning).
3. Wait ≤ 10 s.
4. Call `lab_brain.build_chat_messages("what did the lab learn about
   Aerollm?")` and inspect the system prompt; assert it contains the
   `agents/research/...topic-x_report.md` path **and** the
   "40%" snippet.
5. Tear the process down, start a fresh one, repeat step 4, same
   assertion.

If the E2E witness passes, the loop is closed end-to-end with no
manual rebuild step and across a process restart.

## Tech debt

**Added:**
- A new module `src/arail/pkb_index.py` with module-level state
  (a `set`, a `Lock`, a `Timer`, an `_initialized` boolean). This
  is the cost of "no new long-lived service"; it's bounded but it's
  shared mutable state. Tests that import the module need a
  fixture to reset it.
- The `pkb_pages` table schema gains two columns. Future schema
  changes are still drop-and-rebuild because we did not invest in
  a real migration framework. Acceptable for a small corpus.
- `BuddyAgent.dream` now depends on `pkb.write_buddy_dream`, which
  depends on `pkb_index`. New transitive coupling between the
  buddy module and the indexer.

**Repaid:**
- Removes the implicit "the chat search returns nothing useful
  until you remember to rebuild" gotcha — a real product wart.
- Establishes the `pkb_index` seam so future write surfaces (SRE
  postmortems, user uploads via /knowledge UI) have an obvious
  place to plug into.
- Documents the `pkb_pages` schema explicitly for the first time.

**Net:** roughly zero. New module is ~150 lines; a real product
gain.

## Draft/published flag — answer to the visionary's question

**Recommendation: defer to a follow-up sprint. Do NOT include in
this sprint.**

Justification:
1. The win condition does not mention drafts. The wedge is "writes
   become findable"; gating writes on a quality flag is a different
   problem ("which writes should be findable").
2. We have no current writer that produces drafts. Researcher
   writes finished reports; Buddy's dream is a finished reflection;
   teacher Q&A is a finished consultation. There is nothing to gate
   yet. Adding a `published` column without a producer for
   `published=False` is YAGNI.
3. The visionary's disconfirming evidence — *count chat sessions
   that surface agent-page-grounded answers; if zero after a week,
   the wedge is wrong* — depends on **all** agent writes flowing
   through. Pre-filtering to "published only" before that data
   arrives risks hiding the very signal we need.
4. The `source_kind` column we are adding **already supports**
   future filtering: a draft/published filter can be expressed as
   a `WHERE source_kind != 'agent_draft'` clause without another
   migration. So the option stays open at zero current cost.
5. The displacement risk the visionary flagged ("operators who
   used 'no rebuild yet' as an implicit quality gate lose that
   gate") is real but low: the operator can still distinguish
   agent-written pages from human-curated ones by path
   (`agents/...`) — the path prefix is itself a quality signal.

**If after a week of operation the operator complains that
half-baked agent drafts are surfacing**, the follow-up sprint adds:
(a) a `published: bool` column, (b) Researcher writes
`published=False` first then re-upserts with `published=True` after
its self-check passes, (c) `_semantic_search` filters
`published=True` by default with an "include drafts" override on
the chat tab. That sprint is small because the schema seam is in
place.

## Out of scope / explicitly deferred

Confirmed not in this sprint:
- KB → fine-tune dataset / system-prompt preamble / context-cache
  "compile". (Per SPRINT.md.)
- UI changes to `/knowledge` or `/chat`. (Per SPRINT.md.)
- Wiki rebuild rewrite. (Per SPRINT.md. The wiki module continues
  to use its own asyncio debouncer; we do not unify.)

Discovered and added to deferred list:
- Wiring SRE to write markdown narrative postmortems (currently
  writes JSON state only).
- Adding a `published`/draft flag (see above).
- File-watcher trigger surface (covered by the helper boundary in
  this sprint).
- Multi-process write safety on the same PKB.
- Per-chunk indexing (one row per file is sufficient at current
  corpus size).
- Replacing `hash_embedding` with a real embedder.
- A CLI `arail pkb reindex` command (the existing `pkb compile` CLI
  and the implicit-rebuild path on schema mismatch already cover
  the operator escape hatch).

## Recommended implementation order

1. Create `src/arail/pkb_index.py` with `ensure_ready`,
   `schedule_upsert`, `_flush`, the lock, the timer, and the
   merge-insert + delete fallback. No call sites yet.
2. Update `src/arail/pkb.py:index_all` to write the wider row
   (`mtime`, `source_kind`). `source_kind="user"` for files
   discovered by the rebuild — agent-written paths are detected by
   prefix (`agents/`).
3. Wire `pkb_index.schedule_upsert` into the six existing write
   helpers in `src/arail/pkb.py:534-654`. Each gets a `try/except`
   shim and passes the appropriate `source_kind`.
4. Add `pkb.write_buddy_dream` and refactor
   `BuddyAgent.dream` to call it.
5. Call `pkb_index.ensure_ready()` from the portal startup hook
   (`src/arail/portal/app.py` startup event).
6. Add `tests/test_pkb_index.py`,
   `tests/test_pkb_index_integration.py`,
   `tests/test_pkb_index_perf.py`, and the E2E witness test.
7. Run the full existing suite to confirm no regressions.
8. Document the new module in `docs/` only if QA flags an
   operator-visible behavior; otherwise the docstring + this
   ARCHITECTURE.md are sufficient (per the workspace's
   no-unsolicited-md rule).
