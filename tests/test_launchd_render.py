"""install-daemon.sh renders correct, secret-free LaunchAgent plists.

No launchctl in CI: the script's LAUNCHCTL env override points at /usr/bin/true.
"""

from __future__ import annotations

import pathlib
import plistlib
import shutil
import subprocess

import pytest

REPO = pathlib.Path(__file__).parents[1]
SCRIPT = REPO / "scripts" / "install-daemon.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash required")


def _run_installer(tmp_path, env_lines, *, uninstall=False):
    """Run the installer against a sandbox repo dir with a stub launchctl."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "scripts" / "launchd").mkdir(parents=True)
    (fake_repo / "scripts" / "lib").mkdir(parents=True)
    (fake_repo / ".venv" / "bin").mkdir(parents=True)
    (fake_repo / ".venv" / "bin" / "python").write_text("#!/bin/sh\n")
    (fake_repo / ".venv" / "bin" / "python").chmod(0o755)
    shutil.copy(SCRIPT, fake_repo / "scripts" / "install-daemon.sh")
    # install-daemon.sh unconditionally sources scripts/lib/instances.sh as
    # of the concurrent-worlds sprint's WP2 (ARCHITECTURE.md §2.6: the
    # daemon-liveness/registry helpers live there now) — the fake repo
    # needs a copy too, same as every other fixture that drives a real
    # script sourcing it (see tests/instance_start_driver.sh).
    shutil.copy(REPO / "scripts" / "lib" / "instances.sh",
                fake_repo / "scripts" / "lib" / "instances.sh")
    shutil.copy(REPO / "scripts" / "launchd" / "io.arail.service.plist.template",
                fake_repo / "scripts" / "launchd" / "io.arail.service.plist.template")
    (fake_repo / ".env").write_text("\n".join(env_lines) + "\n")

    home = tmp_path / "home"
    (home / "Library" / "LaunchAgents").mkdir(parents=True)
    args = ["bash", str(fake_repo / "scripts" / "install-daemon.sh")]
    if uninstall:
        args.append("--uninstall")
    result = subprocess.run(
        args, capture_output=True, text=True, timeout=30,
        env={"HOME": str(home), "PATH": "/usr/bin:/bin",
             "LAUNCHCTL": "/usr/bin/true"},
    )
    return result, home / "Library" / "LaunchAgents"


ENV = ["PORTAL_PORT=9999", "LANCE_PORT=7444", "MODEL_BACKEND=ollama_native",
       "ANTHROPIC_API_KEY=sk-secret-canary-value"]


def test_renders_portal_and_memory_plists(tmp_path):
    result, agents = _run_installer(tmp_path, ENV)
    assert result.returncode == 0, result.stdout + result.stderr
    portal = agents / "io.arail.portal.plist"
    memory = agents / "io.arail.memory.plist"
    assert portal.exists() and memory.exists()
    assert not (agents / "io.arail.mlx.plist").exists()   # backend != mlx

    data = plistlib.loads(portal.read_bytes())
    args = data["ProgramArguments"]
    assert args[0].endswith(".venv/bin/python")
    assert "arail.portal.app:app" in args
    assert args[args.index("--port") + 1] == "9999"       # port baked from .env
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert data["ThrottleInterval"] == 15
    assert "lab/logs/portal.out.log" in data["StandardOutPath"]
    mem = plistlib.loads(memory.read_bytes())
    assert mem["ProgramArguments"][mem["ProgramArguments"].index("--port") + 1] == "7444"


def test_no_secrets_in_rendered_plists(tmp_path):
    _, agents = _run_installer(tmp_path, ENV)
    for plist in agents.glob("io.arail.*.plist"):
        text = plist.read_text()
        assert "sk-secret-canary-value" not in text
        assert "ANTHROPIC" not in text
        # Only PATH/PYTHONPATH exported.
        env = plistlib.loads(plist.read_bytes())["EnvironmentVariables"]
        assert set(env) <= {"PATH", "PYTHONPATH"}


def test_mlx_plist_only_when_mlx_backend(tmp_path):
    _, agents = _run_installer(tmp_path,
                               ["PORTAL_PORT=9999", "MODEL_BACKEND=mlx",
                                "MLX_OPENAI_PORT=11498"])
    mlx = agents / "io.arail.mlx.plist"
    assert mlx.exists()
    data = plistlib.loads(mlx.read_bytes())
    assert "arail.mlx_openai_server:app" in data["ProgramArguments"]
    assert data["ProgramArguments"][data["ProgramArguments"].index("--port") + 1] == "11498"


def test_idempotent_second_run(tmp_path):
    result1, agents = _run_installer(tmp_path, ENV)
    # Second run against the same HOME: re-create the sandbox is not needed —
    # rerun the installed copy in place.
    fake_repo = tmp_path / "repo"
    result2 = subprocess.run(
        ["bash", str(fake_repo / "scripts" / "install-daemon.sh")],
        capture_output=True, text=True, timeout=30,
        env={"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin",
             "LAUNCHCTL": "/usr/bin/true"},
    )
    assert result2.returncode == 0
    assert "already up to date" in result2.stdout


def test_uninstall_removes_agents(tmp_path):
    _, agents = _run_installer(tmp_path, ENV)
    assert list(agents.glob("io.arail.*.plist"))
    fake_repo = tmp_path / "repo"
    result = subprocess.run(
        ["bash", str(fake_repo / "scripts" / "install-daemon.sh"), "--uninstall"],
        capture_output=True, text=True, timeout=30,
        env={"HOME": str(tmp_path / "home"), "PATH": "/usr/bin:/bin",
             "LAUNCHCTL": "/usr/bin/true"},
    )
    assert result.returncode == 0
    assert not list(agents.glob("io.arail.*.plist"))
