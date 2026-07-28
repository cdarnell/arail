"""REVIEW.md M1 — the readiness probe must verify token AND checkout, not
just an HTTP 200.

§3.5 stage 5 / §2.3 step 4 both require `token == $instance_token &&
checkout == $REPO_ROOT` before a launch may be declared ready — the
registry record is only written after this check passes (§2.2's "a
record's existence means this instance was, at some point, actually
serving"). Before this fix, `scripts/start.sh`'s [6/8] Portal-up poll
only checked `curl -sf ... >/dev/null` — any HTTP 200 counted, including
one from a foreign process that grabbed the port first (F1's exact
scenario) or a stale process from a different checkout.

Extracts the [6/8] Portal-up polling block VERBATIM out of
scripts/start.sh (never a reimplementation — same technique
test_daemon_predicate.py's guard-extraction test already uses) and drives
it with a stubbed `curl` answering with a foreign token/checkout,
asserting the mismatch branch fires (never falls through to "ready") and
`_instance_cleanup_and_exit` is invoked with exit code 1.

A true end-to-end drive of this stage (a real uvicorn process actually
bound to the target port) is exercised by tests/instance_start_driver.sh
scenario 6 (bind conflict) and by QA's manual two-World launch — a fully
scripted foreign-process variant is impractical here because sourcing
`.venv/bin/activate` always prepends the REAL venv's `bin/` (which has
a real `uvicorn`) ahead of any PATH-based stub, so this extraction test
is the reliable, fast, dependency-free way to pin the comparison logic
itself.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
START_SH = REPO_ROOT / "scripts" / "start.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _extract(text: str, start_marker: str, end_marker: str) -> str:
    start_idx = text.index(start_marker)
    end_idx = text.index(end_marker, start_idx)
    return text[start_idx:end_idx]


def _readiness_block() -> str:
    start_sh = START_SH.read_text(encoding="utf-8")
    json_field_fn = _extract(start_sh, "_json_field() {", "\n}\n") + "\n}\n"
    portal_block = _extract(
        start_sh,
        "    # REVIEW.md M1:",
        '    echo "✓"\n\n    # ── [7/8] Memory up',
    )
    return json_field_fn + "\n" + portal_block


def _run_probe(curl_body: str, curl_ok: bool = True, child_sleep: float = 2) -> subprocess.CompletedProcess:
    """Drives the extracted [6/8] block with a stub `curl` returning
    `curl_body` (or failing outright if curl_ok is False), a real
    backgrounded `sleep` standing in for the uvicorn child (so `kill -0`
    succeeds on the first poll), and a stub `_instance_cleanup_and_exit`
    that reports its exit code instead of actually tearing anything down.

    `child_sleep` is short (~1s) for the "curl never answers" case so the
    loop's own `kill -0` check breaks it quickly instead of running the
    real 60s cap.
    """
    block = _readiness_block()
    curl_body_escaped = curl_body.replace("'", "'\\''")
    curl_fn = (
        f"printf '%s' '{curl_body_escaped}'; exit 0" if curl_ok else "exit 1"
    )
    script = f"""
        set -uo pipefail
        BIND="127.0.0.1"
        portal_port="9199"
        REPO_ROOT="/abs/real/checkout"
        instance_token="expected-token-abc"
        _INST_PIDS=()
        inst_log_dir() {{ echo "/tmp"; }}
        curl() {{ {curl_fn}; }}
        _instance_cleanup_and_exit() {{ echo "CLEANUP_CALLED:$1"; exit "$1"; }}
        sleep {child_sleep} &
        portal_pid=$!
        _drive() {{
        {block}
        echo "READY_FALLTHROUGH"
        }}
        _drive
        kill "$portal_pid" 2>/dev/null || true
    """
    return subprocess.run(
        [_BASH, "-c", script],
        capture_output=True, text=True, timeout=15,
    )


def test_matching_token_and_checkout_is_ready(tmp_path):
    body = '{"slug":"finance","token":"expected-token-abc","checkout":"/abs/real/checkout"}'
    res = _run_probe(body)
    assert "READY_FALLTHROUGH" in res.stdout, res.stdout + res.stderr
    assert "CLEANUP_CALLED" not in res.stdout


def test_foreign_token_is_rejected_not_accepted_as_ready(tmp_path):
    """The exact F1 scenario: an HTTP 200 with the WRONG token must never
    be treated as our instance coming up."""
    body = '{"slug":"foreign","token":"not-our-token","checkout":"/abs/real/checkout"}'
    res = _run_probe(body)
    assert "READY_FALLTHROUGH" not in res.stdout, res.stdout + res.stderr
    assert "CLEANUP_CALLED:1" in res.stdout
    assert "mismatch" in (res.stdout + res.stderr).lower()


def test_wrong_checkout_is_rejected(tmp_path):
    """F4's counterpart at boot time: right token, but a different checkout
    path (e.g. a stale process from another clone) must also fail."""
    body = '{"slug":"finance","token":"expected-token-abc","checkout":"/some/other/checkout"}'
    res = _run_probe(body)
    assert "READY_FALLTHROUGH" not in res.stdout, res.stdout + res.stderr
    assert "CLEANUP_CALLED:1" in res.stdout


def test_no_response_falls_through_to_generic_not_up_message(tmp_path):
    """Distinguish the two failure messages: no answer at all is still
    "portal did not come up" (F1's timeout case), not the mismatch text —
    only a REAL foreign answer should ever say "mismatch"."""
    res = _run_probe("", curl_ok=False, child_sleep=1)
    assert "READY_FALLTHROUGH" not in res.stdout, res.stdout + res.stderr
    assert "CLEANUP_CALLED:1" in res.stdout
    assert "mismatch" not in (res.stdout + res.stderr).lower()
