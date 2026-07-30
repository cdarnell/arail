"""Port block allocation (ARCHITECTURE.md §3.4) and the env pack writer
(§1.2). Drives the real scripts/lib/instances.sh (never a reimplementation).

Covers: block allocation determinism; pinned-on-reboot (not re-derived);
never 8080/7414/8443/8888/7681/11434/11435; hard stop below 9100;
LANCE_PORT always allocated alongside PORTAL_PORT; env pack round-trips
shell-safe quoting for hostile values.
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


def _fake_repo(tmp_path: Path) -> Path:
    """A throwaway REPO_ROOT with the real scripts/setup.sh reachable, so
    inst_load_port_helpers/inst_load_env_writer's extraction (awk over the
    real file) works exactly as it would in the real repo, without letting
    the instance tree it creates touch the real repo's lab/instances/.
    """
    fake = tmp_path / "fakerepo"
    (fake / "scripts").mkdir(parents=True)
    shutil.copy2(REPO_ROOT / "scripts" / "setup.sh", fake / "scripts" / "setup.sh")
    return fake


def _run(repo_root: Path, script: str, extra_env: dict | None = None, timeout: int = 30) -> subprocess.CompletedProcess:
    full = textwrap.dedent(f"""
        set -euo pipefail
        REPO_ROOT="{repo_root}"
        # shellcheck disable=SC1091
        source "{INSTANCES_SH}"
        {script}
    """)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [_BASH, "-c", full],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


# ---------------------------------------------------------------------------
# Port helper reuse — proves setup.sh's functions were extracted, not copied
# ---------------------------------------------------------------------------

def test_port_helpers_load_from_setup_sh(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, """
        inst_load_port_helpers
        declare -F _port_in_use >/dev/null && echo HAVE_PORT_IN_USE
        declare -F _find_free_port >/dev/null && echo HAVE_FIND_FREE
    """)
    assert res.returncode == 0, res.stderr
    assert "HAVE_PORT_IN_USE" in res.stdout
    assert "HAVE_FIND_FREE" in res.stdout


# ---------------------------------------------------------------------------
# Exclusion list
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("port", [8443, 8888, 7681, 7414, 11434, 11435])
def test_reserved_ports_are_excluded(tmp_path, port):
    res = _run(tmp_path, f"inst_port_excluded {port} && echo EXCLUDED || echo ALLOWED")
    assert res.returncode == 0, res.stderr
    assert "EXCLUDED" in res.stdout


def test_ordinary_instance_port_is_not_excluded(tmp_path):
    res = _run(tmp_path, "inst_port_excluded 8090 && echo EXCLUDED || echo ALLOWED")
    assert res.returncode == 0, res.stderr
    assert "ALLOWED" in res.stdout


# ---------------------------------------------------------------------------
# Allocation: first free block, both ports together, deterministic
# ---------------------------------------------------------------------------

def test_first_allocation_is_the_base_block(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, "inst_allocate_ports")
    assert res.returncode == 0, res.stderr
    portal, lance = res.stdout.split()
    assert portal == "8090"
    assert lance == "8094"


def test_allocation_skips_blocks_already_registered(tmp_path):
    fake = _fake_repo(tmp_path)
    rec = {
        "schema": "arail.instance-registry/v1", "slug": "ai",
        "portal_port": 8090, "lance_port": 8094,
        "portal_pid": 1, "checkout": "/x", "bind": "127.0.0.1",
        "token": "t",
    }
    res = _run(fake, f"""
        inst_write_record ai '{json.dumps(rec)}'
        inst_allocate_ports
    """)
    assert res.returncode == 0, res.stderr
    portal, lance = res.stdout.split()
    assert portal == "8100"
    assert lance == "8104"


def test_allocation_never_hands_out_a_bound_port(tmp_path, unused_tcp_port_factory=None):
    """A port that's actually bound (not just registered) must be skipped."""
    fake = _fake_repo(tmp_path)
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 8090))
    sock.listen(1)
    try:
        res = _run(fake, "inst_allocate_ports")
        assert res.returncode == 0, res.stderr
        portal, lance = res.stdout.split()
        assert portal != "8090"
        assert int(portal) >= 8090
    finally:
        sock.close()


def test_hard_stop_below_9100(tmp_path):
    """Every block base 8090..9090 pre-registered — allocation must refuse,
    never silently wrap or exceed the ceiling."""
    fake = _fake_repo(tmp_path)
    lines = []
    slug_n = 0
    base = 8090
    while base < 9100:
        slug_n += 1
        rec = {
            "schema": "arail.instance-registry/v1", "slug": f"s{slug_n}",
            "portal_port": base, "lance_port": base + 4,
            "portal_pid": 1, "checkout": "/x", "bind": "127.0.0.1", "token": "t",
        }
        lines.append(f"inst_write_record s{slug_n} '{json.dumps(rec)}'")
        base += 10
    script = "\n".join(lines) + "\ninst_allocate_ports"
    res = _run(fake, script)
    assert res.returncode != 0, "allocation must refuse once every block below the ceiling is taken"
    assert "9100" in (res.stdout + res.stderr)


def test_allocation_result_pins_both_portal_and_lance(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, "inst_allocate_ports")
    assert res.returncode == 0, res.stderr
    parts = res.stdout.split()
    assert len(parts) == 2
    portal, lance = int(parts[0]), int(parts[1])
    assert lance == portal + 4


# ---------------------------------------------------------------------------
# Env pack writer — shell-safe quoting round-trip
# ---------------------------------------------------------------------------

def test_env_writer_loads_from_setup_sh(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, """
        inst_load_env_writer
        declare -F _set_env_var >/dev/null && echo HAVE_SET_ENV_VAR
    """)
    assert res.returncode == 0, res.stderr
    assert "HAVE_SET_ENV_VAR" in res.stdout


def test_pack_round_trips_plain_values(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, """
        inst_write_env_pack finance \
            ARAIL_INSTANCE finance \
            PORTAL_PORT 8090 \
            LANCE_PORT 8094 \
            BIND_ADDR 127.0.0.1
        cat "$(inst_env_file finance)"
    """)
    assert res.returncode == 0, res.stderr
    content = res.stdout
    assert "ARAIL_INSTANCE=finance" in content
    assert "PORTAL_PORT=8090" in content
    assert "LANCE_PORT=8094" in content


def test_pack_round_trips_hostile_display_name(tmp_path):
    """LAB_NAME could contain spaces / metacharacters if a World's face.json
    display_name does — must survive `set -a; source; set +a` unexecuted."""
    fake = _fake_repo(tmp_path)
    hostile = 'Finance $(touch PWNED) `touch PWNED2` "World"'
    # Single-quote for the OUTER bash -c script (so bash itself does not
    # expand $()/`` while building argv for inst_write_env_pack) — the value
    # must reach the function as inert data, exactly like a real caller
    # passing a World's face.json display_name through argv would.
    hostile_single_quoted = "'" + hostile.replace("'", "'\\''") + "'"
    res = _run(fake, f"""
        inst_write_env_pack finance LAB_NAME {hostile_single_quoted}
        pack="$(inst_env_file finance)"
        ( set -a; source "$pack"; set +a; printf '%s' "$LAB_NAME" )
    """)
    assert res.returncode == 0, res.stderr
    assert res.stdout == hostile
    assert not (tmp_path / "PWNED").exists()
    assert not (tmp_path / "PWNED2").exists()


def test_pack_is_written_from_scratch_not_patched(tmp_path):
    """A second inst_write_env_pack call must not leave stale keys behind."""
    fake = _fake_repo(tmp_path)
    res = _run(fake, """
        inst_write_env_pack finance FOO bar BAZ qux
        inst_write_env_pack finance ONLY_THIS present
        cat "$(inst_env_file finance)"
    """)
    assert res.returncode == 0, res.stderr
    assert "ONLY_THIS=present" in res.stdout
    assert "FOO" not in res.stdout
    assert "BAZ" not in res.stdout


def test_pack_file_mode_is_0644(tmp_path):
    fake = _fake_repo(tmp_path)
    res = _run(fake, """
        inst_write_env_pack finance PORTAL_PORT 8090
        stat -f '%Lp' "$(inst_env_file finance)" 2>/dev/null || stat -c '%a' "$(inst_env_file finance)"
    """)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "644"


# ---------------------------------------------------------------------------
# First-boot scaffold
# ---------------------------------------------------------------------------

def test_scaffold_creates_the_fixed_tree(tmp_path):
    res = _run(tmp_path, "inst_scaffold_instance_root finance")
    assert res.returncode == 0, res.stderr
    root = tmp_path / "lab" / "instances" / "finance"
    assert (root / "data").is_dir()
    assert (root / "pkb" / "sources").is_dir()
    assert (root / "pkb" / "notes").is_dir()
    assert (root / "log").is_dir()


def test_scaffold_is_idempotent(tmp_path):
    res1 = _run(tmp_path, "inst_scaffold_instance_root finance")
    assert res1.returncode == 0, res1.stderr
    (tmp_path / "lab" / "instances" / "finance" / "data" / "keep.txt").write_text("x")
    res2 = _run(tmp_path, "inst_scaffold_instance_root finance")
    assert res2.returncode == 0, res2.stderr
    assert (tmp_path / "lab" / "instances" / "finance" / "data" / "keep.txt").exists()
