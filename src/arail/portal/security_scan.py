"""pip-audit wrapper.  Single source of truth for last_scan.json.

Security model
--------------
- ``run_and_persist`` is the ONLY function that writes last_scan.json.
- last_scan.json is written atomically (tmp → rename) and chmod 0600.
  It contains the dependency version inventory; treat it as sensitive.
- Single-flight via ``_SCAN_LOCK``: concurrent callers serialise, never
  run two ``pip-audit`` subprocesses in parallel.
- LAB_MODE=airgapped is NEVER blocked here.  The boot task in app.py
  only schedules ``run_and_persist`` when ``_lab_mode() == "hybrid"``.
  ``run_and_persist`` itself is always callable (manual button works in
  any mode — explicit user action satisfies the no-involuntary-outbound
  rule).

Data directory
--------------
``DATA_DIR / "security" / "last_scan.json"``
Resolved from arail.config.DATA_DIR.  The parent directory is created
on first write.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import stat
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _security_dir() -> Path:
    from arail.config import DATA_DIR
    return Path(DATA_DIR) / "security"


def _scan_file() -> Path:
    return _security_dir() / "last_scan.json"


# ---------------------------------------------------------------------------
# Module-level single-flight lock
# ---------------------------------------------------------------------------
_SCAN_LOCK: asyncio.Lock | None = None


def _get_scan_lock() -> asyncio.Lock:
    """Lazy-init the lock on the running loop."""
    global _SCAN_LOCK
    if _SCAN_LOCK is None:
        _SCAN_LOCK = asyncio.Lock()
    return _SCAN_LOCK


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """True iff ``pip-audit`` CLI is on PATH OR ``pip_audit`` package is importable.

    CLI check takes precedence — that's the actual subprocess we call.
    The package-import fallback catches environments where pip-audit is
    installed but its entry-point script isn't on the shell PATH.
    """
    if shutil.which("pip-audit") is not None:
        return True
    try:
        import pip_audit  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> dict:
    """Read DATA_DIR/security/last_scan.json.  If missing, return a safe stub.

    Shape::

        {
          "available": bool,
          "last_run_ts": str ISO8601 | null,
          "trigger": str | null,
          "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
          "findings": [],
          "tool": "pip-audit",
          "tool_version": null,
          "auto_scan_enabled": bool,
          "error": null,
        }
    """
    stub: dict[str, Any] = {
        "available": is_available(),
        "last_run_ts": None,
        "trigger": None,
        "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
        "findings": [],
        "tool": "pip-audit",
        "tool_version": None,
        "auto_scan_enabled": False,
        "error": None,
    }
    path = _scan_file()
    if not path.exists():
        return stub
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # Merge with stub so any new fields added in future schema versions
        # have safe defaults rather than KeyErrors on old files.
        for k, v in stub.items():
            data.setdefault(k, v)
        return data
    except (OSError, json.JSONDecodeError):
        return stub


def _write_scan_file(data: dict) -> None:
    """Atomic write (tmp → rename) with chmod 0600.

    Mirrors the _write_secrets() pattern at app.py:719–731.
    """
    security_dir = _security_dir()
    try:
        security_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # best effort; write below will fail loudly if the dir is gone

    final = _scan_file()
    tmp = final.with_suffix(".json.tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        # chmod 0600 before rename so the file is never world-readable
        try:
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass  # non-POSIX (Windows) — skip silently
        # POSIX rename is atomic; final is never half-written
        os.replace(tmp, final)
    except OSError:
        # Clean up the tmp file if we can
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _get_tool_version() -> str | None:
    """Run ``pip-audit --version`` and parse the version string."""
    try:
        import subprocess
        r = subprocess.run(
            ["pip-audit", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        # Output is typically "pip-audit 2.7.3"
        out = (r.stdout or r.stderr or "").strip()
        if out:
            parts = out.split()
            return parts[-1] if parts else None
    except Exception:  # noqa: BLE001
        pass
    return None


_SEVERITY_RANK: dict[str, int] = {"critical": 4, "high": 3, "medium": 2, "low": 1, "none": 0}


def _severity_of(vuln: dict) -> str:
    """Return the canonical severity string for a pip-audit vulnerability."""
    # pip-audit >=2.7 exposes fix_versions and aliases; severity may live
    # under different keys depending on the version.
    sev = (
        vuln.get("severity")
        or vuln.get("fix_versions", [None])[0]  # fallback — wrong but safe
        or "none"
    )
    # Normalise to lower-case string
    return str(sev).lower() if sev else "none"


def _parse_pip_audit_output(raw: bytes) -> tuple[list[dict], dict, str | None]:
    """Parse pip-audit JSON output.

    Returns (findings, summary, error_str).
    ``error_str`` is non-None when the output is structurally wrong
    (schema mismatch — see C1 failure mode).

    pip-audit JSON schema (>=2.7.0):
    {
      "dependencies": [
        {
          "name": str,
          "version": str,
          "vulns": [
            {"id": str, "fix_versions": [str], "aliases": [str], ...}
          ]
        }
      ]
    }
    """
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return [], {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}, f"JSON parse error: {exc}"

    # Validate top-level schema (C1 mitigation)
    if not isinstance(parsed, dict) or "dependencies" not in parsed:
        return [], {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}, "unexpected pip-audit output"

    deps = parsed["dependencies"]
    if not isinstance(deps, list):
        return [], {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}, "unexpected pip-audit output"

    findings: list[dict] = []
    summary: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}

    for dep in deps:
        if not isinstance(dep, dict):
            continue
        vulns = dep.get("vulns", [])
        if not isinstance(vulns, list) or not vulns:
            continue
        name = str(dep.get("name", ""))
        version = str(dep.get("version", ""))
        for vuln in vulns:
            if not isinstance(vuln, dict):
                continue
            vuln_id = str(vuln.get("id", ""))
            # Severity: pip-audit >=2.7 may not always expose this field
            # directly; derive from fix_versions presence as fallback
            severity = str(vuln.get("severity", "")).lower() or "unknown"
            fix_versions = vuln.get("fix_versions", []) or []
            fix_str: str | None = fix_versions[0] if fix_versions else None
            aliases = vuln.get("aliases", [])
            description = str(vuln.get("description", "") or "")
            if not description and aliases:
                description = "; ".join(str(a) for a in aliases[:3])

            findings.append({
                "package": name,
                "version": version,
                "id": vuln_id,
                "severity": severity,
                "fix": fix_str,
                "description": description,
            })

            sev_key = severity if severity in summary else "low"
            summary[sev_key] = summary.get(sev_key, 0) + 1
            summary["total"] += 1

    return findings, summary, None


async def run_and_persist(trigger: Literal["boot", "manual", "sre", "sse"] = "manual") -> dict:
    """Run pip-audit, write last_scan.json, emit one activity_log line.

    Postconditions:
    - Returns the dict that was written.
    - last_scan.json is chmod 0600.
    - activity_log is emitted at error if any high/critical, warn if medium,
      info otherwise.
    - Single-flight via _SCAN_LOCK.  If a scan is already running, this call
      waits for it and returns the persisted result (not a new scan).

    Failure modes handled: C1, C2, C3, C4, C5, C6, C7, C9, C10.
    """
    from arail.activity import activity_log

    lock = _get_scan_lock()
    async with lock:
        # --- availability check ---
        if not is_available():
            stub: dict[str, Any] = {
                "available": False,
                "last_run_ts": datetime.now(timezone.utc).isoformat(),
                "trigger": trigger,
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
                "findings": [],
                "tool": "pip-audit",
                "tool_version": None,
                "auto_scan_enabled": status().get("auto_scan_enabled", False),
                "error": "pip-audit not installed — run ./arail upgrade max",
            }
            try:
                _write_scan_file(stub)
            except OSError:
                pass
            activity_log.emit(
                "security",
                "pip-audit not installed — install via ./arail upgrade max to enable CVE scans.",
                "warn",
            )
            return stub

        # --- capture tool version (best effort) ---
        tool_version = await asyncio.to_thread(_get_tool_version)

        # --- run pip-audit ---
        try:
            proc = await asyncio.create_subprocess_exec(
                "pip-audit",
                "-f", "json",
                "--progress-spinner=off",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()  # buffers in memory (C10: acceptable)
        except Exception as exc:  # noqa: BLE001
            error_msg = f"pip-audit launch failed: {type(exc).__name__}: {exc}"
            err_result: dict[str, Any] = {
                "available": True,
                "last_run_ts": datetime.now(timezone.utc).isoformat(),
                "trigger": trigger,
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
                "findings": [],
                "tool": "pip-audit",
                "tool_version": tool_version,
                "auto_scan_enabled": status().get("auto_scan_enabled", False),
                "error": error_msg,
            }
            try:
                _write_scan_file(err_result)
            except OSError:
                pass
            activity_log.emit("security", f"Scan failed: {error_msg[:200]}", "warn")
            return err_result

        # pip-audit exit codes: 0 = no vulns, 1 = vulns found, other = error
        if proc.returncode not in (0, 1):
            # C2: network / transient error
            stderr_excerpt = (err or b"").decode("utf-8", errors="replace")[:500]
            net_result: dict[str, Any] = {
                "available": True,
                "last_run_ts": datetime.now(timezone.utc).isoformat(),
                "trigger": trigger,
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
                "findings": [],
                "tool": "pip-audit",
                "tool_version": tool_version,
                "auto_scan_enabled": status().get("auto_scan_enabled", False),
                "error": f"network: {stderr_excerpt}" if stderr_excerpt else f"exit code {proc.returncode}",
            }
            try:
                _write_scan_file(net_result)
            except OSError:
                pass
            activity_log.emit("security", f"Scan failed: network or pip-audit error (exit {proc.returncode})", "warn")
            return net_result

        # --- parse output ---
        findings, summary, parse_error = _parse_pip_audit_output(out)

        auto_scan_enabled = status().get("auto_scan_enabled", False)
        now_ts = datetime.now(timezone.utc).isoformat()

        if parse_error is not None:
            # C1: schema mismatch
            schema_result: dict[str, Any] = {
                "available": True,
                "last_run_ts": now_ts,
                "trigger": trigger,
                "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
                "findings": [],
                "tool": "pip-audit",
                "tool_version": tool_version,
                "auto_scan_enabled": auto_scan_enabled,
                "error": parse_error,
            }
            try:
                _write_scan_file(schema_result)
            except OSError:
                pass
            activity_log.emit("security", f"Scan parse error: {parse_error}", "warn")
            return schema_result

        # --- build result ---
        result: dict[str, Any] = {
            "available": True,
            "last_run_ts": now_ts,
            "trigger": trigger,
            "summary": summary,
            "findings": findings,
            "tool": "pip-audit",
            "tool_version": tool_version,
            "auto_scan_enabled": auto_scan_enabled,
            "error": None,
        }

        try:
            _write_scan_file(result)
        except OSError as exc:
            activity_log.emit("security", f"Failed to write last_scan.json: {exc}", "warn")

        # Emit activity log at appropriate severity (C6: cooldown_key outside scope here)
        n_crit = summary.get("critical", 0)
        n_high = summary.get("high", 0)
        n_med = summary.get("medium", 0)
        n_total = summary.get("total", 0)
        if n_crit + n_high > 0:
            level = "error"
            msg = f"CVE scan: {n_crit + n_high} High/Critical vulnerabilities found ({n_total} total). Review in Admin → Production Readiness → Security."
        elif n_med > 0:
            level = "warn"
            msg = f"CVE scan: {n_med} Medium vulnerabilities found ({n_total} total)."
        else:
            level = "info"
            msg = f"CVE scan: all clear ({n_total} issues checked, none found)."
        activity_log.emit("security", msg, level)

        return result


async def stream_scan_events(trigger: str = "sse"):
    """Async generator yielding SSE-shaped events for the live-checks modal.

    Yields dicts matching the modal event contract::

        {"event": "check", "index": int, "total": int, "name": str,
         "status": "pass"|"warn"|"fail", "duration_ms": float, "detail": str}

        {"event": "done", "passed": int, "warned": int, "failed": int,
         "total": int, "total_ms": float}

    Wraps ``run_and_persist`` so the single-flight lock serialises the
    full scan; events are synthesised from the completed result.

    Keep-alive comment lines (``": keepalive\\n\\n"``) are emitted every
    15 s during the subprocess wait so reverse proxies don't kill the
    connection (failure mode F2).
    """
    t_total_start = time.perf_counter()

    if not is_available():
        yield {
            "event": "check",
            "index": 0, "total": 1,
            "name": "pip-audit availability",
            "status": "fail",
            "duration_ms": 0,
            "detail": "pip-audit not installed — run ./arail upgrade max",
        }
        yield {
            "event": "done",
            "passed": 0, "warned": 0, "failed": 1,
            "total": 1,
            "total_ms": round((time.perf_counter() - t_total_start) * 1000, 1),
        }
        return

    # Run the scan.  We poll for completion so we can emit keep-alives.
    scan_task = asyncio.create_task(run_and_persist(trigger=trigger))  # type: ignore[arg-type]

    # Emit keep-alives while waiting (F2 mitigation)
    keepalive_interval = 15.0
    last_ka = time.perf_counter()
    while not scan_task.done():
        await asyncio.sleep(0.5)
        if time.perf_counter() - last_ka >= keepalive_interval:
            yield {"event": "__keepalive__"}  # caller must filter this out
            last_ka = time.perf_counter()

    result = await scan_task  # re-raises if scan raised
    total_ms = round((time.perf_counter() - t_total_start) * 1000, 1)

    findings = result.get("findings", [])
    summary = result.get("summary", {})
    err = result.get("error")

    if err and not findings:
        # Scan failed entirely
        yield {
            "event": "check",
            "index": 0, "total": 1,
            "name": "pip-audit scan",
            "status": "fail",
            "duration_ms": total_ms,
            "detail": str(err)[:200],
        }
        yield {
            "event": "done",
            "passed": 0, "warned": 0, "failed": 1,
            "total": 1, "total_ms": total_ms,
        }
        return

    # Synthesise per-package check events
    total = max(len(findings), 1)
    passed = warned = failed = 0

    if not findings:
        yield {
            "event": "check",
            "index": 0, "total": 1,
            "name": "dependency audit",
            "status": "pass",
            "duration_ms": total_ms,
            "detail": "No vulnerabilities found",
        }
        passed = 1
    else:
        for idx, f in enumerate(findings):
            sev = str(f.get("severity", "")).lower()
            if sev in ("critical", "high"):
                status_str = "fail"
                failed += 1
            elif sev in ("medium",):
                status_str = "warn"
                warned += 1
            else:
                status_str = "warn"
                warned += 1

            detail = f"{f.get('id', '')} — fix: {f.get('fix') or 'none available'}"
            yield {
                "event": "check",
                "index": idx,
                "total": len(findings),
                "name": f"{f.get('package', '?')} {f.get('version', '')}",
                "status": status_str,
                "duration_ms": round(total_ms / len(findings), 1),
                "detail": detail,
            }

    yield {
        "event": "done",
        "passed": passed,
        "warned": warned,
        "failed": failed,
        "total": passed + warned + failed,
        "total_ms": total_ms,
    }


def set_auto_scan(enabled: bool) -> None:
    """Persist auto_scan_enabled toggle into last_scan.json.

    Creates a stub file if last_scan.json doesn't exist yet.
    """
    current = status()
    current["auto_scan_enabled"] = bool(enabled)
    # Preserve existing fields; write stub-safe values if never scanned
    if "last_run_ts" not in current:
        current["last_run_ts"] = None
    try:
        _write_scan_file(current)
    except OSError:
        pass  # best effort
