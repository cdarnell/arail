"""PKB incremental index — in-process debounced upsert into LanceDB.

Public API
----------
ensure_ready(pkb_root)   — Call once at portal startup. Checks the pkb_pages
                           table schema and runs a bounded staleness sweep.
                           Triggers index_all() if the table is missing or
                           schema-mismatched.
schedule_upsert(path)    — Enqueue a path for upsert. Safe to call from any
                           thread; the write helper never blocks. Debounce
                           window is LAB_PKB_UPSERT_DEBOUNCE_SEC (default 2s).
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

# Required columns (and their expected presence) for schema validation.
_REQUIRED_COLS = {"path", "name", "vector", "mtime", "source_kind"}
_VECTOR_DIM = 128
_STALENESS_CAP = 200   # max files checked in the sweep before falling back to index_all
_DEFAULT_DEBOUNCE = 2.0


def _debounce_sec() -> float:
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
    """Read the file and return a row dict, or None if the file is unreadable."""
    from arail.vector_index import hash_embedding
    try:
        text = abs_path.read_text(errors="replace")
    except OSError:
        return None
    snippet = text[:4096]
    name = abs_path.name
    vec = hash_embedding(f"{name} {rel_posix} {snippet}")
    mtime = abs_path.stat().st_mtime
    return {
        "path": rel_posix,
        "name": name,
        "vector": vec,
        "mtime": mtime,
        "source_kind": source_kind,
    }


def _source_kind_for_path(rel_posix: str) -> str:
    """Infer source_kind from the relative path prefix."""
    if rel_posix.startswith("agents/research/"):
        return "agent_research"
    if rel_posix.startswith("agents/experiments/"):
        return "agent_experiment"
    if rel_posix.startswith("agents/synthesis/"):
        return "agent_synthesis"
    if rel_posix.startswith("agents/recommendations/"):
        return "agent_recommendation"
    if rel_posix.startswith("agents/buddy/dreams/"):
        return "agent_buddy_dream"
    if rel_posix.startswith("teacher/"):
        return "teacher_qa"
    return "user"


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


def _schema_ok(table) -> bool:
    """Return True iff the table has all required columns and correct vector dim."""
    try:
        schema = table.schema
        names = set(schema.names)
        if not _REQUIRED_COLS.issubset(names):
            return False
        # Check vector field dimension
        vec_field = schema.field("vector")
        # Arrow FixedSizeList type has .list_size attribute
        fsl = vec_field.type
        size = getattr(fsl, "list_size", None)
        if size is None:
            # Older Arrow: .value_type exists but not list_size
            size = getattr(fsl, "list_size", None) or getattr(fsl, "value_size", None)
        if size is not None and int(size) != _VECTOR_DIM:
            return False
        return True
    except Exception:
        return False


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
        _log.warning("pkb_index: pkb_pages table missing at flush; triggering rebuild")
        try:
            from arail import pkb as pkb_mod
            pkb_mod.index_all(root)
        except Exception as e:
            _log.warning("pkb_index: rebuild in _flush failed: %s", e)
        with _lock:
            _pending.difference_update(snapshot)
        return

    t0 = time.monotonic()
    upserted = 0
    deleted = 0
    failed_paths: set[str] = set()

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
        row = _build_row(abs_path, rel_posix, source_kind)
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
        except Exception as e:
            _log.warning("pkb_index: upsert failed for %s: %s", rel_posix, e)
            failed_paths.add(rel_posix)

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


# ── Public API ────────────────────────────────────────────────────────────

def ensure_ready(pkb_root: Path | None = None) -> None:
    """Check/build the pkb_pages table. Call once at portal startup.

    Detection logic (in order):
    1. If LanceDB is unavailable, return immediately.
    2. If the table is missing, call index_all() and return.
    3. If the schema is wrong (missing columns or wrong vector dim), drop
       and call index_all() once with a log line.
    4. Otherwise run the bounded staleness sweep (cap 200 files).
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
        try:
            from arail import pkb as pkb_mod
            pkb_mod.index_all(root)
        except Exception as e:
            _log.warning("pkb_index: index_all failed: %s", e)
        return

    if not _schema_ok(table):
        _log.info(
            "pkb_index: pkb_pages schema missing required columns or wrong vector dim "
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
        try:
            from arail import pkb as pkb_mod
            pkb_mod.index_all(root)
        except Exception as e:
            _log.warning("pkb_index: index_all after schema drop failed: %s", e)
        return

    # Table exists and schema matches — run bounded staleness sweep.
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
        try:
            from arail import pkb as pkb_mod
            pkb_mod.index_all(root)
        except Exception as e:
            _log.warning("pkb_index: index_all in staleness sweep fallback failed: %s", e)
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
