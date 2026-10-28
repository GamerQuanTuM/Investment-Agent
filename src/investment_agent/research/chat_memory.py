"""Long-term chat memory in Postgres (pgvector).

Every message is stored with a Gemini embedding. On a new turn `build_context` returns the last
few turns of the session plus the older messages most similar to the new one, so a follow-up
like "what about the second one?" or a question about something said twenty turns ago still has
its context. Everything here degrades quietly: if the database, the embedding call or the key is
unavailable, the chat carries on with just the recent turns kept in the session.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar
from typing import Any

from sqlalchemy import select

from investment_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

MEMORY_TIMEOUT_SECONDS = 3.0
RECALL_LIMIT = 4
MAX_STORED_CHARS = 2000
MAX_CONTEXT_CHARS = 2500

# Set once per chat turn; read by the AI-answer writers (chat_ai, education).
conversation_context: ContextVar[str] = ContextVar("conversation_context", default="")


def _enabled() -> bool:
    settings = get_settings()
    return bool(settings.CHAT_MEMORY_ENABLED and settings.GOOGLE_API_KEY)


_background: set[asyncio.Task[None]] = set()


def remember_in_background(session_id: str, role: str, text: str) -> None:
    """Store a message without making the chat reply wait for the embedding call."""
    task = asyncio.get_running_loop().create_task(remember(session_id, role, text))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def remember(session_id: str, role: str, text: str) -> None:
    text = text.strip()[:MAX_STORED_CHARS]
    if not text or not _enabled():
        return
    try:
        from investment_agent.db.models.chat import ChatMemory
        from investment_agent.db.session import async_session_factory
        from investment_agent.llm.embeddings import embed_text

        async def _store() -> None:
            vector = await embed_text(text)
            async with async_session_factory() as session:
                session.add(ChatMemory(session_id=session_id, role=role, text=text, embedding=vector))
                await session.commit()

        await asyncio.wait_for(_store(), MEMORY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Chat memory write skipped: %s", exc)


async def recall(session_id: str, query: str, limit: int = RECALL_LIMIT) -> list[dict[str, str]]:
    """Stored messages from this session closest in meaning to `query`, best first."""
    if not query.strip() or not _enabled():
        return []
    try:
        from investment_agent.db.models.chat import ChatMemory
        from investment_agent.db.session import async_session_factory
        from investment_agent.llm.embeddings import embed_text

        async def _search() -> list[dict[str, str]]:
            vector = await embed_text(query, query=True)
            stmt = (
                select(ChatMemory.role, ChatMemory.text)
                .where(ChatMemory.session_id == session_id)
                .order_by(ChatMemory.embedding.cosine_distance(vector))
                .limit(limit)
            )
            async with async_session_factory() as session:
                rows = (await session.execute(stmt)).all()
            return [{"role": role, "text": text} for role, text in rows]

        return await asyncio.wait_for(_search(), MEMORY_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("Chat memory recall skipped: %s", exc)
        return []


def format_context(recent: list[dict[str, Any]], recalled: list[dict[str, str]]) -> str:
    """Prompt text: relevant older messages first, then the latest turns, capped in size."""
    recent_texts = {turn["text"] for turn in recent}
    older = [m for m in recalled if m["text"] not in recent_texts]
    lines: list[str] = []
    if older:
        lines.append("Earlier in this conversation (related to the new message):")
        lines += [f"- {m['role']}: {m['text']}" for m in older]
    if recent:
        lines.append("Latest messages:")
        lines += [f"- {t['role']}: {t['text']}" for t in recent]
    return "\n".join(lines)[-MAX_CONTEXT_CHARS:]


async def build_context(session_id: str, state: dict[str, Any], message: str) -> str:
    return format_context(state.get("history", []), await recall(session_id, message))
