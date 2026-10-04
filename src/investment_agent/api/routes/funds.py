"""Funds routes: scheme search/detail (B3), SIP backtest and projection (B3), and the
single-fund / suggest-a-mix SIP builders that wrap `research/sip.py` (B4).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from investment_agent.db.models.market import MutualFundScheme
from investment_agent.db.session import async_session_factory
from investment_agent.market.mfapi import (
    CATEGORY_ORDER,
    fetch_nav_history,
    list_schemes,
    scheme_category_label,
)
from investment_agent.market.mfapi import search as mfapi_search
from investment_agent.portfolio.calculations import (
    calculate_annualized_volatility_pct,
    calculate_max_drawdown,
)
from investment_agent.portfolio.fund_metrics import (
    project_sip,
    rolling_return_extremes,
    sip_backtest,
    trailing_cagr,
)
from investment_agent.research.sip import build_fund_sip, suggest_mix

router = APIRouter(prefix="/funds", tags=["Funds"])


def _scheme_summary(row: MutualFundScheme) -> dict[str, Any]:
    return {
        "scheme_code": row.scheme_code,
        "name": row.name,
        "fund_house": row.fund_house,
        "category": row.category,
        "sebi_group": row.sebi_group,
        "plan": row.plan,
        "option": row.option,
        "latest_nav": row.latest_nav,
        "nav_date": row.nav_date.isoformat() if row.nav_date else None,
    }


@router.get("/search")
async def funds_search(
    q: str = Query(..., min_length=1),
    category: str | None = None,
    plan: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    """Search the AMFI scheme master we've synced (B1), which carries plan/option/SEBI
    group classification that mfapi.in's own search doesn't. Falls back to mfapi.in's
    search (unclassified) if the local master has no match, e.g. before the first
    `POST /market/refresh` has populated it."""
    like = f"%{q.strip()}%"
    async with async_session_factory() as session:
        stmt = select(MutualFundScheme).where(
            or_(MutualFundScheme.name.ilike(like), MutualFundScheme.scheme_code == q.strip())
        )
        if category:
            stmt = stmt.where(MutualFundScheme.sebi_group == category.strip().lower())
        if plan:
            stmt = stmt.where(MutualFundScheme.plan == plan.strip().lower())
        stmt = stmt.limit(limit)
        try:
            rows = (await session.scalars(stmt)).all()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Fund search database unavailable: {exc}") from exc

    if rows:
        return {"query": q, "source": "database", "items": [_scheme_summary(row) for row in rows]}

    fallback = await mfapi_search(q)
    return {"query": q, "source": "mfapi.in", "items": fallback[:limit]}


def _labelled_scheme(scheme: dict[str, Any]) -> dict[str, Any]:
    header = scheme.get("amfi_category") or None
    return {**scheme, "category": scheme_category_label(scheme["scheme_name"], header)}


@router.get("/catalogue")
async def funds_catalogue(
    q: str = "",
    category: str = "",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=40, ge=1, le=100),
) -> dict[str, Any]:
    """Live scheme list from https://api.mfapi.in/mf, grouped into fund houses."""
    schemes = [_labelled_scheme(scheme) for scheme in await list_schemes()]
    if not schemes:
        raise HTTPException(status_code=502, detail="The mutual fund catalogue is unavailable right now.")
    houses: dict[str, int] = {}
    for scheme in schemes:
        house = scheme["fund_house"]
        houses[house] = houses.get(house, 0) + 1
    query = q.strip().lower()
    matched = schemes
    if query:
        matched = [
            scheme
            for scheme in schemes
            if query in scheme["scheme_name"].lower() or query in scheme["fund_house"].lower() or query == scheme["scheme_code"]
        ]
    counts: dict[str, int] = {}
    for scheme in matched:
        label = str(scheme["category"])
        counts[label] = counts.get(label, 0) + 1
    selected = category.strip().lower()
    if selected:
        matched = [scheme for scheme in matched if str(scheme["category"]).lower() == selected]
    categories = [{"name": name, "count": counts[name]} for name in CATEGORY_ORDER if counts.get(name)]
    categories.extend(
        {"name": name, "count": count} for name, count in counts.items() if name not in CATEGORY_ORDER
    )
    page = matched[offset : offset + limit]
    next_offset = offset + limit if offset + limit < len(matched) else None
    return {
        "source": "https://api.mfapi.in/mf",
        "scheme_count": len(schemes),
        "fund_house_count": len(houses),
        "fund_houses": [
            {"name": name, "scheme_count": count}
            for name, count in sorted(houses.items(), key=lambda item: item[0].lower())
        ],
        "categories": categories,
        "items": page,
        "total": len(matched),
        "offset": offset,
        "next_offset": next_offset,
    }


@router.get("/{scheme_code}")
async def fund_detail(scheme_code: str) -> dict[str, Any]:
    """Scheme facts (from our synced master, if present) plus trailing returns and risk
    metrics computed from mfapi.in's full NAV history."""
    scheme_code = scheme_code.strip()
    async with async_session_factory() as session:
        try:
            scheme = await session.scalar(select(MutualFundScheme).where(MutualFundScheme.scheme_code == scheme_code))
        except Exception:
            scheme = None

    history = await fetch_nav_history(scheme_code)
    if history is None or not history.get("nav_history"):
        return {
            "scheme_code": scheme_code,
            "status": "DATA_UNAVAILABLE",
            "message": "NAV history could not be fetched for this scheme.",
            "facts": _scheme_summary(scheme) if scheme else None,
        }

    nav_history = history["nav_history"]
    closes = [row["nav"] for row in reversed(nav_history)]  # chronological order for drawdown/volatility

    facts = (
        _scheme_summary(scheme)
        if scheme
        else {
            "scheme_code": history["scheme_code"],
            "name": history.get("scheme_name"),
            "fund_house": history.get("fund_house"),
            "category": history.get("scheme_category"),
            "sebi_group": None,
            "plan": None,
            "option": None,
            "latest_nav": nav_history[0]["nav"],
            "nav_date": nav_history[0]["date"],
        }
    )

    return {
        "scheme_code": history["scheme_code"],
        "status": "OK",
        "facts": facts,
        "trailing_returns_pct": {
            "1y": trailing_cagr(nav_history, 1),
            "3y": trailing_cagr(nav_history, 3),
            "5y": trailing_cagr(nav_history, 5),
            "10y": trailing_cagr(nav_history, 10),
        },
        "risk": {
            "max_drawdown_pct": calculate_max_drawdown(closes),
            "annualized_volatility_pct": calculate_annualized_volatility_pct(closes),
        },
        "rolling_3y_return_pct": rolling_return_extremes(nav_history, window_years=3.0),
        "data_as_of": history.get("data_date"),
        "source_name": history.get("source_name"),
        "source_url": history.get("source_url"),
    }


class SipBacktestRequest(BaseModel):
    scheme_code: str = Field(min_length=1)
    monthly: float = Field(ge=100, le=1_000_000)
    start_date: date | None = None
    step_up_pct: float = Field(default=0.0, ge=0, le=25)


@router.post("/sip/backtest")
async def funds_sip_backtest(request: SipBacktestRequest) -> dict[str, Any]:
    history = await fetch_nav_history(request.scheme_code.strip())
    if history is None or not history.get("nav_history"):
        raise HTTPException(status_code=502, detail="NAV history unavailable for this scheme.")

    nav_history = history["nav_history"]
    start = request.start_date
    if start is None:
        # No explicit start date: backtest as far back as the data supports, capped at 5
        # years, so the default call is both meaningful and fast.
        latest_date = date.fromisoformat(nav_history[0]["date"])
        earliest_date = date.fromisoformat(nav_history[-1]["date"])
        start = max(earliest_date, latest_date - timedelta(days=5 * 365))

    result = sip_backtest(nav_history, request.monthly, start, request.step_up_pct)
    return {"scheme_code": history["scheme_code"], "scheme_name": history.get("scheme_name"), **result}


class SipProjectRequest(BaseModel):
    monthly: float = Field(ge=100, le=1_000_000)
    years: int = Field(ge=1, le=40)
    step_up_pct: float = Field(default=0.0, ge=0, le=25)
    inflation_pct: float = Field(default=0.0, ge=0, le=25)
    annual_return_pct: float = Field(
        default=12.0,
        ge=0,
        le=30,
        description="Assumed flat annual return. Not part of the original spec's field list "
        "for this route, but project_sip() requires one; defaults to a commonly-cited "
        "long-run equity-fund assumption.",
    )


@router.post("/sip/project")
async def funds_sip_project(request: SipProjectRequest) -> dict[str, Any]:
    result = project_sip(
        request.monthly,
        request.years,
        request.annual_return_pct,
        request.step_up_pct,
        request.inflation_pct,
    )
    return {"assumption_note": "This is an assumption based on a chosen flat rate, not a forecast.", **result}


class FundSipRequest(BaseModel):
    scheme_code: str = Field(min_length=1)
    monthly: float = Field(ge=100, le=1_000_000)
    years: int = Field(ge=1, le=40)
    step_up_pct: float = Field(default=0.0, ge=0, le=25)
    inflation_pct: float = Field(default=0.0, ge=0, le=25)


@router.post("/sip/fund")
async def funds_sip_fund(request: FundSipRequest) -> dict[str, Any]:
    """Single real mutual fund: backtest + forward projection + tax estimate + plain-
    language explanation, assembled by `research.sip.build_fund_sip`."""
    return await build_fund_sip(
        request.scheme_code, request.monthly, request.years, request.step_up_pct, request.inflation_pct
    )


class SuggestMixRequest(BaseModel):
    monthly: float = Field(ge=100, le=1_000_000)
    horizon_years: int = Field(ge=1, le=40)
    risk_profile: str = Field(default="moderate")
    return_span: str = Field(default="quarter")
    span_years: int = Field(default=0, ge=0, le=30)
    span_months: int = Field(default=0, ge=0, le=11)


@router.post("/sip/suggest")
async def funds_sip_suggest(request: SuggestMixRequest) -> dict[str, Any]:
    """Deterministic category-weighted mutual fund mix for a horizon/risk profile,
    assembled by `research.sip.suggest_mix`."""
    if request.span_years == 0 and request.span_months == 0 and request.return_span == "custom":
        raise HTTPException(status_code=422, detail="Enter a return span of at least one month.")
    return await suggest_mix(
        request.monthly,
        request.horizon_years,
        request.risk_profile,
        request.return_span,
        request.span_years,
        request.span_months,
    )
