"""REVIEW.md m2 — "tool absent" (no curl) must never be reported as
"service down" in arailctl's two daemon-mode readiness gates (`start` and
`restart`, both under an active launchd supervisor).

A4/F30 (sprints/2026-07-29-elite-cli/ARCHITECTURE.md): every probe must
have a defined answer when the tool it needs is absent. Both gates used to
collapse `svc_wait_http_ready`'s distinct "curl absent" return (2) into
the same `die` a genuinely-down portal gets — on a minimal box without
curl, `./arailctl start`/`restart` under an active daemon always failed,
even when the portal came up fine. The fix: branch on rc 2 (and on
`scripts/lib/services.sh` itself being unreadable, the sibling "cannot
verify" case) and fall back to the pre-readiness-gate behavior (print the
URL, warn once, exit 0) instead of dying.

Drives the REAL blocks extracted verbatim from arailctl (mirroring
test_daemon_predicate.py's `_run_start_guard` extraction pattern) — never
a reimplementation of the gate logic under test. `svc_wait_http_ready` is
stubbed via a throwaway `scripts/lib/services.sh` at a temp REPO_ROOT
(returning 2, or absent entirely) rather than by trying to hide the real
system `curl` from PATH, which — unlike a stubbed function — needs no
platform-specific PATH curation to be deterministic.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ARAILCTL = REPO_ROOT / "arailctl"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _extract(marker_start: str, marker_end: str) -> str:
    src = ARAILCTL.read_text(encoding="utf-8")
    start_idx = src.index(marker_start)
    end_idx = src.index(marker_end, start_idx)
    return src[start_idx:end_idx]


# The `start` case's daemon-mode readiness gate — starting from the
# comment right before its OWN `[[ -f services.sh ]] && source
# services.sh` line (so this test's stub actually gets sourced, exactly
# as the real invocation does it) through (but not including) the
# foreground `exec bash scripts/start.sh` fallthrough a few lines after
# its own `die`.
_START_GATE = _extract(
    "# ARCHITECTURE.md §8.3: this used to print the URL and exit 0",
    'exec bash "$REPO_ROOT/scripts/start.sh" "$@"',
)

# The `restart` case's daemon-mode readiness gate — same shape, starting
# from ITS OWN (differently-worded, so distinct from the marker above)
# comment right before its `[[ -f services.sh ]] && source services.sh`
# line, through (but not including) the "# Foreground." comment that
# follows its own `die`.
_RESTART_GATE = _extract(
    "# §8.3: identical readiness gate to start's daemon branch —",
    "# Foreground. --all is an explicit refusal",
)


def _run(repo_root: Path, gate_src: str, services_sh: str | None) -> subprocess.CompletedProcess:
    """services_sh=None -> scripts/lib/services.sh does not exist at all
    (the sibling "cannot verify" case). services_sh=<text> -> that text
    becomes scripts/lib/services.sh's contents (a throwaway stub, never
    the real file — this test is about arailctl's OWN branching on the
    gate's outcome, not services.sh's own probe logic, which
    tests/cli/root_start_driver.sh already covers against the real file)."""
    (repo_root / "scripts" / "lib").mkdir(parents=True, exist_ok=True)
    if services_sh is not None:
        (repo_root / "scripts" / "lib" / "services.sh").write_text(services_sh, encoding="utf-8")
    script = f"""
        set -uo pipefail
        REPO_ROOT="{repo_root}"
        say()  {{ echo "SAY: $*"; }}
        warn() {{ echo "WARN: $*"; }}
        die()  {{ echo "DIE: $*" >&2; exit 1; }}
        {gate_src}
        echo "GATE_FELL_THROUGH"
    """
    return subprocess.run(
        [_BASH, "-c", script],
        capture_output=True, text=True, timeout=15,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
    )


@pytest.mark.parametrize("which,gate_src", [("start", _START_GATE), ("restart", _RESTART_GATE)])
def test_curl_absent_degrades_instead_of_dying(tmp_path, which, gate_src):
    res = _run(tmp_path, gate_src, services_sh="svc_wait_http_ready() { return 2; }\n")
    assert res.returncode == 0, (
        f"{which}'s daemon readiness gate died on curl-absent (rc 2) instead of "
        f"degrading: {res.stdout}{res.stderr}"
    )
    assert "DIE:" not in res.stdout + res.stderr, res.stdout + res.stderr
    assert "WARN: curl not found" in res.stdout, res.stdout
    assert "SAY:" in res.stdout, res.stdout
    assert "GATE_FELL_THROUGH" not in res.stdout, (
        "the degrade path must exit 0 directly, not fall through to the "
        f"foreground/exec branch: {res.stdout}"
    )


@pytest.mark.parametrize("which,gate_src", [("start", _START_GATE), ("restart", _RESTART_GATE)])
def test_services_sh_missing_degrades_instead_of_dying(tmp_path, which, gate_src):
    res = _run(tmp_path, gate_src, services_sh=None)
    assert res.returncode == 0, (
        f"{which}'s daemon readiness gate died on a missing services.sh "
        f"instead of degrading: {res.stdout}{res.stderr}"
    )
    assert "DIE:" not in res.stdout + res.stderr, res.stdout + res.stderr
    assert "WARN: scripts/lib/services.sh not found" in res.stdout, res.stdout
    assert "SAY:" in res.stdout, res.stdout


@pytest.mark.parametrize("which,gate_src", [("start", _START_GATE), ("restart", _RESTART_GATE)])
def test_portal_genuinely_unreachable_still_dies(tmp_path, which, gate_src):
    """The degrade path must not swallow a REAL failure — curl present,
    services.sh present, portal never answers (rc 1) still dies."""
    res = _run(tmp_path, gate_src, services_sh="svc_wait_http_ready() { return 1; }\n")
    assert res.returncode == 1, res.stdout + res.stderr
    assert "DIE:" in res.stderr, res.stdout + res.stderr
    assert "did not answer within 30s" in res.stderr, res.stdout + res.stderr
