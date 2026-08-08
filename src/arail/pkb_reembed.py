"""``./arailctl pkb reembed`` — explicit, resumable re-embed of one PKB
root's vector index (C2 in ARCHITECTURE.md, arail2-tier1-integration).

Never triggered implicitly. The lazy ``index_all()`` call inside
``pkb._semantic_search`` is removed on this integration (see FM11) — an
empty or stale index degrades honestly instead of firing hundreds of
synchronous embed calls from inside a search request. This is the only
path that (re)writes ``pkb_pages`` with the spec-declared embedder.

Shape, per C2:
  * **Explicit.** Only this command re-embeds. Nothing else calls it.
  * **Shadow build + swap.** Vectors are written into
    ``<pkb_root>/.cache/lancedb.next/`` batch by batch. Only after every
    row succeeds does the live table get replaced — ``pkb_pages.lance`` is
    moved to ``pkb_pages.lance.bak-<ts>`` first, so a crash between steps
    leaves either the old table or the old table plus a ``.next`` dir,
    never a half-embedded live table (FM13).
  * **Resumable + interruptible.** A checkpoint at
    ``<pkb_root>/.cache/reembed-state.json`` is written after every batch.
    SIGINT stops queuing new batches (the in-flight batch finishes and its
    checkpoint is written, so nothing is lost) and the process exits 130.
    ``--resume`` refuses to continue if the checkpoint's
    model/dim/spec_sha256 disagree with the current spec.
  * **Provenance written last**, via ``pkb_provenance`` (C4), after the
    swap — never before.

Usage (invoked by ``arailctl``'s bash dispatcher, one call per resolved
pkb root):
    python -m arail.pkb_reembed --pkb-root PATH [--world-label LABEL]
        [--resume] [--dry-run] [--yes]

Exit codes: 0 ok · 1 error (e.g. LanceDB unavailable, checkpoint spec
mismatch) · 2 bad input (pkb root missing) · 4 EmbeddingError (provider
unavailable) · 130 interrupted (SIGINT; resume with --resume).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Callable

SCHEMA = "arail.reembed_checkpoint/v1"


# --------------------------------------------------------------------------
# paths
# --------------------------------------------------------------------------

def _checkpoint_path(pkb_root: Path) -> Path:
    return pkb_root / ".cache" / "reembed-state.json"


def _shadow_dir(pkb_root: Path) -> Path:
    return pkb_root / ".cache" / "lancedb.next"


def _live_dir(pkb_root: Path) -> Path:
    return pkb_root / ".cache" / "lancedb"


# --------------------------------------------------------------------------
# checkpoint
# --------------------------------------------------------------------------

def _load_checkpoint(pkb_root: Path) -> dict[str, Any] | None:
    path = _checkpoint_path(pkb_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _write_checkpoint(pkb_root: Path, state: dict[str, Any]) -> None:
    path = _checkpoint_path(pkb_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def _clear_checkpoint(pkb_root: Path) -> None:
    try:
        _checkpoint_path(pkb_root).unlink()
    except FileNotFoundError:
        pass


class CheckpointSpecMismatch(RuntimeError):
    """--resume was passed but the checkpoint was started with a different
    embedding spec (model/dim/spec_sha256)."""


# --------------------------------------------------------------------------
# the run
# --------------------------------------------------------------------------

def run(pkb_root: Path, *, resume: bool = False, dry_run: bool = False,
        batch_size: int | None = None, include_docs: bool = True,
        progress: Callable[..., None] = lambda **kw: None) -> dict[str, Any]:
    """Do the reembed. Returns a result dict; never raises for a SIGINT
    (returns ``{"interrupted": True, ...}`` instead) — but DOES raise
    ``arail.dbspec.embed.EmbeddingError`` if the provider is unavailable,
    ``CheckpointSpecMismatch`` if ``--resume``'s checkpoint disagrees with
    the current spec, and ``RuntimeError`` if LanceDB is unavailable.
    """
    import lancedb  # type: ignore[import-not-found]
    from arail import pkb as pkb_mod
    from arail import pkb_provenance
    from arail.vector_index import available, VectorIndex
    from arail.dbspec import embed as embed_mod
    from arail.dbspec.generated.models_registry import EMBEDDING_DIM, embedding_model

    if not available():
        raise RuntimeError("LanceDB is not importable; cannot reembed")

    batch_size = batch_size or embed_mod._BATCH
    model = embedding_model()
    spec_sha = pkb_mod._current_spec_sha256()

    pending_rows = pkb_mod.collect_pending_rows(pkb_root, include_docs=include_docs)
    total = len(pending_rows)

    if dry_run:
        probe_rows = pending_rows[:32]
        t0 = time.monotonic()
        if probe_rows:
            embed_mod.embed_documents([r["embed_input"] for r in probe_rows])
        elapsed = time.monotonic() - t0
        rate = (len(probe_rows) / elapsed) if elapsed > 0 else float("inf")
        eta = (total / rate) if rate not in (0, float("inf")) else 0.0
        return {
            "dry_run": True, "total": total, "probe_rows": len(probe_rows),
            "rows_per_sec": rate, "eta_sec": eta,
        }

    checkpoint = _load_checkpoint(pkb_root) if resume else None
    completed_paths: set[str] = set()
    if checkpoint is not None:
        if (checkpoint.get("model") != model.name
                or checkpoint.get("dim") != EMBEDDING_DIM
                or checkpoint.get("spec_sha256") != spec_sha):
            raise CheckpointSpecMismatch(
                "checkpoint was started with a different embedding spec "
                "(model/dim/spec changed) — refusing to mix vector spaces "
                "in one shadow build. Run without --resume to start over "
                "(the previous shadow build will be discarded).")
        completed_paths = set(checkpoint.get("completed_paths", []))
    elif not resume:
        # Fresh start: discard any stale shadow build from a prior aborted
        # run so it can't get silently mixed with this one.
        _clear_checkpoint(pkb_root)
        shutil.rmtree(_shadow_dir(pkb_root), ignore_errors=True)

    remaining = [r for r in pending_rows if r["path"] not in completed_paths]

    shadow_dir = _shadow_dir(pkb_root)
    shadow_dir.parent.mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(str(shadow_dir))
    table = None
    if completed_paths:
        existing = VectorIndex._existing_tables(db)
        if "pkb_pages" in existing:
            table = db.open_table("pkb_pages")

    started_at = checkpoint.get("started_at") if checkpoint else _now_iso()

    interrupted = {"flag": False}

    def _sigint_handler(signum, frame):  # noqa: ARG001
        interrupted["flag"] = True

    old_handler = signal.signal(signal.SIGINT, _sigint_handler)
    completed_count = len(completed_paths)
    try:
        for start in range(0, len(remaining), batch_size):
            if interrupted["flag"]:
                break
            batch = remaining[start:start + batch_size]
            t0 = time.monotonic()
            vectors = embed_mod.embed_documents([r["embed_input"] for r in batch])
            elapsed = time.monotonic() - t0
            rows = [
                {
                    "path": r["path"], "name": r["name"], "vector": v,
                    "mtime": r["mtime"], "source_kind": r["source_kind"],
                }
                for r, v in zip(batch, vectors)
            ]
            if table is None:
                table = db.create_table("pkb_pages", data=rows, mode="overwrite")
            else:
                table.add(rows)
            completed_paths.update(r["path"] for r in batch)
            completed_count += len(batch)
            _write_checkpoint(pkb_root, {
                "schema": SCHEMA, "model": model.name, "dim": EMBEDDING_DIM,
                "spec_sha256": spec_sha, "started_at": started_at,
                "total": total, "completed_paths": sorted(completed_paths),
                "batch": batch_size,
            })
            rate = (len(batch) / elapsed) if elapsed > 0 else None
            progress(done=completed_count, total=total, rate=rate)
    finally:
        signal.signal(signal.SIGINT, old_handler)

    if interrupted["flag"]:
        return {"interrupted": True, "completed": completed_count, "total": total}

    # All rows succeeded — atomic-ish swap. Only now does the live table
    # move; a crash before this point leaves the old live table untouched
    # plus a (harmless, resumable-or-discardable) .next shadow dir.
    live_dir = _live_dir(pkb_root)
    live_dir.mkdir(parents=True, exist_ok=True)
    live_table = live_dir / "pkb_pages.lance"
    backup_path: str | None = None
    if live_table.exists():
        bak = live_dir / f"pkb_pages.lance.bak-{int(time.time())}"
        os.replace(live_table, bak)
        backup_path = str(bak)
    shadow_table = shadow_dir / "pkb_pages.lance"
    if shadow_table.exists():
        os.replace(shadow_table, live_table)

    pkb_provenance.write(
        live_dir, embedding_model=model.name, embedding_dim=EMBEDDING_DIM,
        spec_sha256=spec_sha, rows=completed_count)

    _clear_checkpoint(pkb_root)
    shutil.rmtree(shadow_dir, ignore_errors=True)

    try:
        from arail import pkb_index
        pkb_index.clear_degraded()
    except Exception:  # noqa: BLE001
        pass

    return {
        "interrupted": False, "completed": completed_count, "total": total,
        "backup": backup_path,
    }


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _default_progress(world_label: str):
    def _p(*, done: int, total: int, rate: float | None = None):
        if rate:
            eta = (total - done) / rate if rate > 0 else 0.0
            print(f"[{world_label}] {done}/{total} rows, {rate:.1f} rows/s, "
                  f"ETA {eta:.0f}s", flush=True)
        else:
            print(f"[{world_label}] {done}/{total} rows", flush=True)
    return _p


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m arail.pkb_reembed",
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pkb-root", required=True,
                   help="Absolute path to the PKB root to reembed.")
    p.add_argument("--world-label", default="root",
                   help="Label used in progress lines / activity events "
                        "(the arailctl dispatcher passes the world slug "
                        "or 'root').")
    p.add_argument("--resume", action="store_true",
                   help="Resume from the last checkpoint. Refuses if the "
                        "checkpoint's model/dim/spec disagree with the "
                        "current spec.")
    p.add_argument("--dry-run", action="store_true",
                   help="Print row count and an ETA from a 32-row timing "
                        "probe. Writes nothing.")
    p.add_argument("--yes", action="store_true",
                   help="Reserved for future confirmation prompts; "
                        "currently a no-op (this verb never prompts).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    pkb_root = Path(args.pkb_root)
    if not pkb_root.exists():
        print(f"error: pkb root {pkb_root} does not exist", file=sys.stderr)
        return 2

    from arail.dbspec.embed import EmbeddingError

    try:
        from arail.activity import activity_log
        activity_log.emit(
            "pkb", f"pkb reembed starting for '{args.world_label}'", "info")
    except Exception:  # noqa: BLE001
        pass

    try:
        result = run(pkb_root, resume=args.resume, dry_run=args.dry_run,
                      progress=_default_progress(args.world_label))
    except CheckpointSpecMismatch as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except EmbeddingError as e:
        print(f"error: {e}", file=sys.stderr)
        return 4
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"[{args.world_label}] dry-run: {result['total']} rows, "
              f"~{result['rows_per_sec']:.1f} rows/s, "
              f"ETA {result['eta_sec']:.0f}s — nothing written")
        return 0

    if result.get("interrupted"):
        print(f"\n[{args.world_label}] interrupted at "
              f"{result['completed']}/{result['total']} rows — checkpoint "
              f"saved. Resume with: ./arailctl pkb reembed ... --resume",
              file=sys.stderr)
        return 130

    print(f"[{args.world_label}] done: {result['completed']}/{result['total']} "
          f"rows re-embedded"
          + (f" (previous index backed up to {result['backup']})"
             if result.get("backup") else ""))
    try:
        from arail.activity import activity_log
        activity_log.emit(
            "pkb", f"pkb reembed finished for '{args.world_label}': "
                   f"{result['completed']} rows", "info")
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
