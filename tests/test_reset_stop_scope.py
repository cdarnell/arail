"""reset.sh stop_services must only target ARAIL processes.

The old implementation pgrep'd bare "uvicorn" — killing ANY uvicorn on the
box. Verify the patterns are module/port scoped by exercising the shell
function with stubbed pgrep/kill.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parents[1]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")

_DRIVER = r"""
set -euo pipefail
info() { :; }
LAB_NAME=test
# Stub process table: pid<TAB>command
PROCS="$PROCS_FILE"
pgrep() {
    # emulate pgrep -f <pattern>
    local pattern="${2:-$1}"
    awk -F'\t' -v pat="$pattern" '$2 ~ pat {print $1}' "$PROCS"
}
KILLED="$KILLED_FILE"
kill() {
    if [[ "${1:-}" == "-0" ]]; then return 1; fi   # everything dies instantly
    if [[ "${1:-}" == "-9" ]]; then shift; fi
    for pid in "$@"; do echo "$pid" >> "$KILLED"; done
}
launchctl() { return 1; }
sleep() { :; }
uname() { echo Darwin; }
# Extract just the stop_services function from reset.sh and run it.
eval "$(awk '/^stop_services\(\)/,/^}/' "$RESET_SH")"
stop_services
"""


def _run_stop(tmp_path, procs):
    procs_file = tmp_path / "procs.tsv"
    procs_file.write_text("".join(f"{pid}\t{cmd}\n" for pid, cmd in procs))
    killed_file = tmp_path / "killed.txt"
    killed_file.write_text("")
    driver = tmp_path / "driver.sh"
    driver.write_text(_DRIVER)
    result = subprocess.run(
        ["bash", str(driver)], capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin",
             "PROCS_FILE": str(procs_file),
             "KILLED_FILE": str(killed_file),
             "RESET_SH": str(REPO / "scripts" / "reset.sh")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return set(killed_file.read_text().split())


def test_foreign_uvicorn_survives(tmp_path):
    killed = _run_stop(tmp_path, [
        ("101", "python -m uvicorn arail.portal.app:app --port 8080"),
        ("102", "python -m uvicorn arail.memory_service:app --port 7414"),
        ("666", "python -m uvicorn other.project.app:app --port 9000"),
        ("667", "uvicorn somebody_elses:app"),
    ])
    assert "101" in killed and "102" in killed
    assert "666" not in killed and "667" not in killed


def test_port_scoped_helpers(tmp_path):
    killed = _run_stop(tmp_path, [
        ("201", "ttyd -p 7681 tmux new-session"),
        ("202", "ttyd -p 9999 someone-elses-terminal"),
        ("203", "code-server --bind-addr 127.0.0.1:8443"),
    ])
    assert "201" in killed
    assert "202" not in killed
    assert "203" in killed
