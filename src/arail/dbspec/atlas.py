"""Atlas CLI wrapper — the compiler for ``spec/schema``.

Atlas owns the relational half of the spec: it diffs declared HCL against the
live SQLite file and emits the DDL. This module shells out to the binary and
turns its output into structured results.

One honesty note that shapes the design. Since Atlas v0.38, ``atlas migrate
lint`` is gated behind an Atlas Pro login: without one it prints an ``Abort:``
and exits non-zero *without linting anything*. Treating that as "lint failed"
would block every apply on a machine that has never logged in, and treating it
as success would claim a gate ran when it did not. So :func:`lint_migrations`
reports which gate actually ran, and the caller prints it. When Atlas lint is
unavailable we run a local destructive-statement gate instead — narrower than
real lint, and labelled as such wherever it appears.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

__all__ = [
    "AtlasError", "AtlasNotInstalled", "atlas_binary", "atlas_version",
    "schema_diff", "schema_apply", "migrate_diff", "lint_migrations",
    "LintResult", "DESTRUCTIVE_SQL",
]

_DEV_URL = "sqlite://dev?mode=memory"

# Statements that destroy or rewrite data. The local gate blocks these; real
# Atlas lint additionally catches subtler hazards (backward-incompatible
# changes, data-dependent constraint additions), which is why we say plainly
# when only the local gate ran.
DESTRUCTIVE_SQL = (
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+INDEX\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\b", re.IGNORECASE),
)


class AtlasError(RuntimeError):
    """An Atlas invocation failed. Message includes Atlas's own output."""


class AtlasNotInstalled(AtlasError):
    def __init__(self) -> None:
        super().__init__(
            "the 'atlas' binary was not found on PATH.\n"
            "Install it with:  brew install ariga/tap/atlas\n"
            "Or set ARAIL_ATLAS_BIN to its full path."
        )


def atlas_binary() -> str:
    override = os.getenv("ARAIL_ATLAS_BIN")
    if override:
        if not Path(override).is_file():
            raise AtlasError(
                f"ARAIL_ATLAS_BIN points at {override}, which is not a file")
        return override
    found = shutil.which("atlas") or "/opt/homebrew/bin/atlas"
    if not Path(found).is_file():
        raise AtlasNotInstalled()
    return found


def _run(args: Sequence[str], *, cwd: Optional[Path] = None
         ) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [atlas_binary(), *args], capture_output=True, text=True,
            cwd=str(cwd) if cwd else None, check=False, timeout=120)
    except subprocess.TimeoutExpired as exc:
        raise AtlasError(f"atlas {' '.join(args)} timed out after 120s") from exc
    except OSError as exc:
        raise AtlasError(f"cannot execute atlas: {exc}") from exc


def atlas_version() -> str:
    proc = _run(["version"])
    first = (proc.stdout or proc.stderr).strip().splitlines()
    return first[0] if first else "unknown"


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite://{db_path}"


def _file_url(path: Path) -> str:
    return f"file://{path.resolve()}"


def schema_diff(db_path: Path, schema_hcl: Path) -> List[str]:
    """SQL statements that would bring ``db_path`` up to ``schema_hcl``.

    Empty list means the database already matches the spec.
    """
    proc = _run(["schema", "diff",
                 "--from", _sqlite_url(db_path),
                 "--to", _file_url(schema_hcl),
                 "--dev-url", _DEV_URL,
                 "--format", "{{ sql . }}"])
    if proc.returncode != 0:
        raise AtlasError(
            f"atlas schema diff failed (exit {proc.returncode}):\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    text = proc.stdout.strip()
    if not text or "Schemas are synced" in text:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def schema_apply(db_path: Path, schema_hcl: Path) -> str:
    """Apply the declared schema. Returns Atlas's report."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    proc = _run(["schema", "apply",
                 "--url", _sqlite_url(db_path),
                 "--to", _file_url(schema_hcl),
                 "--dev-url", _DEV_URL,
                 "--auto-approve"])
    if proc.returncode != 0:
        raise AtlasError(
            f"atlas schema apply failed (exit {proc.returncode}):\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def migrate_diff(name: str, schema_hcl: Path, migrations_dir: Path) -> Optional[Path]:
    """Generate a versioned migration. Returns its path, or None if in sync."""
    migrations_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in migrations_dir.glob("*.sql")}
    proc = _run(["migrate", "diff", name,
                 "--to", _file_url(schema_hcl),
                 "--dev-url", _DEV_URL,
                 "--dir", _file_url(migrations_dir)])
    if proc.returncode != 0:
        raise AtlasError(
            f"atlas migrate diff failed (exit {proc.returncode}):\n"
            f"{proc.stderr.strip() or proc.stdout.strip()}")
    after = {p.name for p in migrations_dir.glob("*.sql")}
    new = sorted(after - before)
    if not new:
        return None
    return migrations_dir / new[-1]


@dataclass(frozen=True)
class LintResult:
    """Outcome of the migration lint gate.

    ``gate`` is ``"atlas"`` when real Atlas lint ran, ``"local"`` when it was
    unavailable and the narrower destructive-statement gate ran instead. The
    distinction is printed, never hidden: a gate that did not run must not
    look like a gate that passed.
    """
    ok: bool
    gate: str
    findings: tuple[str, ...]
    detail: str = ""

    def render(self) -> str:
        if self.gate == "atlas":
            header = "migration lint (atlas migrate lint)"
        else:
            header = ("migration lint (LOCAL destructive-statement gate — "
                      "`atlas migrate lint` requires an Atlas Pro login and "
                      "did not run)")
        lines = [f"{header}: {'PASS' if self.ok else 'BLOCKED'}"]
        lines.extend(f"  - {f}" for f in self.findings)
        if self.detail:
            lines.append(f"  {self.detail}")
        return "\n".join(lines)


_PRO_REQUIRED = re.compile(r"atlas\s+login|Atlas\s+Pro", re.IGNORECASE)


def _local_lint(migration: Path) -> LintResult:
    try:
        sql = migration.read_text(encoding="utf-8")
    except OSError as exc:
        return LintResult(False, "local", (f"cannot read {migration}: {exc}",))
    findings = [
        f"{migration.name}: contains {pattern.pattern.strip()} — destructive"
        for pattern in DESTRUCTIVE_SQL if pattern.search(sql)
    ]
    return LintResult(
        ok=not findings, gate="local", findings=tuple(findings),
        detail=("Run `atlas login` to enable full Atlas lint, which also "
                "catches backward-incompatible and data-dependent changes."),
    )


def lint_migrations(migrations_dir: Path, *,
                    latest: int = 1) -> LintResult:
    """Lint the most recent migration(s). Failures block the caller."""
    migrations = sorted(migrations_dir.glob("*.sql"))
    if not migrations:
        return LintResult(True, "atlas", (), "no migrations to lint")

    proc = _run(["migrate", "lint",
                 "--dir", _file_url(migrations_dir),
                 "--dev-url", _DEV_URL,
                 "--latest", str(latest)])
    combined = f"{proc.stdout}\n{proc.stderr}"

    if proc.returncode != 0 and _PRO_REQUIRED.search(combined):
        return _local_lint(migrations[-1])

    if proc.returncode != 0:
        findings = [ln.strip() for ln in combined.splitlines() if ln.strip()]
        return LintResult(False, "atlas", tuple(findings[:20]))

    return LintResult(True, "atlas", ())
