"""QA pass for the 2026-07-29-elite-cli sprint — the wrapper for
tests/cli/qa_edge_driver.sh plus the strict-xfail pins for every product
defect this pass found (Q1-Q6 in
sprints/2026-07-29-elite-cli/TEST_REPORT.md).

Why xfail and not a fix: QA reports, the builder fixes. Each test below
asserts the CORRECT behaviour (per docs/cli.md's exit-code contract or
ARCHITECTURE.md's own failure-mode table), so it fails today and turns
green the moment the defect is fixed. ``strict=True`` makes an
un-announced fix loud: the test XPASSes, pytest fails the run, and whoever
fixed it is told to delete the marker instead of leaving a permanently
misleading "expected failure" behind.

Same wrapper/skip idioms as tests/test_cli_status.py.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "qa_edge_driver.sh"
LIB_SH = REPO_ROOT / "tests" / "cli" / "lib.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")

# A deliberately minimal PATH: no ttyd/jupyter/code-server/ollama, so a
# scenario's verdict never depends on what the developer happens to have
# installed.
SAFE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _find_test_venv() -> str | None:
    candidates = [
        os.environ.get("ARAIL_TEST_VENV", ""),
        str(REPO_ROOT / ".venv"),
        str(REPO_ROOT.parent / ".venv"),
    ]
    for c in candidates:
        if c and Path(c, "bin", "python").exists():
            return c
    return None


def _fresh_clone(dest: Path) -> Path:
    """The tracked-file shape a `git clone` leaves behind — and nothing
    else. No .env, no lab.conf, no .venv, no lab/: the state every new
    user's very first `./arailctl <verb>` runs in."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / "scripts", dest / "scripts")
    shutil.copy2(REPO_ROOT / "arailctl", dest / "arailctl")
    shutil.copy2(REPO_ROOT / "components.json", dest / "components.json")
    (dest / "docs").mkdir(exist_ok=True)
    shutil.copy2(REPO_ROOT / "docs" / "cli.md", dest / "docs" / "cli.md")
    return dest


def _provisioned_repo(dest: Path, *, lab_conf: str | None = None) -> Path:
    """A fresh clone plus the one file that makes `status` treat the lab as
    configured. No .venv — every scenario below that needs one says so."""
    _fresh_clone(dest)
    (dest / ".env").write_text('LAB_NAME="QA Lab"\nLAB_SHORT_NAME=qa\n')
    if lab_conf is not None:
        (dest / "lab.conf").write_text(lab_conf)
    return dest


def _ctl(repo: Path, *args: str, home: Path, timeout: int = 180):
    """Run ./arailctl non-interactively (no tty on stdin, captured stdout)
    with an isolated HOME so a developer's real launchd plists can never
    leak into a scenario."""
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = SAFE_PATH
    env.pop("ARAIL_COLOR", None)
    env.pop("NO_COLOR", None)
    return subprocess.run(
        [_BASH, "arailctl", *args],
        cwd=str(repo), env=env, capture_output=True, text=True,
        timeout=timeout, stdin=subprocess.DEVNULL,
    )


def _run_harness_snippet(body: str, tmp_path: Path, timeout: int = 240):
    """Run a bash snippet with tests/cli/lib.sh already sourced — the
    fixtures a couple of these repros need (a registry record backed by a
    REAL live process, a fake venv) exist there and must not be
    re-implemented in Python."""
    script = tmp_path / "snippet.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -uo pipefail\n"
        f'source "{LIB_SH}"\n'
        + textwrap.dedent(body)
    )
    env = dict(os.environ)
    env.setdefault("ARAIL_TEST_VENV", _find_test_venv() or "")
    return subprocess.run(
        [_BASH, str(script)], capture_output=True, text=True,
        timeout=timeout, env=env, stdin=subprocess.DEVNULL,
    )


# ---------------------------------------------------------------------------
# The driver wrapper (QA-1..QA-8 — all green)
# ---------------------------------------------------------------------------

def test_qa_edge_driver_scenarios():
    venv = _find_test_venv()
    if venv is None:
        pytest.skip("no usable .venv found for ARAIL_TEST_VENV — cannot import arail.*")
    env = dict(os.environ)
    env["ARAIL_TEST_VENV"] = venv
    result = subprocess.run(
        [_BASH, str(DRIVER)], capture_output=True, text=True, timeout=600, env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# Q1 — `restart` announces a state change that never happened.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q1 (TEST_REPORT.md): arailctl's F13 notice fires on ANY non-zero start "
    "code, even when the stop phase stopped nothing at all. On a fresh "
    "clone — the first thing a new user's `./arailctl restart` hits — the "
    "CLI reports 'the root lab was stopped ... the lab is now DOWN' about a "
    "lab that was never up. F13's own wording ('the operator does not "
    "realize the state changed') presumes a state change occurred."))
def test_q1_restart_does_not_claim_a_stop_that_never_happened(tmp_path):
    repo = _fresh_clone(tmp_path / "repo")
    home = tmp_path / "home"
    home.mkdir()
    res = _ctl(repo, "restart", home=home)
    out = res.stdout + res.stderr
    assert "No running services found" in out, out  # nothing was stopped
    assert "the lab is now DOWN" not in out, out


# ---------------------------------------------------------------------------
# Q2 — doctor's bad-flag exit code contradicts the documented contract.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q2 (TEST_REPORT.md): docs/cli.md's exit-code table assigns 2 to 'usage "
    "error — bad flag ... every verb with flags', and ARCHITECTURE.md §5.2's "
    "doctor row says '2 bad flag'. arailctl folds EVERY non-zero from "
    "`python -m arail.doctor` (including argparse's own 2) into 3 "
    "('degraded'), so a script cannot tell 'this lab is degraded' from 'I "
    "typo'd a flag'."))
def test_q2_doctor_rejects_an_unknown_flag_with_exit_2(tmp_path):
    venv = _find_test_venv()
    if venv is None:
        pytest.skip("doctor needs a real .venv")
    repo = tmp_path / "repo"
    res = _run_harness_snippet(f"""
        FAKE="{repo}"
        make_fake_repo "$FAKE" >/dev/null
        make_fake_venv "$FAKE"
        link_real_uvicorn "$FAKE"
        ( cd "$FAKE" && HOME="{tmp_path}/home" PATH="{SAFE_PATH}" \\
            bash arailctl doctor --zzz-bogus-flag </dev/null >/dev/null 2>&1 )
        echo "rc=$?"
    """, tmp_path, timeout=300)
    rc_line = [ln for ln in res.stdout.splitlines() if ln.startswith("rc=")]
    assert rc_line, res.stdout + res.stderr
    assert rc_line[-1] == "rc=2", rc_line[-1] + "\n" + res.stdout + res.stderr


# ---------------------------------------------------------------------------
# Q3 — `stop` silently reinterprets a malformed target as "stop whatever
# you find", instead of rejecting it.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q3a (TEST_REPORT.md): docs/cli.md's canonical exit-code table assigns 2 "
    "to 'usage error — bad flag, missing flag value ... every verb with "
    "flags', while `stop`'s own section says '0 always ... 2 invalid slug' — "
    "the doc contradicts itself, and the code follows neither: reset.sh's "
    "parser swallows an unknown flag in its catch-all `*)` arm and a "
    "value-less `--world` as an empty slug, and BOTH fall through to the "
    "unscoped auto-resolution branch (see Q3b for why that is the part that "
    "matters) and exit 0. Whichever half of the doc is meant to win, one of "
    "the two must change."))
@pytest.mark.parametrize("argv", [("stop", "--zzz-bogus"), ("stop", "--world")])
def test_q3a_stop_rejects_a_malformed_target_with_exit_2(tmp_path, argv):
    repo = _provisioned_repo(tmp_path / "repo")
    home = tmp_path / "home"
    home.mkdir()
    res = _ctl(repo, *argv, home=home)
    assert res.returncode == 2, (
        f"exit {res.returncode}\n" + res.stdout + res.stderr
    )


@pytest.mark.xfail(strict=True, reason=(
    "Q3b (TEST_REPORT.md): the exit code above is cosmetic; the scope "
    "escalation is not. `stop --world` with its value missing (or a typo'd "
    "`--wrold ai`) becomes a bare `stop`, whose auto-resolution branch stops "
    "the lone live World AND then the root services — the operator asked to "
    "stop ONE World by name and got everything. Same family as REVIEW.md B2, "
    "reached through the argv parser instead of the pid fallback."))
def test_q3b_a_valueless_world_flag_does_not_stop_the_lone_live_world(tmp_path):
    if _find_test_venv() is None:
        pytest.skip("needs the cli harness venv for the live-instance fixture")
    res = _run_harness_snippet(f"""
        WORK="{tmp_path}/w"; mkdir -p "$WORK/home"
        FAKE="$WORK/repo"
        make_fake_repo "$FAKE" >/dev/null
        make_fake_venv "$FAKE"
        PORT="$(cli_test_random_port)"
        cli_test_assert_port_safe "$PORT"
        write_lab_conf "$FAKE" "$PORT" "$((PORT+1))" "$((PORT+2))" "$((PORT+3))" "$((PORT+4))"
        cli_test_write_stub_ps_for_slugs "$FAKE/stubbin" "ai:$((PORT+1))"
        cli_test_fabricate_live_instance "$FAKE" ai "$((PORT+1))"
        PID="$CLI_TEST_LAST_FABRICATED_PID"
        ( cd "$FAKE" && HOME="$WORK/home" PATH="$FAKE/stubbin:{SAFE_PATH}" \\
            _timeout 40 bash arailctl stop --world </dev/null >/dev/null 2>&1 )
        if kill -0 "$PID" 2>/dev/null; then echo "VERDICT=survived"; else echo "VERDICT=killed"; fi
        kill "$PID" 2>/dev/null; wait "$PID" 2>/dev/null
    """, tmp_path, timeout=240)
    assert "VERDICT=survived" in res.stdout, res.stdout + res.stderr


# ---------------------------------------------------------------------------
# Q4 — F3 (half-written lab.conf) is specified but not implemented.
# ---------------------------------------------------------------------------

_HALF_WRITTEN_LAB_CONF = "PORTAL_PORT=not-a-number\nBIND_ADDR=127.0.0.1\n"


@pytest.mark.xfail(strict=True, reason=(
    "Q4 (TEST_REPORT.md): ARCHITECTURE.md F3 names this exact input ('half-"
    "written lab.conf (interrupted setup) => non-numeric PORTAL_PORT') and "
    "specifies the recovery: 'New readers validate ^[0-9]+$ before use ... "
    "Warn once, fall back to the documented default, record in warnings[]; "
    "never abort.' None of that happens: status.sh's service-row emitter "
    "calls int() on the raw value, the ValueError traceback goes to stderr, "
    "and the portal row is silently DROPPED from root.services[] while "
    "warnings[] stays empty."))
def test_q4_half_written_lab_conf_degrades_honestly(tmp_path):
    repo = _provisioned_repo(tmp_path / "repo", lab_conf=_HALF_WRITTEN_LAB_CONF)
    home = tmp_path / "home"
    home.mkdir()
    res = _ctl(repo, "status", "--json", home=home)
    doc = json.loads(res.stdout)          # stdout stays valid JSON (F18 holds)
    services = {s["name"]: s for s in doc["root"]["services"]}
    assert "Traceback (most recent call last)" not in res.stderr, res.stderr
    assert "portal" in services, sorted(services)
    assert doc["warnings"], "an unusable PORTAL_PORT must be recorded in warnings[]"


# ---------------------------------------------------------------------------
# Q5 — control bytes from a shared World's display_name reach the terminal.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q5 (TEST_REPORT.md, pre-existing but inside this sprint's rewritten "
    "surface): a World bundle is made to be SHARED (world-forge / "
    "world-mount), so manifest.display_name is not the operator's own text. "
    "status.sh prints it verbatim, so a bundle can emit CSI sequences (clear "
    "screen, colour), a CR to overwrite the line it is on, or a newline to "
    "forge an extra status row — even when stdout is a pipe, which the same "
    "sprint's F25/gap-10 work made ANSI-free for the CLI's OWN colours. The "
    "--json renderer is already safe (json.dumps escapes control bytes); "
    "only the human one is not."))
def test_q5_hostile_display_name_cannot_emit_control_bytes(tmp_path):
    repo = _provisioned_repo(tmp_path / "repo")
    home = tmp_path / "home"
    home.mkdir()
    reg = repo / "lab" / "instances" / "registry.d"
    reg.mkdir(parents=True)
    evil = "\x1b[2J\x1b[1;31mPWNED\r  ● root       Real Lab   :8080  pid 1\n"
    (reg / "evil.json").write_text(json.dumps({
        "schema": "arail.instance-registry/v1", "slug": "evil",
        "display_name": evil, "checkout": str(repo),
        "instance_root": str(repo / "i"), "data_dir": str(repo / "i" / "d"),
        "pkb_root": str(repo / "i" / "p"), "bind": "127.0.0.1",
        "portal_port": 19999, "lance_port": 20003,
        "launcher_pid": 999999, "portal_pid": 999999, "memory_pid": 999999,
        "token": "t", "started_at": "2026-01-01T00:00:00Z",
        "arailctl_version": "test",
    }))
    res = _ctl(repo, "status", home=home)
    out = res.stdout + res.stderr
    assert "\x1b" not in out, "an ESC byte from display_name reached a piped terminal"
    assert "\r" not in out, "a CR from display_name reached a piped terminal"
    assert "root       Real Lab" not in out, "display_name forged a status row"


# ---------------------------------------------------------------------------
# Q7 — the tier verb's documented unknown-tier code is not the one it uses.
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q7 (TEST_REPORT.md): docs/cli.md:130-131 states, for `tier`, "
    "'Exit: 0 success ... 1 pip/tier failure - 2 unknown tier', and "
    "ARCHITECTURE.md §5.1's tier row says the same. scripts/upgrade.sh "
    "reaches an unknown tier through its generic `die`, which is exit 1 — "
    "indistinguishable from 'the pip install failed', which is precisely "
    "the distinction the documented contract makes."))
@pytest.mark.parametrize("verb", ["tier", "upgrade"])
def test_q7_unknown_tier_is_a_usage_error(tmp_path, verb):
    repo = _provisioned_repo(tmp_path / "repo")
    home = tmp_path / "home"
    home.mkdir()
    res = _ctl(repo, verb, "not-a-tier", home=home)
    assert res.returncode == 2, (
        f"exit {res.returncode}\n" + res.stdout + res.stderr
    )


# ---------------------------------------------------------------------------
# Q6 — an empty --only/--skip value is accepted as "no filter".
# ---------------------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason=(
    "Q6 (TEST_REPORT.md): `--only` with a value is validated against the "
    "closed phase vocabulary, but `--only=` (empty) skips validation "
    "entirely and _install_phase_enabled reads an empty list as 'no filter' "
    "— so an operator who meant to run ONE phase silently runs all five. "
    "docs/cli.md's table calls a missing flag value a usage error (2)."))
def test_q6_install_rejects_an_empty_phase_list(tmp_path):
    if _find_test_venv() is None:
        pytest.skip("install's preflight needs a .venv to consider the lab provisioned")
    res = _run_harness_snippet(f"""
        WORK="{tmp_path}/w"; mkdir -p "$WORK/home"
        FAKE="$WORK/repo"
        make_fake_repo "$FAKE" >/dev/null
        cli_test_mark_provisioned "$FAKE" airgapped
        ( cd "$FAKE" && HOME="$WORK/home" PATH="{SAFE_PATH}" \\
            _timeout 120 bash arailctl install --only= --check </dev/null >/dev/null 2>&1 )
        echo "rc=$?"
    """, tmp_path, timeout=300)
    rc_line = [ln for ln in res.stdout.splitlines() if ln.startswith("rc=")]
    assert rc_line, res.stdout + res.stderr
    assert rc_line[-1] == "rc=2", rc_line[-1] + "\n" + res.stdout + res.stderr
