#!/usr/bin/env python3
"""tests/cli/stub_uvicorn_serving.py — a real-binding stub uvicorn.

The enabling capability named in ARCHITECTURE.md
(sprints/2026-07-29-elite-cli) §16.1: without something that ACTUALLY
BINDS a port and serves real HTTP responses, the root-lab readiness gate
(scripts/start.sh) and the daemon-mode readiness gate (arailctl) are
untestable — the existing instance_start_driver.sh stub uvicorn
deliberately dies instantly and never binds, which is exactly wrong for
these tests.

Invoked via tests/cli/lib.sh:write_stub_uvicorn_serving's tiny bash
wrapper (argv: <module-target> <host> <port>), which is what actually
sits on PATH as `uvicorn`. Every behavior is dialed via environment
variables the driver sets before it runs start.sh/arailctl, so one file
serves every scenario without a second copy:

  STUB_STATUS        HTTP status for /api/instance (default: 200)
  STUB_FIXTURE        path to a JSON file — served verbatim as the
                      /api/instance body (default: {"slug":"root"} — the
                      caller is expected to point this at a fixture with
                      the checkout it wants to assert against)
  STUB_CRASH_AFTER    exit (crash) immediately after answering this many
                      requests total — simulates "answered once, then
                      died" so a readiness gate's dead-pid early-out
                      fires almost immediately instead of waiting the
                      full cap (default: unset = never exits on its own)
  STUB_NEVER_BIND     if "1", accept the SIGTERM contract but never
                      actually bind the socket — simulates a process that
                      starts but never comes up

Routes: GET /api/instance -> STUB_STATUS + STUB_FIXTURE body
        GET /health        -> 200 "ok" (memory/mlx probes)
        anything else      -> 404
"""
from __future__ import annotations

import http.server
import os
import signal
import socketserver
import sys


def _term(*_a: object) -> None:
    os._exit(0)


signal.signal(signal.SIGTERM, _term)
signal.signal(signal.SIGINT, _term)

if os.environ.get("STUB_NEVER_BIND") == "1":
    signal.pause()
    sys.exit(0)

_module = sys.argv[1] if len(sys.argv) > 1 else ""
_host = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
_port = int(sys.argv[3]) if len(sys.argv) > 3 else 8080

_status = int(os.environ.get("STUB_STATUS", "200"))
_fixture_path = os.environ.get("STUB_FIXTURE", "")
_crash_after = os.environ.get("STUB_CRASH_AFTER")
_request_count = 0


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_a: object) -> None:  # noqa: D401 - silence stub
        pass

    def do_GET(self) -> None:  # noqa: N802 - stdlib override
        global _request_count
        _request_count += 1
        if self.path.startswith("/api/instance"):
            body = b'{"slug":"root"}'
            if _fixture_path:
                try:
                    with open(_fixture_path, "rb") as fh:
                        body = fh.read()
                except OSError:
                    pass
            self.send_response(_status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/health"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()
        if _crash_after and _request_count >= int(_crash_after):
            # Answer THIS request, then die — exercises a readiness gate's
            # dead-pid early-out path instead of the full timeout cap.
            os._exit(0)


# REVIEW.md B2/T35: a golden-path scenario stops this stub and immediately
# rebinds the SAME port for a fresh instance (stop --root; restart --root).
# Without SO_REUSEADDR, macOS leaves the just-closed listening socket in a
# state that makes the very next bind() fail with "Address already in
# use" (Errno 48) even though nothing is actually still listening — the
# same reuse gap tests/cli/lib.sh:write_stub_listen_only's python stub
# already avoids via setsockopt(SO_REUSEADDR). allow_reuse_address is
# TCPServer's documented equivalent.
socketserver.TCPServer.allow_reuse_address = True

with socketserver.TCPServer((_host, _port), _Handler) as httpd:
    httpd.serve_forever()
