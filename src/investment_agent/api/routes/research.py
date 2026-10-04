import asyncio
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
from investment_agent.research.sip import build_etf_sip

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
    """ETF-mix SIP (unchanged route/shape). Real mutual-fund SIP tools live under
    `/funds/sip/*` (see `api/routes/funds.py`)."""
    return await build_etf_sip(request.monthly_amount, request.horizon_years, request.style)


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


@router.get("/score/{symbol}")
async def research_score(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """F2 deterministic Quality/Valuation/Momentum/Risk score (0-100 each + overall)."""
    from investment_agent.research.stock_score import build_stock_score

    venue = "BSE" if exchange.upper() == "BSE" else "NSE"
    try:
        return await build_stock_score(symbol.strip(), venue)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/compare")
async def research_compare(symbols: str, exchange: str = "NSE") -> dict[str, Any]:
    """F9: side-by-side F2 scores for multiple symbols. `symbols` is comma-separated
    (e.g. `?symbols=TCS,INFY,WIPRO`). Registered before `/{asset_id}` below so this
    literal path isn't swallowed by that catch-all."""
    from investment_agent.research.stock_score import build_stock_score

    venue = "BSE" if exchange.upper() == "BSE" else "NSE"
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not requested:
        raise HTTPException(status_code=400, detail="Provide at least one symbol, e.g. ?symbols=TCS,INFY")
    if len(requested) > 5:
        raise HTTPException(status_code=400, detail="Compare at most 5 symbols at a time.")

    async def _score_or_error(symbol: str) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(build_stock_score(symbol, venue), timeout=20.0)
        except Exception as exc:
            return {"symbol": symbol, "status": "DATA_UNAVAILABLE", "message": str(exc)}

    results = await asyncio.gather(*(_score_or_error(symbol) for symbol in requested))
    return {"symbols": requested, "items": results}


@router.get("/predictions")
async def list_predictions(limit: int = 50) -> dict[str, Any]:
    """List logged predictions (Gap 7), newest first — mainly for verifying outcome
    scoring is actually running, not a polished UI feature on its own."""
    from investment_agent.db.models.prediction import PredictionLog

    async with async_session_factory() as session:
        rows = (
            await session.scalars(
                select(PredictionLog).order_by(PredictionLog.created_at.desc()).limit(min(limit, 200))
            )
        ).all()
    return {
        "items": [
            {
                "prediction_id": row.prediction_id,
                "asset_id": row.asset_id,
                "status": row.status,
                "confidence": row.confidence,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "evaluation_due_date": row.evaluation_due_date.isoformat() if row.evaluation_due_date else None,
                "outcome_status": row.outcome_status,
                "evaluation_notes": row.evaluation_notes,
                "entry_price": (row.expected_conditions or {}).get("entry_price"),
            }
            for row in rows
        ]
    }


@router.post("/predictions/evaluate")
async def evaluate_predictions() -> dict[str, Any]:
    """Trigger Gap 7's outcome scoring: classify every prediction past its
    `evaluation_due_date` with no `outcome_status` yet, against its current price."""
    from investment_agent.research.outcome_scoring import evaluate_due_predictions

    try:
        return await evaluate_due_predictions()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Could not evaluate predictions: {exc}") from exc


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
