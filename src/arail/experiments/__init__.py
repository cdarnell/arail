"""arail.experiments — Autonomous tuning loop for the disk-streamed
research model.

Module layout:

    tuning.py         Load / validate / save config/tuning.yml (the
                      whitelisted surface area the agent is allowed
                      to touch).
    git_ops.py        Safe git primitives: current SHA, dirty check,
                      experiment branches, structured commits.
    bench.py          Benchmark runner. Wraps the AeroLLM backend,
                      measures TTFT + decode tok/s + disk bytes read,
                      records with git context.
    autoresearch.py   The loop: snapshot baseline → propose variants
                      from the hand-curated candidate list → apply →
                      bench → commit if beats threshold.

Everything here assumes a 1 TB-class research model is configured
in tuning.yml (DeepSeek-R1 / Llama-3.1-405B / Kimi-K2). The
whole point of this module is that a 1 TB model is too big to
fit in RAM, so we're measuring and improving the disk-streaming
code path.
"""

from arail.experiments.tuning import TuningConfig, load_tuning, save_tuning
from arail.experiments.bench import BenchRun, run_bench
from arail.experiments.git_ops import GitState, git_state

__all__ = [
    "TuningConfig",
    "load_tuning",
    "save_tuning",
    "BenchRun",
    "run_bench",
    "GitState",
    "git_state",
]
