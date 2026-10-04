import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_status_page(async_client: AsyncClient):
    response = await async_client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    assert "Backend is running" in body
    assert "PostgreSQL" in body
    assert "Redis" in body


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"healthy", "degraded"}
    assert "dependencies" in data
    assert "postgres" in data["dependencies"]
    assert "indstocks" in data["dependencies"]
    assert "routing_tiers" in data
    assert "primary" in data["routing_tiers"]
    assert "cheap" in data["routing_tiers"]
    assert "reasoning" in data["routing_tiers"]


@pytest.mark.asyncio
async def test_research_run_endpoint(async_client: AsyncClient):
    payload = {
        "user_id": "api_test_user",
        "monthly_budget": 20000.0,
    }
    response = await async_client.post("/research/run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["VERIFIED", "INSUFFICIENT_EVIDENCE"]
    assert data["decision"] in ["OPPORTUNITY", "NO_ACTION"]
    assert "recommendation" in data


@pytest.mark.asyncio
async def test_research_asset_status_endpoint(async_client: AsyncClient):
    response = await async_client.get("/research/TCS.NS")
    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"] == "TCS"
    assert data["market"] == "NSE"
    assert data["status"] == "DATA_UNAVAILABLE"
