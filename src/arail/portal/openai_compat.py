"""OpenAI-compatible shim for ARAIL — /api/openai/v1/*.

Mounts two routes on the existing FastAPI app:
  GET  /api/openai/v1/models           → list_models()
  POST /api/openai/v1/chat/completions → chat()

These routes let opencode (and any future OpenAI-client tool) talk to whatever
Compute Source the lab's Chat tab is using — AirLLM, MLX, Ollama, or cloud.

Design decisions (ARCHITECTURE.md Sprint 2 @ 0967b7f):
  - Shim wraps _run_chat_completion[_stream] helpers (A5 — no /api/chat/completions
    route exists; these helpers are the shared core).
  - Not gated by tier — loopback perimeter is the security boundary (A9).
  - Never logs Authorization headers or message content (F-SEC-CRED-4).
  - source='opencode' passed to cost_tracker (F-SHIM-7).
  - Provider prefix stripped from inbound model id (F-SHIM-4).
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from typing import Any, AsyncIterator

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

_log = logging.getLogger(__name__)

_OWNED_BY = "arail-lab"


# ---------------------------------------------------------------------------
# Lazy imports — avoids circular import; mirrors opencode.py pattern
# ---------------------------------------------------------------------------

def _run_chat_completion(**kw) -> Any:   # pragma: no cover — patched in tests
    from arail.portal.app import _run_chat_completion as _impl
    return _impl(**kw)


def _run_chat_completion_stream(**kw):   # pragma: no cover — patched in tests
    from arail.portal.app import _run_chat_completion_stream as _impl
    return _impl(**kw)


def _scan_local_models(force: bool = False) -> dict:  # pragma: no cover
    from arail.portal.app import _scan_local_models as _impl
    return _impl(force=force)


def _get_chat_model_load_state() -> dict:  # pragma: no cover
    from arail.portal.app import _get_chat_model_load_state as _impl
    return _impl()


try:
    from arail.costs import cost_tracker   # type: ignore[import]
except Exception:  # noqa: BLE001
    cost_tracker = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _strip_provider_prefix(model: str) -> str:
    """Strip <provider>/ prefix so 'lab-local/Qwen' → 'Qwen'. (F-SHIM-4)"""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _openai_error(message: str, error_type: str, status: int) -> JSONResponse:
    """Return an OpenAI-shaped error response. (F-SHIM-5)"""
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": error_type, "code": None}},
    )


def _to_chat_args(body: dict) -> dict | None:
    """Map OpenAI request body → kwargs for _run_chat_completion[_stream].

    Returns None when validation fails (caller returns 400).
    Handles: messages → message + history + system prefix.
    (F-SHIM-3)
    """
    messages = body.get("messages")
    if not messages or not isinstance(messages, list):
        return None

    # Separate system messages from conversation turns
    system_parts: list[str] = []
    turns: list[dict] = []
    for msg in messages:
        role = (msg.get("role") or "").lower()
        content = str(msg.get("content") or "")
        if role == "system":
            system_parts.append(content)
        else:
            turns.append({"role": role, "content": content})

    if not turns:
        return None

    # Last user turn is the active message
    active_message = turns[-1]["content"]
    prior_turns = turns[:-1]

    # Build history as list of {user, assistant} dicts (alternating pairs)
    history: list[dict] = []
    i = 0
    while i < len(prior_turns) - 1:
        if prior_turns[i]["role"] == "user" and prior_turns[i + 1]["role"] == "assistant":
            history.append({
                "user": prior_turns[i]["content"],
                "assistant": prior_turns[i + 1]["content"],
            })
            i += 2
        else:
            i += 1

    # Prepend system content to active message if present
    if system_parts:
        system_prefix = "\n".join(system_parts)
        active_message = f"[System: {system_prefix}]\n\n{active_message}"

    model_raw = str(body.get("model") or "")
    model = _strip_provider_prefix(model_raw)

    return {
        "message": active_message,
        "history": history,
        "backend_override": None,
        "model_override": model if model else None,
        "temperature": float(body.get("temperature", 0.7)),
        "top_p": float(body.get("top_p", 1.0)) if body.get("top_p") is not None else None,
        "max_tokens": int(body.get("max_tokens", 512)),
    }


def _make_stream_id() -> str:
    return f"chatcmpl-{secrets.token_hex(12)}"


def _make_chunk(
    *,
    delta: dict,
    model: str,
    stream_id: str,
    finish_reason: str | None = None,
) -> str:
    """Return a single SSE line: data: <json>\\n\\n (F-SHIM-1)"""
    chunk = {
        "id": stream_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


# ---------------------------------------------------------------------------
# Route: GET /api/openai/v1/models
# ---------------------------------------------------------------------------

async def openai_compat_models() -> dict:
    """Return loaded + locally-available models in OpenAI envelope.

    Not gated by tier — loopback perimeter is the boundary (A9).
    Never raises. (ARCHITECTURE.md §Interface contracts)
    """
    try:
        scan = _scan_local_models()
        model_ids: set[str] = set()
        for m in scan.get("models", []):
            mid = m.get("id") or m.get("name") or ""
            if mid:
                model_ids.add(mid)

        # Include the currently-loaded model (covers runtime-served case — A8)
        try:
            load_state = _get_chat_model_load_state()
            loaded_model = load_state.get("model") if load_state.get("state") == "ready" else None
            if loaded_model:
                model_ids.add(loaded_model)
        except Exception:  # noqa: BLE001
            pass

        now = int(time.time())
        data = [
            {
                "id": mid,
                "object": "model",
                "created": now,
                "owned_by": _OWNED_BY,
            }
            for mid in sorted(model_ids)
        ]
        return {"object": "list", "data": data}
    except Exception:  # noqa: BLE001
        _log.warning("openai_compat: /models failed", exc_info=True)
        return {"object": "list", "data": []}


# ---------------------------------------------------------------------------
# Route: POST /api/openai/v1/chat/completions
# ---------------------------------------------------------------------------

async def openai_compat_chat(request: Request):
    """OpenAI-compatible chat completions proxy.

    Translates OpenAI request → _run_chat_completion[_stream].
    Never logs Authorization headers or message content. (F-SEC-CRED-4)
    source='opencode' for cost_tracker. (F-SHIM-7)
    """
    t0 = time.monotonic()

    # Parse body — never log message content
    try:
        body = await request.json()
    except Exception:
        return _openai_error("Invalid JSON body", "invalid_request_error", 400)

    if not isinstance(body, dict):
        return _openai_error("Request body must be a JSON object", "invalid_request_error", 400)

    model_raw = str(body.get("model") or "")
    if not model_raw:
        return _openai_error("'model' field is required", "invalid_request_error", 400)

    model_display = model_raw  # used in response envelope

    stream_val = body.get("stream", False)
    if isinstance(stream_val, str):
        do_stream = stream_val.lower() not in ("false", "0", "no")
    else:
        do_stream = bool(stream_val)

    chat_args = _to_chat_args(body)
    if chat_args is None:
        return _openai_error(
            "'messages' must be a non-empty array with at least one non-system entry",
            "invalid_request_error",
            400,
        )

    _log.info(
        "openai_compat: model=%s stream=%s",
        model_raw, do_stream,
    )
    # NOTE: intentionally do NOT log body.messages or Authorization header

    if do_stream:
        return await _handle_stream(chat_args, model_display, t0)
    else:
        return await _handle_non_stream(chat_args, model_display, t0)


async def _handle_non_stream(chat_args: dict, model: str, t0: float):
    """Handle stream=False path. (F-SHIM-2)"""
    stream_id = _make_stream_id()
    try:
        result = await _run_chat_completion(**chat_args)
    except Exception as exc:  # noqa: BLE001
        _log.error("openai_compat: backend exception: %s", type(exc).__name__)
        return _openai_error(str(exc), "server_error", 500)

    if result.get("error") and not result.get("reply"):
        return _openai_error(str(result["error"]), "server_error", 500)

    reply = result.get("reply") or ""
    tokens_out = result.get("tokens_used") or 0
    prompt_tokens = max(len(chat_args.get("message", "")) // 4, 1)

    latency_ms = round((time.monotonic() - t0) * 1000, 1)
    _log.info("openai_compat: finish_reason=stop latency_ms=%s", latency_ms)

    # Track cost with source='opencode' (F-SHIM-7)
    try:
        if cost_tracker is not None:
            cost_tracker.track(
                backend=result.get("backend") or "unknown",
                model=result.get("model") or model,
                tokens_in=prompt_tokens,
                tokens_out=tokens_out,
                latency_ms=result.get("latency_ms") or latency_ms,
                source="opencode",
            )
    except Exception:  # noqa: BLE001
        pass

    return JSONResponse(content={
        "id": stream_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": reply},
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": tokens_out,
            "total_tokens": prompt_tokens + tokens_out,
        },
    })


async def _handle_stream(chat_args: dict, model: str, t0: float):
    """Handle stream=True path — emit OpenAI SSE chunks. (F-SHIM-1, F-SHIM-8)"""
    stream_id = _make_stream_id()

    async def _generator() -> AsyncIterator[str]:
        role_sent = False
        try:
            async for event in _run_chat_completion_stream(**chat_args):
                etype = event.get("type")
                if etype == "start":
                    # Emit role-only delta on first chunk
                    if not role_sent:
                        role_sent = True
                        yield _make_chunk(
                            delta={"role": "assistant", "content": ""},
                            model=model,
                            stream_id=stream_id,
                        )
                elif etype == "delta":
                    delta_text = event.get("delta") or ""
                    if not role_sent:
                        role_sent = True
                        yield _make_chunk(
                            delta={"role": "assistant", "content": delta_text},
                            model=model,
                            stream_id=stream_id,
                        )
                    else:
                        yield _make_chunk(
                            delta={"content": delta_text},
                            model=model,
                            stream_id=stream_id,
                        )
                elif etype == "final":
                    err = event.get("error")
                    if err:
                        error_chunk = {
                            "error": {
                                "message": str(err),
                                "type": "backend_error",
                                "code": None,
                            }
                        }
                        yield f"data: {json.dumps(error_chunk)}\n\n"
                    # Emit stop chunk
                    yield _make_chunk(
                        delta={},
                        model=model,
                        stream_id=stream_id,
                        finish_reason="stop",
                    )
                    latency_ms = round((time.monotonic() - t0) * 1000, 1)
                    _log.info(
                        "openai_compat: stream finish_reason=stop latency_ms=%s",
                        latency_ms,
                    )
                    # Track cost (F-SHIM-7)
                    try:
                        if cost_tracker is not None:
                            tokens_out = event.get("tokens_used") or 0
                            prompt_tokens = max(len(chat_args.get("message", "")) // 4, 1)
                            cost_tracker.track(
                                backend=event.get("backend") or "unknown",
                                model=event.get("model") or model,
                                tokens_in=prompt_tokens,
                                tokens_out=tokens_out,
                                latency_ms=event.get("latency_ms") or latency_ms,
                                source="opencode",
                            )
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            _log.error("openai_compat: stream backend exception: %s", type(exc).__name__)
            error_chunk = {
                "error": {
                    "message": str(exc),
                    "type": "server_error",
                    "code": None,
                }
            }
            yield f"data: {json.dumps(error_chunk)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Registration helper — called from app.py
# ---------------------------------------------------------------------------

def register_routes(app) -> None:
    """Mount the two OpenAI-compat routes on the given FastAPI app.

    Called from app.py after all other setup. No module-level side effects.
    """
    app.get("/api/openai/v1/models")(openai_compat_models)
    app.post("/api/openai/v1/chat/completions")(openai_compat_chat)
