"""Small OpenAI-compatible HTTP server backed by the local MLX runtime.

This is the bridge for integrations that want an OpenAI-style API but
where OGLab's primary local runtime is still direct MLX/mlx-lm.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Iterator

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from oglab.router.backends import MLXBackend, ModelResponse

app = FastAPI(title="OGLab MLX OpenAI Server")

_BACKEND: MLXBackend | None = None


def _backend() -> MLXBackend:
    global _BACKEND
    if _BACKEND is None:
        _BACKEND = MLXBackend()
    return _BACKEND


def _render_messages(messages: list[dict[str, Any]], backend: MLXBackend) -> str:
    tokenizer = getattr(backend, "tokenizer", None)
    if tokenizer is not None and hasattr(tokenizer, "apply_chat_template"):
        try:
            kwargs: dict[str, Any] = {
                "tokenize": False,
                "add_generation_prompt": True,
            }
            model_name = str(getattr(backend, "model_name", "") or "").lower()
            if "qwen" in model_name:
                kwargs["enable_thinking"] = False
            rendered = tokenizer.apply_chat_template(messages, **kwargs)
            if isinstance(rendered, str) and rendered.strip():
                return rendered
        except Exception:
            pass

    parts: list[str] = []
    for item in messages:
        role = str(item.get("role") or "user").upper()
        content = str(item.get("content") or "")
        parts.append(f"{role}: {content}")
    parts.append("ASSISTANT:")
    return "\n\n".join(parts)


def _usage(prompt: str, response: ModelResponse) -> dict[str, int]:
    prompt_tokens = max(len(prompt) // 4, 1)
    completion_tokens = max(int(response.tokens_used or 0), 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


@app.get("/health")
def health() -> dict[str, Any]:
    backend = _backend()
    return {
        "ok": True,
        "backend": "mlx",
        "model": backend.model_name,
    }


@app.get("/v1/models")
def models() -> dict[str, Any]:
    backend = _backend()
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": backend.model_name,
                "object": "model",
                "created": now,
                "owned_by": "oglab-mlx",
            }
        ],
    }


@app.post("/v1/chat/completions")
async def chat_completions(body: dict[str, Any]) -> Any:
    backend = _backend()
    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        return JSONResponse({"error": {"message": "messages required"}}, status_code=400)

    prompt = _render_messages(messages, backend)
    max_tokens = int(body.get("max_tokens") or 512)
    temperature = float(body.get("temperature") or 0.7)
    top_p_raw = body.get("top_p")
    try:
        top_p = float(str(top_p_raw)) if top_p_raw not in (None, "") else None
    except (TypeError, ValueError):
        top_p = None
    stream = bool(body.get("stream"))
    model_name = str(body.get("model") or backend.model_name)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    if stream:
        def _generate() -> Iterator[str]:
            final: ModelResponse | None = None
            try:
                for item in backend.stream_complete(
                    prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                ):
                    if isinstance(item, ModelResponse):
                        final = item
                        continue
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": item},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
            except Exception as exc:  # noqa: BLE001
                err = {
                    "error": {"message": str(exc)},
                }
                yield f"data: {json.dumps(err)}\n\n"
            if final is not None:
                done_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                    "usage": _usage(prompt, final),
                }
                yield f"data: {json.dumps(done_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(_generate(), media_type="text/event-stream")

    response = backend.complete(
        prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_name,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response.text},
            "finish_reason": "stop",
        }],
        "usage": _usage(prompt, response),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "oglab.mlx_openai_server:app",
        host=os.getenv("BIND_ADDR", "127.0.0.1"),
        port=int(os.getenv("MLX_OPENAI_PORT", "11435")),
        log_level="warning",
    )