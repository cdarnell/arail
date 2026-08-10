"""Unit tests for arail.dbspec.ensure — tests 1-12 of
sprints/2026-08-10-arail2-persistence-instantiated/ARCHITECTURE.md §7.

No callers wired yet (recommended implementation order step 1): this is the
whole risk surface of the "seamless" DB path, so it lands proven first.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

from arail.dbspec.ensure import ensure_db, classify_migration, MIGRATION_NAME_RE

REPO_SPEC_DIR = Path(__file__).resolve().parents[1] / "spec"


def _snapshot(path: Path) -> set:
    if not path.exists():
        return set()
    return {
        (str(p.relative_to(path)), p.stat().st_size if p.is_file() else None)
        for p in path.rglob("*")
    }


# ── 1. apply=False on empty dir is write-free ──────────────────────────────

def test_apply_false_on_empty_dir_is_pending_and_write_free(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    before = _snapshot(d)
    report = ensure_db(d, apply=False, spec_dir=REPO_SPEC_DIR)
    after = _snapshot(d)

    assert report.present is False
    assert after == before, "apply=False must perform zero writes"
    assert report.state in ("pending", "unavailable")


# ── 2. apply=True on empty dir creates the db ───────────────────────────────

def test_apply_true_on_empty_dir_creates_db(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    report = ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)

    assert report.state == "created"
    db_path = d / "arail.db"
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    try:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == report.version
        row = conn.execute(
            "SELECT version, spec_sha256 FROM schema_version "
            "ORDER BY version DESC LIMIT 1").fetchone()
        assert row is not None
        assert row[1] == report.spec_sha256
    finally:
        conn.close()


# ── 3. idempotence ──────────────────────────────────────────────────────────

def test_apply_true_idempotent(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)
    second = ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)

    assert second.state == "ok"
    assert second.applied == []


# ── 5. lossy classifier, table-driven ──────────────────────────────────────

@pytest.mark.parametrize("sql,expected", [
    ("DROP TABLE x;", "LOSSY"),
    ("ALTER TABLE x DROP COLUMN y;", "LOSSY"),
    ("DELETE FROM worlds;", "LOSSY"),
    ("UPDATE worlds SET status = 'x';", "LOSSY"),
    ("CREATE TABLE new_x (id text); INSERT INTO new_x SELECT * FROM x; "
     "DROP TABLE x; ALTER TABLE new_x RENAME TO x;", "LOSSY"),
    ("CREATE TABLE x (id text);", "SAFE-FORWARD"),
    ("CREATE INDEX idx_x ON x (id);", "SAFE-FORWARD"),
    ("ALTER TABLE x ADD COLUMN y text;", "SAFE-FORWARD"),
    # Fail-closed cases: a lossy statement inside a comment or a string
    # literal is ALLOWED to false-positive as LOSSY (never allowed to
    # false-negative as safe).
    ("-- DROP TABLE x;\nCREATE TABLE y (id text);", "LOSSY"),
    ("CREATE TABLE y (id text, note text DEFAULT 'DROP TABLE x');", "LOSSY"),
])
def test_lossy_classifier_table_driven(sql, expected):
    assert classify_migration(sql) == expected


# ── 6. ahead ────────────────────────────────────────────────────────────────

def test_user_version_ahead_of_ledger(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)
    conn = sqlite3.connect(d / "arail.db")
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    before = _snapshot(d)
    report = ensure_db(d, apply=False, spec_dir=REPO_SPEC_DIR)
    after = _snapshot(d)

    assert report.state == "ahead"
    assert after == before


def test_user_version_ahead_apply_true_makes_no_writes(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)
    conn = sqlite3.connect(d / "arail.db")
    conn.execute("PRAGMA user_version = 999")
    conn.close()

    report = ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)
    assert report.state == "ahead"
    assert report.applied == []


# ── 7. diverged ─────────────────────────────────────────────────────────────

def test_diverged_migration_file_mutated(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    spec_copy = tmp_path / "spec"
    _copy_spec(spec_copy)
    ensure_db(d, apply=True, spec_dir=spec_copy)

    mig = next((spec_copy / "schema" / "migrations").glob("*.sql"))
    mig.write_text(mig.read_text() + "\n-- tampered\n")

    before = _snapshot(d)
    report = ensure_db(d, apply=False, spec_dir=spec_copy)
    after = _snapshot(d)

    assert report.state == "diverged"
    assert after == before


def _copy_spec(dest: Path) -> None:
    import shutil
    shutil.copytree(REPO_SPEC_DIR, dest)


# ── 8. failure isolation ────────────────────────────────────────────────────

def test_failure_isolation_bad_migration(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    spec_copy = tmp_path / "spec"
    _copy_spec(spec_copy)
    migrations_dir = spec_copy / "schema" / "migrations"

    # Migration 2: syntactically broken SQL.
    (migrations_dir / "20260808155712_broken.sql").write_text(
        "CREATE TBLE this_is_not_valid_sql (;")
    # Migration 3: would otherwise be fine.
    (migrations_dir / "20260808155713_third.sql").write_text(
        "CREATE TABLE third_table (id text);")

    report = ensure_db(d, apply=True, spec_dir=spec_copy)

    assert report.state == "blocked"
    assert report.applied == ["20260808155711_baseline.sql"]
    conn = sqlite3.connect(d / "arail.db")
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        # migration 2's DDL never landed.
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "third_table" not in tables
    finally:
        conn.close()


# ── 9. no atlas/lancedb/embed imported ──────────────────────────────────────

def test_ensure_does_not_import_atlas_lancedb_or_embed(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    for mod in ("atlas", "lancedb", "arail.dbspec.atlas", "arail.dbspec.embed"):
        sys.modules.pop(mod, None)

    ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)

    assert "lancedb" not in sys.modules
    assert "arail.dbspec.atlas" not in sys.modules
    assert "arail.dbspec.embed" not in sys.modules


# ── 10. unwritable data_dir ─────────────────────────────────────────────────

@pytest.mark.skipif(os.name == "nt", reason="posix permissions only")
def test_unwritable_data_dir_blocked(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    d.chmod(0o500)
    try:
        report = ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)
    finally:
        d.chmod(0o700)

    assert report.state == "blocked"
    assert report.action


# ── 11. truncated/garbage arail.db ─────────────────────────────────────────

def test_truncated_db_blocked_and_untouched(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    db_path = d / "arail.db"
    db_path.write_bytes(b"not a sqlite file at all")
    before = db_path.read_bytes()

    report = ensure_db(d, apply=False, spec_dir=REPO_SPEC_DIR)

    assert report.state == "blocked"
    assert db_path.read_bytes() == before


def test_truncated_db_blocked_apply_true_never_deletes(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    db_path = d / "arail.db"
    db_path.write_bytes(b"not a sqlite file at all")
    before = db_path.read_bytes()

    report = ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR)

    assert report.state == "blocked"
    assert db_path.exists()
    assert db_path.read_bytes() == before


# ── 12. concurrency ──────────────────────────────────────────────────────────

def test_concurrent_apply_both_finish_ok(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    results = []

    def _run():
        results.append(ensure_db(d, apply=True, spec_dir=REPO_SPEC_DIR))

    t1 = threading.Thread(target=_run)
    t2 = threading.Thread(target=_run)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    for r in results:
        assert r.state in ("created", "updated", "ok")

    conn = sqlite3.connect(d / "arail.db")
    try:
        ver = conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == 1
        conn.execute("SELECT 1 FROM schema_version").fetchone()
    finally:
        conn.close()


# ── misc contract checks ────────────────────────────────────────────────────

def test_migration_name_regex_rejects_traversal():
    assert MIGRATION_NAME_RE.match("20260808155711_baseline.sql")
    assert not MIGRATION_NAME_RE.match("../../etc/passwd.sql")
    assert not MIGRATION_NAME_RE.match("00_x.sql")
    assert not MIGRATION_NAME_RE.match("20260808155711_Baseline.sql")


def test_unavailable_when_no_migrations_dir(tmp_path: Path):
    d = tmp_path / "data"
    d.mkdir()
    empty_spec = tmp_path / "spec_empty"
    (empty_spec / "schema" / "migrations").mkdir(parents=True)
    report = ensure_db(d, apply=False, spec_dir=empty_spec)
    assert report.state == "unavailable"
    assert not (d / "arail.db").exists()
