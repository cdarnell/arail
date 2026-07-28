"""Regression tests for the defects found by a REAL two-World launch.

Sprint: sprints/2026-07-28-concurrent-worlds/ (QA pass).

WP4 deferred "a real manual launch of two Worlds on 8090/8100" to review;
review deferred it to QA. Every test in this file exists because that launch
finally happened and found something no stubbed test could: the WP4 driver and
tests/test_instance_start.py both use a stub ``uvicorn`` that exits immediately
and never binds, so nothing in the suite had ever spoken HTTP to a real portal.

QA-fix pass (sprints/2026-07-28-concurrent-worlds/BUILD_LOG.md): findings are
fixed one at a time; each fixed finding's xfail marker is removed and its
assertions flipped to pin the CORRECT behaviour, in the same commit as the
fix. See BUILD_LOG.md's "QA-fix pass" section for the fix->commit mapping.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PY = REPO_ROOT / "src" / "arail" / "portal" / "app.py"
START_SH = REPO_ROOT / "scripts" / "start.sh"
RESET_SH = REPO_ROOT / "scripts" / "reset.sh"
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"


def _onboarding_gate_allowlist() -> list[str]:
    """The ``allowed_prefixes`` tuple inside ``onboarding_gate``."""
    text = APP_PY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) \
                and node.name == "onboarding_gate":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "allowed_prefixes"
                    for t in sub.targets
                ):
                    return [
                        e.value for e in sub.value.elts  # type: ignore[attr-defined]
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    ]
    raise AssertionError("onboarding_gate's allowed_prefixes not found")


# ---------------------------------------------------------------------------
# QA-B1 — the readiness probe's endpoint is blocked by the onboarding gate
# ---------------------------------------------------------------------------

def test_api_instance_is_reachable_before_the_lab_is_onboarded() -> None:
    """QA-B1 (FIXED): a brand-new instance root has never been onboarded — by
    construction.

    ``_lab_password_set()`` resolves ``ARAIL_PASSWORD`` from the env, else from
    ``ARAIL_ENV_FILE`` — which for an instance is its own ``instance.env``, a
    file ``inst_write_env_pack`` is forbidden from putting a secret into
    (ARCHITECTURE §1.2). So the gate is False for every first boot, and
    ``onboarding_gate`` answers ``/api/instance`` with 401 ``lab_not_onboarded``.

    ``start.sh``'s probe uses ``curl -sf``, which discards non-2xx, so the
    poll sees an empty body, never matches the token, and burns the full 60 s
    cap before killing the child and reporting "portal did not come up" —
    a message that names the wrong cause.

    Reproduced live on 2026-07-28: with ``ARAIL_PASSWORD`` exported, the exact
    same launch reached ``[6/8] Portal up… ✓`` and both Worlds came up on
    8090/8100 with matching tokens. Without it, both timed out.

    ``/api/instance`` is read-only, loopback-bound, and returns a documented
    non-credential nonce — it belongs on the allow-list beside
    ``/api/system/health``, which is there for exactly this reason.
    """
    allow = _onboarding_gate_allowlist()
    assert any("/api/instance" == p or "/api/instance".startswith(p) for p in allow), (
        "/api/instance is gated behind onboarding; the readiness probe that "
        f"stage [6/8] depends on can never succeed. allow-list={allow}"
    )


def test_the_readiness_probe_targets_api_instance() -> None:
    """Pins the coupling QA-B1 depends on, so the two cannot drift apart."""
    body = START_SH.read_text(encoding="utf-8")
    assert "/api/instance" in body
    assert re.search(r"curl -sf[^\n]*\$\{?BIND\}?:\$\{?portal_port\}?/api/instance",
                     body), "stage [6/8] no longer probes /api/instance"


def test_the_probe_now_distinguishes_an_http_error_from_no_answer() -> None:
    """QA-B1 (FIXED, mechanism half): ``curl -sf`` alone collapses "gated",
    "crashed", and "not listening" into one empty string. The fix rides
    ``-w '%{http_code}'`` alongside the pre-existing ``-sf`` (curl still
    writes the format string on a failed/refused request — ``-f`` only
    affects whether the body is kept), so a real HTTP error status is
    distinguishable from no answer at all, and a FUTURE gate regression
    would be named instead of reported as "portal did not come up".
    """
    body = START_SH.read_text(encoding="utf-8")
    probe = [ln for ln in body.splitlines()
             if "/api/instance" in ln and "curl" in ln]
    assert probe, "no curl probe against /api/instance found"
    assert all("-sf" in ln for ln in probe)
    assert any("http_code" in ln for ln in probe), (
        "the probe no longer captures a status code — QA-B1's future-"
        "regression diagnosis has regressed"
    )


# ---------------------------------------------------------------------------
# QA-B2 — onboarding writes a credential into the 0644 env pack
# ---------------------------------------------------------------------------

def test_the_onboarding_writer_never_targets_the_instance_env_pack() -> None:
    """QA-B2 (FIXED): ``_env_file_path()`` used to honour ``ARAIL_ENV_FILE``
    unconditionally. The env pack sets ``ARAIL_ENV_FILE=<instance>/instance.env``
    (§1.2 — it is "the load-bearing line"), so the onboarding flow's credential
    write used to land in the pack.

    Verified live on 2026-07-28: after ``POST /api/welcome/setup`` against a
    running instance, ``instance.env`` contained
    ``ARAIL_PASSWORD=<plaintext>`` and ``OPEN_NOTEBOOK_ENCRYPTION_KEY=<plaintext>``.

    Two consequences, both real:
      1. ``inst_write_env_pack`` truncates the pack (``: > "$env_file"``) and
         re-``chmod 0644``s it. That path fires whenever ``--port`` differs
         from the pinned value, so ``./arailctl start --world X --port N``
         SILENTLY DESTROYS the operator's passphrase and notebook encryption
         key and re-widens the file's mode.
      2. A secret in a file the sprint documents as 0644 and secret-free
         contradicts both §1.2 and the standing repo convention.

    (Mitigating, and observed: the onboarding writer itself chmods the file to
    0600, so the window is narrow — until the next pack rewrite.)
    """
    src = APP_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    env_file_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_env_file_path":
            env_file_fn = ast.get_source_segment(src, node) or ""
    assert env_file_fn is not None, "_env_file_path not found"
    assert "ARAIL_INSTANCE" in env_file_fn, (
        "_env_file_path does not special-case an instance process, so the "
        "onboarding credential write targets instance.env"
    )


def test_the_env_pack_writer_truncates_and_widens_the_file_it_rewrites() -> None:
    """The mechanism half of QA-B2, asserted on the shell so a fix to either
    side is visible.
    """
    lib = INSTANCES_SH.read_text(encoding="utf-8")
    assert ': > "$env_file"' in lib, "pack writer no longer truncates"
    assert 'chmod 0644 "$env_file"' in lib, "pack writer no longer chmods 0644"
    start = START_SH.read_text(encoding="utf-8")
    # ...and start.sh calls it on the --port-change branch of a RE-boot.
    assert start.count("inst_write_env_pack") >= 2, (
        "inst_write_env_pack is no longer called on both the first-boot and "
        "the --port-rewrite paths — re-check QA-B2's blast radius"
    )


# ---------------------------------------------------------------------------
# QA-4 — the memory readiness probe checks a route that does not exist
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="QA-4 (OPEN): stage [7/8] probes GET / on the memory service, which "
           "has no / route and returns 404. `curl -sf` treats 404 as failure, "
           "so EVERY instance launch reports a false 20 s degradation. "
           "See TEST_REPORT.md.",
)
def test_the_memory_readiness_probe_uses_a_route_the_service_serves() -> None:
    """Observed live: both instances printed
    "memory service did not answer within 20 s — chat works, memory features
    degrade" while ``GET :LANCE_PORT/health`` returned
    ``{"service":"arail-memory","status":"ok", ...}`` with a correctly
    instance-scoped ``workflow_file``.

    A launch that reports healthy infrastructure as degraded is worse than one
    that says nothing: it is a false negative on the one surface this sprint
    sells (a legible, staged, honest launch), and it costs 20 s every time.
    """
    body = START_SH.read_text(encoding="utf-8")
    probe = [ln for ln in body.splitlines()
             if "lance_port" in ln and "curl" in ln]
    assert probe, "stage [7/8]'s memory probe not found"
    assert all("/health" in ln for ln in probe), (
        "the memory readiness probe does not target /health: " + "; ".join(probe)
    )


def test_the_memory_service_serves_health_but_not_root() -> None:
    """The fact QA-4 rests on. If the service ever grows a ``/`` route this
    test fails and QA-4 can be closed as moot.
    """
    ms = (REPO_ROOT / "src" / "arail" / "memory_service.py").read_text(encoding="utf-8")
    assert '@app.get("/health")' in ms
    assert '@app.get("/")' not in ms, (
        "memory_service now serves / — QA-4 is moot, retire the xfail above"
    )


# ---------------------------------------------------------------------------
# QA-11 — root-lab stop is port-scoped but not checkout-scoped
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="QA-11 (OPEN): stop_services()'s pgrep patterns match on module + "
           "port but not on checkout, so `./arailctl stop` in checkout A kills "
           "checkout B's root-lab services (both default to 8080/7414). "
           "Reproduced accidentally during this QA pass. See TEST_REPORT.md.",
)
def test_root_lab_stop_patterns_are_scoped_to_this_checkout() -> None:
    """F15 scoped ``stop_services`` by PORT. Two checkouts of ARAIL on one
    machine both default to ``PORTAL_PORT=8080`` / ``LANCE_PORT=7414``, so the
    port adds no discrimination between them.

    This matters because a second checkout is not hypothetical here — it is
    the BRIEF's motivating incident verbatim ("the daemon ... was resolving
    ``arail`` to a *different checkout* via the venv's editable install"). The
    instance path is already immune: registry records carry ``checkout`` and
    ``stop_instance`` kills only verified recorded PIDs. Only the legacy
    root-lab path is exposed.

    Reproduced 2026-07-28: ``reset.sh stop --all`` inside a sandbox checkout
    killed a ``uvicorn arail.memory_service --port 7414`` process belonging to
    a different checkout on the same machine.
    """
    body = RESET_SH.read_text(encoding="utf-8")
    start = body.index("stop_services() {")
    end = body.index("\n}\n", start)
    fn = body[start:end]
    patterns = re.findall(r'"(uvicorn\.\*arail[^"]+)"', fn)
    assert patterns, "stop_services' uvicorn patterns not found"
    for p in patterns:
        assert "REPO_ROOT" in p or "checkout" in p, (
            f"pattern is not checkout-scoped: {p}"
        )


def test_instance_stop_is_checkout_scoped_via_the_registry() -> None:
    """The positive half: ``stop_instance`` never pattern-matches — it kills
    only PIDs recorded in THIS checkout's ``registry.d/`` that additionally
    verify on module + port. Confirmed live: ``stop --world alpha`` killed
    alpha's 3 processes, left beta and the shared Ollama untouched, and
    preserved alpha's staged tree.
    """
    body = RESET_SH.read_text(encoding="utf-8")
    start = body.index("stop_instance() {")
    end = body.index("\n}\n", start)
    fn = body[start:end]
    assert "pgrep" not in fn, "stop_instance must never pattern-match for PIDs"
    assert "inst_read_record" in fn
    assert "did not verify" in fn, "the skip-and-report path is gone"
