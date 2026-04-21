"""
Thin wrapper around the lab's model_router. Canvas backend never talks
to LLMs directly — everything goes through the lab router so backend
switches (Ollama -> OpenRouter -> Claude -> local MLX) are a single
env change in the lab's .env.
"""
import os
import sys
from pathlib import Path


# Add the lab root to sys.path so we can import model_router.
# Canvas lives at lab/core/knowledge-canvas, so lab root is 3 up.
_LAB_ROOT = Path(__file__).resolve().parents[4]
if str(_LAB_ROOT) not in sys.path:
    sys.path.insert(0, str(_LAB_ROOT))


async def complete(prompt: str, system: str | None = None, temperature: float = 0.3) -> str:
    try:
        from model_router.router import route_completion  # lab-provided
        return await route_completion(
            prompt=prompt, system=system, temperature=temperature,
            backend=os.getenv("ROUTER_BACKEND"),
            model=os.getenv("ROUTER_MODEL"),
        )
    except ImportError:
        return await _ollama_fallback(prompt, system, temperature)


async def _ollama_fallback(prompt: str, system: str | None, temperature: float) -> str:
    import httpx
    url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    model = os.getenv("ROUTER_MODEL", "llama3.1:8b")
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{url}/api/chat", json={
            "model": model, "messages": messages,
            "options": {"temperature": temperature}, "stream": False,
        })
        r.raise_for_status()
        return r.json()["message"]["content"]
