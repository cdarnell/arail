"""`./arailctl start` must bring up Ollama when it's needed, and `reset`
must never orphan or mishandle it.

Ollama backs the default chat model (llama-ai-eng) on every tier — but
`setup.sh` only ever launches it transiently, as a side effect of
`ollama pull`/`ollama create` at setup time. Nothing previously kept it
running afterward: a fresh terminal session, a reboot, or simply closing
the one that ran setup left chat unable to reach `127.0.0.1:11434` with
no recovery path short of the user manually running `ollama serve`.

The fix threads a single rule through start.sh, reset.sh, and
install-daemon.sh: **only ever manage an Ollama we started ourselves.**
An Ollama the user runs independently (brew services, another project,
manually) is never started twice, never killed, never assumed. The
handoff between "start.sh launched it" and "a later ./arailctl stop/reset
should clean it up" is a pidfile at
`${DATA_DIR}/.ollama-started-by-arail.pid` — present only when we are the
owner, read (never blindly trusted) by reset.sh.

SAFETY, same rule as tests/test_reset_paths.py: only the *scoped* `data`
mode is driven here. `stop`/`full`/`destroy` call stop_services(), whose
OTHER kill patterns (uvicorn/ttyd/jupyter/code-server) are unscoped
`pgrep -f` against the whole machine — running those under pytest could
kill a real developer's running lab. reset_data() is safe to drive
directly: it does not call stop_services(), and the ollama-kill logic
added to it only ever touches the specific PID recorded in the sandboxed
pidfile — a PID this test itself spawns, never a pattern match.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RESET_SH = REPO_ROOT / "scripts" / "reset.sh"
START_SH = REPO_ROOT / "scripts" / "start.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _make_sandbox(tmp_path: Path) -> Path:
    """A throwaway repo root holding a copy of the real reset.sh.

    reset.sh derives REPO_ROOT from its own location and cd's there, so a
    copy under tmp is fully self-contained — it can't touch the real repo,
    and its DATA_DIR resolves to the sandbox's own lab/data.
    """
    fake = tmp_path / "fakerepo"
    (fake / "scripts").mkdir(parents=True)
    shutil.copy2(RESET_SH, fake / "scripts" / "reset.sh")
    return fake


def _run_reset(fake_repo: Path, mode: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_BASH, "scripts/reset.sh", mode, "--yes"],
        cwd=fake_repo,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fake_repo / "home"), **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


def _spawn_dummy_process() -> subprocess.Popen:
    """A real, harmless, sandbox-owned process this test can safely kill."""
    return subprocess.Popen(["sleep", "300"])


def _reaped_dead(proc: subprocess.Popen, timeout: float = 2.0) -> bool:
    """True once `proc` has actually exited.

    Deliberately NOT `os.kill(pid, 0)`: a Popen child we haven't reaped
    yet is a zombie after it dies — `kill(pid, 0)` still reports it as
    "alive" (a real PID-table entry exists) until something calls
    wait()/poll() on it, which would make this test's own alive-check a
    false positive for "the fix didn't work." `proc.poll()` performs
    that reap and returns the real exit status once available.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(0.05)
    return proc.poll() is not None


# ---------------------------------------------------------------------------
# reset_data() stops an Ollama it recorded owning, before wiping DATA_DIR
# ---------------------------------------------------------------------------

def test_reset_data_kills_owned_ollama_before_wiping_data_dir(tmp_path):
    """If we own the pidfile'd process, reset data stops it (not orphans it)."""
    fake = _make_sandbox(tmp_path)
    data_dir = fake / "lab" / "data"
    data_dir.mkdir(parents=True)

    proc = _spawn_dummy_process()
    try:
        (data_dir / ".ollama-started-by-arail.pid").write_text(str(proc.pid), encoding="utf-8")
        assert proc.poll() is None, "sanity: the dummy process must start out running"

        res = _run_reset(fake, "data")
        assert res.returncode == 0, res.stdout + res.stderr

        assert _reaped_dead(proc), (
            "reset data must stop an Ollama it started before deleting the "
            "pidfile that was the only record of it — otherwise it survives, "
            "orphaned, with nothing left able to find or stop it later."
        )
        assert not data_dir.exists(), "reset data should still remove lab/data/"
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


def test_reset_data_ignores_stale_pidfile_without_erroring(tmp_path):
    """A pidfile pointing at an already-dead PID must not fail the reset."""
    fake = _make_sandbox(tmp_path)
    data_dir = fake / "lab" / "data"
    data_dir.mkdir(parents=True)

    # Spawn-then-kill-and-reap to get a PID that is guaranteed dead (and,
    # having been reaped, not left as a zombie that could confuse a
    # naive PID-existence check elsewhere).
    proc = _spawn_dummy_process()
    proc.kill()
    proc.wait(timeout=5)
    dead_pid = proc.pid

    (data_dir / ".ollama-started-by-arail.pid").write_text(str(dead_pid), encoding="utf-8")

    res = _run_reset(fake, "data")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not data_dir.exists()


def test_reset_data_with_no_pidfile_behaves_exactly_as_before(tmp_path):
    """No pidfile at all — the pre-existing reset data behavior, unchanged."""
    fake = _make_sandbox(tmp_path)
    data_dir = fake / "lab" / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "some-state.json").write_text("{}", encoding="utf-8")

    res = _run_reset(fake, "data")
    assert res.returncode == 0, res.stdout + res.stderr
    assert not data_dir.exists()


def test_reset_data_never_touches_a_pidfile_under_a_different_data_dir(tmp_path):
    """LAB_PKB-style override respected: ARAIL_DATA_DIR changes where the
    pidfile is looked for, mirroring reset.sh's own _resolve_data_dir()."""
    fake = _make_sandbox(tmp_path)
    custom_data = tmp_path / "custom-data"
    custom_data.mkdir()

    proc = _spawn_dummy_process()
    try:
        (custom_data / ".ollama-started-by-arail.pid").write_text(str(proc.pid), encoding="utf-8")

        res = _run_reset(fake, "data", {"ARAIL_DATA_DIR": str(custom_data)})
        assert res.returncode == 0, res.stdout + res.stderr

        assert _reaped_dead(proc), (
            "the pidfile lookup must honor ARAIL_DATA_DIR the same way "
            "start.sh's writer does, or the two scripts silently disagree "
            "about where the handoff file lives"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# start.sh's Ollama decision logic (extracted, run standalone with a mocked
# ollama/curl on PATH) — a full start.sh run needs a real venv + uvicorn
# import of arail.portal.app, out of scope for a unit test of this fix.
# ---------------------------------------------------------------------------

_OLLAMA_SNIPPET = r"""
#!/usr/bin/env bash
set -euo pipefail
PIDS=()
info() { echo "[info] $*"; }

_expand_tilde_for_ollama() {
    case "${1-}" in
        "~")   printf '%s' "$HOME" ;;
        "~/"*) printf '%s%s' "$HOME" "${1#\~}" ;;
        *)     printf '%s' "${1-}" ;;
    esac
}
if [[ -n "${ARAIL_DATA_DIR:-}" ]]; then
    OLLAMA_DATA_DIR="$(_expand_tilde_for_ollama "$ARAIL_DATA_DIR")"
else
    OLLAMA_DATA_DIR="$(_expand_tilde_for_ollama "${LAB_ROOT:-lab}")"
    OLLAMA_DATA_DIR="${OLLAMA_DATA_DIR%/}/data"
fi
OLLAMA_PIDFILE="${OLLAMA_DATA_DIR%/}/.ollama-started-by-arail.pid"
if command -v ollama &>/dev/null; then
    if curl -sf -m 2 "http://${OLLAMA_HOST:-127.0.0.1:11434}/api/version" >/dev/null 2>&1; then
        info "Ollama already running"
    else
        info "Ollama starting"
        ollama serve &
        OLLAMA_PID=$!
        PIDS+=("$OLLAMA_PID")
        mkdir -p "$(dirname "$OLLAMA_PIDFILE")"
        echo "$OLLAMA_PID" > "$OLLAMA_PIDFILE"
    fi
else
    info "Ollama not installed"
fi
echo "PIDFILE=${OLLAMA_PIDFILE}"
echo "PIDS=${PIDS[*]:-}"
# Clean up whatever we spawned so the test doesn't leak background jobs.
for pid in "${PIDS[@]:-}"; do [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true; done
"""


def _write_fake_bin(bindir: Path, name: str, script: str) -> None:
    p = bindir / name
    p.write_text(f"#!/usr/bin/env bash\n{script}\n", encoding="utf-8")
    p.chmod(0o755)


def test_start_snippet_does_not_start_ollama_when_already_reachable(tmp_path):
    """This is the exact scenario that matters most: an Ollama the user runs
    independently must never be duplicated or interfered with."""
    fake = tmp_path / "sandbox"
    fake.mkdir()
    bindir = fake / "bin"
    bindir.mkdir()

    _write_fake_bin(bindir, "ollama", "exit 0")
    _write_fake_bin(bindir, "curl", "exit 0")  # every curl call "succeeds" — already reachable
    snippet = fake / "snippet.sh"
    snippet.write_text(_OLLAMA_SNIPPET, encoding="utf-8")
    snippet.chmod(0o755)

    res = subprocess.run(
        [_BASH, str(snippet)],
        cwd=fake,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(fake)},
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Ollama already running" in res.stdout
    assert "PIDS=" in res.stdout and res.stdout.split("PIDS=")[1].split("\n")[0].strip() == "", (
        "an already-reachable Ollama must not be started a second time"
    )
    assert not (fake / "lab").exists(), "no pidfile should be written when we didn't start anything"


def test_start_snippet_starts_and_records_ollama_when_unreachable(tmp_path):
    fake = tmp_path / "sandbox"
    fake.mkdir()
    bindir = fake / "bin"
    bindir.mkdir()

    _write_fake_bin(bindir, "ollama", 'if [[ "$1" == "serve" ]]; then exec sleep 300; fi')
    _write_fake_bin(bindir, "curl", "exit 1")  # every curl call "fails" — never reachable
    snippet = fake / "snippet.sh"
    snippet.write_text(_OLLAMA_SNIPPET, encoding="utf-8")
    snippet.chmod(0o755)

    res = subprocess.run(
        [_BASH, str(snippet)],
        cwd=fake,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(fake)},
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Ollama starting" in res.stdout
    pidfile_line = [l for l in res.stdout.splitlines() if l.startswith("PIDFILE=")][0]
    # The snippet never cd's anywhere absolute, so its printed path is
    # relative to `cwd=fake` — resolve before comparing.
    pidfile = (fake / pidfile_line.split("=", 1)[1]).resolve()
    assert pidfile == (fake / "lab" / "data" / ".ollama-started-by-arail.pid").resolve()
    assert (fake / "lab" / "data" / ".ollama-started-by-arail.pid").exists()


def test_start_snippet_skips_gracefully_when_ollama_not_installed(tmp_path):
    fake = tmp_path / "sandbox"
    fake.mkdir()
    bindir = fake / "bin"
    bindir.mkdir()  # deliberately no `ollama` shim on PATH

    snippet = fake / "snippet.sh"
    snippet.write_text(_OLLAMA_SNIPPET, encoding="utf-8")
    snippet.chmod(0o755)

    res = subprocess.run(
        [_BASH, str(snippet)],
        cwd=fake,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "HOME": str(fake)},
        capture_output=True, text=True, timeout=15,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Ollama not installed" in res.stdout


# ---------------------------------------------------------------------------
# Syntax sanity — the real, unmodified scripts still parse cleanly.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("script", ["start.sh", "reset.sh", "install-daemon.sh"])
def test_script_syntax_is_valid(script):
    path = REPO_ROOT / "scripts" / script
    res = subprocess.run([_BASH, "-n", str(path)], capture_output=True, text=True, timeout=10)
    assert res.returncode == 0, res.stderr
