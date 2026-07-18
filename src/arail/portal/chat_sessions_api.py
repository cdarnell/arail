"""Chat conversations API — list/create/fold/rename/delete.

Storage per docs/conversation-memory.md (PKB root, event-log transcript);
the persistence hooks for live turns are in the /api/chat/stream handler.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

chat_sessions_router = APIRouter(prefix="/api/chat/conversations",
                                 tags=["chat"])


def _store():
    from arail.chat.conversations import ConversationStore
    return ConversationStore()


@chat_sessions_router.get("")
async def conversations_list() -> Dict[str, Any]:
    return {"conversations": _store().list()}


class NewConversation(BaseModel):
    title: str = ""


@chat_sessions_router.post("")
async def conversations_create(req: NewConversation) -> Dict[str, Any]:
    return _store().create(req.title)


@chat_sessions_router.get("/{cid}")
async def conversations_get(cid: str, last_n_turns: int = 200) -> Dict[str, Any]:
    store = _store()
    meta = store.get_meta(cid)
    if meta is None:
        raise HTTPException(status_code=404, detail="unknown conversation")
    folded = store.fold(cid, last_n_turns=last_n_turns)
    return {**folded, "meta": meta}


class Rename(BaseModel):
    title: str


@chat_sessions_router.patch("/{cid}")
async def conversations_rename(cid: str, req: Rename) -> Dict[str, Any]:
    meta = _store().rename(cid, req.title)
    if meta is None:
        raise HTTPException(status_code=404, detail="unknown conversation")
    return meta


@chat_sessions_router.delete("/{cid}")
async def conversations_delete(cid: str) -> Dict[str, Any]:
    if not _store().delete(cid):
        raise HTTPException(status_code=404, detail="unknown conversation")
    return {"deleted": cid}
