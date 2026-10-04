from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field
from sqlalchemy import select

from investment_agent.api.dependencies import get_investment_graph
from investment_agent.db.models.market import FundamentalSnapshot
from investment_agent.db.session import async_session_factory
from investment_agent.graph.state import InvestmentGraphState
from investment_agent.research.chat import chat_turn
from investment_agent.research.guidance import guide_symbol
from investment_agent.research.sip import build_sip

router = APIRouter(prefix="/research", tags=["Research"])


class GuidanceRequest(BaseModel):
    symbol: str = Field(min_length=1)
    exchange: str = "NSE"
    horizon_years: int = Field(default=5, ge=0, le=30)
    horizon_months: int = Field(default=0, ge=0, le=11)
    monthly_budget: float = Field(default=25000.0, gt=0)


@router.post("/guidance")
async def research_guidance(request: GuidanceRequest) -> dict[str, Any]:
    """Score one live quote for the user's holding span."""
    if request.horizon_years == 0 and request.horizon_months == 0:
        raise HTTPException(status_code=400, detail="Enter a holding span in years, months, or both.")
    venue = "BSE" if request.exchange.upper() == "BSE" else "NSE"
    try:
        return await guide_symbol(
            request.symbol.strip(),
            request.horizon_years,
            request.monthly_budget,
            venue,
            request.horizon_months,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1)


class SipRequest(BaseModel):
    monthly_amount: float = Field(gt=0)
    horizon_years: int = Field(ge=1, le=30)
    style: str = "flexi"


@router.post("/chat")
async def research_chat(request: ChatRequest) -> dict[str, Any]:
    """Ask follow-up questions until intent, horizon, amount, and style are known."""
    return await chat_turn(request.session_id, request.message)


@router.post("/sip")
async def research_sip(request: SipRequest) -> dict[str, Any]:
    return await build_sip(request.monthly_amount, request.horizon_years, request.style)


class RunResearchRequest(BaseModel):
    user_id: str = Field(default="user_default")
    monthly_budget: float = Field(default=25000.0, gt=0)
    candidates: list[dict[str, Any]] | None = None


class RunResearchResponse(BaseModel):
    status: str
    decision: str
    confidence: float
    evidence_quality: str
    recommendation: dict[str, Any]
    bull_case: dict[str, Any] | None = None
    bear_case: dict[str, Any] | None = None
    warnings: list[str]
    errors: list[str]


@router.post("/run", response_model=RunResearchResponse)
async def run_research_pipeline(
    request: RunResearchRequest,
    graph: CompiledStateGraph = Depends(get_investment_graph),
) -> RunResearchResponse:
    """Trigger the multi-agent investment research and guidance graph."""
    initial_state: InvestmentGraphState = {
        "user_id": request.user_id,
        "monthly_budget": request.monthly_budget,
    }
    if request.candidates is not None:
        initial_state["candidates"] = request.candidates

    try:
        final_state: dict[str, Any] = await graph.ainvoke(initial_state)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Graph execution failed: {e!s}",
        )

    rec = final_state.get("recommendation", {})
    selected_symbol = rec.get("asset_id")
    return RunResearchResponse(
        status=final_state.get("execution_status", "UNKNOWN"),
        decision=rec.get("decision", "NO_ACTION"),
        confidence=final_state.get("confidence", 0.0),
        evidence_quality=final_state.get("evidence_quality", "UNKNOWN"),
        recommendation=rec,
        bull_case=final_state.get("bull_case", {}).get(selected_symbol) if selected_symbol else None,
        bear_case=final_state.get("bear_case", {}).get(selected_symbol) if selected_symbol else None,
        warnings=final_state.get("warnings", []),
        errors=final_state.get("errors", []),
    )


@router.get("/{asset_id}")
async def get_asset_research_status(asset_id: str) -> dict[str, Any]:
    """Return the latest stored fundamental snapshot for a symbol."""
    symbol = asset_id.upper().removesuffix(".NS").removesuffix(".BO")
    snapshot = None
    try:
        async with async_session_factory() as session:
            snapshot = await session.scalar(
                select(FundamentalSnapshot)
                .where(FundamentalSnapshot.symbol == symbol)
                .order_by(FundamentalSnapshot.data_date.desc())
            )
    except Exception:
        snapshot = None
    if snapshot is None:
        return {
            "asset_id": symbol,
            "status": "DATA_UNAVAILABLE",
            "market": "NSE",
            "message": "No sourced fundamental snapshot is stored for this symbol.",
        }
    return {
        "asset_id": symbol,
        "status": "SNAPSHOT",
        "market": "NSE",
        "source_name": snapshot.source_name,
        "source_url": snapshot.source_url,
        "data_date": snapshot.data_date.isoformat(),
        "roe_pct": snapshot.roe_pct,
        "eps": snapshot.eps,
    }
