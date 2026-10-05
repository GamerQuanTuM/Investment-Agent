"""Chat session state: Redis first (key `chat:{session_id}`, 24h TTL, shared across workers
and restarts), with a per-process in-memory copy as the fallback when Redis is unreachable.

Every save writes both. A load prefers Redis and falls back to memory, so a Redis outage
degrades to single-process behaviour instead of losing the conversation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from investment_agent.market.cache import CacheTTL, cache_delete, cache_get, cache_set

logger = logging.getLogger(__name__)

HISTORY_TURNS = 6

_memory: dict[str, str] = {}


def _key(session_id: str) -> str:
    return f"chat:{session_id}"


def new_state() -> dict[str, Any]:
    return {
        "intent": None,  # the flow currently being filled in
        "slots": {},
        "last_asked": None,  # name of the question we are waiting on
        "symbol_candidates": [],
        "last_result": None,  # {"intent": ..., "slots": {...}} of the last finished plan
        "history": [],  # [{"role": "user"|"assistant", "text": str}], last HISTORY_TURNS turns
    }


async def load_session(session_id: str) -> dict[str, Any]:
    raw = await cache_get(_key(session_id))
    if raw is None:
        raw = _memory.get(session_id)
    if raw:
        try:
            state = json.loads(raw)
            if isinstance(state, dict):
                return {**new_state(), **state}
        except ValueError:
            logger.info("Discarding unreadable chat session %s", session_id)
    return new_state()


async def save_session(session_id: str, state: dict[str, Any]) -> None:
    state["history"] = state.get("history", [])[-HISTORY_TURNS * 2 :]
    raw = json.dumps(state, default=str)
    _memory[session_id] = raw
    await cache_set(_key(session_id), raw, CacheTTL.CHAT_SESSION)


async def reset_session(session_id: str) -> dict[str, Any]:
    _memory.pop(session_id, None)
    await cache_delete(_key(session_id))
    return new_state()


def add_turn(state: dict[str, Any], user_text: str, reply_text: str) -> None:
    history = state.setdefault("history", [])
    history.append({"role": "user", "text": user_text})
    history.append({"role": "assistant", "text": reply_text})
    state["history"] = history[-HISTORY_TURNS * 2 :]
