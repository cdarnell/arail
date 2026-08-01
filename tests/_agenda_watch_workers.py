"""Injectable stand-ins for ``agenda_watch._extract_candidates_worker``.

QA round 13. These live in an importable module (not inside the test file)
because ``_extract_candidates_bounded`` uses the ``spawn`` start method: the
worker callable is pickled *by reference* (module + qualname) and re-imported
in the fresh child interpreter, so a closure or a locally-defined function
cannot be used to inject a failure mode.
"""
import os
import time


def crash_after_ready(text, pattern_specs, conn):
    """Sends the startup sentinel, then dies hard without a result — the
    OOM-killer / segfault shape. The parent must notice via EOF, not hang."""
    conn.send(("ready", None))
    os._exit(9)


def hang_after_ready(text, pattern_specs, conn):
    """Sends the startup sentinel then never produces a result — the
    catastrophic-backtracking shape, without needing a real evil regex."""
    conn.send(("ready", None))
    time.sleep(600)


def slow_to_start(text, pattern_specs, conn):
    """Simulates a heavily-loaded spawn: the interpreter/import cost lands
    *before* the sentinel, exceeding the old single 2.0s budget, then the
    match itself is instant. This must succeed under the two-phase protocol."""
    time.sleep(3.0)
    conn.send(("ready", None))
    conn.send(("result", {"slow": ["ok"]}))


def huge_result(text, pattern_specs, conn):
    """A result far larger than a pipe buffer — the parent must drain it
    rather than time out or deadlock."""
    conn.send(("ready", None))
    conn.send(("result", {"big": ["x" * 500_000]}))


def never_ready(text, pattern_specs, conn):
    """Starts but never confirms readiness."""
    time.sleep(600)
