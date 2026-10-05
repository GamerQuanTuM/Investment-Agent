"""Deterministic "N stocks for ₹X" picker. Python decides every symbol, share count and rupee
amount here; no model is consulted and none may change the result.

Pipeline (all pure functions except `load_pick_universe`):

1. `load_pick_universe` joins the stored stock master (fundamental snapshots), the latest
   price bars and the F2 factor scores (`portfolio/scoring.py`) into `Candidate`s.
2. `filter_candidates` drops anything we cannot responsibly rank: no price, stale price,
   missing fundamentals, penny/illiquid names (market-cap / volume floors from settings).
3. `build_stock_plan` ranks by overall score, enforces diversification (max 2 per sector,
   market-cap mix by risk profile, max 30% of the budget per sector), splits the budget in
   proportion to score within per-stock weight bounds, then converts to WHOLE shares. A name
   priced above its allocation is dropped and the next candidate takes its place.

"Future potential" is never predicted. Each row only carries measurable, backward-looking
signals (3y revenue/profit CAGR, ROE/ROCE, P/E vs. peers and its own range, sector 12-month
move from our own price data), labelled as past growth and quality, not a forecast.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from investment_agent.config.settings import get_settings
from investment_agent.db.models.market import DailyBar, FundamentalSnapshot
from investment_agent.db.session import async_session_factory
from investment_agent.portfolio.calculations import (
    calculate_annualized_volatility_pct,
    calculate_distance_from_high_pct,
    calculate_max_drawdown,
    calculate_pb_ratio,
    calculate_return_pct,
)
from investment_agent.portfolio.scoring import build_score_card

logger = logging.getLogger(__name__)

MIN_STOCKS = 3
MAX_STOCKS = 15
DEFAULT_STOCKS = 10
MAX_PER_SECTOR = 2
SECTOR_BUDGET_CAP = 0.30
MIN_WEIGHT_OF_EQUAL = 0.5  # a position is never below half of an equal split
SMALL_POSITION_INR = 5000.0  # average position below this triggers the reality check
LARGE_CAP_MIN_CR = 50_000.0
MID_CAP_MIN_CR = 15_000.0
UNIVERSE_TTL = timedelta(minutes=5)

# Share of the picks (rounded down) allowed per band beyond large caps, by risk profile.
BAND_LIMITS: dict[str, dict[str, float]] = {
    "conservative": {"mid": 0.2, "small": 0.0},
    "moderate": {"mid": 0.4, "small": 0.1},
    "aggressive": {"mid": 0.5, "small": 0.3},
}

DISCLAIMER = (
    "Educational guidance, not SEBI-registered investment advice. It does not place orders, "
    "and past growth and quality are not a forecast of future returns."
)
GROWTH_NOTE = (
    "Growth, quality and valuation figures describe the past, not a forecast. "
    "Nothing here is a target price or an expected return."
)

_FACTOR_LABELS = {
    "quality": "Business quality",
    "valuation": "Valuation",
    "momentum": "Recent price trend",
    "risk": "Steadiness",
}
_FACTOR_ORDER = ("quality", "valuation", "momentum", "risk")


@dataclass
class Candidate:
    symbol: str
    name: str
    sector: str
    price: float | None
    price_time: datetime | None
    market_cap_cr: float | None
    avg_volume: float | None
    data_date: datetime | None
    factors: dict[str, float | None] = field(default_factory=dict)  # quality/valuation/momentum/risk
    overall: float | None = None
    signals: dict[str, float | None] = field(default_factory=dict)
    source_name: str = ""
    source_url: str = ""

    @property
    def band(self) -> str:
        return market_cap_band(self.market_cap_cr)


def market_cap_band(market_cap_cr: float | None) -> str:
    if market_cap_cr is None:
        return "small"
    if market_cap_cr >= LARGE_CAP_MIN_CR:
        return "large"
    if market_cap_cr >= MID_CAP_MIN_CR:
        return "mid"
    return "small"


def clamp_count(count: int | None) -> int:
    return max(MIN_STOCKS, min(MAX_STOCKS, count if count else DEFAULT_STOCKS))


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# ----------------------------------------------------------------------- filtering


def filter_candidates(
    candidates: list[Candidate],
    *,
    now: datetime,
    max_age_hours: float,
    min_market_cap_cr: float,
    min_avg_volume: float,
) -> tuple[list[Candidate], dict[str, int]]:
    """Keep only names we can rank responsibly; count why the rest were dropped."""
    kept: list[Candidate] = []
    excluded: dict[str, int] = defaultdict(int)
    max_age = timedelta(hours=max_age_hours)
    for cand in candidates:
        price_time = _aware(cand.price_time)
        if cand.price is None or cand.price <= 0:
            excluded["missing_price"] += 1
        elif price_time is None or now - price_time > max_age:
            excluded["stale_price"] += 1
        elif cand.factors.get("quality") is None or cand.overall is None:
            excluded["missing_fundamentals"] += 1
        elif cand.market_cap_cr is None or cand.market_cap_cr < min_market_cap_cr:
            excluded["below_market_cap_floor"] += 1
        elif cand.avg_volume is not None and cand.avg_volume > 0 and cand.avg_volume < min_avg_volume:
            excluded["illiquid"] += 1
        else:
            kept.append(cand)
    return kept, dict(excluded)


# ------------------------------------------------------------------------ selection


def _effective_risk(risk_profile: str | None, experience_level: str | None) -> str:
    """A beginner who did not choose a risk level starts from the large-cap-heavy mix."""
    if risk_profile in BAND_LIMITS:
        if experience_level == "beginner" and risk_profile == "aggressive":
            return "moderate"
        return risk_profile
    return "conservative" if experience_level == "beginner" else "moderate"


def _select(
    pool: list[Candidate], count: int, risk: str, *, enforce_bands: bool
) -> list[Candidate]:
    limits = BAND_LIMITS[risk]
    band_max = {band: math.floor(limits[band] * count + 1e-9) for band in ("mid", "small")}
    chosen: list[Candidate] = []
    per_sector: dict[str, int] = defaultdict(int)
    per_band: dict[str, int] = defaultdict(int)
    for cand in pool:
        if len(chosen) >= count:
            break
        if per_sector[cand.sector] >= MAX_PER_SECTOR:
            continue
        if enforce_bands and cand.band != "large" and per_band[cand.band] >= band_max[cand.band]:
            continue
        chosen.append(cand)
        per_sector[cand.sector] += 1
        per_band[cand.band] += 1
    return chosen


def select_diversified(pool: list[Candidate], count: int, risk: str) -> tuple[list[Candidate], bool]:
    """Top-scored names under the sector cap and the market-cap mix. If the mix leaves the
    list short, the band limits (never the sector cap) are relaxed; the bool says so."""
    chosen = _select(pool, count, risk, enforce_bands=True)
    if len(chosen) >= count:
        return chosen, False
    relaxed = _select(pool, count, risk, enforce_bands=False)
    return (relaxed, True) if len(relaxed) > len(chosen) else (chosen, False)


# ------------------------------------------------------------------------ allocation


def allocate_weights(chosen: list[Candidate]) -> dict[str, float]:
    """Budget weights proportional to overall score, within per-stock bounds and the sector
    cap. Deterministic iterative projection; the result never sums above 1."""
    n = len(chosen)
    if n == 0:
        return {}
    w_min = MIN_WEIGHT_OF_EQUAL / n
    w_max = min(1.0, max(0.20, 2.0 / n))
    sectors = {c.sector for c in chosen}
    sector_cap = max(SECTOR_BUDGET_CAP, 1.0 / len(sectors) + 1e-9)
    scores = {c.symbol: max(float(c.overall or 0.0), 1.0) for c in chosen}
    sector_of = {c.symbol: c.sector for c in chosen}
    total_score = sum(scores.values())
    weights = {s: v / total_score for s, v in scores.items()}

    for _ in range(200):
        weights = {symbol: min(max(weight, w_min), w_max) for symbol, weight in weights.items()}
        by_sector: dict[str, float] = defaultdict(float)
        for symbol, weight in weights.items():
            by_sector[sector_of[symbol]] += weight
        for sector, total in by_sector.items():
            if total > sector_cap + 1e-12:
                factor = sector_cap / total
                for symbol in weights:
                    if sector_of[symbol] == sector:
                        weights[symbol] *= factor
        residual = 1.0 - sum(weights.values())
        if abs(residual) < 1e-10:
            break
        by_sector = defaultdict(float)
        for symbol, weight in weights.items():
            by_sector[sector_of[symbol]] += weight
        if residual > 0:
            room = {
                s: scores[s]
                for s, w in weights.items()
                if w < w_max - 1e-12 and by_sector[sector_of[s]] < sector_cap - 1e-12
            }
        else:
            room = {s: scores[s] for s, w in weights.items() if w > w_min + 1e-12}
        if not room:
            break
        room_total = sum(room.values())
        for symbol, score in room.items():
            weights[symbol] += residual * score / room_total
    total = sum(weights.values())
    if total > 1.0:
        weights = {s: w / total for s, w in weights.items()}
    return weights


def _signal_text(cand: Candidate, factor: str) -> str:
    sig = cand.signals
    score = cand.factors.get(factor)
    label = _FACTOR_LABELS[factor]
    roe, profit, revenue = sig.get("roe_pct"), sig.get("profit_cagr_3y_pct"), sig.get("revenue_cagr_3y_pct")
    pe, sector_pct = sig.get("pe_ratio"), sig.get("pe_percentile_in_sector")
    move, vol = sig.get("return_12m_pct"), sig.get("volatility_pct")
    detail: list[str] = []
    if factor == "quality":
        if roe is not None:
            detail.append(f"ROE {roe:.1f}%")
        if profit is not None:
            detail.append(f"3-year profit growth {profit:.1f}% a year")
        elif revenue is not None:
            detail.append(f"3-year revenue growth {revenue:.1f}% a year")
    elif factor == "valuation":
        if pe is not None:
            detail.append(f"P/E {pe:.1f}")
        if sector_pct is not None:
            detail.append(f"cheaper than {100 - sector_pct:.0f}% of sector peers")
    elif factor == "momentum":
        if move is not None:
            detail.append(f"12-month price change {move:.1f}%")
    elif factor == "risk" and vol is not None:
        detail.append(f"yearly price swing {vol:.1f}%")
    suffix = f" ({', '.join(detail)})" if detail else ""
    return f"{label} {score or 0:.0f}/100{suffix}"


def top_factors(cand: Candidate, how_many: int = 2) -> list[str]:
    ranked = sorted(
        (f for f in _FACTOR_ORDER if cand.factors.get(f) is not None),
        key=lambda f: -(cand.factors[f] or 0.0),
    )
    return [_signal_text(cand, f) for f in ranked[:how_many]]


def reality_check(budget: float, rows: list[dict[str, Any]], leftover: float) -> str | None:
    """Honest cost-of-small-positions note; always present when positions are small."""
    if not rows:
        return None
    average = (budget - leftover) / len(rows) if len(rows) else budget
    if average >= SMALL_POSITION_INR:
        return None
    return (
        f"Reality check: ₹{budget:,.0f} split across {len(rows)} stocks is only about "
        f"₹{average:,.0f} per stock. Shares are bought whole, so ₹{leftover:,.0f} stays unused after "
        "rounding. Brokerage and demat (DP) charges are charged per trade, so they weigh much "
        "more on small positions. For a small amount, one diversified index fund or ETF "
        "SIP often does the same spreading job at lower cost."
    )


def build_stock_plan(
    candidates: list[Candidate],
    *,
    budget: float,
    count: int | None = None,
    risk_profile: str | None = None,
    experience_level: str | None = None,
    sectors_wanted: list[str] | None = None,
    horizon_years: int | None = None,
) -> dict[str, Any]:
    """Select and size a diversified list from already-filtered `candidates`."""
    target = clamp_count(count)
    risk = _effective_risk(risk_profile, experience_level)
    caveats: list[str] = []
    ranked = sorted(candidates, key=lambda c: (-(c.overall or 0.0), c.symbol))

    pool = ranked
    if sectors_wanted:
        wanted = [s.lower() for s in sectors_wanted]
        preferred = [c for c in ranked if any(w in c.sector.lower() for w in wanted)]
        if len(preferred) >= MIN_STOCKS:
            pool = preferred
            if len({c.sector for c in preferred}) < 2:
                caveats.append(
                    "Everything you asked for sits in one sector, so this list is less diversified than usual."
                )
        else:
            caveats.append(
                "I couldn't find enough stocks in the sectors you asked for with fresh data, "
                "so I picked across all sectors instead."
            )

    if not ranked:
        return {
            "status": "DATA_UNAVAILABLE",
            "reason": "no_eligible_stocks",
            "message": "No stock passed the data checks (fresh price, fundamentals, liquidity).",
        }

    dropped: set[str] = set()
    chosen: list[Candidate] = []
    weights: dict[str, float] = {}
    relaxed = False
    for _ in range(len(pool) + 1):
        remaining = [c for c in pool if c.symbol not in dropped]
        chosen, relaxed = select_diversified(remaining, target, risk)
        weights = allocate_weights(chosen)
        too_dear = {c.symbol for c in chosen if c.price and c.price > budget * weights[c.symbol]}
        if not too_dear:
            break
        dropped |= too_dear
    else:
        chosen, weights = [], {}

    if not chosen:
        return {
            "status": "DATA_UNAVAILABLE",
            "reason": "unaffordable",
            "message": (
                f"With ₹{budget:,.0f} I couldn't fit even {MIN_STOCKS} diversified whole shares "
                "from the stocks that passed the data checks. A larger amount, or an index fund "
                "SIP, would work better."
            ),
        }

    rows: list[dict[str, Any]] = []
    for cand in chosen:
        assert cand.price is not None  # guaranteed by filter_candidates
        allocation = budget * weights[cand.symbol]
        shares = math.floor(allocation / cand.price + 1e-9)
        rows.append(
            {
                "symbol": cand.symbol,
                "name": cand.name,
                "sector": cand.sector,
                "market_cap_band": cand.band,
                "price": round(cand.price, 2),
                "shares": shares,
                "amount_inr": round(shares * cand.price, 2),
                "target_weight_pct": round(weights[cand.symbol] * 100, 1),
                "weight_pct": 0.0,
                "score": round(cand.overall or 0.0, 1),
                "why": top_factors(cand),
                "signals": {k: v for k, v in cand.signals.items() if v is not None},
                "data_as_of": (_aware(cand.price_time) or datetime.now(UTC)).date().isoformat(),
            }
        )
    rows = [r for r in rows if r["shares"] >= 1]
    total_invested = round(sum(r["amount_inr"] for r in rows), 2)
    for r in rows:
        r["weight_pct"] = round(r["amount_inr"] / total_invested * 100, 1) if total_invested else 0.0
    leftover = round(budget - total_invested, 2)

    sector_totals: dict[str, float] = defaultdict(float)
    for r in rows:
        sector_totals[r["sector"]] += r["amount_inr"]
    sector_split = [
        {"sector": sector, "pct": round(amount / total_invested * 100, 1)}
        for sector, amount in sorted(sector_totals.items(), key=lambda kv: -kv[1])
    ]

    if len(rows) < target:
        caveats.append(
            f"You asked for {target} stocks but only {len(rows)} fit the data, liquidity, "
            "diversification and whole-share checks at this budget."
        )
    if relaxed:
        caveats.append(
            "There weren't enough large-cap names with fresh data, so the market-cap mix is looser than usual."
        )
    check = reality_check(budget, rows, leftover)
    if check:
        caveats.append(check)

    return {
        "status": "OK",
        "budget": round(budget, 2),
        "requested_count": target,
        "risk_profile": risk,
        "experience_level": experience_level,
        "horizon_years": horizon_years,
        "rows": rows,
        "total_invested": total_invested,
        "leftover": leftover,
        "data_as_of": min(r["data_as_of"] for r in rows) if rows else None,
        "sector_split": sector_split,
        "caveats": caveats,
        "reality_check": check,
        "growth_note": GROWTH_NOTE,
        "disclaimer": DISCLAIMER,
        "dropped_unaffordable": sorted(dropped),
    }


# ---------------------------------------------------------------------------- loader


def score_candidate(
    snapshot: dict[str, Any],
    closes: list[float],
    volumes: list[float],
    price_time: datetime | None,
    sector_pe_values: list[float],
) -> Candidate:
    """Build one `Candidate` from stored rows with the F2 scoring functions (Python only)."""
    price = closes[-1] if closes else None
    eps = snapshot.get("eps")
    pe = round(price / eps, 2) if price and eps and eps > 0 else None
    pe_history = [round(c / eps, 2) for c in closes if c > 0] if eps and eps > 0 else []
    book = snapshot.get("book_value_per_share")
    pb = None
    if price and book and book > 0:
        try:
            pb = calculate_pb_ratio(price, book)
        except ValueError:
            pb = None
    last_year = closes[-252:]
    ret_6m = calculate_return_pct(last_year[-126], last_year[-1]) if len(last_year) >= 126 else None
    ret_12m = calculate_return_pct(last_year[0], last_year[-1]) if len(last_year) >= 200 else None
    distance = calculate_distance_from_high_pct(last_year) if last_year else None
    vol = calculate_annualized_volatility_pct(last_year) if len(last_year) >= 20 else None
    drawdown = calculate_max_drawdown(last_year) if len(last_year) >= 20 else None

    card = build_score_card(
        quality_inputs={
            "roe_pct": snapshot.get("roe_pct"),
            "roce_pct": snapshot.get("roce_pct"),
            "debt_to_equity": snapshot.get("debt_to_equity"),
            "interest_coverage": None,
            "fcf": None,
            "revenue_growth_3y_cagr_pct": snapshot.get("revenue_growth_3y_cagr_pct"),
            "profit_growth_3y_cagr_pct": snapshot.get("profit_growth_3y_cagr_pct"),
        },
        valuation_inputs={
            "pe_ratio": pe,
            "pe_history": pe_history,
            "pb_ratio": pb,
            "sector_pe_values": sector_pe_values,
        },
        momentum_inputs={
            "return_6m_pct": ret_6m,
            "return_12m_pct": ret_12m,
            "distance_from_52w_high_pct": distance,
        },
        risk_inputs={
            "annualized_volatility_pct": vol,
            "max_drawdown_pct": drawdown,
            "promoter_pledge_pct": snapshot.get("promoter_pledge_pct"),
        },
    )
    sector_pctile = next(
        (i["value"] for i in card["valuation"]["inputs"] if i["label"] == "P/E vs. sector peers"), None
    )
    recent = [v for v in volumes[-20:] if v and v > 0]
    return Candidate(
        symbol=snapshot["symbol"],
        name=snapshot.get("name") or snapshot["symbol"],
        sector=snapshot.get("sector") or "Unclassified",
        price=price,
        price_time=price_time,
        market_cap_cr=snapshot.get("market_cap_cr"),
        avg_volume=(sum(recent) / len(recent)) if recent else None,
        data_date=snapshot.get("data_date"),
        factors={name: card[name]["score"] for name in _FACTOR_ORDER},
        overall=card["overall"],
        signals={
            "roe_pct": snapshot.get("roe_pct"),
            "roce_pct": snapshot.get("roce_pct"),
            "revenue_cagr_3y_pct": snapshot.get("revenue_growth_3y_cagr_pct"),
            "profit_cagr_3y_pct": snapshot.get("profit_growth_3y_cagr_pct"),
            "pe_ratio": pe,
            "pe_percentile_in_sector": sector_pctile,
            "return_12m_pct": ret_12m,
            "volatility_pct": vol,
        },
        source_name=snapshot.get("source_name") or "",
        source_url=snapshot.get("source_url") or "",
    )


_universe_cache: tuple[datetime, list[Candidate]] | None = None


async def load_pick_universe(*, use_cache: bool = True) -> list[Candidate]:
    """Stock master joined with the latest prices and F2 scores, from our own database.
    Empty when the DB is unreachable or the market sync has not run."""
    global _universe_cache
    now = datetime.now(UTC)
    if use_cache and _universe_cache is not None and now - _universe_cache[0] < UNIVERSE_TTL:
        return _universe_cache[1]
    try:
        async with async_session_factory() as session:
            snaps = (
                await session.scalars(
                    select(FundamentalSnapshot).order_by(FundamentalSnapshot.data_date.desc())
                )
            ).all()
            bar_rows = (
                await session.execute(
                    select(DailyBar.symbol, DailyBar.bar_time, DailyBar.close, DailyBar.volume)
                    .where(DailyBar.bar_time >= now - timedelta(days=420))
                    .order_by(DailyBar.symbol, DailyBar.bar_time)
                )
            ).all()
    except Exception:
        logger.info("Stock picker universe database lookup unavailable")
        return []

    series: dict[str, list[tuple[datetime, float, float]]] = defaultdict(list)
    for symbol, bar_time, close, volume in bar_rows:
        if close and close > 0:
            series[symbol.upper()].append((_aware(bar_time) or now, float(close), float(volume or 0)))

    latest: dict[str, FundamentalSnapshot] = {}
    for snap in snaps:
        latest.setdefault(snap.symbol.upper(), snap)

    peers: dict[str, list[float]] = defaultdict(list)
    for symbol, snap in latest.items():
        bars = series.get(symbol)
        if bars and snap.eps and snap.eps > 0:
            peers[snap.sector].append(bars[-1][1] / snap.eps)

    candidates: list[Candidate] = []
    for symbol, snap in latest.items():
        bars = series.get(symbol, [])
        snapshot = {
            "symbol": symbol,
            "name": snap.name,
            "sector": snap.sector,
            "eps": snap.eps,
            "book_value_per_share": snap.book_value_per_share,
            "roe_pct": snap.roe_pct,
            "roce_pct": snap.roce_pct,
            "debt_to_equity": snap.debt_to_equity,
            "promoter_pledge_pct": snap.promoter_pledge_pct,
            "revenue_growth_3y_cagr_pct": snap.revenue_growth_3y_cagr_pct,
            "profit_growth_3y_cagr_pct": snap.profit_growth_3y_cagr_pct,
            "market_cap_cr": snap.market_cap_cr,
            "data_date": _aware(snap.data_date),
            "source_name": snap.source_name,
            "source_url": snap.source_url,
        }
        candidates.append(
            score_candidate(
                snapshot,
                [b[1] for b in bars],
                [b[2] for b in bars],
                bars[-1][0] if bars else None,
                peers[snap.sector],
            )
        )

    by_sector: dict[str, list[float]] = defaultdict(list)
    for cand in candidates:
        move = cand.signals.get("return_12m_pct")
        if move is not None:
            by_sector[cand.sector].append(move)
    for cand in candidates:
        moves = by_sector.get(cand.sector, [])
        cand.signals["sector_median_return_12m_pct"] = (
            round(statistics.median(moves), 2) if len(moves) >= 3 else None
        )
    _universe_cache = (now, candidates)
    return candidates


def pick_filters() -> dict[str, float]:
    settings = get_settings()
    return {
        "max_age_hours": float(settings.MARKET_DATA_MAX_AGE_HOURS),
        "min_market_cap_cr": settings.STOCK_PICK_MIN_MARKET_CAP_CR,
        "min_avg_volume": settings.STOCK_PICK_MIN_AVG_VOLUME,
    }
