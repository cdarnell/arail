"""Tests for AeroLLMBackend's per-model chat-template dispatch.

Regression coverage for F-1 (sprints/2026-07-11-aerollm-release-arail-verify/
TEST_REPORT.md): _wrap_chatml used to hardcode Qwen2.5 ChatML for every
model routed through AeroLLMBackend, producing garbage output for
non-ChatML checkpoints (e.g. gpt-oss's harmony format). The fix loads
the model's own tokenizer/chat_template from its local directory and
dispatches via _wrap_prompt() instead of assuming one family.

Uses a fake aerollm_api module (no real Metal/weights) and a fake
transformers module (no real tokenizer load, and crucially no real
`import torch` — transformers' lazy AutoTokenizer resolution pulls in
torch, which is fragile to double-import when the full suite has
already touched it elsewhere) so this runs on any host, including CI.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


def _make_fake_aerollm_api() -> types.ModuleType:
    fake = types.ModuleType("aerollm_api")
    fake.__version__ = "0.0.0-test"

    class FakeRuntime:
        def __init__(self, model_path: str, **kwargs: Any) -> None:
            self._model_path = model_path

        def start(self) -> None:
            pass

        def generate(self, prompt: str, **kwargs: Any) -> str:
            return FakeRuntime.next_output

        next_output = ""

    fake.Runtime = FakeRuntime
    return fake


class _FakeTokenizer:
    """Stands in for a transformers PreTrainedTokenizer, exposing just
    what _wrap_prompt() / complete() touch."""

    def __init__(self, family: str):
        self.family = family
        self.bos_token = "<bos>"
        self.pad_token = "<pad>"
        self.unk_token = "<unk>"
        if family == "chatml":
            self.eos_token = "<|im_end|>"
            self.all_special_tokens = [
                "<bos>", "<pad>", "<unk>", "<|im_end|>", "<|im_start|>",
            ]
        elif family == "harmony":
            self.eos_token = "<|return|>"
            self.all_special_tokens = [
                "<bos>", "<pad>", "<unk>", "<|return|>", "<|start|>",
                "<|end|>", "<|message|>", "<|channel|>",
            ]
        elif family == "no_template":
            self.eos_token = "</s>"
            self.all_special_tokens = ["<bos>", "<pad>", "<unk>", "</s>"]
        else:
            raise ValueError(family)

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        if self.family == "no_template":
            raise ValueError("This tokenizer does not have a chat_template")
        user_content = next(m["content"] for m in messages if m["role"] == "user")
        system_content = next(m["content"] for m in messages if m["role"] == "system")
        if self.family == "chatml":
            return (
                f"<|im_start|>system\n{system_content}<|im_end|>\n"
                f"<|im_start|>user\n{user_content}<|im_end|>\n"
                "<|im_start|>assistant\n"
            )
        # harmony
        return (
            f"<|start|>system<|message|>{system_content}<|end|>"
            f"<|start|>user<|message|>{user_content}<|end|>"
            "<|start|>assistant"
        )


_FAKE_MODEL_DIR = "/tmp/fake-aerollm-chat-template-model"


@pytest.fixture(autouse=True)
def _patch_env_and_model(monkeypatch, tmp_path):
    model_dir = tmp_path / "some-model"
    model_dir.mkdir()
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("AEROLLM_MODEL", "some-model")
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    monkeypatch.delenv("AEROLLM_DRAFT_MODEL", raising=False)
    monkeypatch.delenv("AEROLLM_RING_DEPTH", raising=False)


@pytest.fixture(autouse=True)
def _clear_shared():
    from arail.router.backends import AeroLLMBackend
    AeroLLMBackend._shared.clear()
    yield
    AeroLLMBackend._shared.clear()


@pytest.fixture(autouse=True)
def _fake_aerollm_api(monkeypatch):
    fake = _make_fake_aerollm_api()
    monkeypatch.setitem(sys.modules, "aerollm_api", fake)
    return fake


def _make_fake_transformers(tokenizer_family: "str | None") -> types.ModuleType:
    """Fake the whole `transformers` module so __init__'s lazy
    `from transformers import AutoTokenizer` never touches the real
    (torch-backed) package.

    tokenizer_family=None simulates AutoTokenizer.from_pretrained
    failing (e.g. transformers missing, or a checkpoint transformers
    can't read).
    """
    fake = types.ModuleType("transformers")

    class FakeAutoTokenizer:
        @staticmethod
        def from_pretrained(model_path, **kwargs):
            if tokenizer_family is None:
                raise OSError("no tokenizer")
            return _FakeTokenizer(tokenizer_family)

    fake.AutoTokenizer = FakeAutoTokenizer
    return fake


def _make_backend(monkeypatch, tokenizer_family: "str | None"):
    """Construct an AeroLLMBackend with a stubbed tokenizer load.
    monkeypatch.setitem ensures sys.modules['transformers'] (real,
    fake, or absent) is restored once the test ends."""
    from arail.router.backends import AeroLLMBackend

    fake_transformers = _make_fake_transformers(tokenizer_family)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    return AeroLLMBackend()


# ── _wrap_prompt dispatch ─────────────────────────────────────────────────


def test_chatml_family_gets_chatml_wrapping(monkeypatch):
    backend = _make_backend(monkeypatch, "chatml")
    wrapped = backend._wrap_prompt("hi there")
    assert "<|im_start|>user\nhi there<|im_end|>" in wrapped
    assert "<|start|>" not in wrapped


def test_harmony_family_gets_harmony_wrapping_not_chatml(monkeypatch):
    """The core regression: a gpt-oss-family tokenizer must NOT be
    wrapped in Qwen2.5's ChatML tags."""
    backend = _make_backend(monkeypatch, "harmony")
    wrapped = backend._wrap_prompt("hi there")
    assert "<|start|>user<|message|>hi there<|end|>" in wrapped
    assert "<|im_start|>" not in wrapped
    assert "<|im_end|>" not in wrapped


def test_missing_tokenizer_falls_back_to_legacy_chatml(monkeypatch):
    """If the tokenizer can't be loaded at all, fall back to the
    historic Qwen2.5 ChatML wrap rather than crashing."""
    backend = _make_backend(monkeypatch, None)
    assert backend._tokenizer is None
    wrapped = backend._wrap_prompt("hi there")
    assert "<|im_start|>user\nhi there<|im_end|>" in wrapped


def test_tokenizer_without_chat_template_falls_back_to_raw_prompt(monkeypatch):
    """A tokenizer that loads but has no chat_template (apply_chat_template
    raises) should NOT silently get Qwen2.5 ChatML slapped on — send the
    prompt through unwrapped instead."""
    backend = _make_backend(monkeypatch, "no_template")
    assert backend._tokenizer is not None
    wrapped = backend._wrap_prompt("hi there")
    assert wrapped == "hi there"


def test_already_wrapped_harmony_prompt_is_not_double_wrapped(monkeypatch):
    backend = _make_backend(monkeypatch, "harmony")
    pre_wrapped = "<|start|>user<|message|>hi there<|end|><|start|>assistant"
    assert backend._wrap_prompt(pre_wrapped) == pre_wrapped


def test_already_wrapped_chatml_prompt_is_not_double_wrapped(monkeypatch):
    backend = _make_backend(monkeypatch, "chatml")
    pre_wrapped = "<|im_start|>user\nhi there<|im_end|>\n<|im_start|>assistant\n"
    assert backend._wrap_prompt(pre_wrapped) == pre_wrapped


# ── complete() output stripping ────────────────────────────────────────────


def test_complete_strips_harmony_special_tokens_generically(monkeypatch):
    """Output stripping must not be hardcoded to <|im_end|> — a harmony
    response's own turn markers should be stripped too."""
    import aerollm_api

    backend = _make_backend(monkeypatch, "harmony")
    aerollm_api.Runtime.next_output = "<|message|>hello!<|return|>"
    resp = backend.complete("hi there")
    assert resp.text == "hello!"
    assert "<|message|>" not in resp.text
    assert "<|return|>" not in resp.text


def test_complete_strips_chatml_special_tokens(monkeypatch):
    import aerollm_api

    backend = _make_backend(monkeypatch, "chatml")
    aerollm_api.Runtime.next_output = "hello!<|im_end|>"
    resp = backend.complete("hi there")
    assert resp.text == "hello!"
