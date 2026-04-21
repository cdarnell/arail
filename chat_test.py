import asyncio
from oglab.portal.app import _run_chat_completion

async def main():
    resp = await _run_chat_completion(
        message='Reply with exactly: chat-ok',
        history=[],
        backend_override=None,
        model_override=None,
        temperature=0.1,
        top_p=0.9,
        max_tokens=12
    )
    print(resp)

if __name__ == "__main__":
    asyncio.run(main())
