import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import text

from investment_agent.api.dependencies import get_app_settings
from investment_agent.config.settings import Settings
from investment_agent.db.session import async_engine

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    app_name: str
    environment: str
    primary_llm_provider: str
    primary_llm_model: str
    routing_tiers: dict[str, str]
    dependencies: dict[str, str]
    timestamp: datetime


async def _probe_postgres() -> str:
    try:
        async with asyncio.timeout(20):
            async with async_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unavailable"


async def _probe_redis() -> str:
    try:
        from redis.asyncio import Redis

        settings = get_app_settings()
        client = Redis.from_url(
            settings.resolved_redis_url,
            socket_connect_timeout=20,
            socket_timeout=20,
        )
        try:
            async with asyncio.timeout(20):
                await client.ping()
        finally:
            await client.aclose()
        return "ok"
    except Exception:
        return "unavailable"


async def _dependency_status(settings: Settings) -> tuple[str, dict[str, str]]:
    dependencies = {
        "postgres": await _probe_postgres(),
        "redis": await _probe_redis(),
        "indstocks": "configured" if settings.indstocks_configured else "missing",
    }
    status = (
        "healthy"
        if dependencies["postgres"] == "ok" and dependencies["redis"] == "ok"
        else "degraded"
    )
    return status, dependencies


def _status_page(status: str, dependencies: dict[str, str]) -> str:
    def row(label: str, value: str) -> str:
        up = value == "ok"
        tone = "up" if up else "down"
        text = "up" if up else "down"
        return (
            f'<li><span>{label}</span><strong class="{tone}">{text}</strong></li>'
        )

    headline = "Backend is running"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{headline}</title>
  <style>
    body {{ font-family: Segoe UI, sans-serif; margin: 0; background: #0f1419; color: #e7ecf1; }}
    main {{ max-width: 32rem; margin: 4rem auto; padding: 0 1.25rem; }}
    h1 {{ font-size: 1.75rem; margin-bottom: 0.25rem; }}
    p {{ color: #9aa7b4; }}
    ul {{ list-style: none; padding: 0; margin: 1.5rem 0 0; }}
    li {{ display: flex; justify-content: space-between; padding: 0.85rem 0; border-top: 1px solid #243040; }}
    .up {{ color: #3dd68c; }}
    .down {{ color: #ff6b6b; }}
  </style>
</head>
<body>
  <main>
    <h1>{headline}</h1>
    <p>Overall status: {status}</p>
    <ul>
      <li><span>Backend</span><strong class="up">up</strong></li>
      {row("PostgreSQL", dependencies["postgres"])}
      {row("Redis", dependencies["redis"])}
    </ul>
  </main>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def status_page(settings: Settings = Depends(get_app_settings)) -> HTMLResponse:
    """Show that the API process is up and whether Postgres and Redis answer."""
    status, dependencies = await _dependency_status(settings)
    return HTMLResponse(_status_page(status, dependencies))


@router.get("/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    """Return process health plus Postgres, Redis, and INDstocks configuration."""
    status, dependencies = await _dependency_status(settings)
    return HealthResponse(
        status=status,
        app_name=settings.APP_NAME,
        environment=settings.APP_ENV,
        primary_llm_provider=settings.PRIMARY_LLM_PROVIDER,
        primary_llm_model=settings.PRIMARY_LLM_MODEL,
        dependencies=dependencies,
        routing_tiers={
            "primary": f"{settings.PRIMARY_LLM_PROVIDER}:{settings.PRIMARY_LLM_MODEL}",
            "cheap": f"{settings.CHEAP_LLM_PROVIDER}:{settings.CHEAP_LLM_MODEL}",
            "reasoning": f"{settings.REASONING_LLM_PROVIDER}:{settings.REASONING_LLM_MODEL}",
            "local": f"{settings.LOCAL_LLM_PROVIDER}:{settings.LOCAL_LLM_MODEL}",
            "fallback": f"{settings.FALLBACK_LLM_PROVIDER}:{settings.FALLBACK_LLM_MODEL}",
        },
        timestamp=datetime.now(UTC),
    )
