"""PKB incremental index — in-process debounced upsert into LanceDB.

Public API
----------
ensure_ready(pkb_root)   — Call once at portal startup. Checks the pkb_pages
                           table schema and runs a bounded staleness sweep.
                           Triggers index_all() if the table is missing or
                           schema-mismatched (dimension mismatch never drops
                           the table — see C2/FM12).
schedule_upsert(path)    — Enqueue a path for upsert. Safe to call from any
                           thread; the write helper never blocks. Debounce
                           window is LAB_PKB_UPSERT_DEBOUNCE_SEC (default 2s),
                           or the error back-off (60s) while degraded.
embedding_status()       — (ok, message) for the embedding subsystem. ok is
                           False after an EmbeddingError until a flush or
                           index_all succeeds again (C1).
set_degraded(reason)     — Mark the embedding subsystem degraded. Called at
                           every C1 call site that catches EmbeddingError.
clear_degraded()         — Clear the degraded flag. Called on any successful
                           index_all()/flush.
_reset_for_tests()       — Reset module-level state between tests. Not for
                           production use.

Design notes
------------
* threading.Timer — not asyncio — so this module works from sync helpers,
  async portal handlers, and CLI entrypoints without requiring a running
  event loop. Deliberately diverges from wiki.py's asyncio debouncer.
* One threading.Lock serializes all state mutations and the merge_insert call.
* The file write is NEVER blocked by indexing. Every schedule_upsert call
  in the write helpers is wrapped in try/except Exception: pass.
* merge_insert upsert path (LanceDB ≥ 0.5). Falls back to delete+add if
  merge_insert is absent on a pinned env.
* Path safety: paths outside pkb_root are rejected via relative_to().
* C1 error contract (ARCHITECTURE.md): an embedding outage must be
  impossible to mistake for an empty corpus. Every call site that can
  trigger a network embed call catches ``arail.dbspec.embed.EmbeddingError``
  *separately* from every other exception: logs at ERROR (not WARNING),
  emits an ``activity_log`` event at severity "error", and sets the module
  degraded flag via ``set_degraded()``. Non-embedding exceptions keep the
  original WARNING behaviour — those are the SKIP/DEGRADE classes, not LOUD.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

# ── Module-level coalescer state ─────────────────────────────────────────

_lock: threading.Lock = threading.Lock()
_pending: set[str] = set()          # POSIX relative paths
_timer: threading.Timer | None = None
_initialized: bool = False
_pkb_root_cache: Path | None = None  # set by ensure_ready

# ── C1: degraded-embedding state ─────────────────────────────────────────
# Set by every call site that catches EmbeddingError; cleared by the next
# successful index_all()/flush. Read via embedding_status() by pkb.py's
# search-payload status, ./arailctl doctor, and (once wired) the /knowledge
# banner and Buddy's context header.
_degraded: bool = False
_degraded_reason: str = ""

# Required columns (and their expected presence) for schema validation.
_REQUIRED_COLS = {"path", "name", "vector", "mtime", "source_kind"}
_STALENESS_CAP = 200   # max files checked in the sweep before falling back to index_all
_DEFAULT_DEBOUNCE = 2.0
_ERROR_BACKOFF_SEC = 60.0  # C1/FM17: back off retries after an EmbeddingError


def _vector_dim() -> int:
    """The spec-declared embedding dimension. A function, not a module
    constant, so it always reflects the current spec/models.hcl rather than
    a value frozen at import time — matters once ``embedding_model()``'s
    declared dimension can change without a code deploy."""
    from arail.dbspec.generated.models_registry import EMBEDDING_DIM
    return EMBEDDING_DIM


def set_degraded(reason: str) -> None:
    """Mark the embedding subsystem degraded. Idempotent; safe to call from
    any thread (no lock needed — a stale read of a bool/str pair is
    harmless, and callers only ever set it to a fresher reason)."""
    global _degraded, _degraded_reason
    _degraded = True
    _degraded_reason = reason


def clear_degraded() -> None:
    """Clear the degraded flag — called after any successful embedding
    call. A no-op if not currently degraded."""
    global _degraded, _degraded_reason
    _degraded = False
    _degraded_reason = ""


def embedding_status() -> tuple[bool, str]:
    """(ok, message). ok=False means the last embedding call failed and
    callers should treat search results / index state as degraded until it
    clears. Read by ``arail.pkb.retrieval_status()``, ``./arailctl doctor``,
    and (once wired) UI surfaces."""
    return (not _degraded, _degraded_reason)


def _index_all_reporting_embedding_errors(root: Path, context: str) -> None:
    """Shared body for every ``pkb.index_all()`` call site in this module.

    Catches ``EmbeddingError`` (LOUD, per C1) separately from every other
    exception (kept as the original WARNING/SKIP behaviour). Never raises —
    the caller sites all treat index_all() as best-effort background work,
    same as before this contract existed.
    """
    from arail.dbspec.embed import EmbeddingError

    try:
        from arail import pkb as pkb_mod
        pkb_mod.index_all(root)
        clear_degraded()
    except EmbeddingError as e:
        _log.error("pkb_index: %s: embedding provider unavailable: %s", context, e)
        try:
            from arail.activity import activity_log
            activity_log.emit(
                "pkb", f"KB index build failed ({context}): embedding provider "
                       f"unavailable — {e}", "error")
        except Exception:
            pass
        set_degraded(str(e))
    except Exception as e:  # noqa: BLE001 — SKIP/DEGRADE class, original behaviour
        _log.warning("pkb_index: %s failed: %s", context, e)


def _debounce_sec() -> float:
    """Normal debounce, or the 60s error back-off while degraded (FM17) —
    a dead embedding provider must not turn the debounce timer into a
    tight retry storm."""
    if _degraded:
        return _ERROR_BACKOFF_SEC
    try:
        return float(os.environ.get("LAB_PKB_UPSERT_DEBOUNCE_SEC", _DEFAULT_DEBOUNCE))
    except (TypeError, ValueError):
        return _DEFAULT_DEBOUNCE


# ── Helpers ───────────────────────────────────────────────────────────────

def _vector_db_path(root: Path) -> Path:
    return root / ".cache" / "lancedb"


def _pkb_root_from_env() -> Path:
    """Resolve PKB root the same way pkb.py does."""
    from arail.config import PKB_ROOT
    return PKB_ROOT


def _build_row(abs_path: Path, rel_posix: str, source_kind: str) -> dict[str, Any] | None:
    """Read the file and return a row dict, or None if the file is
    unreadable (SKIP class — an OSError here is a per-item concern, not a
    provider outage).

    Raises ``arail.dbspec.embed.EmbeddingError`` (LOUD, per C1) if the
    embedding call fails — deliberately NOT caught here. The one caller,
    ``_flush``, catches it separately from every other exception so a dead
    provider aborts the whole flush instead of being recorded as a
    per-path failure and retried in a tight loop (FM17)."""
    from arail.dbspec.embed import embed_documents
    try:
        text = abs_path.read_text(errors="replace")
    except OSError:
        return None
    snippet = text[:4096]
    name = abs_path.name
    vec = embed_documents([f"{name} {rel_posix} {snippet}"])[0]
    mtime = abs_path.stat().st_mtime
    return {
        "path": rel_posix,
        "name": name,
        "vector": vec,
        "mtime": mtime,
        "source_kind": source_kind,
    }


def _source_kind_for_path(rel_posix: str) -> str:
    """Infer source_kind from the relative path prefix.

    Delegates to the single implementation in ``arail.pkb`` so the two indexing
    paths (full rebuild vs incremental upsert) can never drift apart. (The
    review-queue's ``compiled_kb.kind_of`` is a deliberately separate vocabulary
    — e.g. it labels dreams ``agent_dream`` and adds ``world_term`` — and is not
    merged here.)"""
    from arail.pkb import _source_kind_for_rel
    return _source_kind_for_rel(rel_posix)


def _open_table(db, name: str):
    """Open an existing table; returns None if not present."""
    from arail.vector_index import VectorIndex
    existing = VectorIndex._existing_tables(db)
    if name in existing:
        try:
            return db.open_table(name)
        except Exception:
            return None
    return None


def _schema_column_status(table) -> tuple[bool, bool]:
    """Return (missing_columns, dim_mismatch).

    Split out from the old single ``_schema_ok`` bool so ``ensure_ready``
    can tell the two failure kinds apart (C2/FM12): missing columns is a
    cheap, offline, safe-to-drop-and-rebuild schema upgrade; a dimension
    mismatch (e.g. 128 hash -> 768 nomic) is NEVER safe to drop — that is
    how a config change silently empties a user's index. ``(True, False)``
    on any read failure (unreadable schema): treated as "needs rebuild",
    never as a dimension issue, since we genuinely don't know the dimension.
    """
    try:
        schema = table.schema
        names = set(schema.names)
        missing_columns = not _REQUIRED_COLS.issubset(names)
        dim_mismatch = False
        if "vector" in names:
            vec_field = schema.field("vector")
            # Arrow FixedSizeList type has .list_size attribute.
            fsl = vec_field.type
            size = getattr(fsl, "list_size", None)
            if size is None:
                # Older Arrow: .value_type exists but not list_size.
                size = getattr(fsl, "value_size", None)
            if size is not None and int(size) != _vector_dim():
                dim_mismatch = True
        return missing_columns, dim_mismatch
    except Exception:
        return True, False


def _schema_ok(table) -> bool:
    """True iff the table has all required columns and the correct vector
    dimension. Thin wrapper over ``_schema_column_status`` kept for any
    caller/test that only wants the combined answer."""
    missing_columns, dim_mismatch = _schema_column_status(table)
    return not missing_columns and not dim_mismatch


def _flush() -> None:
    """Flush the pending set to LanceDB. Called by the debounce timer."""
    global _timer
    from arail.vector_index import available

    if not available():
        _log.warning("pkb_index: LanceDB not available; skipping flush")
        with _lock:
            _timer = None
        return

    with _lock:
        _timer = None
        if not _pending:
            return
        snapshot = set(_pending)
        # Do NOT clear _pending yet — only clear the paths we successfully
        # process (delete or upsert). On error, keep them so next arm retries.
        root = _pkb_root_cache

    if root is None:
        return

    import lancedb  # type: ignore[import-not-found]

    db_path = _vector_db_path(root)
    db_path.mkdir(parents=True, exist_ok=True)
    try:
        db = lancedb.connect(str(db_path))
    except Exception as e:
        _log.warning("pkb_index: cannot connect to LanceDB: %s", e)
        return

    table = _open_table(db, "pkb_pages")
    if table is None:
        # Table disappeared between ensure_ready and flush — rebuild.
        _index_all_reporting_embedding_errors(root, "flush: pkb_pages table missing")
        with _lock:
            _pending.difference_update(snapshot)
        return

    from arail.dbspec.embed import EmbeddingError

    t0 = time.monotonic()
    upserted = 0
    deleted = 0
    failed_paths: set[str] = set()
    embedding_aborted = False

    for rel_posix in snapshot:
        abs_path = root / rel_posix
        if not abs_path.exists():
            # File was deleted between schedule_upsert and flush.
            try:
                escaped = rel_posix.replace("'", "''")
                table.delete(f"path = '{escaped}'")
                deleted += 1
            except Exception as e:
                _log.warning("pkb_index: delete failed for %s: %s", rel_posix, e)
                failed_paths.add(rel_posix)
            continue

        source_kind = _source_kind_for_path(rel_posix)
        try:
            row = _build_row(abs_path, rel_posix, source_kind)
        except EmbeddingError as e:
            # C1/FM17: an EmbeddingError on one path must NOT be recorded as
            # a per-path failure and retried in a tight loop. Abort the
            # whole flush, keep every remaining path in _pending (including
            # this one) for the next arm, degrade, and back off to 60s.
            _log.error("pkb_index: flush aborted — embedding provider "
                       "unavailable: %s", e)
            try:
                from arail.activity import activity_log
                activity_log.emit(
                    "pkb", f"KB flush aborted: embedding provider unavailable "
                           f"({e})", "error")
            except Exception:
                pass
            set_degraded(str(e))
            embedding_aborted = True
            break
        if row is None:
            continue

        try:
            mi = getattr(table, "merge_insert", None)
            if mi is not None:
                # Preferred: single merge_insert transaction
                table.merge_insert("path") \
                     .when_matched_update_all() \
                     .when_not_matched_insert_all() \
                     .execute([row])
            else:
                # Fallback: delete + add
                escaped = rel_posix.replace("'", "''")
                table.delete(f"path = '{escaped}'")
                table.add([row])
            upserted += 1
            clear_degraded()
        except Exception as e:
            _log.warning("pkb_index: upsert failed for %s: %s", rel_posix, e)
            failed_paths.add(rel_posix)

    if embedding_aborted:
        # _pending is untouched — the whole snapshot, including whatever
        # this loop hadn't reached yet, stays queued for the next arm.
        # Re-arm here (not just wait for the next schedule_upsert) so a dead
        # Ollama is retried automatically at the 60s back-off rather than
        # only on the next unrelated file write.
        with _lock:
            _arm_timer()
        return

    elapsed_ms = int((time.monotonic() - t0) * 1000)
    _log.info(
        "pkb_index: upserted %d rows, deleted %d rows in %d ms",
        upserted, deleted, elapsed_ms,
    )

    # Emit to activity log (best-effort)
    try:
        from arail.activity import activity_log
        if upserted or deleted:
            activity_log.emit(
                "pkb",
                f"pkb_index: upserted {upserted} rows, deleted {deleted} rows in {elapsed_ms} ms",
                "info",
            )
    except Exception:
        pass

    with _lock:
        # Remove successfully processed paths; keep failed ones for retry.
        _pending.difference_update(snapshot - failed_paths)


def _arm_timer() -> None:
    """Cancel any existing timer and start a fresh debounce. Must be called under _lock."""
    global _timer
    if _timer is not None:
        _timer.cancel()
    _timer = threading.Timer(_debounce_sec(), _flush)
    _timer.daemon = True
    _timer.start()


def flush_now() -> None:
    """Flush any pending upserts immediately instead of waiting out the
    debounce window. Used after a World mount/swap so the KB is searchable
    right away rather than seconds later. Cancels the pending timer, runs the
    same ``_flush`` synchronously. Never raises; no-op when LanceDB is absent
    (``_flush`` self-guards)."""
    global _timer
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
    try:
        _flush()
    except Exception as e:  # noqa: BLE001
        _log.warning("pkb_index: flush_now failed: %s", e)


# ── Public API ────────────────────────────────────────────────────────────

def ensure_ready(pkb_root: Path | None = None) -> None:
    """Check/build the pkb_pages table. Call once at portal startup.

    Detection logic (in order):
    1. If LanceDB is unavailable, return immediately.
    2. If the table is missing, call index_all() and return.
    3. If required columns are missing, drop and call index_all() once
       (cheap, offline-safe schema upgrade).
    4. If only the vector *dimension* differs from the current spec
       (e.g. 128-dim hash -> 768-dim nomic), NEVER drop the table — degrade
       with an actionable message and leave the rows exactly as they are
       (C2/FM12). An explicit ``./arailctl pkb reembed`` is the only path
       that rewrites those rows.
    5. If the schema and dimension are fine but the provenance sidecar
       (C4) disagrees with — or is missing for — the current spec, degrade;
       no query is served from a table whose provenance disagrees with the
       spec.
    6. Otherwise run the bounded staleness sweep (cap 200 files).
       If more than 200 stale files are found, fall back to index_all().
    """
    global _initialized, _pkb_root_cache

    from arail.vector_index import available

    with _lock:
        if _initialized:
            return
        root = pkb_root or _pkb_root_from_env()
        _pkb_root_cache = root
        _initialized = True

    if not available():
        _log.warning("pkb_index: LanceDB not available; ensure_ready is a no-op")
        return

    if not root.exists():
        _log.warning("pkb_index: pkb_root %s does not exist; skipping ensure_ready", root)
        return

    import lancedb  # type: ignore[import-not-found]

    db_path = _vector_db_path(root)
    db_path.mkdir(parents=True, exist_ok=True)
    try:
        db = lancedb.connect(str(db_path))
    except Exception as e:
        _log.warning("pkb_index: cannot connect to LanceDB in ensure_ready: %s", e)
        return

    table = _open_table(db, "pkb_pages")

    if table is None:
        _log.info("pkb_index: pkb_pages table missing — building index")
        _index_all_reporting_embedding_errors(root, "ensure_ready: table missing")
        return

    missing_columns, dim_mismatch = _schema_column_status(table)

    if dim_mismatch and not missing_columns:
        reason = (
            "pkb_pages index was built with a different embedding "
            "dimension than the current spec declares — run "
            "`./arailctl pkb reembed` to upgrade. Existing rows are "
            "untouched."
        )
        _log.warning("pkb_index: %s", reason)
        set_degraded(reason)
        try:
            from arail.activity import activity_log
            activity_log.emit("pkb", reason, "warn")
        except Exception:
            pass
        return

    if missing_columns:
        _log.info(
            "pkb_index: pkb_pages schema missing required columns "
            "— dropping and rebuilding (schema upgrade)"
        )
        try:
            from arail.activity import activity_log
            activity_log.emit("pkb", "Rebuilding KB index for schema upgrade", "info")
        except Exception:
            pass
        try:
            db.drop_table("pkb_pages")
        except Exception:
            pass
        _index_all_reporting_embedding_errors(root, "ensure_ready: schema drop-and-rebuild")
        return

    # C4: schema and dimension are fine, but the vectors may still have
    # been built by a different model (same dimension, wrong space) — or
    # never provenance-tracked at all (a legacy hash table that happens to
    # share the current dimension by coincidence). Never serve a query from
    # a table whose provenance disagrees with the spec.
    from arail import pkb_provenance
    from arail.dbspec.generated.models_registry import embedding_model as _embedding_model
    current_model = _embedding_model()
    record = pkb_provenance.read(db_path)
    if not pkb_provenance.agrees_with_spec(
            record, embedding_model=current_model.name, embedding_dim=_vector_dim()):
        if record is None:
            reason = (
                "pkb_pages index has no provenance record — treated as a "
                "legacy index. Run `./arailctl pkb reembed` to upgrade."
            )
        else:
            reason = (
                f"pkb_pages index provenance "
                f"({record.get('embedding_model')}/{record.get('embedding_dim')}d) "
                f"disagrees with the current spec "
                f"({current_model.name}/{_vector_dim()}d) — run "
                f"`./arailctl pkb reembed` to upgrade. Existing rows are untouched."
            )
        _log.warning("pkb_index: %s", reason)
        set_degraded(reason)
        return

    # Table exists, schema and provenance both match — run the bounded
    # staleness sweep.
    clear_degraded()
    _staleness_sweep(root, table, db)


def _staleness_sweep(root: Path, table, db) -> None:
    """Compare on-disk file mtimes to table row mtimes; schedule upserts for stale files."""
    from arail import pkb as pkb_mod

    # Load the current table rows into a dict: rel_posix -> mtime
    try:
        rows = table.to_pandas()[["path", "mtime"]].to_dict("records")
        indexed_mtimes: dict[str, float] = {r["path"]: float(r["mtime"]) for r in rows}
    except Exception as e:
        _log.warning("pkb_index: staleness sweep could not read table: %s", e)
        return

    indexed_paths = set(indexed_mtimes.keys())
    on_disk_paths: set[str] = set()
    stale_count = 0
    cap_exceeded = False

    for abs_path, _text in pkb_mod._iter_pkb_files(root):
        try:
            rel_posix = abs_path.relative_to(root).as_posix()
        except ValueError:
            continue
        on_disk_paths.add(rel_posix)
        disk_mtime = abs_path.stat().st_mtime
        table_mtime = indexed_mtimes.get(rel_posix)
        if table_mtime is None or disk_mtime > table_mtime:
            stale_count += 1
            if stale_count > _STALENESS_CAP:
                cap_exceeded = True
                break
            with _lock:
                _pending.add(rel_posix)

    if cap_exceeded:
        _log.info(
            "pkb_index: staleness sweep found >%d stale files; triggering full index_all",
            _STALENESS_CAP,
        )
        try:
            from arail.activity import activity_log
            activity_log.emit("pkb", "KB staleness sweep: too many stale files, rebuilding index", "info")
        except Exception:
            pass
        with _lock:
            _pending.clear()
        _index_all_reporting_embedding_errors(root, "staleness sweep: cap exceeded")
        return

    # Delete rows for files that no longer exist on disk.
    for rel_posix in indexed_paths - on_disk_paths:
        with _lock:
            _pending.add(rel_posix)

    if stale_count > 0 or (indexed_paths - on_disk_paths):
        _log.info(
            "pkb_index: staleness sweep found %d stale/new files and %d deleted",
            stale_count, len(indexed_paths - on_disk_paths),
        )
        # Arm the timer to flush any stale paths queued above.
        with _lock:
            if _pending:
                _arm_timer()


def schedule_upsert(path: Path, *, pkb_root: Path | None = None) -> None:
    """Enqueue a path for incremental upsert. Never raises; never blocks writes.

    The path must be inside pkb_root. Paths outside are silently rejected.
    The actual LanceDB write happens after the debounce window expires.
    """
    global _pkb_root_cache
    from arail.vector_index import available
    if not available():
        return

    # Never embed staged World bundle-machinery (agenda/drift/roster/spec/
    # terms.json) — the world's content is indexed as per-term pages instead.
    try:
        from arail.world_mount import is_world_machinery_path
        if is_world_machinery_path(path):
            return
    except Exception:  # noqa: BLE001
        pass

    root = pkb_root or _pkb_root_cache or _pkb_root_from_env()

    # Lazily initialize if ensure_ready was never called.
    with _lock:
        if _pkb_root_cache is None:
            _pkb_root_cache = root

    try:
        # Resolve both paths to canonical absolute paths before comparing,
        # so symlinks and ".." components can't escape pkb_root.
        resolved_path = path.resolve()
        resolved_root = root.resolve()
        rel_posix = resolved_path.relative_to(resolved_root).as_posix()
    except ValueError:
        _log.warning(
            "pkb_index: schedule_upsert rejected path outside pkb_root: %s", path
        )
        return

    with _lock:
        _pending.add(rel_posix)
        _arm_timer()


def _reset_for_tests() -> None:
    """Reset all module-level state. Call from test fixtures only."""
    global _pending, _timer, _initialized, _pkb_root_cache
    with _lock:
        if _timer is not None:
            _timer.cancel()
            _timer = None
        _pending.clear()
        _initialized = False
        _pkb_root_cache = None
    clear_degraded()
