"""QA edge-case sweep for the Concurrent-Worlds instance layer.

Sprint: sprints/2026-07-28-concurrent-worlds/ (QA pass, post-WEAK_PASS).

These are the cases the builder and the reviewer did not write: regex
boundaries, valid-JSON-wrong-type registry records, port boundary values,
hostile display names flowing into the env pack, and the bash/Python slug-jail
conformance the architecture asserts but nothing pinned.

Everything here drives the REAL ``scripts/lib/instances.sh`` (never a
reimplementation), matching the technique tests/test_instance_registry.py
already established.

Tests marked ``xfail(strict=True)`` document a live defect reported in
TEST_REPORT.md. When the builder fixes it the test XPASSes, which pytest
reports as a FAILURE under strict mode — so the fix cannot land without the
marker being removed. That is deliberate: a green suite must never hide an
open bug, and a fixed bug must never leave a stale xfail behind.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTANCES_SH = REPO_ROOT / "scripts" / "lib" / "instances.sh"
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"
START_SH = REPO_ROOT / "scripts" / "start.sh"
STATUS_SH = REPO_ROOT / "scripts" / "status.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")

_MIN_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _run(repo_root: Path, script: str, *, errexit: bool = True, timeout: int = 30):
    """Source the real instances.sh with REPO_ROOT=<repo_root>, then run script.

    ``errexit`` mirrors the option set every real caller (start.sh, status.sh,
    reset.sh) uses: ``set -euo pipefail``. Several defects below are only
    observable under ``-e``, so the default must be the production setting —
    a harness that quietly drops ``-e`` cannot see them (that is precisely how
    REVIEW.md's n2 escaped the builder's own probe tests).
    """
    opts = "set -euo pipefail" if errexit else "set -uo pipefail"
    full = textwrap.dedent(
        f"""
        {opts}
        REPO_ROOT="{repo_root}"
        # shellcheck disable=SC1091
        source "{INSTANCES_SH}"
        {script}
        """
    )
    return subprocess.run(
        [_BASH, "-c", full],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={"PATH": _MIN_PATH, "HOME": str(repo_root / "_home")},
    )


@pytest.fixture()
def fake_repo(tmp_path: Path) -> Path:
    """A minimal checkout: real scripts/, empty lab/, isolated HOME."""
    repo = tmp_path / "repo"
    (repo / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(INSTANCES_SH, repo / "scripts" / "lib" / "instances.sh")
    shutil.copy(SETUP_SH, repo / "scripts" / "setup.sh")
    (repo / "lab" / "instances" / "registry.d").mkdir(parents=True)
    (repo / "lab" / "worlds").mkdir(parents=True)
    (repo / "_home").mkdir()
    return repo


def _write_record(repo: Path, slug: str, **overrides) -> Path:
    rec = {
        "schema": "arail.instance-registry/v1",
        "slug": slug,
        "display_name": slug.title(),
        "checkout": str(repo),
        "instance_root": str(repo / "lab" / "instances" / slug),
        "data_dir": str(repo / "lab" / "instances" / slug / "data"),
        "pkb_root": str(repo / "lab" / "instances" / slug / "pkb"),
        "bind": "127.0.0.1",
        "portal_port": 8090,
        "lance_port": 8094,
        "launcher_pid": 999999,
        "portal_pid": 999999,
        "memory_pid": 999999,
        "token": "tok-" + slug,
        "started_at": "2026-07-28T00:00:00Z",
        "arailctl_version": "qa",
    }
    rec.update(overrides)
    f = repo / "lab" / "instances" / "registry.d" / f"{slug}.json"
    f.write_text(json.dumps(rec), encoding="utf-8")
    return f


# ---------------------------------------------------------------------------
# 1. Slug jail — regex boundaries, and bash/Python conformance
# ---------------------------------------------------------------------------

# ARCHITECTURE.md §1.2 states the bash jail "MUST match
# src/arail/world_mount.py:141 (_SLUG_RE)". Nothing pinned that claim.
_SLUG_CASES_ACCEPT = ["a", "0", "ai", "video-games", "a-b-c", "9-lives", "x" * 200]
_SLUG_CASES_REJECT = [
    "",            # empty
    "-ai",         # leading hyphen
    "Ai",          # uppercase
    "a_b",         # underscore
    "a.b",         # dot — the traversal alphabet
    "..",
    "../etc",
    "/abs",
    "a b",         # space
    "a/b",
    "ai\\",
    "ai;rm -rf /",
    "$(id)",
    "`id`",
    "ai$IFS",
    "école",  # non-ASCII
    "аi",     # Cyrillic 'а' homoglyph of 'a' — confusable slug
]


@pytest.mark.parametrize("slug", _SLUG_CASES_ACCEPT)
def test_slug_jail_accepts_well_formed_slugs(fake_repo: Path, slug: str) -> None:
    # Slugs travel through argv, never interpolated into the script text.
    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; '
         'if inst_valid_slug "$1"; then echo ACCEPT; else echo REJECT; fi',
         "bash", slug],
        capture_output=True, text=True, timeout=20,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )
    assert r.stdout.strip() == "ACCEPT", f"{slug!r} should be a legal slug: {r.stderr}"


@pytest.mark.parametrize("slug", _SLUG_CASES_REJECT)
def test_slug_jail_rejects_hostile_and_malformed_slugs(fake_repo: Path, slug: str) -> None:
    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; '
         'if inst_valid_slug "$1"; then echo ACCEPT; else echo REJECT; fi',
         "bash", slug],
        capture_output=True, text=True, timeout=20,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )
    assert r.stdout.strip() == "REJECT", f"{slug!r} must be rejected by the slug jail"
    # And nothing may have executed: a command-substitution slug must not run.
    assert "uid=" not in r.stdout


def test_a_nul_byte_cannot_reach_the_slug_jail_at_all() -> None:
    """An embedded NUL cannot cross an exec(2) argv boundary, so
    ``--world $'ai\\0b'`` is unreachable from a shell. Pinned so a future
    refactor that starts reading slugs from a FILE (where NULs are
    expressible) has to confront it deliberately.
    """
    with pytest.raises(ValueError):
        subprocess.run([_BASH, "-c", "true", "bash", "ai\x00b"],
                       capture_output=True, timeout=10)


def test_slug_jail_rejects_a_trailing_newline_that_python_slug_re_accepts() -> None:
    """The bash jail is STRICTER than the Python one, and that asymmetry is safe.

    Python's ``$`` matches before a trailing newline, so ``_SLUG_RE.match("ai\\n")``
    is truthy — a classic re gotcha. bash's ERE ``$`` anchors at true end-of-string
    and rejects it. ARCHITECTURE.md §1.2 claims the two jails match; they do not.

    This test pins the divergence AND pins its direction: the destructive path
    (``stop --world``, which deletes a registry file) is the bash one, so the
    stricter side guards the dangerous surface. If a future change ever makes
    bash the LOOSER of the two, this test fails and the traversal analysis in
    REVIEW.md M5 must be redone.
    """
    from arail.world_mount import _SLUG_RE  # noqa: PLC0415

    assert _SLUG_RE.match("ai\n") is not None, "Python _SLUG_RE behaviour changed"

    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT=/tmp; source "{INSTANCES_SH}"; '
         'if inst_valid_slug "$1"; then echo ACCEPT; else echo REJECT; fi',
         "bash", "ai\n"],
        capture_output=True, text=True, timeout=20,
        env={"PATH": _MIN_PATH, "HOME": "/tmp"},
    )
    assert r.stdout.strip() == "REJECT"


# ---------------------------------------------------------------------------
# 2. Registry records that are VALID JSON but not an object (F16 gap)
# ---------------------------------------------------------------------------

_NON_OBJECT_BODIES = ["[1,2,3]", '"hello"', "42", "null", "true"]


@pytest.mark.parametrize("body", _NON_OBJECT_BODIES)
def test_inst_record_field_survives_a_non_object_record(fake_repo: Path, body: str) -> None:
    """QA-6 (FIXED): ``inst_record_field`` tracebacks on valid-JSON-wrong-type input.

    ``inst_read_record``'s try/except covers ``json.load`` only, so a registry
    file holding an array/scalar parses fine (no quarantine, F16's ``.bad`` file
    never appears) and is handed to ``inst_record_field``, whose own try/except
    likewise wraps only ``json.loads`` — ``data.get(...)`` then raises
    AttributeError/TypeError. Under the production ``set -euo pipefail`` this is
    a raw Python traceback on the operator's terminal.

    F16 is explicit: a bad record renders ``✗ unreadable`` and is quarantined;
    it "never crashes ``status``, never blocks ``start``."
    """
    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; '
         'inst_record_field "$1" slug',
         "bash", body],
        capture_output=True, text=True, timeout=20,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )
    assert "Traceback" not in r.stderr, (
        "inst_record_field leaked a Python traceback for a non-object record "
        f"({body}): {r.stderr}"
    )
    assert r.returncode == 0


def test_status_reports_a_non_object_registry_record_instead_of_deleting_it(
    fake_repo: Path,
) -> None:
    """QA-6 (FIXED, operator-visible half): ``status`` must never silently drop a record.

    Observed today: six Python tracebacks on stderr, no ``✗ unreadable`` row,
    no ``<slug>.json.bad`` quarantine — and ``inst_prune_all`` then classifies
    the record as stale and ``rm``s it. The corrupt file is gone and the
    operator was never told which instance it described.
    """
    reg = fake_repo / "lab" / "instances" / "registry.d"
    (reg / "weird.json").write_text("[1,2,3]", encoding="utf-8")
    shutil.copy(STATUS_SH, fake_repo / "scripts" / "status.sh")

    r = subprocess.run(
        [_BASH, str(fake_repo / "scripts" / "status.sh")],
        cwd=str(fake_repo), capture_output=True, text=True, timeout=60,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )
    combined = r.stdout + r.stderr
    assert "Traceback" not in r.stderr, (
        "status leaked Python tracebacks for a non-object registry record:\n" + r.stderr
    )
    assert "unreadable" in combined, "F16 requires an ✗ unreadable row"
    assert (reg / "weird.json.bad").exists() or (reg / "weird.json").exists(), (
        "the corrupt record was silently deleted — F16 requires quarantine, "
        "and §2.5 forbids status destroying what it did not report"
    )


def test_inst_alive_rejects_every_malformed_portal_pid(fake_repo: Path) -> None:
    """Boundary values in the liveness predicate's PID field.

    0 (== "signal the whole process group" for kill(2)), -1 (== "every process
    the caller may signal"), a float, a string, null, and an absurdly large PID
    must all read as NOT alive. A `kill -0 0` that succeeded would make every
    record with a zeroed PID look live, and `stop` would then signal the group.
    """
    cases = ["0", "-1", "-999", '"eighty"', "null", "3.5", "99999999", '""']
    for pidval in cases:
        rec = fake_repo / "lab" / "instances" / "registry.d" / "t.json"
        rec.write_text(
            '{"slug":"t","portal_pid":%s,"portal_port":8090,"bind":"127.0.0.1",'
            '"token":"x","checkout":"/x"}' % pidval,
            encoding="utf-8",
        )
        r = _run(fake_repo, 'if inst_alive t; then echo ALIVE; else echo dead; fi',
                 errexit=False)
        assert r.stdout.strip() == "dead", f"portal_pid={pidval} was treated as live"


def test_inst_read_record_never_follows_a_symlink_out_of_the_registry(
    fake_repo: Path, tmp_path: Path
) -> None:
    """A registry entry that is a symlink to a file outside lab/ must not be
    quarantined by MOVING the target (mv -f follows the link's *name*, so the
    link is renamed, not the target) — pin that the victim file survives.
    """
    victim = tmp_path / "victim.json"
    victim.write_text("{not json", encoding="utf-8")
    link = fake_repo / "lab" / "instances" / "registry.d" / "evil.json"
    link.symlink_to(victim)

    r = _run(fake_repo, 'inst_read_record evil || echo "rc=$?"', errexit=False)
    assert victim.exists(), "quarantine moved a file outside the registry directory"
    assert victim.read_text(encoding="utf-8") == "{not json"
    assert "rc=2" in r.stdout


# ---------------------------------------------------------------------------
# 3. Port allocation boundaries
# ---------------------------------------------------------------------------

def test_allocation_survives_a_registry_record_with_a_non_numeric_port(
    fake_repo: Path,
) -> None:
    _write_record(fake_repo, "bad", portal_port="eighty", lance_port=None)
    r = _run(fake_repo, 'inst_allocate_ports', errexit=False)
    assert r.returncode == 0, r.stderr
    assert "Traceback" not in r.stderr
    portal, lance = r.stdout.split()
    assert int(lance) == int(portal) + 4


def test_allocation_skips_a_block_whose_lance_port_alone_is_registered(
    fake_repo: Path,
) -> None:
    """Off-by-one guard: a record pinning ONLY 8094 must invalidate the whole
    8090 block, not just the lance half — otherwise two instances share 8094.
    """
    _write_record(fake_repo, "half", portal_port=None, lance_port=8094)
    r = _run(fake_repo, 'inst_allocate_ports', errexit=False)
    assert r.returncode == 0, r.stderr
    portal, lance = (int(x) for x in r.stdout.split())
    assert portal != 8090 and lance != 8094


def test_allocation_never_returns_a_port_on_the_exclusion_list(fake_repo: Path) -> None:
    """Pre-register every block up to the ceiling except the ones straddling a
    reserved port, and assert allocation refuses rather than handing one out.
    """
    excluded = {8443, 8888, 7681, 7414, 11434, 11435}
    for k in range(0, 101):
        base = 8090 + 10 * k
        if base >= 9100:
            break
        _write_record(fake_repo, f"b{k}", portal_port=base, lance_port=base + 4)
    r = _run(fake_repo, 'inst_allocate_ports', errexit=False)
    assert r.returncode != 0, "allocation must hard-stop below 9100"
    assert "9100" in r.stderr
    for line in r.stdout.split():
        assert int(line) not in excluded


# ---------------------------------------------------------------------------
# 4. Env pack — hostile / unicode / whitespace display names
# ---------------------------------------------------------------------------

_HOSTILE_NAMES = [
    'World "quoted"',
    "World $(touch /tmp/arail-qa-pwned)",
    "World `touch /tmp/arail-qa-pwned2`",
    "World ${HOME}",
    "World\\backslash",
    "  leading and trailing  ",
    "Ünïcödé Wörld \U0001f30d",
    "مرحبا ​ World",   # RTL + zero-width space
    "World\twith\ttabs",
    "World\nPORTAL_PORT=31337",                       # newline injection attempt
    "World\nARAIL_DATA_DIR=/tmp/pwned",
    "'; rm -rf /tmp/nope; echo '",
]


def _write_pack_with_name(fake_repo: Path, name: str):
    script = (
        'inst_write_env_pack qa '
        'LAB_ROOT "$2" '
        'ARAIL_DATA_DIR "$2/data" '
        'PORTAL_PORT 8090 '
        'LANCE_PORT 8094 '
        'LAB_NAME "$1" '
        'LAB_SHORT_NAME qa\n'
        'pack="$(inst_env_file qa)"\n'
        '( set -a; source "$pack"; set +a; '
        '  printf "NAME<%s>\\nPORT<%s>\\nLANCE<%s>\\nROOT<%s>\\n" '
        '    "$LAB_NAME" "$PORTAL_PORT" "$LANCE_PORT" "$LAB_ROOT" )\n'
    )
    return subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; ' + script,
         "bash", name, str(fake_repo / "lab" / "instances" / "qa")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )


@pytest.mark.parametrize("name", _HOSTILE_NAMES)
def test_env_pack_round_trips_a_hostile_display_name_through_bash(
    fake_repo: Path, name: str
) -> None:
    """LAB_NAME comes from a World bundle's manifest ``display_name``. Fork
    users author their own bundles, so this is operator-supplied text on a path
    that both ``bash source`` and ``python-dotenv`` parse.

    Three properties, all required:
      1. no command substitution executes when the pack is sourced;
      2. bash's value equals the original byte-for-byte;
      3. nothing after LAB_NAME in the pack is displaced (a newline-injected
         ``KEY=value`` line must stay INSIDE the quoted value).

    Property 3 currently holds only because ``inst_write_env_pack``'s callers
    happen to emit PORTAL_PORT/LAB_ROOT *before* LAB_NAME and the readers use
    ``head -n1``. Reordering the key list in start.sh would break it — which is
    exactly why it is pinned here rather than left to inspection.
    """
    marker_a = Path("/tmp/arail-qa-pwned")
    marker_b = Path("/tmp/arail-qa-pwned2")
    for m in (marker_a, marker_b):
        if m.exists():
            m.unlink()

    r = _write_pack_with_name(fake_repo, name)
    assert r.returncode == 0, r.stderr
    assert not marker_a.exists() and not marker_b.exists(), (
        "command substitution executed while sourcing the env pack"
    )
    out = r.stdout
    assert f"NAME<{name}>" in out, f"LAB_NAME did not round-trip: {out!r}"
    assert "PORT<8090>" in out, "a hostile LAB_NAME displaced PORTAL_PORT"
    assert "LANCE<8094>" in out
    assert "ROOT<" + str(fake_repo / "lab" / "instances" / "qa") + ">" in out


@pytest.mark.parametrize("name", ["World $(id)", "World `id`"])
def test_bash_and_python_dotenv_agree_on_the_env_pack(fake_repo: Path, name: str) -> None:
    """QA-9 (FIXED for $/backtick/backslash): "python-dotenv and bash source
    agree on the env pack" — A32.5.

    ARCHITECTURE §6.1 leans on this: mechanism (1) is ``set -a; source`` in
    start.sh, mechanism (2) is ``ARAIL_ENV_FILE`` → ``load_dotenv`` in
    config.py. They used to disagree for any value containing ``$`` or a
    backtick: ``_set_env_var`` escaped them for bash's double-quote rules,
    and python-dotenv does not recognise ``\\$``/`` \\` `` as escapes at all
    (its double-quote decode table is ``\\\\ \\' \\" \\a \\b \\f \\n \\r \\t
    \\v`` only), so it kept reading the literal backslash.

    Fix: prefer single-quoting whenever the value contains no literal single
    quote (``scripts/setup.sh``'s ``shell_safe``) — single quotes are fully
    literal for ``$`` and backtick in BOTH readers, so the two mechanisms
    agree with zero escaping instead of a bash-specific one.

    Reachable two ways: a World's ``display_name`` (cosmetic — LAB_NAME used
    to render with stray backslashes for a process launched WITHOUT the shell
    wrapper), and — the one that matters — a **checkout path containing
    ``$``**, which is legal on macOS and Linux (see the companion test below).
    """
    from dotenv import dotenv_values  # noqa: PLC0415

    r = _write_pack_with_name(fake_repo, name)
    assert r.returncode == 0, r.stderr
    bash_value = r.stdout.split("NAME<", 1)[1].split(">\n", 1)[0]
    vals = dotenv_values(str(fake_repo / "lab" / "instances" / "qa" / "instance.env"))
    assert vals.get("PORTAL_PORT") == "8090"
    assert vals.get("LAB_NAME") == bash_value, (
        f"python-dotenv read {vals.get('LAB_NAME')!r}; bash read {bash_value!r}"
    )


@pytest.mark.xfail(
    strict=True,
    reason="QA-9 residual, ACCEPTED (not the reachable case QA-9 reported): "
           "python-dotenv unconditionally interpolates a literal ${NAME} "
           "substring on read, regardless of quote style or escaping — there "
           "is no escape hatch for it in this library version (verified "
           "against dotenv/variables.py: the interpolation regex runs on the "
           "already-decoded value with no awareness of what quoted/escaped "
           "it). Bash reads 'World ${HOME}' literally; dotenv_values() "
           "expands it to the real $HOME. Not reachable via this writer's "
           "callers today: World display_name and instance paths have no "
           "reason to contain literal ${...} syntax. See "
           "sprints/2026-07-28-concurrent-worlds/BUILD_LOG.md 'QA-fix pass'.",
)
def test_bash_and_python_dotenv_agree_on_a_braces_style_reference() -> None:
    """The one QA-9 shape quoting alone cannot fix: ``${NAME}`` braces syntax.

    Split out from ``test_bash_and_python_dotenv_agree_on_the_env_pack``
    (whose other two parametrized values — ``$(id)``, `` `id` `` — are now
    fixed and asserted for real above) because this one genuinely can't be:
    python-dotenv's own interpolation pass has no escape mechanism, so no
    value written to the pack can make ``dotenv_values()`` read a literal
    ``${...}`` substring back unchanged.
    """
    from dotenv import dotenv_values  # noqa: PLC0415

    tmp = Path(tempfile.mkdtemp())
    p = tmp / "instance.env"
    p.write_text("LAB_NAME='World ${HOME}'\n", encoding="utf-8")
    r = subprocess.run(
        [_BASH, "-c", f'set -a; source "{p}"; set +a; printf "%s" "$LAB_NAME"'],
        capture_output=True, text=True, timeout=10,
    )
    bash_value = r.stdout
    vals = dotenv_values(str(p))
    assert vals.get("LAB_NAME") == bash_value, (
        f"python-dotenv read {vals.get('LAB_NAME')!r}; bash read {bash_value!r}"
    )


def test_a_checkout_path_containing_a_dollar_sign_no_longer_diverges(
    fake_repo: Path,
) -> None:
    """QA-9 (FIXED), the reachable-and-harmful half, stated as a path, not a
    name: a checkout path containing ``$`` (legal on macOS/Linux) used to
    make ``LAB_ROOT``/``ARAIL_DATA_DIR``/``LAB_PKB`` resolve to DIFFERENT
    directories depending on how the process was started, while still
    passing the §6.4 boot assertion (both variants were absolute) — an
    isolation-relevant divergence, not a cosmetic one.
    """
    from dotenv import dotenv_values  # noqa: PLC0415

    weird_root = "/tmp/arail$qa/lab/instances/qa"
    r = subprocess.run(
        [_BASH, "-c",
         f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; '
         'inst_write_env_pack qa LAB_ROOT "$1" PORTAL_PORT 8090\n'
         'pack="$(inst_env_file qa)"\n'
         '( set -a; source "$pack"; set +a; printf "ROOT<%s>\\n" "$LAB_ROOT" )\n',
         "bash", weird_root],
        capture_output=True, text=True, timeout=30,
        env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
    )
    assert r.returncode == 0, r.stderr
    assert f"ROOT<{weird_root}>" in r.stdout, "bash must read the literal path"

    vals = dotenv_values(str(fake_repo / "lab" / "instances" / "qa" / "instance.env"))
    assert vals.get("LAB_ROOT") == weird_root, (
        f"python-dotenv read {vals.get('LAB_ROOT')!r}; bash read {weird_root!r} — "
        "the two loaders disagree again"
    )


def test_env_pack_is_world_readable_and_carries_no_secret_key(fake_repo: Path) -> None:
    """§1.2 'Not in the pack': no LAB_MODE, no ARAIL_AUTOCHECKS, no token, no
    secret. The pack is 0644 precisely BECAUSE it must never hold a credential.
    """
    r = _run(
        fake_repo,
        'inst_write_env_pack qa LAB_ROOT /tmp/x PORTAL_PORT 8090 LAB_NAME Hi\n'
        'inst_env_file qa\n',
        errexit=False,
    )
    assert r.returncode == 0, r.stderr
    pack = Path(r.stdout.strip().splitlines()[-1])
    assert oct(pack.stat().st_mode)[-3:] == "644"
    text = pack.read_text(encoding="utf-8")
    for banned in ("ARAIL_INSTANCE_TOKEN", "LAB_MODE", "ARAIL_AUTOCHECKS",
                   "SECRET", "API_KEY", "PASSWORD", "IDE_PASSWORD"):
        assert banned not in text, f"{banned} must never be written to the env pack"


# ---------------------------------------------------------------------------
# 5. Concurrency — two DIFFERENT slugs racing for the same port block
# ---------------------------------------------------------------------------

def test_two_concurrent_allocations_for_different_slugs_can_pick_the_same_block(
    fake_repo: Path,
) -> None:
    """Documented, bounded TOCTOU.

    ``inst_allocate_ports`` reads the registry and bind-tests, but the record
    that claims the block is only written at the END of an 8-stage launch. Two
    ``start --world A`` / ``start --world B`` invocations that overlap therefore
    both see 8090 free and both pin it. The O_EXCL claim (F6) is PER SLUG, so it
    does not serialise different slugs.

    This is not a data-loss path — the loser fails the stage [5/8] bind check or
    the stage [6/8] token probe with a named error, and no registry record is
    written for it. But the loser's env pack is left permanently pinned to a
    port it can never have, so every subsequent boot of that World fails the
    same way until the pack is hand-edited or deleted.

    Pinned here so the behaviour is a decision, not an accident.
    """
    procs = []
    for _ in range(2):
        procs.append(subprocess.Popen(
            [_BASH, "-c",
             f'set -uo pipefail; REPO_ROOT="{fake_repo}"; source "{INSTANCES_SH}"; '
             'inst_allocate_ports'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={"PATH": _MIN_PATH, "HOME": str(fake_repo / "_home")},
        ))
    outs = [p.communicate(timeout=60)[0].strip() for p in procs]
    assert all(o for o in outs)
    assert outs[0] == outs[1] == "8090 8094", (
        "allocation is expected to be non-atomic across slugs; if this now "
        "differs, the race was closed and TEST_REPORT.md's QA-7 can be retired"
    )


def test_claim_is_per_slug_and_does_not_serialise_different_worlds(
    fake_repo: Path,
) -> None:
    """The O_EXCL claim guards one slug (F6). Confirm two different slugs both
    claim successfully — that is the design, and it is why the allocation race
    above exists.
    """
    r = _run(
        fake_repo,
        'a="$(inst_claim_file alpha)"; b="$(inst_claim_file beta)"\n'
        'mkdir -p "$(inst_registry_dir)"\n'
        'if ( set -o noclobber; echo $$ > "$a" ) 2>/dev/null; then echo A_OK; fi\n'
        'if ( set -o noclobber; echo $$ > "$b" ) 2>/dev/null; then echo B_OK; fi\n'
        'if ( set -o noclobber; echo $$ > "$a" ) 2>/dev/null; then echo A_TWICE; '
        'else echo A_REFUSED; fi\n',
        errexit=False,
    )
    assert "A_OK" in r.stdout and "B_OK" in r.stdout
    assert "A_REFUSED" in r.stdout and "A_TWICE" not in r.stdout


# ---------------------------------------------------------------------------
# 6. _json_field — REVIEW.md n2, still open
# ---------------------------------------------------------------------------

def test_json_field_does_not_abort_start_sh_on_a_non_json_probe_response() -> None:
    """QA-8 / REVIEW.md n2 (FIXED): ``_json_field`` used to have no try/except.

    The readiness probe at stage [6/8] feeds it whatever answered the port with
    HTTP 200. A code-server / jupyter / unrelated web app returns HTML, and
    ``json.loads`` raises: the command substitution fails, and under
    ``set -euo pipefail`` the assignment aborts the stage. The operator gets a
    raw JSONDecodeError instead of M1's named
    "port N was taken during startup … token/checkout mismatch" — the very
    message M1 exists to deliver, in its single most likely case.

    Note the extraction here uses the PRODUCTION option set. The builder's own
    tests/test_instance_readiness_probe.py harness runs without ``-e``, which is
    why it cannot observe this.
    """
    body = START_SH.read_text(encoding="utf-8")
    start = body.index("_json_field() {")
    end = body.index("\n}\n", start) + 3
    fn = body[start:end]

    r = subprocess.run(
        [_BASH, "-c",
         "set -euo pipefail\n" + fn +
         '\nprobe_token="$(_json_field "$1" token)"\n'
         'echo "REACHED token=[$probe_token]"\n',
         "bash", "<html><body>code-server</body></html>"],
        capture_output=True, text=True, timeout=20,
        env={"PATH": _MIN_PATH, "HOME": "/tmp"},
    )
    assert "Traceback" not in r.stderr, (
        "_json_field leaked a Python traceback for a non-JSON 200 body:\n" + r.stderr
    )
    assert "REACHED" in r.stdout, (
        "_json_field aborted the enclosing stage under `set -e` — M1's named "
        "error is unreachable for a foreign HTTP-200 responder"
    )


def test_json_field_handles_a_json_scalar_and_a_json_array_body() -> None:
    """QA-8 (FIXED), second shape: a valid-JSON non-object 200 body. Same
    defect class, other shapes: a 200 body of ``[]`` or ``"ok"`` is
    valid JSON but has no ``.get``.
    """
    body = START_SH.read_text(encoding="utf-8")
    start = body.index("_json_field() {")
    end = body.index("\n}\n", start) + 3
    fn = body[start:end]
    for payload in ("[]", '"ok"', "3"):
        r = subprocess.run(
            [_BASH, "-c",
             "set -euo pipefail\n" + fn +
             '\nv="$(_json_field "$1" token)"\necho "REACHED[$v]"\n',
             "bash", payload],
            capture_output=True, text=True, timeout=20,
            env={"PATH": _MIN_PATH, "HOME": "/tmp"},
        )
        assert "Traceback" not in r.stderr, f"payload {payload}: {r.stderr}"
        assert "REACHED" in r.stdout, f"payload {payload} aborted the stage"


# ---------------------------------------------------------------------------
# 7. Empty / missing collections
# ---------------------------------------------------------------------------

def test_every_registry_reader_is_a_no_op_on_a_missing_registry_directory(
    tmp_path: Path,
) -> None:
    """Fresh checkout, `lab/instances/` never created. Nothing may raise, and
    nothing may CREATE the directory as a side effect of reading (§WP1: this
    library has no side effects on source, and `--list`/`status` must stay
    side-effect-free).
    """
    repo = tmp_path / "bare"
    (repo / "scripts" / "lib").mkdir(parents=True)
    shutil.copy(INSTANCES_SH, repo / "scripts" / "lib" / "instances.sh")
    (repo / "_home").mkdir()

    r = _run(
        repo,
        'inst_list_slugs | wc -l\n'
        'inst_prune_all && echo PRUNE_OK\n'
        'inst_any_alive || echo NONE_ALIVE\n'
        'inst_ports_registered | wc -l\n',
        errexit=True,
    )
    assert r.returncode == 0, r.stderr
    assert "PRUNE_OK" in r.stdout and "NONE_ALIVE" in r.stdout
    assert not (repo / "lab").exists(), (
        "a read-only registry query created lab/instances/ as a side effect"
    )


def test_registry_containing_only_quarantine_and_tmp_files_lists_nothing(
    fake_repo: Path,
) -> None:
    """Off-by-one in the glob: ``*.json`` must not pick up ``x.json.bad`` or
    ``x.json.tmp`` (a crashed writer's leftovers), or `status` would render a
    phantom instance named ``x.json``.
    """
    reg = fake_repo / "lab" / "instances" / "registry.d"
    (reg / "x.json.bad").write_text("{oops", encoding="utf-8")
    (reg / "y.json.tmp").write_text("{}", encoding="utf-8")
    (reg / "notjson.txt").write_text("{}", encoding="utf-8")
    r = _run(fake_repo, 'inst_list_slugs', errexit=False)
    assert r.stdout.strip() == "", f"phantom slugs listed: {r.stdout!r}"


def test_write_record_leaves_no_tmp_file_behind_on_success(fake_repo: Path) -> None:
    r = _run(
        fake_repo,
        "inst_write_record fin '{\"slug\":\"fin\",\"portal_port\":8090}'\n"
        'ls "$(inst_registry_dir)"\n',
        errexit=True,
    )
    assert r.returncode == 0, r.stderr
    listing = r.stdout.split()
    assert "fin.json" in listing
    assert not any(n.endswith(".tmp") for n in listing), listing


def test_write_record_refuses_a_non_json_payload_without_clobbering_the_old_record(
    fake_repo: Path,
) -> None:
    """Atomicity: a failed write must leave the PREVIOUS record intact, since
    `status`/`stop` read it to find the live PIDs.
    """
    _write_record(fake_repo, "fin", portal_port=8090)
    before = (fake_repo / "lab" / "instances" / "registry.d" / "fin.json").read_text()
    r = _run(fake_repo, "inst_write_record fin 'not json at all' || echo WRITE_REFUSED",
             errexit=False)
    assert "WRITE_REFUSED" in r.stdout
    after = (fake_repo / "lab" / "instances" / "registry.d" / "fin.json").read_text()
    assert after == before, "a rejected write damaged the existing record"
