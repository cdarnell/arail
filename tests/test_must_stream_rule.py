"""Test the 35B hardware-floor rule and metadata override registry.

Sprint: 2026-05-03-models-admin-dashboard
Architect MUST-HIT scenarios covered:
  - A2  Capacity-0 / regex fails (unknown model) -> defaults to small
  - A4  Override regex non-O(1) cost -> lru_cache covers it
  - A6  HF-id vs local-dir-name mismatch for Llama-4 -> regex matches both
  - B1  Llama-4 pattern collision (Llama-3-Maverick-17B-128E should NOT match)
  - B3  HF-id vs local form (alias of A6)
  - B4  Case sensitivity

Plus the paranoid edge-case hunt:
  - Empty / None / whitespace inputs -> False
  - Non-string inputs -> False (defensive)
  - Boundary values (35.0 == HARDWARE_FLOOR_TOTAL_B -> NOT streamed)
  - Unicode / very-long names -> handled, no crash
  - get_total_params returns proper float, None when unknown
  - Llama-4 Maverick total params is exactly 400.0
"""

from __future__ import annotations

import pytest

from arail import model_specs
from arail.model_specs import (
    HARDWARE_FLOOR_TOTAL_B,
    MODEL_METADATA_OVERRIDES,
    get_total_params,
    must_stream,
)


# ---------------------------------------------------------------------------
# Module-level invariants — fail fast if someone moves the threshold
# ---------------------------------------------------------------------------

def test_hardware_floor_constant_is_35():
    """HARDWARE_FLOOR_TOTAL_B is THE hard hardware floor — locked at 35B."""
    assert HARDWARE_FLOOR_TOTAL_B == 35.0


def test_metadata_overrides_is_a_list_of_pattern_dict_tuples():
    """Override registry shape: each entry must be (compiled_regex, dict)."""
    import re as _re
    assert isinstance(MODEL_METADATA_OVERRIDES, list)
    for entry in MODEL_METADATA_OVERRIDES:
        assert isinstance(entry, tuple) and len(entry) == 2
        pat, meta = entry
        assert isinstance(pat, _re.Pattern)
        assert isinstance(meta, dict)
        assert "total_params_b" in meta
        assert isinstance(meta["total_params_b"], (int, float))
        assert meta["total_params_b"] > 0


# ---------------------------------------------------------------------------
# Llama-4 Maverick — A6 (HF-id vs local), B3 (alias), B4 (case)
# ---------------------------------------------------------------------------

def test_must_stream_llama4_maverick_local_dir():
    """A6: local symlink dir name `Llama-4-Maverick-17B-128E-Instruct-fp8`."""
    assert must_stream("Llama-4-Maverick-17B-128E-Instruct-fp8") is True


def test_must_stream_llama4_maverick_hf_id():
    """A6: HF id `meta-llama/Llama-4-Maverick-17B-128E-Instruct`."""
    assert must_stream("meta-llama/Llama-4-Maverick-17B-128E-Instruct") is True


def test_must_stream_llama4_uppercase():
    """B4: case-insensitivity — IGNORECASE flag on the regex."""
    assert must_stream("LLAMA-4-MAVERICK-17B-128E-INSTRUCT-FP8") is True


def test_must_stream_llama4_lowercase():
    """B4: lowercase variant."""
    assert must_stream("llama-4-maverick-17b-128e-instruct-fp8") is True


def test_must_stream_llama4_mixed_case():
    """B4: mixed case."""
    assert must_stream("LlAmA-4-MaVeRiCk-17B-128E") is True


def test_get_total_params_llama4_maverick_is_400b():
    """Llama-4 Maverick metadata override returns 400.0."""
    assert get_total_params("Llama-4-Maverick-17B-128E-Instruct-fp8") == 400.0


def test_get_total_params_llama4_maverick_hf_id():
    """HF id resolves to the same 400B."""
    assert get_total_params("meta-llama/Llama-4-Maverick-17B-128E-Instruct") == 400.0


# ---------------------------------------------------------------------------
# B1 — Llama-4 pattern collision: Llama-3-Maverick-17B-128E must NOT match
# ---------------------------------------------------------------------------

def test_llama3_maverick_does_not_match_llama4_pattern():
    """B1: regex requires `Llama-4` prefix; Llama-3 must not collide."""
    assert get_total_params("Llama-3-Maverick-17B-128E") is None


def test_llama4_scout_3b_does_not_match():
    """B1: pattern requires 17B AND 128E — Scout-3B must not collide."""
    assert get_total_params("Llama-4-Scout-3B") is None


def test_llama4_without_maverick_does_not_match():
    """B1: pattern requires "Maverick" string — bare Llama-4 must not collide."""
    assert get_total_params("Llama-4-7B") is None


# ---------------------------------------------------------------------------
# Regex fallback — names without an override
# ---------------------------------------------------------------------------

def test_must_stream_llama_70b_via_regex():
    """70B parses out of the name → exceeds 35B → streamed."""
    assert must_stream("Llama-3.1-70B") is True


def test_must_stream_qwen_8b_via_regex():
    """8B parses → under 35B → not streamed."""
    assert must_stream("Qwen3-8B") is False


def test_must_stream_qwen_8b_4bit_via_regex():
    """Quantization suffix doesn't break regex parsing."""
    assert must_stream("Qwen3-8B-4bit") is False


def test_must_stream_405b_via_regex():
    """405B clearly exceeds 35B."""
    assert must_stream("Llama-3.1-405B") is True


def test_must_stream_3b_via_regex():
    """Tiny model → not streamed."""
    assert must_stream("tinyllama-3b") is False


# ---------------------------------------------------------------------------
# Boundary values — exactly 35B is NOT streamed (threshold is `> 35`)
# ---------------------------------------------------------------------------

def test_must_stream_exactly_35b_is_false():
    """Boundary: 35B == floor is NOT streamed (strict greater-than)."""
    assert must_stream("Model-35B") is False


def test_must_stream_36b_is_true():
    """Boundary: 36B is one tick over the floor."""
    assert must_stream("Model-36B") is True


def test_must_stream_34b_is_false():
    """Boundary: 34B is just under."""
    assert must_stream("Model-34B") is False


def test_must_stream_decimal_above_floor():
    """Boundary: 35.5B is over."""
    assert must_stream("Model-35.5B") is True


# ---------------------------------------------------------------------------
# A2 — Unknown / unparseable / empty input → False (safer default)
# ---------------------------------------------------------------------------

def test_must_stream_empty_string_is_false():
    """Empty string -> False (safer default per docstring)."""
    assert must_stream("") is False


def test_must_stream_whitespace_only_is_false():
    """A regex won't match whitespace -> safe default False."""
    assert must_stream("   ") is False


def test_must_stream_none_is_false():
    """None should not crash — must_stream guards on falsy input."""
    # The function signature is str, but Python won't enforce that.
    # The function's docstring says "bad input -> False (safer default)".
    assert must_stream(None) is False  # type: ignore[arg-type]


def test_must_stream_unparseable_name_is_false():
    """A name with no number+unit pattern returns False."""
    assert must_stream("some-random-thing-no-numbers") is False


def test_must_stream_just_numbers_no_unit():
    """Numbers without B/M/K suffix don't match the regex."""
    assert must_stream("model-12345") is False


def test_must_stream_megabyte_unit_under_floor():
    """500M = 0.5B → never above 35B."""
    assert must_stream("model-500M") is False


def test_must_stream_kilobyte_unit_never_streamed():
    """K unit is always under 35B (handled in the K branch)."""
    assert must_stream("model-9999K") is False


def test_get_total_params_empty_string_is_none():
    assert get_total_params("") is None


def test_get_total_params_unknown_is_none():
    assert get_total_params("totally-unknown-model") is None


# ---------------------------------------------------------------------------
# Defensive — hostile / unusual inputs that must not crash
# ---------------------------------------------------------------------------

def test_must_stream_unicode_in_name_does_not_crash():
    """Unicode characters in name → graceful handling."""
    # Should fall through to the regex; no parse → False.
    assert must_stream("café-model-héllo") is False


def test_must_stream_very_long_name_does_not_crash():
    """A 4KB name should not OOM or hang the lru_cache."""
    name = "x" * 4096
    assert must_stream(name) is False


def test_must_stream_path_separator_in_name_does_not_crash():
    """Slashes (HF-id form) must work; backslashes too."""
    assert must_stream("foo/bar-7B") is False
    assert must_stream("foo\\bar-7B") is False


def test_must_stream_special_regex_chars_in_name():
    """Regex meta-chars in the name must not be interpreted."""
    # parens, brackets, dots, asterisks
    for hostile in ["(.*)-7B", "model[1]-7B", "model.7B", "{x}-7B"]:
        # no crash; result is whatever the inline regex produces
        result = must_stream(hostile)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# A4 — lru_cache verification (idempotency, repeat-call cheap)
# ---------------------------------------------------------------------------

def test_must_stream_lru_cache_idempotent():
    """Calling twice returns the same value (cache hit)."""
    name = "Llama-4-Maverick-17B-128E-Instruct-fp8"
    a = must_stream(name)
    b = must_stream(name)
    assert a is b is True


def test_must_stream_cache_info_present():
    """lru_cache decorator exposes cache_info()."""
    assert hasattr(must_stream, "cache_info")
    assert hasattr(must_stream, "cache_clear")
    info = must_stream.cache_info()
    assert info.maxsize == 512


def test_get_total_params_cache_info_present():
    """lru_cache exposed on get_total_params too."""
    assert hasattr(get_total_params, "cache_info")
    info = get_total_params.cache_info()
    assert info.maxsize == 512


# ---------------------------------------------------------------------------
# Module-level imports stay clean — no crash on import (setup-on-clean-machine)
# ---------------------------------------------------------------------------

def test_module_reimport_clean():
    """Re-importing model_specs after a hot-reload should be safe."""
    import importlib
    importlib.reload(model_specs)
    # After reload, must_stream still works.
    assert model_specs.must_stream("Llama-3.1-70B") is True
