"""Gemini embeddings (free tier) for chat memory. Reads GOOGLE_API_KEY."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from investment_agent.config.settings import get_settings


@lru_cache
def _embedder() -> Any:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    settings = get_settings()
    return GoogleGenerativeAIEmbeddings(
        model=settings.EMBEDDING_MODEL,
        google_api_key=settings.GOOGLE_API_KEY,
        output_dimensionality=settings.EMBEDDING_DIMENSIONS,
    )


async def embed_text(text: str, *, query: bool = False) -> list[float]:
    """One embedding vector. `query=True` for a search query, False for a stored message."""
    task = "RETRIEVAL_QUERY" if query else "RETRIEVAL_DOCUMENT"
    return list(await _embedder().aembed_query(text, task_type=task))
