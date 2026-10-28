"""Live progress for long answers, so the UI can show what the agent is doing (like ChatGPT's
"Searching the web..." steps).

The streaming endpoints install a sink for the duration of one request; any code running inside
it calls `emit`. With no sink installed (plain JSON endpoints, tests) `emit` does nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

Sink = Callable[[dict[str, Any]], None]

_sink: ContextVar[Sink | None] = ContextVar("progress_sink", default=None)


def set_sink(sink: Sink | None) -> Any:
    return _sink.set(sink)


def emit(step_id: str, label: str, detail: str | None = None, *, done: bool = False) -> None:
    """Report a step. Calling again with the same id and done=True marks it finished."""
    sink = _sink.get()
    if sink is not None:
        sink(
            {
                "type": "step",
                "id": step_id,
                "label": label,
                "detail": detail,
                "status": "done" if done else "running",
            }
        )
