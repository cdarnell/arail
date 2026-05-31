"""Unit tests for the portable `_arail_timeout` shim in scripts/setup.sh.

WHY: GNU `timeout(1)` is absent on stock macOS (it's `gtimeout` only after
`brew install coreutils`). Before the shim, every `timeout 900 ollama pull …`
in the ai-eng install ladder failed instantly on a clean Mac, so setup
finished with NO model installed — breaking "everyone gets ai-eng on first
setup". These tests pin the three branches: real `timeout`, `gtimeout`
fallback, and neither-present (run uncapped + warn).

OOM-SAFETY: nothing here runs ollama/curl or downloads. The "command" the
shim wraps is a trivial marker script under a per-test stub dir, and PATH is
restricted to that dir so the branch under test is deterministic.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _extract_shim() -> str:
    """Pull the `_arail_timeout() { … }` function text out of setup.sh."""
    lines = SETUP_SH.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("_arail_timeout() {"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i] == "}")
    return "\n".join(lines[start:end + 1])


def _run(tmp_path: Path, *, timeout_stub: bool, gtimeout_stub: bool) -> subprocess.CompletedProcess:
    binp = tmp_path / "bin"
    binp.mkdir()

    def _write(name: str, body: str):
        p = binp / name
        p.write_text(body)
        p.chmod(0o755)

    # The wrapped command: a marker that proves it actually ran.
    _write("marker", "#!/bin/bash\necho RAN_MARKER \"$@\"\n")
    # Real timeout/gtimeout stubs announce themselves, then exec the rest.
    if timeout_stub:
        _write("timeout", '#!/bin/bash\necho VIA_TIMEOUT\nshift\nexec "$@"\n')
    if gtimeout_stub:
        _write("gtimeout", '#!/bin/bash\necho VIA_GTIMEOUT\nshift\nexec "$@"\n')

    script = tmp_path / "drive.sh"
    script.write_text(
        "set -uo pipefail\n"
        'warn() { echo "WARN $*" >&2; }\n'
        f"{_extract_shim()}\n"
        '_arail_timeout 7 marker hello\n'
    )
    # PATH restricted to the stub bin so only the intended branch is reachable.
    # Shebangs use /bin/bash directly (no /usr/bin/env PATH lookup needed).
    return subprocess.run(
        [BASH, str(script)],
        env={"PATH": str(binp)},
        capture_output=True, text=True, timeout=30,
    )


def test_uses_real_timeout_when_present(tmp_path):
    r = _run(tmp_path, timeout_stub=True, gtimeout_stub=True)
    assert r.returncode == 0
    assert "VIA_TIMEOUT" in r.stdout
    assert "VIA_GTIMEOUT" not in r.stdout          # timeout wins over gtimeout
    assert "RAN_MARKER hello" in r.stdout           # command actually ran


def test_falls_back_to_gtimeout(tmp_path):
    r = _run(tmp_path, timeout_stub=False, gtimeout_stub=True)
    assert r.returncode == 0
    assert "VIA_GTIMEOUT" in r.stdout
    assert "RAN_MARKER hello" in r.stdout


def test_runs_uncapped_when_neither_present(tmp_path):
    # The stock-macOS case: no timeout, no gtimeout. Must still run the
    # command (so ai-eng installs) and warn once.
    r = _run(tmp_path, timeout_stub=False, gtimeout_stub=False)
    assert r.returncode == 0
    assert "RAN_MARKER hello" in r.stdout
    assert "VIA_TIMEOUT" not in r.stdout
    assert "VIA_GTIMEOUT" not in r.stdout
    assert "WARN" in r.stderr                        # warned about missing timeout
