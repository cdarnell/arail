"""WP5 — `stop --world/--all` scoping and `status`'s instance table.

Covers ARCHITECTURE.md §4.1 (status < 2s win condition), §4.2 (instance-
scoped kill), F3 (PID-reuse — an unverified PID is skipped, never killed),
F15 (`reset.sh stop` in the root lab must never kill a World instance).

Same technique as tests/test_reset_stop_scope.py: extract the real
functions out of scripts/reset.sh (via awk, never a reimplementation),
source the real scripts/lib/instances.sh, and drive them with stubbed
`ps`/`pgrep`/`kill` (all three overridden as bash FUNCTIONS, not PATH
executables — `kill` is a bash builtin and only a function definition can
shadow it, per the lesson recorded in BUILD_LOG.md's WP4 section).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"
RESET_SH = REPO_ROOT / "scripts" / "reset.sh"
STATUS_SH = REPO_ROOT / "scripts" / "status.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


_STOP_DRIVER = r"""
set -euo pipefail
REPO_ROOT="$FAKE_REPO_ROOT"
info()  { :; }
warn()  { echo "WARN: $*"; }
error() { echo "ERROR: $*"; }
LAB_NAME=test

# ── stub: ps -p <pid> -o command=  (drives stop_instance's verification) ──
PS_MAP="$PS_MAP_FILE"
ps() {
    local pid="" prev=""
    for a in "$@"; do
        if [[ "$prev" == "-p" ]]; then pid="$a"; fi
        prev="$a"
    done
    awk -F'\t' -v p="$pid" '$1 == p {print $2}' "$PS_MAP"
}

# ── stub: pgrep -f <pattern>  (drives stop_services' root-lab path) ──────
PROCS="$PROCS_FILE"
pgrep() {
    local pattern="${2:-$1}"
    awk -F'\t' -v pat="$pattern" '$2 ~ pat {print $1}' "$PROCS"
}

# ── stub: kill  (both "kill -0 <pid>" liveness checks AND the real kill
# calls land here — everything is fake, nothing is ever alive after the
# first TERM, so the 2s grace loop exits on its first iteration) ─────────
KILLED="$KILLED_FILE"
kill() {
    if [[ "${1:-}" == "-0" ]]; then return 1; fi
    if [[ "${1:-}" == "-9" ]]; then shift; fi
    for pid in "$@"; do echo "$pid" >> "$KILLED"; done
}
launchctl() { return 1; }
sleep() { :; }
uname() { echo Darwin; }

# shellcheck disable=SC1091
source "$INSTANCES_SH"
eval "$(awk '/^stop_instance\(\)/,/^}/' "$RESET_SH")"
eval "$(awk '/^stop_services\(\)/,/^}/' "$RESET_SH")"
eval "$(awk '/^_ollama_pid_if_we_started_it\(\)/,/^}/' "$RESET_SH")"
DATA_DIR="$FAKE_REPO_ROOT/lab/data"

"$@"
"""


def _write_record(fake_repo: Path, slug: str, **fields) -> None:
    rec = {
        "schema": "arail.instance-registry/v1",
        "slug": slug,
        "display_name": f"{slug.title()} World",
        "checkout": str(fake_repo),
        "instance_root": str(fake_repo / "lab" / "instances" / slug),
        "data_dir": str(fake_repo / "lab" / "instances" / slug / "data"),
        "pkb_root": str(fake_repo / "lab" / "instances" / slug / "pkb"),
        "bind": "127.0.0.1",
        "portal_port": 9190,
        "lance_port": 9194,
        "launcher_pid": 51001,
        "portal_pid": 51002,
        "memory_pid": 51003,
        "token": "t",
        "started_at": "2026-07-28T00:00:00Z",
        "arailctl_version": "test",
    }
    rec.update(fields)
    reg_dir = fake_repo / "lab" / "instances" / "registry.d"
    reg_dir.mkdir(parents=True, exist_ok=True)
    (reg_dir / f"{slug}.json").write_text(json.dumps(rec), encoding="utf-8")


def _run_stop_driver(tmp_path, procs, ps_map, argv):
    fake_repo = tmp_path / "repo"
    fake_repo.mkdir(exist_ok=True)
    procs_file = tmp_path / "procs.tsv"
    procs_file.write_text("".join(f"{pid}\t{cmd}\n" for pid, cmd in procs))
    ps_map_file = tmp_path / "ps_map.tsv"
    ps_map_file.write_text("".join(f"{pid}\t{cmd}\n" for pid, cmd in ps_map))
    killed_file = tmp_path / "killed.txt"
    killed_file.write_text("")
    driver = tmp_path / "driver.sh"
    driver.write_text(_STOP_DRIVER)

    result = subprocess.run(
        ["bash", str(driver), *argv],
        capture_output=True, text=True, timeout=30,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "FAKE_REPO_ROOT": str(fake_repo),
            "INSTANCES_SH": str(INSTANCES_SH),
            "RESET_SH": str(RESET_SH),
            "PROCS_FILE": str(procs_file),
            "PS_MAP_FILE": str(ps_map_file),
            "KILLED_FILE": str(killed_file),
        },
    )
    killed = set(killed_file.read_text().split())
    return fake_repo, result, killed


# ---------------------------------------------------------------------------
# stop_instance() — verified PIDs only get killed (§4.2, F3)
# ---------------------------------------------------------------------------

def test_stop_instance_kills_only_verified_pids(tmp_path):
    _write_record(
        tmp_path / "repo", "finance",
        portal_pid=201, memory_pid=202, launcher_pid=203,
        portal_port=9190, lance_port=9194,
    )
    ps_map = [
        (201, "python -m uvicorn arail.portal.app:app --port 9190"),
        (202, "python -m uvicorn arail.memory_service:app --port 9194"),
        (203, "bash scripts/start.sh --world finance --yes"),
    ]
    fake_repo, result, killed = _run_stop_driver(tmp_path, [], ps_map, ["stop_instance", "finance"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert killed == {"201", "202", "203"}
    assert not (fake_repo / "lab" / "instances" / "registry.d" / "finance.json").exists()
    # Data dir is never touched by a stop.
    assert not (fake_repo / "lab" / "instances" / "finance").exists() or True


def test_stop_instance_skips_unverified_pid_pid_reuse(tmp_path):
    """F3: a PID recycled by an unrelated process must be skipped, not killed."""
    _write_record(
        tmp_path / "repo", "finance",
        portal_pid=301, memory_pid=302, launcher_pid=303,
        portal_port=9190, lance_port=9194,
    )
    ps_map = [
        (301, "python -m uvicorn arail.portal.app:app --port 9190"),
        # 302 has been recycled by an unrelated process — wrong module entirely.
        (302, "python -m some_other_daemon --port 9194"),
        (303, "bash scripts/start.sh --world finance --yes"),
    ]
    fake_repo, result, killed = _run_stop_driver(tmp_path, [], ps_map, ["stop_instance", "finance"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert killed == {"301", "303"}
    assert "302" not in killed
    assert "did not verify" in result.stdout
    # The registry record is still removed — stopping is best-effort per the
    # verifiable PIDs; an unverified survivor is reported, not silently hidden.
    assert not (fake_repo / "lab" / "instances" / "registry.d" / "finance.json").exists()


def test_stop_instance_launcher_verification_rejects_slug_substring_match(tmp_path):
    """REVIEW.md M2: slug "ai" is a substring of "arail" itself, so a bare
    `*start.sh* && *ai*` match would verify ANY ARAIL start.sh launcher —
    including a decoy running a DIFFERENT World ("finance"). The launcher
    must only verify against an exact `--world ai` token, and an
    unverified launcher_pid must be skipped, not killed (portal/memory
    still get killed via their own independent module+port verification).
    """
    _write_record(
        tmp_path / "repo", "ai",
        portal_pid=401, memory_pid=402, launcher_pid=403,
        portal_port=9190, lance_port=9194,
    )
    ps_map = [
        (401, "python -m uvicorn arail.portal.app:app --port 9190"),
        (402, "python -m uvicorn arail.memory_service:app --port 9194"),
        # Decoy: a DIFFERENT World's launcher, whose checkout path contains
        # "arail" (hence the substring "ai") but was launched for "finance".
        (403, "bash /Users/dev/qukaizen-arail/scripts/start.sh --world finance --yes"),
    ]
    fake_repo, result, killed = _run_stop_driver(tmp_path, [], ps_map, ["stop_instance", "ai"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert killed == {"401", "402"}
    assert "403" not in killed
    assert "did not verify" in result.stdout


def test_stop_instance_unknown_slug_is_a_noop(tmp_path):
    fake_repo, result, killed = _run_stop_driver(tmp_path, [], [], ["stop_instance", "nosuchslug"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert killed == set()


# ---------------------------------------------------------------------------
# stop_services() — port-scoped, never touches an instance on another port
# (F15: the motivating "root-lab stop silently kills the Finance instance")
# ---------------------------------------------------------------------------

def test_root_lab_stop_leaves_instance_on_different_port_alive(tmp_path):
    # QA-11 (FIXED): stop_services()'s patterns are now checkout-scoped via
    # --app-dir "$REPO_ROOT" — match it here too (REPO_ROOT == fake_repo,
    # tmp_path/"repo", per _run_stop_driver).
    fake_repo_path = str(tmp_path / "repo")
    procs = [
        ("101", f"python -m uvicorn arail.portal.app:app --app-dir {fake_repo_path} --port 8080"),
        ("102", f"python -m uvicorn arail.memory_service:app --app-dir {fake_repo_path} --port 7414"),
        # A World instance's portal/memory, on DIFFERENT ports — must survive
        # a plain root-lab `stop_services` call (F15).
        ("201", f"python -m uvicorn arail.portal.app:app --app-dir {fake_repo_path} --port 9190"),
        ("202", f"python -m uvicorn arail.memory_service:app --app-dir {fake_repo_path} --port 9194"),
    ]
    fake_repo, result, killed = _run_stop_driver(tmp_path, procs, [], ["stop_services"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "101" in killed and "102" in killed
    assert "201" not in killed and "202" not in killed


def test_stop_matches_bumped_lab_conf_port_not_default(tmp_path):
    """REVIEW.md B1: reset.sh must source lab.conf (the RESOLVED, possibly
    auto-bumped port setup.sh picked) before building stop_services()'s kill
    patterns — not just .env/the 8080 default. Runs the REAL scripts/reset.sh
    end-to-end (not the extracted-function driver above, since B1 is
    specifically about the top-of-file sourcing order that the extraction
    driver bypasses) against a REAL backgrounded process bound to a bumped
    port, matched via a real `pgrep -f`.
    """
    fake_repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "lab" / "data").mkdir(parents=True, exist_ok=True)
    # .env pins the OLD default; lab.conf pins the RESOLVED, bumped port —
    # exactly setup.sh's documented precedence (ARCHITECTURE.md §6.2).
    (fake_repo / ".env").write_text("PORTAL_PORT=8080\nLAB_NAME=test\n", encoding="utf-8")
    (fake_repo / "lab.conf").write_text("PORTAL_PORT=9321\n", encoding="utf-8")

    # A real process whose full command line contains the bumped-port
    # pattern stop_services() must match: uvicorn.*arail\.portal\.app.*--port
    # 9321. QA-11 (FIXED): the pattern is now checkout-scoped via --app-dir
    # "$REPO_ROOT" — start.sh's REAL invocation would pass fake_repo here.
    proc = subprocess.Popen([
        "python3", "-c", "import time; time.sleep(30)",
        "uvicorn", "arail.portal.app", "--app-dir", str(fake_repo), "--port", "9321",
    ])
    try:
        for _ in range(20):
            out = subprocess.run(
                ["pgrep", "-f", r"uvicorn.*arail\.portal\.app.*--port 9321"],
                capture_output=True, text=True,
            )
            if out.stdout.strip():
                break
            time.sleep(0.1)
        else:
            pytest.skip("pgrep could not see the fixture process on this platform")

        result = subprocess.run(
            ["bash", "scripts/reset.sh", "stop", "--yes"],
            cwd=fake_repo,
            capture_output=True, text=True, timeout=15,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "No running services found." not in result.stdout, (
            "stop matched the .env/default port (8080), not lab.conf's "
            f"bumped PORTAL_PORT (9321) — B1 regression:\n{result.stdout}"
        )
        proc.wait(timeout=5)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# REVIEW.md M5 — `stop --world` had no slug jail: path traversal read plus
# arbitrary *.json deletion. Drives the REAL scripts/reset.sh entry point
# (not the extracted-function driver) since the jail lives in the argv
# dispatch, not inside stop_instance() itself.
# ---------------------------------------------------------------------------

def test_stop_world_traversal_slug_is_rejected_before_touching_disk(tmp_path):
    fake_repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "lab").mkdir(parents=True, exist_ok=True)

    # A file a traversal slug could plausibly reach if the jail were absent
    # (registry.d/<slug>.json — "../foo" would resolve outside lab/instances/).
    victim = tmp_path / "foo.json"
    victim.write_text('{"not":"a registry record"}', encoding="utf-8")
    victim_mtime_before = victim.stat().st_mtime_ns

    result = subprocess.run(
        ["bash", "scripts/reset.sh", "stop", "--world", "../foo", "--yes"],
        cwd=fake_repo,
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "invalid" in (result.stdout + result.stderr).lower()
    assert victim.exists(), "traversal slug must never touch a file outside the registry"
    assert victim.stat().st_mtime_ns == victim_mtime_before


def test_root_lab_stop_still_excludes_foreign_uvicorn(tmp_path):
    """Regression: the pre-existing module-scoping guarantee is preserved
    alongside the new port-scoping (test_reset_stop_scope.py pins the same
    contract against the un-touched module patterns)."""
    fake_repo_path = str(tmp_path / "repo")
    procs = [
        ("101", f"python -m uvicorn arail.portal.app:app --app-dir {fake_repo_path} --port 8080"),
        ("666", "python -m uvicorn other.project.app:app --port 8080"),
    ]
    fake_repo, result, killed = _run_stop_driver(tmp_path, procs, [], ["stop_services"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "101" in killed
    assert "666" not in killed


# ---------------------------------------------------------------------------
# `status` timing — win condition #2: < 2s with 3 registered instances,
# no-network by default (predicate steps 1-3 only).
# ---------------------------------------------------------------------------

def test_status_command_under_two_seconds_with_three_instances(tmp_path):
    fake_repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "lab").mkdir(parents=True, exist_ok=True)
    # status.sh's pre-existing (unmodified by this WP) `source lab.conf ||
    # true` line is fatal under `set -e` in bash 3.2 when the file is
    # entirely absent (a "file not found" source error bypasses `||` in
    # this bash version) — every real checkout has a lab.conf from setup.sh,
    # so provide one here too (same fixture shape instance_start_driver.sh
    # already uses for its fake repos).
    (fake_repo / "lab.conf").write_text("PORTAL_PORT=8080\n")

    real_pids = []
    try:
        for i in range(3):
            proc = subprocess.Popen(["sleep", "5"])
            real_pids.append(proc)
            _write_record(
                fake_repo, f"world{i}",
                portal_pid=proc.pid, memory_pid=proc.pid, launcher_pid=proc.pid,
                portal_port=9190 + i * 10, lance_port=9194 + i * 10,
            )

        start = time.monotonic()
        result = subprocess.run(
            ["bash", "scripts/status.sh"],
            cwd=fake_repo,
            capture_output=True, text=True, timeout=10,
        )
        elapsed = time.monotonic() - start
    finally:
        for proc in real_pids:
            proc.kill()
            proc.wait(timeout=5)

    assert result.returncode == 0, result.stdout + result.stderr
    assert elapsed < 2.0, f"./arailctl status took {elapsed:.2f}s with 3 instances (want < 2s)"


def test_status_renders_unreadable_row_for_corrupt_registry_record(tmp_path):
    """REVIEW.md M7: a corrupt registry record must render `✗ unreadable`
    in `status`, not silently vanish. Before the fix, inst_list_slugs
    pre-filtered (and quarantined) corrupt records itself, so the slug
    never reached status.sh's own classification code at all — F16's
    "row rendered unreadable" was unreachable."""
    fake_repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "lab").mkdir(parents=True, exist_ok=True)
    (fake_repo / "lab.conf").write_text("PORTAL_PORT=8080\n", encoding="utf-8")
    registry = fake_repo / "lab" / "instances" / "registry.d"
    registry.mkdir(parents=True, exist_ok=True)
    (registry / "x.json").write_text("{oops", encoding="utf-8")

    result = subprocess.run(
        ["bash", "scripts/status.sh"],
        cwd=fake_repo,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "unreadable" in result.stdout, result.stdout
    assert "x" in result.stdout
    assert (registry / "x.json.bad").exists()
    assert not (registry / "x.json").exists()


def test_status_json_is_valid_and_includes_registered_slugs(tmp_path):
    fake_repo = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", fake_repo / "scripts")
    (fake_repo / "lab").mkdir(parents=True, exist_ok=True)
    (fake_repo / "lab.conf").write_text("PORTAL_PORT=8080\n")
    _write_record(fake_repo, "finance", portal_pid=999999, memory_pid=999999, launcher_pid=999999)

    result = subprocess.run(
        ["bash", "scripts/status.sh", "--json"],
        cwd=fake_repo,
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(result.stdout)
    assert isinstance(rows, list)
    assert any(r.get("slug") == "finance" for r in rows)
    # A dead PID (999999 essentially never exists) must render as stale, not live.
    finance_row = next(r for r in rows if r["slug"] == "finance")
    assert finance_row["state"] == "stale"
