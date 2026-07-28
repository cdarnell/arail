"""scripts/lib/instances.sh — registry write/read/prune, liveness predicate.

Covers ARCHITECTURE.md §2 and failure modes F2 (stale PID), F3 (PID reuse),
F16 (corrupt JSON quarantine). Drives the real shell functions (not a
reimplementation) via a stubbed PATH so `kill -0` / `ps` / `launchctl` are
deterministic, matching the pattern tests/test_reset_stop_scope.py already
uses for reset.sh.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _run(repo_root: Path, script: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Source instances.sh with REPO_ROOT=<repo_root>, then run `script`."""
    full = textwrap.dedent(f"""
        set -euo pipefail
        REPO_ROOT="{repo_root}"
        # shellcheck disable=SC1091
        source "{INSTANCES_SH}"
        {script}
    """)
    return subprocess.run(
        [_BASH, "-c", full],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )


def _sample_record(**overrides) -> dict:
    rec = {
        "schema": "arail.instance-registry/v1",
        "slug": "finance",
        "display_name": "Finance World",
        "checkout": "/abs/path/to/repo",
        "instance_root": "/abs/path/to/repo/lab/instances/finance",
        "data_dir": "/abs/path/to/repo/lab/instances/finance/data",
        "pkb_root": "/abs/path/to/repo/lab/instances/finance/pkb",
        "bind": "127.0.0.1",
        "portal_port": 8090,
        "lance_port": 8094,
        "launcher_pid": 41221,
        "portal_pid": 41223,
        "memory_pid": 41224,
        "token": "c1f0abcd",
        "started_at": "2026-07-28T14:03:11Z",
        "arailctl_version": "test",
    }
    rec.update(overrides)
    return rec


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_path_helpers_are_absolute_and_derived_from_repo_root(tmp_path):
    res = _run(tmp_path, """
        inst_root_dir
        inst_registry_dir
        inst_instance_dir finance
        inst_env_file finance
        inst_data_dir finance
        inst_pkb_dir finance
    """)
    assert res.returncode == 0, res.stderr
    lines = res.stdout.strip().splitlines()
    assert lines[0] == str(tmp_path / "lab" / "instances")
    assert lines[1] == str(tmp_path / "lab" / "instances" / "registry.d")
    assert lines[2] == str(tmp_path / "lab" / "instances" / "finance")
    assert lines[3] == str(tmp_path / "lab" / "instances" / "finance" / "instance.env")
    assert lines[4] == str(tmp_path / "lab" / "instances" / "finance" / "data")
    assert lines[5] == str(tmp_path / "lab" / "instances" / "finance" / "pkb")


def test_slug_jail_matches_world_mount_regex(tmp_path):
    res = _run(tmp_path, """
        inst_valid_slug "finance" && echo VALID1
        inst_valid_slug "ai-ml" && echo VALID2
        inst_valid_slug "-bad" && echo SHOULD_NOT_PRINT
        inst_valid_slug "../etc" && echo SHOULD_NOT_PRINT
        inst_valid_slug "Finance" && echo SHOULD_NOT_PRINT
        true
    """)
    assert res.returncode == 0, res.stderr
    out = res.stdout
    assert "VALID1" in out and "VALID2" in out
    assert "SHOULD_NOT_PRINT" not in out


# ---------------------------------------------------------------------------
# Registry write / read — atomic tmp+replace, never hand-rolled JSON
# ---------------------------------------------------------------------------

def test_write_then_read_round_trips(tmp_path):
    rec = _sample_record()
    payload = json.dumps(rec)
    res = _run(tmp_path, f"""
        inst_write_record finance '{payload}'
        inst_read_record finance
    """)
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout)
    assert got == rec


def test_write_uses_tmp_plus_replace_no_tmp_file_left_behind(tmp_path):
    rec = _sample_record()
    payload = json.dumps(rec)
    res = _run(tmp_path, f"""
        inst_write_record finance '{payload}'
    """)
    assert res.returncode == 0, res.stderr
    registry = tmp_path / "lab" / "instances" / "registry.d"
    assert (registry / "finance.json").exists()
    assert not (registry / "finance.json.tmp").exists()


def test_read_missing_record_returns_nonzero_no_output(tmp_path):
    res = _run(tmp_path, """
        if inst_read_record ghost; then echo "SHOULD_NOT_SUCCEED"; else echo "absent-ok"; fi
    """)
    assert res.returncode == 0, res.stderr
    assert "absent-ok" in res.stdout
    assert "SHOULD_NOT_SUCCEED" not in res.stdout


def test_corrupt_json_is_quarantined_not_fatal(tmp_path):
    registry = tmp_path / "lab" / "instances" / "registry.d"
    registry.mkdir(parents=True)
    (registry / "broken.json").write_text("{not json", encoding="utf-8")
    res = _run(tmp_path, """
        if inst_read_record broken; then echo "SHOULD_NOT_SUCCEED"; else echo "handled: $?"; fi
    """)
    assert res.returncode == 0, res.stderr
    assert "SHOULD_NOT_SUCCEED" not in res.stdout
    assert not (registry / "broken.json").exists(), "corrupt record must be moved, not left in place"
    assert (registry / "broken.json.bad").exists(), "corrupt record must be quarantined to <slug>.json.bad"


def test_list_slugs_skips_corrupt_and_lists_valid(tmp_path):
    rec = _sample_record(slug="ai")
    payload = json.dumps(rec)
    registry = tmp_path / "lab" / "instances" / "registry.d"
    res = _run(tmp_path, f"""
        inst_write_record ai '{payload}'
        mkdir -p "{registry}"
        echo '{{not json' > "{registry}/broken.json"
        inst_list_slugs
    """)
    assert res.returncode == 0, res.stderr
    slugs = res.stdout.split()
    assert "ai" in slugs
    assert "broken" not in slugs


# ---------------------------------------------------------------------------
# Liveness predicate — steps 1-3 (no network)
# ---------------------------------------------------------------------------

_STUB_PROCS = """
    # Stub ps/kill so the predicate is deterministic without real PIDs.
    kill() {{
        if [[ "${{1:-}}" == "-0" ]]; then
            case "$2" in
                {alive_pids}) return 0 ;;
                *) return 1 ;;
            esac
        fi
        return 0
    }}
    ps() {{
        # emulate: ps -p <pid> -o command=
        local pid=""
        while [[ $# -gt 0 ]]; do
            case "$1" in
                -p) pid="$2"; shift 2 ;;
                *) shift ;;
            esac
        done
        case "$pid" in
            {cmd_cases}
            *) return 1 ;;
        esac
    }}
"""


def test_alive_record_passes_predicate(tmp_path):
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(
        alive_pids="999",
        cmd_cases='999) echo "python -m uvicorn arail.portal.app:app --port 8090" ;;',
    )
    res = _run(tmp_path, f"""
        {stub}
        inst_write_record finance '{payload}'
        inst_alive finance && echo ALIVE
    """)
    assert res.returncode == 0, res.stderr
    assert "ALIVE" in res.stdout


def test_dead_pid_is_not_alive_f2(tmp_path):
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(alive_pids="NONE", cmd_cases="")
    res = _run(tmp_path, f"""
        {stub}
        inst_write_record finance '{payload}'
        inst_alive finance && echo ALIVE || echo DEAD
    """)
    assert res.returncode == 0, res.stderr
    assert "DEAD" in res.stdout


def test_pid_reused_by_unrelated_process_is_not_alive_f3(tmp_path):
    """A recycled PID belonging to an unrelated process must fail step 3."""
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(
        alive_pids="999",
        cmd_cases='999) echo "/usr/bin/some-unrelated-daemon --foo" ;;',
    )
    res = _run(tmp_path, f"""
        {stub}
        inst_write_record finance '{payload}'
        inst_alive finance && echo ALIVE || echo REJECTED
    """)
    assert res.returncode == 0, res.stderr
    assert "REJECTED" in res.stdout


def test_wrong_port_in_cmdline_is_not_alive(tmp_path):
    """cmdline matches the module but a different --port fails step 3."""
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(
        alive_pids="999",
        cmd_cases='999) echo "python -m uvicorn arail.portal.app:app --port 9999" ;;',
    )
    res = _run(tmp_path, f"""
        {stub}
        inst_write_record finance '{payload}'
        inst_alive finance && echo ALIVE || echo REJECTED
    """)
    assert res.returncode == 0, res.stderr
    assert "REJECTED" in res.stdout


def test_prune_removes_only_stale_never_touches_data(tmp_path):
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(alive_pids="NONE", cmd_cases="")
    data_dir = tmp_path / "lab" / "instances" / "finance" / "data"
    res = _run(tmp_path, f"""
        {stub}
        mkdir -p "{data_dir}"
        echo "user data" > "{data_dir}/keep.txt"
        inst_write_record finance '{payload}'
        inst_prune finance
    """)
    assert res.returncode == 0, res.stderr
    registry = tmp_path / "lab" / "instances" / "registry.d"
    assert not (registry / "finance.json").exists(), "stale record must be pruned"
    assert (data_dir / "keep.txt").exists(), "prune must never touch instance data"


def test_prune_leaves_alive_record_untouched(tmp_path):
    rec = _sample_record(portal_pid=999, portal_port=8090)
    payload = json.dumps(rec)
    stub = _STUB_PROCS.format(
        alive_pids="999",
        cmd_cases='999) echo "python -m uvicorn arail.portal.app:app --port 8090" ;;',
    )
    res = _run(tmp_path, f"""
        {stub}
        inst_write_record finance '{payload}'
        inst_prune finance
    """)
    assert res.returncode == 0, res.stderr
    registry = tmp_path / "lab" / "instances" / "registry.d"
    assert (registry / "finance.json").exists(), "prune must not remove a live record"


# ---------------------------------------------------------------------------
# daemon_active — plist existence is necessary but not sufficient
# ---------------------------------------------------------------------------

def test_daemon_active_false_when_no_plist(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    res = subprocess.run(
        [_BASH, "-c", f"""
            set -euo pipefail
            REPO_ROOT="{tmp_path}"
            HOME="{home}"
            export HOME
            source "{INSTANCES_SH}"
            daemon_active && echo ACTIVE || echo INACTIVE
        """],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    assert res.returncode == 0, res.stderr
    assert "INACTIVE" in res.stdout


def test_daemon_active_false_when_plist_exists_but_not_loaded(tmp_path):
    home = tmp_path / "home"
    agents_dir = home / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "io.arail.portal.plist").write_text("<plist/>", encoding="utf-8")
    res = subprocess.run(
        [_BASH, "-c", f"""
            set -euo pipefail
            REPO_ROOT="{tmp_path}"
            HOME="{home}"
            export HOME
            uname() {{ echo Darwin; }}
            launchctl() {{ return 1; }}  # not loaded
            source "{INSTANCES_SH}"
            daemon_active && echo ACTIVE || echo INACTIVE
        """],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    assert res.returncode == 0, res.stderr
    assert "INACTIVE" in res.stdout


def test_daemon_active_true_only_with_pid_line(tmp_path):
    home = tmp_path / "home"
    agents_dir = home / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "io.arail.portal.plist").write_text("<plist/>", encoding="utf-8")
    res = subprocess.run(
        [_BASH, "-c", f"""
            set -euo pipefail
            REPO_ROOT="{tmp_path}"
            HOME="{home}"
            export HOME
            uname() {{ echo Darwin; }}
            launchctl() {{ printf '{{\\n\\t"PID" = 4242;\\n}};\\n'; }}
            source "{INSTANCES_SH}"
            daemon_active && echo ACTIVE || echo INACTIVE
        """],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )
    assert res.returncode == 0, res.stderr
    assert "ACTIVE" in res.stdout
