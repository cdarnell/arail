"""Shared fixtures for the setup-ladder mock tests.

OOM-SAFETY (workspace MEMORY: this machine OOMs under concurrent uvicorn +
LLM loads): NOTHING here runs real ollama, real curl, or downloads a single
byte. Every external command is a PATH shim under a per-test stub dir. The
bash harness sources scripts/setup.sh with its `main "$@"` line stripped and
calls only the ai-eng fetch ladder (the back half of install_services()).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent / "run_install_models.sh"


class LadderResult:
    def __init__(self, returncode: int, output: str, calllog: str):
        self.returncode = returncode
        self.output = output          # combined stdout+stderr of install ladder
        self.calllog = calllog        # newline log of stub invocations
        # install_services()'s own return (the harness echoes it)
        self.ladder_exit = None
        for line in output.splitlines():
            if line.startswith("__INSTALL_MODELS_EXIT__="):
                self.ladder_exit = int(line.split("=", 1)[1])

    def calls(self, needle: str) -> int:
        return sum(1 for ln in self.calllog.splitlines() if needle in ln)

    def called(self, needle: str) -> bool:
        return self.calls(needle) > 0


# ---- stub bodies -----------------------------------------------------------
# Each is a tiny bash script. They append to $QA_LOG so tests can assert which
# external commands ran and with what args. None of them touch the network.

_OLLAMA_STUB = r"""#!/usr/bin/env bash
case "$1" in
  --version) echo "ollama version {ollama_version}" ;;
  show)
    # $2 is the model name being probed. Treat as "installed" only if it is
    # listed in $QA_INSTALLED (space-separated).
    for m in $QA_INSTALLED; do [[ "$2" == "$m" ]] && exit 0; done
    exit 1 ;;
  pull)
    echo "PULL $2" >> "$QA_LOG"
    case "$2" in
      hf.co/*) [[ "$QA_HF_OK" == "1" ]] && exit 0 || exit 1 ;;
      llama3.2:1b) [[ "$QA_LLAMA_PULL_OK" == "1" ]] && exit 0 || exit 1 ;;
      *) [[ "$QA_PREVIEW_PULL_OK" == "1" ]] && exit 0 || exit 1 ;;
    esac ;;
  create) echo "CREATE $*" >> "$QA_LOG"; [[ "$QA_CREATE_OK" == "1" ]] && exit 0 || exit 1 ;;
  cp) echo "CP $*" >> "$QA_LOG"; [[ "$QA_CP_OK" == "1" ]] && exit 0 || exit 1 ;;
  *) exit 0 ;;
esac
"""

_CURL_STUB = r"""#!/usr/bin/env bash
echo "CURL $*" >> "$QA_LOG"
# Honour -o <file>: write fake bytes so sha256sum has something to read.
prev=""
for a in "$@"; do
  if [[ "$prev" == "-o" ]]; then printf 'FAKE_GGUF_BYTES' > "$a"; fi
  prev="$a"
done
[[ "$QA_CURL_OK" == "1" ]] && exit 0 || exit 22
"""

_SHA_STUB = r"""#!/usr/bin/env bash
# Emit $QA_FAKE_SHA for whatever file is passed (default: matches nothing).
echo "${QA_FAKE_SHA:-0000000000000000000000000000000000000000000000000000000000000000}  $1"
"""

_NOOP_STUB = "#!/usr/bin/env bash\nexit 0\n"
_TIMEOUT_STUB = '#!/usr/bin/env bash\nshift\nexec "$@"\n'


@pytest.fixture
def ladder(tmp_path):
    """Return a callable: run the ai-eng install ladder with given env.

    Keyword args become QA_* env knobs read by the stubs. Defaults model the
    current reality: nothing installed, HF pull fails (artifact not uploaded),
    curl fails, sha placeholder.
    """
    binp = tmp_path / "bin"
    binp.mkdir()

    def _write(name: str, body: str):
        p = binp / name
        p.write_text(body)
        p.chmod(0o755)

    def _run(*, ollama_version="0.5.0", installed="", hf_ok="0",
             llama_pull_ok="1", preview_pull_ok="1", create_ok="1",
             cp_ok="1", curl_ok="0", fake_sha="deadbeef", env=None):
        _write("ollama", _OLLAMA_STUB.format(ollama_version=ollama_version))
        _write("curl", _CURL_STUB)
        _write("sha256sum", _SHA_STUB)
        _write("timeout", _TIMEOUT_STUB)
        for tool in ("ttyd", "tmux", "agent-browser", "brew", "npm"):
            _write(tool, _NOOP_STUB)
        qa_log = tmp_path / "calls.log"
        qa_log.write_text("")

        run_env = dict(os.environ)
        run_env.update({
            "REPO_ROOT": str(REPO_ROOT),
            "STUB_BIN": str(binp),
            "QA_LOG": str(qa_log),
            "QA_INSTALLED": installed,
            "QA_HF_OK": hf_ok,
            "QA_LLAMA_PULL_OK": llama_pull_ok,
            "QA_PREVIEW_PULL_OK": preview_pull_ok,
            "QA_CREATE_OK": create_ok,
            "QA_CP_OK": cp_ok,
            "QA_CURL_OK": curl_ok,
            "QA_FAKE_SHA": fake_sha,
            "ARAIL_NONINTERACTIVE": "1",
        })
        if env:
            run_env.update(env)

        proc = subprocess.run(
            ["bash", str(HARNESS)],
            env=run_env, capture_output=True, text=True, timeout=60,
        )
        return LadderResult(proc.returncode,
                            proc.stdout + proc.stderr,
                            qa_log.read_text())

    return _run
