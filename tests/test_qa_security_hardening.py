"""QA security pass for the 2026-07-29-elite-cli sprint — the gates
tests/test_cli_security_scan.py (T30-T32) leaves reachable.

Every test here PASSES against the shipped code: the invariants hold, the
GATES were narrower than the invariants. Three gaps this pass found by
trying to falsify T30-T32 rather than re-verifying them:

1. T32's stop-pattern set is ``pkill`` / ``brew services stop`` /
   ``systemctl stop`` / ``launchctl unload|stop`` plus a bare ``kill``.
   ``killall ollama`` matches NONE of them — ``\\bkill\\b`` does not match
   inside "killall" — and neither does ``ollama stop <model>``, which is a
   real Ollama subcommand that evicts a model another lab may be mid-
   inference on. A line reading ``killall ollama`` could be added to
   install.sh today and T32 would stay green (verified against T32's own
   pattern tuple).
2. T30/T32 scan install.sh, services.sh and status.sh only — but this
   sprint also rewrote reset.sh, start.sh, update.sh and arailctl, and
   start.sh is the script that composes per-instance env packs, i.e. the
   one place a cross-instance secrets copy would plausibly be written.
3. Neither gate constrains what a scanned script may PRINT: the
   per-instance token is a liveness nonce, but "never echoed back" is a
   standing repo rule (CLAUDE.md) with no test behind it.

Plus one behavioural (not static) gate the sprint's own B3 fix left open:
REVIEW.md B3 is pinned by an AST assertion on the exception handler and by
unit assertions on the module global. Nothing asserts the invariant where
it actually matters — in the HTTP response body of the anonymous,
pre-onboarding ``GET /api/instance``, on BOTH the root and the World
branch, after a real induced warm-up failure.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every shell surface this sprint touched that can plausibly signal a
# process, read a secret, or print one.
SPRINT_SHELL_FILES = (
    REPO_ROOT / "arailctl",
    REPO_ROOT / "scripts" / "install.sh",
    REPO_ROOT / "scripts" / "status.sh",
    REPO_ROOT / "scripts" / "start.sh",
    REPO_ROOT / "scripts" / "reset.sh",
    REPO_ROOT / "scripts" / "update.sh",
    REPO_ROOT / "scripts" / "lib" / "services.sh",
)


def _code_lines(path: Path):
    """(lineno, text) for every non-blank, non-comment line. Same
    deliberately simple convention as tests/test_cli_security_scan.py —
    trailing inline comments are not stripped, which can only ever make
    this scan noisier, never quieter."""
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        yield i, line


# ---------------------------------------------------------------------------
# QA-S1 — "never touch an Ollama we didn't start" (CLAUDE.md), enforced
# across every sprint-touched script and against the two spellings T32's
# pattern set cannot see.
# ---------------------------------------------------------------------------

# A broad process-sweep is never acceptable in these files: the repo's
# ownership rule is pidfile-based (reset.sh's _ollama_pid_if_we_started_it,
# start.sh's OLLAMA_PIDFILE), and every one of these kills something the
# lab may not own.
_BROAD_SWEEP = (
    r"\bkillall\b",
    r"\bpkill\b",
)
# Ollama-specific eviction/stop verbs, whether or not a signal is involved.
_OLLAMA_EVICTION = (
    r"\bollama\s+stop\b",       # evicts a resident model — possibly a sibling's
    r"\bollama\s+rm\b",         # deletes weights from the shared model store
    r"brew\s+services\s+(stop|restart)\s+ollama",
    r"systemctl\s+(stop|restart)\s+ollama",
    r"launchctl\s+(unload|stop|kickstart)\s+.*ollama",
    r"\bkillall\b.*ollama",
)


def test_qa_s1_no_broad_process_sweep_in_any_sprint_touched_script():
    offenders = []
    for path in SPRINT_SHELL_FILES:
        for i, line in _code_lines(path):
            for pat in _BROAD_SWEEP:
                if re.search(pat, line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "a broad process sweep (killall/pkill) appeared in a lifecycle "
        "script — every stop in this repo must be pid-verified "
        "(instances.sh's registry records, start.sh's ${PIDS[@]}, or the "
        "ollama pidfile), never a pattern match over the whole process "
        "table:\n" + "\n".join(offenders)
    )


def test_qa_s1_no_script_evicts_or_deletes_a_shared_ollama_model():
    offenders = []
    for path in SPRINT_SHELL_FILES:
        for i, line in _code_lines(path):
            for pat in _OLLAMA_EVICTION:
                if re.search(pat, line, re.IGNORECASE):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "a script evicts a model from, or deletes a model out of, the "
        "MACHINE-SHARED ollama daemon. Only `ollama list`/`pull`/`create` "
        "are allowed (install.sh's models phase); a `stop`/`rm` reaches "
        "into every other lab on the box, including a sibling World "
        "instance mid-inference:\n" + "\n".join(offenders)
    )


def test_qa_s1_ollama_is_only_ever_killed_via_its_own_pidfile():
    """The positive half: every `kill` naming an ollama pid must take that
    pid from the pidfile helper, never from a pattern match. Guards the
    mechanism T32's static scan assumes but never checks in reset.sh."""
    reset_sh = REPO_ROOT / "scripts" / "reset.sh"
    src = reset_sh.read_text(encoding="utf-8")
    assert "_ollama_pid_if_we_started_it" in src, (
        "reset.sh no longer resolves the ollama pid through the "
        "started-by-arail pidfile — the ownership rule lost its mechanism"
    )
    for i, line in _code_lines(reset_sh):
        if re.search(r"\bkill\b(?!\s*-0)", line) and "ollama" in line.lower():
            assert "ollama_pid" in line, (
                f"reset.sh:{i} kills an ollama by something other than the "
                f"pidfile-derived $ollama_pid: {line.strip()}"
            )


# ---------------------------------------------------------------------------
# QA-S2 — per-instance secrets are never shared, copied, linked, or echoed
# (CLAUDE.md: "treat any code path that copies or links a secrets.env
# between instances (or from the root lab) as a bug, not a convenience").
# T30 checks three files for the literal string; this checks what is DONE
# with it, across every script the sprint touched.
# ---------------------------------------------------------------------------

# A mover verb in COMMAND position (start of line, or after a `;`/`|`/
# `&&`/`||`/`$(`/`(`), not merely somewhere in the text — otherwise the
# `.` of "secrets.env" itself reads as the POSIX `source` builtin and the
# one legitimate shape below false-positives.
_SECRET_MOVERS = re.compile(
    r"(?:^|[;&|(]|\$\()\s*(cp|ln|mv|scp|rsync|tar|cat|source|\.)\s")
# ...and any redirection whose operand is the secrets file.
_SECRET_REDIRECT = re.compile(r"[<>]\s*\"?[^\"\s]*secrets\.env")


def test_qa_s2_no_script_copies_links_or_reads_a_secrets_file():
    offenders = []
    for path in SPRINT_SHELL_FILES:
        for i, line in _code_lines(path):
            if "secrets.env" not in line:
                continue
            if _SECRET_MOVERS.search(line) or _SECRET_REDIRECT.search(line):
                # `[[ -f "$X/secrets.env" ]]` is a pure existence test and
                # is the ONLY legitimate shape (start.sh:768 uses it to
                # print "provider keys are per-instance"); it has no mover
                # verb in command position and no redirection.
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "a lifecycle script copies, links, redirects or sources a "
        "secrets.env. Each World instance's provider keys live in ITS OWN "
        "data/ dir at 0600; any sharing silently lets one lab read "
        "another's:\n" + "\n".join(offenders)
    )


def test_qa_s2_no_script_prints_a_secret_or_an_instance_token():
    """CLAUDE.md: tokens "never echoed back, never logged". The instance
    token is a liveness nonce rather than a credential, but the rule is
    absolute and had no gate; the passphrase absolutely is a credential."""
    offenders = []
    printers = re.compile(r"\b(echo|printf|say|info|warn|die)\b")
    secretish = re.compile(
        r"\$\{?(ARAIL_INSTANCE_TOKEN|instance_token|ARAIL_PASSWORD|"
        r"IDE_PASSWORD|OPEN_NOTEBOOK_ENCRYPTION_KEY|ANTHROPIC_API_KEY|"
        r"OPENAI_API_KEY|XAI_API_KEY)\b")
    for path in SPRINT_SHELL_FILES:
        for i, line in _code_lines(path):
            if printers.search(line) and secretish.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}: {line.strip()}")
    assert not offenders, (
        "a lifecycle script prints a token or a credential:\n"
        + "\n".join(offenders)
    )


# ---------------------------------------------------------------------------
# Positive controls. A static scan that finds nothing is indistinguishable
# from a static scan that CANNOT find anything — which is exactly how
# T32's pattern set came to miss `killall ollama`. Feed the detectors
# synthetic offenders and require them to fire.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("offending_line", [
    "    killall ollama",
    "    killall -9 ollama",
    "    pkill -f 'uvicorn arail.portal'",
    "    ollama stop ai-engineer",
    "    ollama rm llama-ai-eng",
    "    brew services stop ollama",
    "    systemctl stop ollama",
    "    launchctl unload ~/Library/LaunchAgents/com.ollama.plist",
])
def test_qa_s1_detectors_actually_fire(offending_line):
    hit = any(re.search(p, offending_line) for p in _BROAD_SWEEP) or \
        any(re.search(p, offending_line, re.IGNORECASE) for p in _OLLAMA_EVICTION)
    assert hit, (
        f"the QA-S1 scan would NOT flag {offending_line.strip()!r} — this "
        "gate can go vacuously green"
    )


@pytest.mark.parametrize("offending_line", [
    '    cp "$root/lab/data/secrets.env" "$inst/data/secrets.env"',
    '    ln -s "$root/secrets.env" "$inst/secrets.env"',
    '    source "$sibling/data/secrets.env"',
    '    . "$sibling/data/secrets.env"',
    '    keys="$(cat "$sibling/data/secrets.env")"',
    '    while IFS= read -r l; do :; done < "$sibling/data/secrets.env"',
    '    rsync -a "$a/secrets.env" "$b/secrets.env"',
])
def test_qa_s2_detectors_actually_fire(offending_line):
    assert _SECRET_MOVERS.search(offending_line) or _SECRET_REDIRECT.search(offending_line), (
        f"the QA-S2 scan would NOT flag {offending_line.strip()!r} — this "
        "gate can go vacuously green"
    )


def test_qa_s2_detector_does_not_flag_a_bare_existence_test():
    """The one shape that must stay allowed — start.sh:768's `[[ -f ... ]]`
    check, which reads nothing. If this starts flagging, the gate has
    become noise and will be disabled by the next person it annoys."""
    line = '        if [[ -f "$REPO_ROOT/lab/data/secrets.env" ]]; then'
    assert not _SECRET_MOVERS.search(line)
    assert not _SECRET_REDIRECT.search(line)


# ---------------------------------------------------------------------------
# QA-S3 — REVIEW.md B3, asserted where it matters: the anonymous,
# pre-onboarding HTTP response, after a REAL induced warm-up failure, on
# BOTH branches of GET /api/instance.
# ---------------------------------------------------------------------------

# Everything F16 bans, packed into one exception message: a credentialed
# provider URL, an absolute $HOME path (hence the OS username), a model id,
# and an API key.
_POISON = (
    "https://alice:sk-live-SECRET@provider.example.com/v1 refused while "
    "loading /Users/alice/lab/models/qwen2.5-7b-instruct/config.json "
    "(model qkz-project-aware-2b)"
)
_BANNED_SUBSTRINGS = (
    "sk-live-SECRET", "provider.example.com", "/Users/alice",
    "qwen2.5-7b-instruct", "qkz-project-aware-2b", "config.json",
    "ConnectionError", "alice",
)


@pytest.fixture()
def poisoned_warm(monkeypatch):
    """Drive the real _warm_primary_router() into its exception path with a
    message carrying every shape F16 forbids."""
    import arail.portal.app as app_mod

    class _Boom:
        backend_name = "openai_compat"

        def complete(self, *a, **k):
            raise ConnectionError(_POISON)

    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: _Boom())
    monkeypatch.setenv("ARAIL_TIER0_BOOT_WARM", "1")
    asyncio.run(app_mod._warm_primary_router())
    assert app_mod._MODEL_WARM_SKIP_REASON is not None, (
        "the induced failure did not reach the exception path — this "
        "fixture is no longer exercising anything"
    )
    return app_mod


@pytest.mark.parametrize("branch", ["root", "world"])
def test_qa_s3_api_instance_leaks_nothing_after_a_failed_warm(
        poisoned_warm, monkeypatch, branch):
    from fastapi.testclient import TestClient
    app_mod = poisoned_warm
    skip_reason = app_mod._MODEL_WARM_SKIP_REASON
    backend = app_mod._MODEL_WARM_BACKEND

    if branch == "root":
        monkeypatch.delenv("ARAIL_INSTANCE", raising=False)
    else:
        monkeypatch.setenv("ARAIL_INSTANCE", "finance")
        monkeypatch.setenv("ARAIL_INSTANCE_TOKEN", "nonce-123")

    with TestClient(app_mod.app) as client:
        # _startup() re-runs on __enter__ and would clobber the globals the
        # fixture just set — restore them once the app is up, exactly as
        # tests/test_warm_up.py documents for its own TestClient tests.
        monkeypatch.setattr(app_mod, "_MODEL_WARM_SKIP_REASON", skip_reason)
        monkeypatch.setattr(app_mod, "_MODEL_WARM_BACKEND", backend)
        r = client.get("/api/instance")

    assert r.status_code == 200, r.text
    body = r.json()
    haystack = " ".join(f"{k}={v}" for k, v in body.items())
    for needle in _BANNED_SUBSTRINGS:
        assert needle not in haystack, (
            f"GET /api/instance ({branch} branch) leaked {needle!r} after a "
            f"failed warm-up — this endpoint is reachable with NO passphrase "
            f"set (onboarding_gate's allow-list). Body: {body}"
        )
    # warm_skipped must be the fixed sentence, not merely "not the poison".
    assert body["warm_skipped"] == app_mod._MODEL_WARM_SKIP_REASON_ON_EXCEPTION, (
        body["warm_skipped"]
    )
    assert body["backend"] in (None, "aerollm", "claude", "ollama_native",
                               "openai_compat"), body["backend"]
    assert body["warm_ms"] is None or isinstance(body["warm_ms"], int)


def test_qa_s3_the_real_message_still_reaches_the_authenticated_log(poisoned_warm):
    """The other half of B3's fix: suppressing the detail anonymously is
    only correct if the operator can still find it. If this ever stops
    being true, the fix has turned into a silent swallow."""
    app_mod = poisoned_warm
    entries = app_mod.activity_log.recent(50)
    blob = " ".join(str(e) for e in entries)
    assert "provider.example.com" in blob, (
        "the real warm-up failure text no longer reaches activity_log — "
        "B3's fix moved the detail there deliberately; losing it makes the "
        "failure undiagnosable"
    )
