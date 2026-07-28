"""WP2 — the plist-existence trap is retired everywhere (F8, F9).

Covers ARCHITECTURE.md §2.6's rule: after this sprint, the strings
`~/Library/LaunchAgents/io.arail.portal.plist` and
`launchctl list io.arail.portal` appear in exactly one place each — inside
scripts/lib/instances.sh — and every call site (arailctl, start.sh,
status.sh, install-daemon.sh, reset.sh) drives daemon_active()/
daemon_plist_installed() instead of re-deriving the check locally.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


# ---------------------------------------------------------------------------
# The grep gate itself, pinned as a regression test (not just a one-off
# builder check) so a future edit can't silently reintroduce a duplicate.
# ---------------------------------------------------------------------------

def test_plist_and_launchctl_strings_appear_only_in_instances_lib():
    pattern = r"LaunchAgents/io\.arail\.portal\.plist\|launchctl list io\.arail\.portal"
    res = subprocess.run(
        ["grep", "-rn", pattern, "arailctl", "scripts/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    hits = [ln for ln in res.stdout.splitlines() if ln.strip()]
    offenders = [ln for ln in hits if "scripts/lib/instances.sh" not in ln]
    assert not offenders, (
        "The plist-existence / launchctl-list strings leaked outside "
        f"scripts/lib/instances.sh:\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# daemon_active() / daemon_plist_installed() semantics (F8, F9)
# ---------------------------------------------------------------------------

def _run_with_stubs(home: Path, plist_present: bool, launchctl_pid: str | None) -> subprocess.CompletedProcess:
    plist_setup = ""
    if plist_present:
        agents_dir = home / "Library" / "LaunchAgents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "io.arail.portal.plist").write_text("<plist/>", encoding="utf-8")

    if launchctl_pid is not None:
        launchctl_body = f'printf \'{{\\n\\t"PID" = {launchctl_pid};\\n}};\\n\''
    else:
        launchctl_body = "return 1"  # not loaded

    script = f"""
        set -euo pipefail
        REPO_ROOT="{REPO_ROOT}"
        HOME="{home}"
        export HOME
        uname() {{ echo Darwin; }}
        launchctl() {{ {launchctl_body}; }}
        source "{INSTANCES_SH}"
        if daemon_active; then echo ACTIVE; else echo INACTIVE; fi
        if daemon_plist_installed; then echo INSTALLED; else echo NOT_INSTALLED; fi
    """
    return subprocess.run(
        [_BASH, "-c", script],
        capture_output=True, text=True, timeout=15,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )


def test_f8_no_plist_no_daemon(tmp_path):
    res = _run_with_stubs(tmp_path / "home", plist_present=False, launchctl_pid=None)
    assert res.returncode == 0, res.stderr
    assert "INACTIVE" in res.stdout
    assert "NOT_INSTALLED" in res.stdout


def test_f9_plist_installed_but_not_loaded_is_inactive(tmp_path):
    """The plist-existence trap: file present, launchctl reports nothing."""
    res = _run_with_stubs(tmp_path / "home", plist_present=True, launchctl_pid=None)
    assert res.returncode == 0, res.stderr
    assert "INACTIVE" in res.stdout
    assert "INSTALLED" in res.stdout


def test_daemon_active_true_only_with_pid_line(tmp_path):
    res = _run_with_stubs(tmp_path / "home", plist_present=True, launchctl_pid="4242")
    assert res.returncode == 0, res.stderr
    assert "ACTIVE" in res.stdout
    assert "INSTALLED" in res.stdout


# ---------------------------------------------------------------------------
# start.sh: F8 refuses a foreground start while active; F9 proceeds
# in the foreground with an informational line when installed-but-inactive.
# ---------------------------------------------------------------------------

def _run_start_guard(
    home: Path, plist_present: bool, launchctl_pid: str | None,
    list_only: bool = False, world_slug: str = "",
) -> subprocess.CompletedProcess:
    """Drive just start.sh's daemon guard block via a stubbed environment.

    Sources instances.sh the same way start.sh does, then re-runs the exact
    guard block extracted from start.sh so this stays pinned to the real
    file (not a reimplementation), mirroring tests/test_reset_stop_scope.py's
    extraction pattern. The guard now runs AFTER arg parsing (REVIEW.md m2),
    so it reads LIST_ONLY/WORLD_SLUG/BIND/PORTAL_PORT from the caller —
    exactly the variables start.sh's own arg-parsing block would have set.
    """
    start_sh = (REPO_ROOT / "scripts" / "start.sh").read_text(encoding="utf-8")
    marker_start = "# Daemon mode guard"
    marker_end = "[[ -f .venv/bin/activate ]]"
    start_idx = start_sh.index(marker_start)
    end_idx = start_sh.index(marker_end)
    guard_block = start_sh[start_idx:end_idx]

    if plist_present:
        agents_dir = home / "Library" / "LaunchAgents"
        agents_dir.mkdir(parents=True, exist_ok=True)
        (agents_dir / "io.arail.portal.plist").write_text("<plist/>", encoding="utf-8")

    if launchctl_pid is not None:
        launchctl_body = f'printf \'{{\\n\\t"PID" = {launchctl_pid};\\n}};\\n\''
    else:
        launchctl_body = "return 1"

    script = f"""
        set -uo pipefail
        REPO_ROOT="{REPO_ROOT}"
        HOME="{home}"
        export HOME
        BIND="127.0.0.1"
        LIST_ONLY="{1 if list_only else 0}"
        WORLD_SLUG="{world_slug}"
        uname() {{ echo Darwin; }}
        launchctl() {{ {launchctl_body}; }}
        # shellcheck disable=SC1091
        source "{INSTANCES_SH}"
        {guard_block}
        echo "GUARD_PASSED"
    """
    return subprocess.run(
        [_BASH, "-c", script],
        capture_output=True, text=True, timeout=15,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )


def test_start_refuses_when_daemon_active(tmp_path):
    res = _run_start_guard(tmp_path / "home", plist_present=True, launchctl_pid="4242")
    assert res.returncode == 1
    assert "Daemon mode is active" in res.stdout
    assert "GUARD_PASSED" not in res.stdout


def test_start_proceeds_foreground_when_installed_but_inactive(tmp_path):
    res = _run_start_guard(tmp_path / "home", plist_present=True, launchctl_pid=None)
    assert res.returncode == 0, res.stderr
    assert "installed but inactive" in res.stdout
    assert "GUARD_PASSED" in res.stdout


def test_start_proceeds_silently_when_no_plist(tmp_path):
    res = _run_start_guard(tmp_path / "home", plist_present=False, launchctl_pid=None)
    assert res.returncode == 0, res.stderr
    assert "Daemon mode is active" not in res.stdout
    assert "GUARD_PASSED" in res.stdout


# ---------------------------------------------------------------------------
# REVIEW.md B2 — `./arailctl start --world <slug>` must not be silently
# swallowed by arailctl's daemon_active branch. Drives the REAL arailctl
# dispatch (never a reimplementation): with a stubbed HOME/launchctl/uname
# making daemon_active() true, `start --world <slug>` must still reach
# start.sh's own refusal, which names the slug (F8, ARCHITECTURE.md §4.4) —
# not the generic "Lab supervised by launchd" success line the daemon
# branch used to print unconditionally, discarding --world.
# ---------------------------------------------------------------------------

ARAILCTL = REPO_ROOT / "arailctl"


def _stub_bin_dir(tmp_path: Path, launchctl_pid: int) -> Path:
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir()
    (bin_dir / "uname").write_text("#!/usr/bin/env bash\necho Darwin\n", encoding="utf-8")
    (bin_dir / "launchctl").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "list" ]]; then\n'
        f'    printf \'{{\\n\\t"PID" = {launchctl_pid};\\n}};\\n\'\n'
        "    exit 0\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    for name in ("uname", "launchctl"):
        (bin_dir / name).chmod(0o755)
    return bin_dir


def _run_arailctl(tmp_path: Path, argv: list[str], daemon_active: bool) -> subprocess.CompletedProcess:
    home = tmp_path / "home"
    agents_dir = home / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True)
    (agents_dir / "io.arail.portal.plist").write_text("<plist/>", encoding="utf-8")
    stub_bin = _stub_bin_dir(tmp_path, launchctl_pid=4242 if daemon_active else 0)
    env = {
        "HOME": str(home),
        "PATH": f"{stub_bin}:/usr/bin:/bin:/usr/sbin:/sbin",
    }
    return subprocess.run(
        [_BASH, str(ARAILCTL), *argv],
        capture_output=True, text=True, timeout=20, env=env,
    )


def test_arailctl_start_world_reaches_refusal_naming_slug_when_daemon_active(tmp_path):
    res = _run_arailctl(tmp_path, ["start", "--world", "finance"], daemon_active=True)
    out = res.stdout + res.stderr
    assert res.returncode != 0, out
    assert "finance" in out
    assert "Daemon mode is active" in out
    # Must NOT silently kickstart the ROOT lab and claim success — the B2 bug.
    assert "Lab supervised by launchd" not in out


def test_arailctl_start_list_bypasses_daemon_guard_entirely(tmp_path):
    """--list is side-effect-free and must reach start.sh's catalog printer
    even when daemon_active is true, per REVIEW.md m2 (the guard moved
    below arg parsing so --list/--help aren't blocked by it)."""
    res = _run_arailctl(tmp_path, ["start", "--list"], daemon_active=True)
    out = res.stdout + res.stderr
    # Must reach start.sh (forwarded), not stop at arailctl's daemon branch.
    assert "Lab supervised by launchd" not in out
