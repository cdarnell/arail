"""AirLLM subprocess worker.

Runs in its own Python process so a Metal command-buffer timeout (which
raises a C++ ``std::runtime_error`` and aborts the process) only kills
the worker — the lab portal stays alive and respawns the worker on the
next call.

Protocol: newline-delimited JSON on stdio.
  parent → stdin:  one JSON object per line, fields:
    {"id": str, "type": "complete", "prompt": str,
     "max_tokens": int, "temperature": float, "top_p": float|null}
    {"id": str, "type": "ping"}
  stdout → parent: one JSON object per line, fields:
    {"type": "ready", "model": str}                       (once, after load)
    {"type": "fatal", "error": str}                       (load failed; exits)
    {"id": str, "ok": true,  "text": str, "tokens": int,
     "latency_ms": float, "model": str}                   (per complete)
    {"id": str, "ok": false, "error": str}                (per failed call)
    {"id": str, "ok": true,  "ready": true}               (per ping)

stdout is reserved for the protocol. AirLLM (and any library) noise
from prints/loggers is redirected to stderr so the parent's diagnostic
drain picks it up without corrupting the JSON stream.
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any


# ── Reserve stdout for the protocol ───────────────────────────────────
# AirLLM and friends print "found index file…" / "found_layers:{…}" to
# stdout during load. Those lines would corrupt our JSON channel, so we
# capture the real stdout for protocol use and route everything else
# (including future logger.info calls) to stderr where the parent reads
# it for diagnostics.
_PROTOCOL_OUT = sys.stdout
sys.stdout = sys.stderr


def _send(obj: dict[str, Any]) -> None:
    _PROTOCOL_OUT.write(json.dumps(obj) + "\n")
    _PROTOCOL_OUT.flush()


def _load_model() -> tuple[Any, str]:
    from airllm import AutoModel  # type: ignore

    # TODO(deep-model): set the 20–30B open deep model id here. See ARCHITECTURE
    #   sprint 2026-05-30-model-hosting-reframe § Part 1. Until set, deep mode
    #   shows a "configure your deep model" notice — it does NOT download anything.
    _sentinel = "__TODO_DEEP_MODEL__"
    model_name = os.getenv("AIRLLM_MODEL", _sentinel)
    if model_name == _sentinel:
        raise RuntimeError(
            "Deep model is not configured. Set AIRLLM_MODEL in .env to a concrete "
            "model id and restart the lab. See NOTICE and "
            "sprints/2026-05-30-model-hosting-reframe/ARCHITECTURE.md § Part 1."
        )
    compression = os.getenv("AIRLLM_COMPRESSION", "4bit") or None
    if compression == "none":
        compression = None

    models_dir = os.getenv("ARAIL_MODELS_DIR", "lab/models")
    cache_dir = os.path.join(models_dir, "airllm_cache")
    os.makedirs(cache_dir, exist_ok=True)

    local_dir = os.path.join(models_dir, model_name.split("/")[-1])
    model_path = local_dir if os.path.isdir(local_dir) else model_name

    load_kwargs: dict[str, Any] = {
        "compression": compression,
        "layer_shards_saving_path": cache_dir,
    }
    hf_token = os.getenv("HF_TOKEN")
    if hf_token:
        load_kwargs["hf_token"] = hf_token

    model = AutoModel.from_pretrained(model_path, **load_kwargs)
    return model, model_name


def _run_complete(
    model: Any,
    model_name: str,
    max_length: int,
    prompt: str,
    max_tokens: int,
    temperature: float,
    top_p: float | None,
) -> dict[str, Any]:
    t0 = time.time()
    input_tokens = model.tokenizer(
        [prompt],
        return_tensors="pt",
        return_attention_mask=False,
        truncation=True,
        max_length=max_length,
        padding=False,
    )
    gen_kwargs: dict[str, Any] = {
        "max_new_tokens": max_tokens,
        "use_cache": True,
        "return_dict_in_generate": True,
    }
    if temperature != 1.0 or top_p is not None:
        gen_kwargs["do_sample"] = True
        gen_kwargs["temperature"] = temperature
        if top_p is not None:
            gen_kwargs["top_p"] = top_p

    input_ids = input_tokens["input_ids"]
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            input_ids = input_ids.cuda()
    except ImportError:
        pass

    generation = model.generate(input_ids, **gen_kwargs)

    if isinstance(generation, str):
        text = generation
        if text.startswith(prompt):
            text = text[len(prompt):]
        text = text.strip()
        tokens_used = len(model.tokenizer(text)["input_ids"])
    else:
        text = model.tokenizer.decode(
            generation.sequences[0], skip_special_tokens=True
        )
        if text.startswith(prompt):
            text = text[len(prompt):]
        text = text.strip()
        tokens_used = len(generation.sequences[0]) - len(input_tokens["input_ids"][0])

    return {
        "text": text,
        "tokens": max(int(tokens_used), 0),
        "latency_ms": (time.time() - t0) * 1000.0,
        "model": model_name,
    }


def main() -> int:
    try:
        model, model_name = _load_model()
        max_length = int(os.getenv("AIRLLM_MAX_LENGTH", "512"))
    except Exception as e:  # noqa: BLE001
        sys.stderr.write(traceback.format_exc())
        sys.stderr.flush()
        _send({"type": "fatal", "error": f"{type(e).__name__}: {e}"})
        return 1

    _send({"type": "ready", "model": model_name})

    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _send({"id": None, "ok": False, "error": f"bad json: {e}"})
            continue

        rid = req.get("id")
        kind = req.get("type")

        if kind == "ping":
            _send({"id": rid, "ok": True, "ready": True})
            continue

        if kind != "complete":
            _send({"id": rid, "ok": False, "error": f"unknown type: {kind!r}"})
            continue

        try:
            result = _run_complete(
                model,
                model_name,
                max_length,
                str(req.get("prompt", "")),
                int(req.get("max_tokens", 512)),
                float(req.get("temperature", 0.7)),
                req.get("top_p"),
            )
            _send({"id": rid, "ok": True, **result})
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(traceback.format_exc())
            sys.stderr.flush()
            _send({"id": rid, "ok": False,
                   "error": f"{type(e).__name__}: {e}"})

    return 0


if __name__ == "__main__":
    sys.exit(main())
