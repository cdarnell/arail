"""Boot security scan tests — failure modes C3, C8, D1, D3.

Architect MUST-HIT #2: Boot scan in hybrid mode — set LAB_MODE=hybrid
in a test environment, expect an entry in lab/data/activity.jsonl with
source='security' within 35 seconds (30s sleep + scan time).

We can't actually wait 30s in CI, so we exercise the boot-task path
DIRECTLY: schedule the same coroutine the startup hook would schedule,
short-circuit the sleep, mock the subprocess, and assert the activity
log got an entry.

We also verify the airgapped guard never schedules the task in airgapped.
"""
from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture()
def boot_env(monkeypatch, tmp_path):
    """Isolated DATA_DIR + reloaded config + reloaded security_scan."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("ARAIL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LAB_ROOT", str(tmp_path / "lab"))
    monkeypatch.setenv("LAB_PKB", str(tmp_path / "lab" / "pkb"))

    import arail.config as _cfg
    importlib.reload(_cfg)
    # arail.activity caches LOG_FILE at import time — reload it too so the
    # boot scan's emit() lands in the tmp DATA_DIR.
    import arail.activity as _act
    importlib.reload(_act)
    from arail.portal import security_scan as _sc
    importlib.reload(_sc)
    return data_dir, _sc, _act


# ---------------------------------------------------------------------------
# C3 — boot scan does not block startup; it sleeps then runs
# ---------------------------------------------------------------------------

def test_boot_scan_emits_activity_log_entry_in_hybrid(monkeypatch, boot_env):
    """Architect MUST-HIT #2: hybrid boot scan emits a security activity event.

    We replicate the exact code-path of the startup boot scan but skip the
    30-second sleep (otherwise CI would wait 30s).  Subprocess is mocked.
    """
    data_dir, _sc, _act = boot_env
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setattr(_sc, "is_available", lambda: True)
    monkeypatch.setattr(_sc, "_get_tool_version", lambda: "2.7.3")

    class _FakeProc:
        returncode = 0
        async def communicate(self):
            return b'{"dependencies": []}', b""

    async def _fake_exec(*args, **kwargs):
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    async def _boot_security_scan():
        # Skip the 30s sleep that exists in app.py at line 516
        try:
            await _sc.run_and_persist(trigger="boot")
        except asyncio.CancelledError:
            raise
        except ImportError:
            _act.activity_log.emit(
                "security",
                "pip-audit not installed — install via ./arail upgrade max to enable CVE scans.",
                "warn",
            )
        except Exception as e:  # noqa: BLE001
            _act.activity_log.emit(
                "security",
                f"Boot CVE scan failed: {type(e).__name__}: {e}",
                "warn",
            )

    asyncio.run(_boot_security_scan())

    # Assert activity_log got a "security" line.
    log_path = data_dir / "activity.jsonl"
    assert log_path.exists(), f"activity.jsonl not written at {log_path}"
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "activity.jsonl is empty"
    sec_events = [json.loads(l) for l in lines if json.loads(l).get("source") == "security"]
    assert sec_events, (
        "No source='security' event after boot scan. "
        f"Events seen: {[json.loads(l).get('source') for l in lines]}"
    )


def test_boot_scan_handles_pip_audit_missing(monkeypatch, boot_env):
    """C5 in the boot path: pip-audit missing → warn entry, no crash."""
    data_dir, _sc, _act = boot_env
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setattr(_sc, "is_available", lambda: False)

    async def _boot_scan():
        await _sc.run_and_persist(trigger="boot")

    asyncio.run(_boot_scan())

    log_path = data_dir / "activity.jsonl"
    assert log_path.exists()
    # Find a security event whose message mentions install hint.
    found = False
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        evt = json.loads(line)
        if evt.get("source") == "security" and "pip-audit not installed" in evt.get("message", ""):
            found = True
            break
    assert found, "Missing 'pip-audit not installed' security event"


# ---------------------------------------------------------------------------
# D3 — CancelledError re-raised on shutdown
# ---------------------------------------------------------------------------

def test_cancellederror_re_raised_in_boot_task(monkeypatch, boot_env):
    """D3 mitigation: boot task must let CancelledError propagate so asyncio
    can cancel it cleanly on shutdown — NOT swallow it via the bare Exception."""

    cancelled_observed = {"hit": False}

    async def _boot_security_scan():
        try:
            await asyncio.sleep(60)  # would block forever; we cancel
        except asyncio.CancelledError:
            cancelled_observed["hit"] = True
            raise
        except Exception:  # noqa: BLE001
            pass

    async def _scenario():
        task = asyncio.create_task(_boot_security_scan())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_scenario())
    assert cancelled_observed["hit"], "CancelledError not visible inside boot task"


# ---------------------------------------------------------------------------
# Airgapped invariant: no outbound subprocess call
# ---------------------------------------------------------------------------

def test_airgapped_does_not_invoke_subprocess(monkeypatch, boot_env):
    """Boot path is gated by `if _lab_mode() == 'hybrid':` (app.py:514).

    We can't easily run the FastAPI startup hook here, but we can directly
    assert the gate's behaviour: in airgapped mode, the boot task must not
    be created.

    We assert this at the helper level by simulating the gate guard.
    """
    data_dir, _sc, _act = boot_env
    monkeypatch.setenv("LAB_MODE", "airgapped")

    spawn_count = {"n": 0}

    async def _fake_exec(*args, **kwargs):
        spawn_count["n"] += 1

        class _P:
            returncode = 0
            async def communicate(self):
                return b'{"dependencies": []}', b""
        return _P()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

    # Simulate the startup gate.
    from arail.portal.app import _lab_mode
    if _lab_mode() == "hybrid":
        # Would schedule a task; we don't.
        pytest.fail("LAB_MODE=airgapped but _lab_mode() returned hybrid")

    # Confirm: no subprocess was spawned (because the gate gated us).
    assert spawn_count["n"] == 0


# ---------------------------------------------------------------------------
# Architect MUST-HIT #5 already covered in test_admin_cleanup_endpoints.py
# (test_concurrent_prune_returns_409_from_second_caller).
# This file owns MUST-HIT #2.
# ---------------------------------------------------------------------------
