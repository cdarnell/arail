"""Template content for the auto-generated ``lab/pkb/research/train.py``.

The drafter writes this stub the first time a goal is set. Most lab
goals are pure config tuning, so the default body is a no-op — the
autoresearch loop rewrites ``config/tuning.yml`` directly. When a goal
needs real training (LoRA, SFT, distillation), the user edits the file
in place.
"""

from __future__ import annotations

# We keep the body as a single-source-of-truth string so tests can
# assert against it without re-reading the generated file.
TRAIN_PY_TEMPLATE = '''"""train.py — apply a research variant to the deep model.

The autoresearch loop calls :func:`apply_variant` before each variant's
benchmark run, and :func:`revert_variant` after, so every measurement
starts from a known baseline.

Default behavior is a **no-op**: pure-config variants (KV cache bits,
prefill chunk size, prefetch lookahead, etc.) are written straight
into ``config/tuning.yml`` by the loop and don't need a separate apply
step. The stub exists so a goal that needs real training (LoRA,
fine-tuning, distillation) has an obvious file to edit.

When you do add real training:
- Keep the function signatures stable — autoresearch passes the same
  ``variant`` dict it parsed out of program.md's ``## Knobs`` block.
- Honor the convention that ``revert_variant`` is the inverse of
  ``apply_variant`` — the loop runs experiments in isolation and
  expects the world to be back at baseline between runs.
- Surface progress via the activity log
  (``arail.activity.activity_log.emit("researcher", ...)``) so the
  Researcher card on /agents shows your training progress.

See ``lab/pkb/research/README.md`` for the full recipe contract.
"""

from __future__ import annotations

from typing import Any, Dict


def apply_variant(variant: Dict[str, Any]) -> None:
    """Apply a research variant to the deep model.

    Default: no-op. Pure-config knobs are handled by autoresearch.py
    rewriting tuning.yml. Override when your variant requires actual
    training (LoRA adapters, SFT runs, distillation steps, etc.).
    """
    return None


def revert_variant(variant: Dict[str, Any]) -> None:
    """Undo whatever ``apply_variant`` did, returning to baseline.

    Default: no-op (since apply_variant is a no-op). Override symmetrically
    with apply_variant — the autoresearch loop relies on this returning
    the world to a clean baseline between variants.
    """
    return None
'''
