"""Atlas-free, codegen-free replay of the committed migration ledger.

``./arailctl db apply`` (see ``arail.dbspec.cli``/``atlas``) is a developer
tool: it shells out to the ``atlas`` binary, generates a new migration file
into ``spec/schema/migrations/``, lints it, and regenerates code into the
source tree. A user who clones the repo and runs ``./arailctl setup`` has
none of that installed and must never need it (Assumption 1,
sprints/2026-08-10-arail2-persistence-instantiated/ARCHITECTURE.md).

This module is the seamless path instead: it replays the already-committed,
already-lint-gated migration files in ``spec/schema/migrations/`` into a
per-data-dir SQLite file, using ``PRAGMA user_version`` as the applied-
migration cursor (Assumption 4 — invisible to ``atlas schema diff``, so it
adds no drift against ``spec/schema/schema.hcl``). It never authors a
migration, never invokes ``atlas``, never runs codegen, and never touches
Lance reconciliation or the 1.x->2.0 import — those stay behind their own
explicit verbs (§4.2 of ARCHITECTURE.md).

The safe/lossy line (§4.2)
---------------------------
SAFE-FORWARD  A checked-in migration, index > current ``user_version``, whose
              SQL contains no ``DROP TABLE``/``DROP INDEX``/``DROP COLUMN``/
              ``DELETE``/``UPDATE``/rename-based table-rebuild pattern.
              Applied automatically when ``apply=True``.
LOSSY         Any pending migration containing one of the statements above.
              Never applied by this module, ever — ``state="blocked"``,
              naming ``./arailctl db apply --allow-destructive``.
The classifier is a static regex over the raw SQL text. It intentionally
does not distinguish a real ``DROP TABLE`` from one that only appears inside
a SQL comment or a string literal — a false positive (classifying safe SQL
as lossy) is acceptable; a false negative (an actually-destructive statement
slipping through as safe) is not. It fails closed, never open (test 5).

Divergence detection
---------------------
"Hash matches the ledger" (§4.2) is implemented as *self-consistency*, not
literal parity with Atlas's own (undocumented, binary-only) migration
digest algorithm: the first time this module applies a migration file, it
records a plain sha256 of that file's bytes in a JSON sidecar next to the
database (``<data_dir>/.arail_ensure_state.json`` — the same pattern the
vector-index provenance sidecar already uses elsewhere in this codebase).
Every later call re-hashes the file and compares against what it recorded.
A mismatch is DIVERGED. This catches "someone edited an already-applied
migration file" without depending on the ``atlas`` binary (Assumption 1)
or adding an unspecced table to the SQLite schema (Assumption 4's
fallback would require adding a spec'd table; a sidecar file avoids that
entirely). Cross-checking against ``atlas.sum``'s own hash format is
explicitly out of scope here and is covered instead by the dev-only
"atlas schema diff" test (test 4) gated on the ``atlas`` binary being
present — see the "Architect feedback required" note in this sprint's
BUILD_LOG.md.

Write discipline (contract, §4.1)
----------------------------------
``apply=False`` performs **zero writes**: no file creation, no directory
creation, no PRAGMA writes, no ``sqlite3.connect(path)`` in the mode that
would create a missing file. ``status`` and ``doctor`` use only this mode.
This is the exact bug a previous sprint shipped in a read-only check; do
not reintroduce it (see the module test ``test_apply_false_is_write_free``
in ``tests/test_dbspec_ensure.py``, which snapshots the directory tree
before/after).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from arail.dbspec import db as dbmod

try:
    import fcntl  # posix only
except ImportError:  # pragma: no cover — non-posix
    fcntl = None

# F17: two processes/threads calling ensure_db(apply=True) on the same
# data_dir concurrently must both finish with a valid, correctly-versioned
# database — "last writer wins at the same version, both end ok, no
# corruption" (ARCHITECTURE.md F17). A thread-level lock keyed by data_dir
# handles the in-process case (concurrent Worlds are one-process-per-World,
# so this is the realistic case); an flock on a sidecar lock file extends
# the same guarantee across processes on POSIX, best-effort elsewhere.
_thread_locks: dict = {}
_thread_locks_guard = threading.Lock()


def _thread_lock_for(data_dir: Path) -> threading.Lock:
    key = str(data_dir)
    with _thread_locks_guard:
        lock = _thread_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _thread_locks[key] = lock
        return lock


@contextlib.contextmanager
def _apply_lock(data_dir: Path):
    data_dir.mkdir(parents=True, exist_ok=True)
    with _thread_lock_for(data_dir):
        if fcntl is None:
            yield
            return
        lock_path = data_dir / ".arail_ensure.lock"
        with open(lock_path, "a+") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

__all__ = ["EnsureReport", "ensure_db", "classify_migration", "MIGRATION_NAME_RE"]

SCHEMA = "arail.db-ensure/v1"

# Test 36: only files matching this pattern are ever eligible to be read as
# migrations — a path-traversal-ish name (``../../etc/passwd.sql``,
# ``00_x.sql``) is silently ignored, not executed.
MIGRATION_NAME_RE = re.compile(r"^\d{14}_[a-z0-9_]+\.sql$")

_SIDECAR_NAME = ".arail_ensure_state.json"

_LOSSY_RE = re.compile(
    r"(\bDROP\s+TABLE\b|\bDROP\s+INDEX\b|\bDROP\s+COLUMN\b|\bDELETE\s+FROM\b|"
    r"\bUPDATE\s+\S+\s+SET\b|\bALTER\s+TABLE\s+\S+\s+RENAME\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EnsureReport:
    schema: str
    data_dir: str
    db_path: str
    present: bool
    applied: list
    pending: list
    version: int
    spec_version: int
    spec_sha256: str
    state: str
    detail: str
    action: str


def classify_migration(sql_text: str) -> str:
    """"SAFE-FORWARD" or "LOSSY". Fails closed (test 5): a classifier that
    cannot prove a statement is safe must call it LOSSY, never the reverse.
    """
    if _LOSSY_RE.search(sql_text):
        return "LOSSY"
    return "SAFE-FORWARD"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migration_files(migrations_dir: Path) -> list:
    if not migrations_dir.is_dir():
        return []
    return sorted(
        p for p in migrations_dir.iterdir()
        if p.is_file() and MIGRATION_NAME_RE.match(p.name)
    )


def _split_statements(sql_text: str) -> list:
    parts = [s.strip() for s in sql_text.split(";")]
    return [s for s in parts if s]


def _sidecar_path(data_dir: Path) -> Path:
    return data_dir / _SIDECAR_NAME


def _load_sidecar(data_dir: Path) -> dict:
    path = _sidecar_path(data_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:  # noqa: BLE001 — a corrupt sidecar is not fatal
        return {}


def _save_sidecar(data_dir: Path, state: dict) -> None:
    path = _sidecar_path(data_dir)
    path.write_text(json.dumps(state, indent=2, sort_keys=True))


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_user_version_readonly(db_path: Path) -> int:
    """Open strictly read-only (``mode=ro``) — never creates the file, never
    writes a byte, even a ``-wal``/``-shm`` sidecar."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        row = conn.execute("PRAGMA user_version").fetchone()
        return int(row[0]) if row else 0
    finally:
        conn.close()


def _load_spec_meta(spec_dir: Path):
    """Returns (version, sha256) or (0, "") if the spec cannot be loaded.
    Never raises — a spec load failure becomes a state, not an exception
    (contract: ensure_db never raises to a caller)."""
    try:
        from arail.dbspec.spec import load_spec
        spec_obj = load_spec(spec_dir)
        return spec_obj.version, spec_obj.sha256
    except Exception:  # noqa: BLE001
        return 0, ""


def ensure_db(data_dir, *, apply: bool = False, spec_dir=None) -> EnsureReport:
    data_dir = Path(data_dir)
    spec_dir = Path(spec_dir) if spec_dir is not None else Path("spec")
    migrations_dir = spec_dir / "schema" / "migrations"
    db_path = dbmod.database_path(data_dir)
    present = db_path.exists()

    spec_version, spec_sha256 = _load_spec_meta(spec_dir)

    def _report(**kw) -> EnsureReport:
        base = dict(
            schema=SCHEMA, data_dir=str(data_dir), db_path=str(db_path),
            present=present, applied=[], pending=[], version=0,
            spec_version=spec_version, spec_sha256=spec_sha256,
            state="unavailable", detail="", action="",
        )
        base.update(kw)
        return EnsureReport(**base)

    if not migrations_dir.is_dir():
        return _report(
            state="unavailable",
            detail=f"no migrations directory at {migrations_dir}",
        )

    migrations = _migration_files(migrations_dir)
    if not migrations:
        return _report(
            state="unavailable",
            detail=f"no eligible migration files in {migrations_dir}",
        )

    # Read the current cursor without ever creating the file.
    if not db_path.exists():
        version = 0
    else:
        try:
            version = _read_user_version_readonly(db_path)
        except sqlite3.DatabaseError as exc:
            return _report(
                state="blocked",
                detail=f"cannot read {db_path}: {exc}",
                action="./arailctl doctor",
            )

    total = len(migrations)

    # AHEAD.
    if version > total:
        return _report(
            state="ahead", version=version,
            detail=(f"database is at schema v{version} but this checkout "
                    f"only knows {total} migration(s)"),
            action="update this checkout — this database was written by a "
                   "newer ARAIL",
        )

    # DIVERGED — check every migration this DB claims to have already
    # applied against the recorded sidecar hash, if we have one.
    sidecar = _load_sidecar(data_dir)
    for m in migrations[:version]:
        recorded = sidecar.get(m.name)
        if recorded is None:
            continue  # unknown provenance (e.g. applied by `db apply`) — not verifiable, not flagged
        if recorded != _file_hash(m):
            return _report(
                state="diverged", version=version,
                detail=f"{m.name} has changed since it was applied",
                action="./arailctl db plan",
            )

    pending_files = migrations[version:total]
    pending_names = [m.name for m in pending_files]

    if not apply:
        if not pending_files:
            return _report(state="ok" if present else "unavailable",
                            version=version, pending=[])
        first_class = classify_migration(pending_files[0].read_text())
        if first_class == "LOSSY":
            return _report(
                state="blocked", version=version, pending=pending_names,
                detail=f"{pending_files[0].name} contains statements that "
                       f"can remove or rewrite data",
                action="./arailctl db apply --allow-destructive",
            )
        return _report(state="pending", version=version, pending=pending_names,
                        detail="safe-forward migration(s) not yet applied",
                        action="./arailctl start, or ./arailctl install")

    # ---- apply=True ----
    try:
        with _apply_lock(data_dir):
            try:
                conn = dbmod.connect(data_dir, create=True)
            except dbmod.DatabaseError as exc:
                return _report(
                    state="blocked", version=version,
                    detail=str(exc), action="./arailctl doctor",
                )
            try:
                return _apply_locked(conn, data_dir, migrations, total, present,
                                     spec_version, spec_sha256, _report)
            finally:
                conn.close()
    except OSError as exc:
        # Unwritable data_dir (chmod 0500, etc): cannot even take the lock.
        return _report(
            state="blocked", version=version,
            detail=f"cannot write to {data_dir}: {exc}",
            action="./arailctl doctor",
        )


def _apply_locked(conn, data_dir, migrations, total, present,
                  spec_version, spec_sha256, _report) -> EnsureReport:
    # Re-read the cursor now that we hold the lock — this is the
    # authoritative value for this apply, immune to the TOCTOU race between
    # the earlier read-only pre-check and lock acquisition (F17).
    cur_version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    sidecar = _load_sidecar(data_dir)
    applied: list = []
    if True:
        for m in migrations[cur_version:total]:
            sql_text = m.read_text()
            if classify_migration(sql_text) == "LOSSY":
                break  # never auto-applied — stop, leave it (and everything
                       # after it) pending.
            statements = _split_statements(sql_text)
            next_version = cur_version + 1
            try:
                with dbmod.transaction(conn):
                    for stmt in statements:
                        conn.execute(stmt)
                    conn.execute(f"PRAGMA user_version = {next_version}")
            except sqlite3.Error as exc:
                # F2: per-file transaction rolled back; user_version stays
                # at the last fully-applied migration.
                return _report(
                    state="blocked", version=cur_version, applied=applied,
                    pending=[x.name for x in migrations[cur_version:total]],
                    detail=f"{m.name} failed to apply: {exc}",
                    action="./arailctl doctor",
                )
            sidecar[m.name] = _file_hash(m)
            _save_sidecar(data_dir, sidecar)
            applied.append(m.name)
            cur_version = next_version

        pending_now = [x.name for x in migrations[cur_version:total]]

        if applied and spec_version:
            dbmod.record_version(conn, spec_version, spec_sha256, _now_iso())

        if pending_now:
            # Stopped early because the next pending migration is LOSSY.
            state = "blocked"
            detail = (f"{migrations[cur_version].name} contains statements "
                      f"that can remove or rewrite data")
            action = "./arailctl db apply --allow-destructive"
        elif applied:
            state = "created" if not present else "updated"
            detail = ""
            action = ""
        else:
            state = "ok"
            detail = ""
            action = ""

        return _report(
            state=state, version=cur_version, applied=applied,
            pending=pending_now, detail=detail, action=action,
        )


def _report_line(report: "EnsureReport") -> str:
    """One human-readable line for a single root — the shape `install`'s
    per-root summary and `start`'s single line both use. Quiet boot
    (F10): the caller decides whether to print at all; this only decides
    the wording once it has decided to print."""
    if report.state in ("created", "updated"):
        verb = "created" if report.state == "created" else "applied"
        n = len(report.applied)
        plural = "" if n == 1 else "s"
        return (f"db: {verb} {n} migration{plural} at {report.db_path} "
                f"(schema v{report.version})")
    if report.state == "ok":
        return f"db: {report.db_path} — ok (schema v{report.version})"
    # blocked / ahead / diverged / unavailable
    detail = f" — {report.detail}" if report.detail else ""
    action = f" — run {report.action}" if report.action else ""
    return f"db: {report.db_path} — {report.state}{detail}{action}"


def main(argv=None) -> int:  # pragma: no cover — thin CLI shim, exercised
    # via scripts/install.sh and scripts/start.sh, not directly by pytest.
    """``python -m arail.dbspec.ensure <data_dir> [--apply]`` — the shell
    integration point for ``install``/``start``, so neither has to embed
    Python beyond a single ``python -m`` invocation (matches the existing
    ``python -m arail.compiled_kb bootstrap`` pattern in
    ``scripts/install.sh``). Exits 0 for ok/created/updated/pending
    (pending is not a hard failure — start still boots, per §4.5), and 3
    for blocked/ahead/diverged/unavailable, so a caller that cares can
    detect "did not come up clean" without parsing prose."""
    import argparse
    import sys as _sys

    ap = argparse.ArgumentParser(prog="python -m arail.dbspec.ensure")
    ap.add_argument("data_dir")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--spec-dir", default=None)
    ap.add_argument("--quiet-ok", action="store_true",
                    help="print nothing when state is 'ok' with nothing applied")
    ap.add_argument("--json", action="store_true",
                    help="print the EnsureReport as one JSON line instead "
                         "of the human summary — status/doctor's contract "
                         "with this CLI, never used by install/start")
    args = ap.parse_args(argv)

    report = ensure_db(args.data_dir, apply=args.apply, spec_dir=args.spec_dir)
    if args.json:
        import json as _json
        print(_json.dumps({
            "schema": report.schema, "data_dir": report.data_dir,
            "db_path": report.db_path, "present": report.present,
            "applied": report.applied, "pending": report.pending,
            "version": report.version, "spec_version": report.spec_version,
            "spec_sha256": report.spec_sha256, "state": report.state,
            "detail": report.detail, "action": report.action,
        }))
    elif not (args.quiet_ok and report.state == "ok" and not report.applied):
        print(_report_line(report))
    return 0 if report.state in ("ok", "created", "updated", "pending") else 3


if __name__ == "__main__":  # pragma: no cover
    import sys
    sys.exit(main())
