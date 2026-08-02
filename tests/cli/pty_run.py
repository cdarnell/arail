#!/usr/bin/env python3
"""tests/cli/pty_run.py — run a command with a REAL pty on stdin/stdout.

The World picker (scripts/start.sh) is gated on `[[ -t 0 ]]`: a pipe, a
heredoc, and `< /dev/null` all take the non-interactive branch by design
(VISION §3's "never guess" ruling). So a driver that wants to exercise the
picker *as an operator sees it* cannot feed it on stdin the usual way —
it needs an actual terminal, which is what this provides.

Usage:
    pty_run.py <keystrokes> <cmd> [args...]

<keystrokes> is written to the pty master immediately after fork (use
'\\n' for a bare Enter, '2\\n' to choose option 2). Everything the child
writes — stdout and stderr alike, since a pty merges them — is relayed to
this process's stdout. Exits with the child's own exit status, so a
driver can assert on rc exactly as it does for a non-pty run.

Deliberately no timeout of its own: every caller already wraps this in
tests/cli/lib.sh's `_timeout`, which kills the whole process group. A
second, inner timeout would only make which one fired ambiguous.
"""
from __future__ import annotations

import os
import pty
import select
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    keystrokes = sys.argv[1].encode()
    cmd = sys.argv[2:]

    pid, fd = pty.fork()
    if pid == 0:
        # Child: becomes the command, with the pty slave as its ctty.
        try:
            os.execvp(cmd[0], cmd)
        except Exception as exc:  # pragma: no cover — exec failure path
            print(f"pty_run: cannot exec {cmd[0]}: {exc}", file=sys.stderr)
            os._exit(127)

    os.write(fd, keystrokes)

    # Relay STREAMING, never buffered-until-exit. The callers wrap this in
    # lib.sh's `_timeout`, which SIGKILLs the whole process group — a
    # version that accumulated into a bytearray and wrote once at the end
    # produced ZERO output for every scenario that legitimately runs to the
    # timeout (a lab that comes up blocks in `wait` and never exits), which
    # reads exactly like "the picker never rendered".
    sink = sys.stdout.buffer
    while True:
        try:
            ready, _, _ = select.select([fd], [], [], 60)
        except (OSError, ValueError):
            break
        if not ready:
            break
        try:
            chunk = os.read(fd, 65536)
        except OSError:
            # EIO on the master is the normal end-of-session signal when
            # the last slave fd closes — not an error worth reporting.
            break
        if not chunk:
            break
        sink.write(chunk)
        sink.flush()

    try:
        _, status = os.waitpid(pid, 0)
    except ChildProcessError:  # pragma: no cover
        status = 0

    if os.WIFSIGNALED(status):
        return 128 + os.WTERMSIG(status)
    return os.WEXITSTATUS(status)


if __name__ == "__main__":
    sys.exit(main())
