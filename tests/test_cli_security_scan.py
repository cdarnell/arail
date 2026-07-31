"""Security static-scan tests — T30, T31, T32
(sprints/2026-07-29-elite-cli/ARCHITECTURE.md §16.2, the repo CLAUDE.md's
20% security allocation for this sprint).

REVIEW.md m5: these three gates were named in the sprint's own test
strategy but never built. The invariants they check were verified TRUE
by inspection at review time ("I verified all three invariants hold in
fact today") — this file turns that one-time verification into a
regression gate, so a future change that violates one of them fails CI
instead of needing a second manual audit.

Static source-text scans only (no process spawned, no portal needed) —
same style as tests/test_instance_isolation_audit.py's own "hardcoded
lab write path" scan.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
SERVICES_SH = REPO_ROOT / "scripts" / "lib" / "services.sh"
STATUS_SH = REPO_ROOT / "scripts" / "status.sh"
START_SH = REPO_ROOT / "scripts" / "start.sh"

_ROOT_PATH_MARKER = 'if [[ -n "$TARGET_SLUG" ]]; then'


def _non_comment_lines(path: Path):
    """Yield (1-based line number, line text) for every non-blank,
    non-comment line — a bare '#'-prefixed line (after stripping leading
    whitespace) is a comment; this does not attempt to strip trailing
    inline comments, matching test_instance_isolation_audit.py's own
    (deliberately simple, false-negative-tolerant) convention."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield i, line


def _start_sh_root_path_lines():
    """start.sh's root-lab section: everything from the instance/root
    branch point (the instance path always `exit 0`s before this) to
    EOF. Isolating it matters because the INSTANCE path has its own,
    separately-audited kill usage (_instance_cleanup_and_exit's
    ${_INST_PIDS[@]} loop, elsewhere in this same file) that T31 is not
    about."""
    lines = START_SH.read_text(encoding="utf-8").splitlines()
    start_idx = next(
        (i for i, line in enumerate(lines) if _ROOT_PATH_MARKER in line), None,
    )
    assert start_idx is not None, (
        "start.sh's instance/root branch point moved — update "
        "_start_sh_root_path_lines() to match its new shape"
    )
    return list(enumerate(lines[start_idx:], start=start_idx + 1))


# ---------------------------------------------------------------------------
# T30 — secrets.env is never read, copied, linked, or referenced by any of
# this sprint's new code paths (install.sh, services.sh, the status
# collector). Mirrors the existing per-instance secrets invariant
# (CLAUDE.md: "Per-instance secrets are never shared or auto-copied").
# ---------------------------------------------------------------------------

def test_t30_secrets_env_never_referenced_outside_a_comment():
    offenders = []
    for path in (INSTALL_SH, SERVICES_SH, STATUS_SH):
        for i, line in _non_comment_lines(path):
            if "secrets.env" in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "secrets.env referenced outside a comment in a new-this-sprint "
        "script (T30):\n" + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# T31 — no new code path signals a pid it did not spawn or verify (F1).
# services.sh contains no kill/pkill/pgrep at all EXCEPT `kill -0` (a
# liveness check, not a signal — the same idiom instances.sh:inst_alive
# already uses; BUILD_LOG's WP2 note on why a literal substring-grep needs
# this carve-out). start.sh's root path signals only ${PIDS[@]}.
# ---------------------------------------------------------------------------

def test_t31_services_sh_has_no_kill_pkill_pgrep_except_kill_dash_0():
    offenders = []
    for i, line in _non_comment_lines(SERVICES_SH):
        if re.search(r"\bpkill\b|\bpgrep\b", line):
            offenders.append(f"{i}: {line.strip()}")
            continue
        for m in re.finditer(r"\bkill\b", line):
            if re.match(r"\s*-0\b", line[m.end():]):
                continue  # kill -0: a liveness check, not a signal
            offenders.append(f"{i}: {line.strip()}")
    assert not offenders, (
        "services.sh signals a process or searches the process table — "
        "it may only ever probe loopback HTTP/TCP state, plus the one "
        "`kill -0` liveness-check carve-out (T31):\n" + "\n".join(offenders)
    )


def test_t31_start_sh_root_path_kill_targets_pids_array_only():
    offenders = []
    saw_the_pids_kill = False
    for i, line in _start_sh_root_path_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(r"\bpkill\b|\bpgrep\b", line):
            offenders.append(f"{i}: {stripped}")
            continue
        for m in re.finditer(r"\bkill\b", line):
            if re.match(r"\s*-0\b", line[m.end():]):
                continue  # kill -0: a liveness check (F31's identity gate)
            if "PIDS[@]" in line:
                saw_the_pids_kill = True
                continue
            offenders.append(f"{i}: {stripped}")
    assert not offenders, (
        "start.sh's root path signals a pid outside ${PIDS[@]} — F1 "
        "requires the kill list to be exactly (and only) what this "
        "shell spawned (T31):\n" + "\n".join(offenders)
    )
    assert saw_the_pids_kill, (
        "expected to find the root path's own cleanup() kill over "
        '${PIDS[@]} — did the cleanup mechanism move or get renamed? '
        "(a false pass here would mean this test stopped exercising "
        "anything)"
    )


# ---------------------------------------------------------------------------
# T32 — Ollama untouched unless we started it. install, status, and the
# root readiness gate never kill/pkill/`brew services stop`/`systemctl
# stop`/`launchctl unload` an ollama process; the pidfile rule
# (scripts/start.sh's OLLAMA_PIDFILE, reset.sh's
# _ollama_pid_if_we_started_it) is unchanged and out of this file's scope.
# ---------------------------------------------------------------------------

_OLLAMA_STOP_PATTERNS = (
    r"\bpkill\b",
    r"brew\s+services\s+stop",
    r"systemctl\s+stop",
    r"launchctl\s+(unload|stop)",
)


def test_t32_install_and_status_never_stop_ollama():
    offenders = []
    for path in (INSTALL_SH, STATUS_SH):
        for i, line in _non_comment_lines(path):
            if "ollama" not in line.lower():
                continue
            for pat in _OLLAMA_STOP_PATTERNS:
                if re.search(pat, line, re.IGNORECASE):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
            # A bare, non--0 `kill` naming ollama (as opposed to a `kill`
            # whose target is some unrelated $pid on the same line) would
            # also be a T32 violation — neither file has a legitimate
            # reason to kill anything at all (install.sh only ever runs
            # `ollama list`/`pull`/`create`; status.sh only reads the
            # pidfile).
            if re.search(r"\bkill\b(?!\s*-0)", line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "install.sh/status.sh appear to stop/kill ollama — only "
        "`ollama list`/`pull`/`create` (install.sh) and a pidfile read "
        "(status.sh) are allowed (T32):\n" + "\n".join(offenders)
    )


def test_t32_start_sh_root_readiness_gate_never_force_stops_ollama():
    offenders = []
    for i, line in _start_sh_root_path_lines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "ollama" not in line.lower():
            continue
        for pat in _OLLAMA_STOP_PATTERNS:
            if re.search(pat, line, re.IGNORECASE):
                offenders.append(f"{i}: {stripped}")
    assert not offenders, (
        "start.sh's root readiness gate appears to force-stop ollama "
        "outside the pidfile-gated PIDS[@] cleanup path (T32):\n"
        + "\n".join(offenders)
    )
    # And the positive half: the root path's own ollama pid, when it
    # started one, is added to ${PIDS[@]} — the SAME array T31 pins as
    # the only thing cleanup() ever signals. No separate kill/pattern
    # match for ollama exists anywhere in the root path.
    root_src = "\n".join(line for _, line in _start_sh_root_path_lines())
    assert 'PIDS+=("$OLLAMA_PID")' in root_src, (
        "expected the root path's OLLAMA_PID to be folded into "
        "${PIDS[@]} (the single kill-list this scan pins) — did ollama "
        "cleanup move to a separate mechanism?"
    )
