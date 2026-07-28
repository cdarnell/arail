"""Regressions found while re-verifying the QA-fix pass.

Sprint: sprints/2026-07-28-concurrent-worlds/ (QA re-test, post-fix).

Both findings here were *created or newly exposed* by the QA-fix pass itself:

- **QA-15** — QA-B1's fix made instance onboarding reachable for the first
  time; QA-B2's fix then redirected the *pack* write to a per-instance 0600
  store but left the **same request handler's** `lab.conf` write pointed at the
  shared repo-root file. Neither could be observed before, because a first boot
  could never complete.
- **QA-17** — QA-11's fix depends on an argv marker (`--app-dir <REPO_ROOT>`)
  that a process started by the *previous* `start.sh` does not carry, so
  `./arailctl stop` cannot see an already-running lab across the upgrade.

Both are pinned with strict xfail: green while open, red the moment they are
fixed without the marker being retired.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PY = REPO_ROOT / "src" / "arail" / "portal" / "app.py"
RESET_SH = REPO_ROOT / "scripts" / "reset.sh"
START_SH = REPO_ROOT / "scripts" / "start.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


_STOP_DRIVER = r"""
set -euo pipefail
info() { :; }
LAB_NAME=test
REPO_ROOT=/repo
PROCS="$PROCS_FILE"
pgrep() {
    local pattern="${2:-$1}"
    awk -F'\t' -v pat="$pattern" '$2 ~ pat {print $1}' "$PROCS"
}
KILLED="$KILLED_FILE"
kill() {
    if [[ "${1:-}" == "-0" ]]; then return 1; fi
    if [[ "${1:-}" == "-9" ]]; then shift; fi
    for pid in "$@"; do echo "$pid" >> "$KILLED"; done
}
launchctl() { return 1; }
sleep() { :; }
uname() { echo Darwin; }
eval "$(awk '/^stop_services\(\)/,/^}/' "$RESET_SH")"
stop_services
"""


def _run_stop_services(procs, tmp_path: Path | None = None) -> set[str]:
    """Drive the REAL ``stop_services`` against a stubbed process table."""
    import tempfile  # noqa: PLC0415

    d = Path(tempfile.mkdtemp())
    procs_file = d / "procs.tsv"
    procs_file.write_text("".join(f"{pid}\t{cmd}\n" for pid, cmd in procs))
    killed_file = d / "killed.txt"
    killed_file.write_text("")
    driver = d / "driver.sh"
    driver.write_text(_STOP_DRIVER)
    r = subprocess.run(
        [_BASH, str(driver)], capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin",
             "PROCS_FILE": str(procs_file),
             "KILLED_FILE": str(killed_file),
             "RESET_SH": str(RESET_SH)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return set(killed_file.read_text().split())


def _fn_source(name: str) -> str:
    text = APP_PY.read_text(encoding="utf-8")
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    raise AssertionError(f"{name} not found in app.py")


# ---------------------------------------------------------------------------
# QA-15 — onboarding still writes a credential OUTSIDE the instance root
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="QA-15 (OPEN): _patch_lab_conf_password writes IDE_PASSWORD=<the "
           "operator's passphrase> into the CWD-relative, checkout-SHARED "
           "lab.conf from inside an instance process. QA-B2's fix redirected "
           "the instance.env write but not this one. Reproduced live: alpha "
           "onboarded, then beta onboarded, and beta's passphrase overwrote "
           "alpha's in the one shared file. See TEST_REPORT.md.",
)
def test_the_onboarding_handler_writes_no_credential_outside_the_instance_root() -> None:
    """§7: "Isolation that has an exception is not isolation."

    ``POST /api/welcome/setup`` performs two credential writes. QA-B2 fixed the
    first (``_write_env_kv`` → ``_env_file_path`` → now the per-instance 0600
    ``secrets.env``). The second, ``_patch_lab_conf_password``, still targets a
    bare ``Path("lab.conf")`` — CWD-relative, and every instance shares one CWD
    (the checkout root), so:

      * instance A's passphrase leaves A's root entirely;
      * ``start.sh``/``reset.sh`` both ``set -a; source lab.conf``, so **A's
        process environment ends up carrying B's passphrase** as
        ``IDE_PASSWORD`` — the work-lab/personal-lab separation the BRIEF names
        as the audience expectation;
      * last writer wins, so A's IDE password silently stops being A's.

    Verified live 2026-07-28 in a two-instance sandbox: after alpha
    (``CANARY-alpha-pw-1``) then beta (``CANARY-beta-pw-2``), the shared
    ``lab.conf`` contained only ``IDE_PASSWORD=CANARY-beta-pw-2``, while each
    instance's own ``secrets.env`` correctly held its own value at 0600.

    Mitigating (why this is MEDIUM, not HIGH): ``lab.conf`` is chmod 0600, so
    no *other* OS user can read it, and ``IDE_PASSWORD`` governs code-server,
    which §3.6 says an instance never starts. The contract violation is real;
    the exploit surface is same-user only.
    """
    src = _fn_source("_patch_lab_conf_password")
    assert "ARAIL_INSTANCE" in src, (
        "_patch_lab_conf_password has no instance guard — an instance process "
        "writes the operator's passphrase into the checkout-shared lab.conf"
    )


def test_the_instance_onboarding_secret_sink_is_per_instance_and_0600() -> None:
    """The half QA-B2 *did* fix, pinned so it cannot silently revert.

    Confirmed live: ``<instance>/data/secrets.env`` was created 0600 with the
    instance's own passphrase, and ``instance.env`` was byte-unchanged.
    """
    src = _fn_source("_env_file_path")
    assert "ARAIL_INSTANCE" in src and "_secrets_path()" in src, (
        "_env_file_path no longer redirects an instance's onboarding write to "
        "the per-instance secrets store — QA-B2 has regressed"
    )
    kv = _fn_source("_write_env_kv")
    assert "_chmod_600" in kv, "the onboarding writer no longer chmods 0600"


def test_identity_keys_written_by_onboarding_are_inert_for_an_instance() -> None:
    """Side effect of QA-B2's redirect, documented rather than asserted-away.

    ``/api/welcome/setup`` also writes ``LAB_NAME``/``LAB_SHORT_NAME`` through
    ``_write_env_kv``. For an instance those now land in ``secrets.env``, which
    ``config.py`` never loads (it loads ``ARAIL_ENV_FILE`` — the pack). So the
    "name your lab" step of the welcome flow is a **dead write** for an
    instance: the pack's ``LAB_NAME`` (from the World's ``display_name``) wins.

    That is arguably correct — a World instance's identity should come from the
    World — but it is silent. Filed LOW (QA-16); pinned here so that if
    ``secrets.env`` ever *does* get loaded into the environment, the fact that
    it carries identity keys is not a surprise.
    """
    text = APP_PY.read_text(encoding="utf-8")
    assert '_write_env_kv("LAB_NAME"' in text
    cfg = (REPO_ROOT / "src" / "arail" / "config.py").read_text(encoding="utf-8")
    assert "secrets.env" not in cfg, (
        "config.py now loads secrets.env — the identity keys the welcome flow "
        "writes there would start overriding the instance pack's LAB_NAME"
    )


# ---------------------------------------------------------------------------
# QA-17 — QA-11's argv marker is invisible on an already-running lab
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="QA-17 (OPEN): QA-11's fix matches on `--app-dir <REPO_ROOT>`, an "
           "argv marker only processes started by the NEW start.sh carry. "
           "After upgrading, `./arailctl stop` cannot see a lab that is "
           "already running and prints 'No running services found.' — the "
           "exact silent-stop shape REVIEW.md B1 blocked on. See TEST_REPORT.md.",
)
def test_root_lab_stop_can_still_stop_a_lab_started_before_the_upgrade() -> None:
    """QA-11 traded one silent-stop failure for a narrower one.

    ``stop_services``' patterns now require ``--app-dir <REPO_ROOT>`` in the
    uvicorn argv. That marker is emitted by the *new* ``start.sh``. A lab that
    was already running when the operator pulled this change has the *old*
    argv, so no pattern matches it.

    Reproduced 2026-07-28 with a process whose argv is exactly the pre-upgrade
    invocation: the new pattern found nothing, the old (port-only) pattern
    found it, and ``reset.sh stop`` reported "No running services found."
    while the process kept running.

    Every existing user hits this once, on the first stop after upgrading.
    A checkout check that does not depend on the target's argv — e.g.
    verifying the matched PID's actual cwd — would cover both generations.

    This drives the REAL ``stop_services`` against a stubbed process table
    (same extraction harness as ``tests/test_reset_stop_scope.py``) rather
    than grepping its source, because the source contains the word "cwd" in a
    comment and a naive grep passes for the wrong reason.
    """
    killed = _run_stop_services(
        [
            # Started by the PREVIOUS start.sh — no --app-dir in argv.
            ("301", "python -m uvicorn arail.portal.app:app --port 8080"),
            ("302", "python -m uvicorn arail.memory_service:app --port 7414"),
            # Started by the NEW start.sh, same checkout — the control.
            ("303", "python -m uvicorn arail.portal.app:app --app-dir /repo --port 8080"),
        ]
    )
    assert "303" in killed, "harness broken — the new-style process must be killed"
    assert "301" in killed and "302" in killed, (
        "a root lab started before this upgrade is invisible to `./arailctl "
        "stop` — it prints 'No running services found.' and leaves the lab "
        "running (REVIEW.md B1's silent-stop shape, re-created)"
    )


def test_the_app_dir_marker_is_actually_emitted_by_start_sh() -> None:
    """The premise QA-11's fix rests on. If start.sh stops emitting the marker,
    stop_services silently matches nothing at all — for every lab, not just
    pre-upgrade ones.
    """
    body = START_SH.read_text(encoding="utf-8")
    assert body.count('--app-dir "$REPO_ROOT"') >= 3, (
        "start.sh no longer passes --app-dir on all three root-lab uvicorn "
        "invocations that reset.sh's patterns require"
    )


# ---------------------------------------------------------------------------
# QA-18 — the accepted "${NAME}" residual is an env-var exfiltration primitive
# ---------------------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="QA-18 (OPEN, security): a World display_name of '${IDE_PASSWORD}' "
           "is written literally to the pack, read literally by bash, and "
           "EXPANDED TO THE REAL SECRET by python-dotenv — which then sets it "
           "as LAB_NAME, a value rendered in the UI. The QA-fix pass filed "
           "this shape as an accepted cosmetic residual; it is not cosmetic. "
           "See TEST_REPORT.md.",
)
def test_a_braces_reference_in_a_display_name_cannot_expand_to_an_env_secret(
    tmp_path: Path,
) -> None:
    """The QA-fix pass accepted the ``${NAME}`` divergence on the grounds that
    "World display_name and instance paths have no reason to contain literal
    ``${...}`` syntax." True of a *well-behaved* bundle — but the writer's job
    is to be safe against one that isn't, and World bundles are authored by
    fork users and shared between them.

    Demonstrated 2026-07-28 end-to-end through the real
    ``inst_write_env_pack`` → real ``_set_env_var``:

        pack line          LAB_NAME='${IDE_PASSWORD}'
        bash               ${IDE_PASSWORD}          (literal — safe)
        dotenv_values()    SUPERSECRET-ide-pw       (the real value)
        load_dotenv()      SUPERSECRET-ide-pw       (into os.environ)

    ``LAB_NAME`` is a displayed field (page title, nav, brand), so this turns a
    World bundle into a read primitive for any variable in the portal
    process's environment — which, because ``start.sh`` does
    ``set -a; source lab.conf``, includes ``IDE_PASSWORD``.

    Why it is MEDIUM and not HIGH: the production launch path exports LAB_NAME
    via ``set -a; source pack`` *before* uvicorn starts, and ``load_dotenv``
    defaults to ``override=False``, so the literal value wins there. The
    expansion lands on §6.1's *second*, explicitly-designed-for mechanism — a
    process started without the shell wrapper — and on any caller using
    ``dotenv_values()``.

    The fix belongs at the writer (reject or neutralise a literal ``${`` in a
    pack value — a display name has no legitimate need for it), not at
    ``config.py``'s ``interpolate=False``, which would change how every
    ``.env`` in the app is read.
    """
    from dotenv import dotenv_values  # noqa: PLC0415

    instances_sh = REPO_ROOT / "scripts" / "lib" / "instances.sh"
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    shutil.copy(REPO_ROOT / "scripts" / "setup.sh", repo / "scripts" / "setup.sh")

    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{repo}"; source "{instances_sh}"; '
         'inst_write_env_pack qa LAB_ROOT /tmp/x PORTAL_PORT 8090 '
         'LAB_NAME "$1" LAB_SHORT_NAME qa',
         "bash", "${IDE_PASSWORD}"],
        capture_output=True, text=True, timeout=60,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(tmp_path)},
    )
    assert r.returncode == 0, r.stderr

    pack = repo / "lab" / "instances" / "qa" / "instance.env"
    import os as _os  # noqa: PLC0415

    prev = _os.environ.get("IDE_PASSWORD")
    _os.environ["IDE_PASSWORD"] = "SUPERSECRET-ide-pw"
    try:
        got = dotenv_values(str(pack)).get("LAB_NAME")
    finally:
        if prev is None:
            _os.environ.pop("IDE_PASSWORD", None)
        else:
            _os.environ["IDE_PASSWORD"] = prev

    assert got != "SUPERSECRET-ide-pw", (
        "a World display_name of '${IDE_PASSWORD}' expanded to the real "
        "secret when the pack was read via python-dotenv — LAB_NAME is a "
        "displayed field, so this exfiltrates an environment secret into the UI"
    )


def test_app_dir_marker_and_reset_pattern_agree_on_argument_order() -> None:
    """``pgrep -f`` matches the pattern against the whole command line in
    order, so ``--app-dir`` must precede ``--port`` in the emitted argv for
    ``uvicorn.*--app-dir X.*--port N`` to match. Pinned because reordering the
    flags in start.sh would silently break every root-lab stop.
    """
    body = START_SH.read_text(encoding="utf-8")
    for m in re.finditer(r"uvicorn arail\.[\w.]+:app(.{0,400}?)\n\n", body, re.S):
        block = m.group(1)
        if "--app-dir" not in block or "--port" not in block:
            continue
        assert block.index("--app-dir") < block.index("--port"), (
            "an invocation emits --port before --app-dir; reset.sh's "
            "'--app-dir .* --port' pattern cannot match it:\n" + block
        )
