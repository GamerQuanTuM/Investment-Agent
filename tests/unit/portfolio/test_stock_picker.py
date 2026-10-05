"""Stock picker: pure selection and allocation over a fixture universe (no DB, no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from investment_agent.portfolio import stock_picker as sp
from investment_agent.portfolio.stock_picker import Candidate, build_stock_plan, filter_candidates

NOW = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
SECTORS = ["Technology", "Financial Services", "Healthcare", "Energy", "Consumer Defensive", "Industrials"]


def cand(
    symbol: str,
    sector: str,
    price: float,
    overall: float,
    *,
    cap: float | None = 120_000.0,
    volume: float | None = 2_000_000.0,
    age_hours: float = 2.0,
    quality: float | None = 70.0,
) -> Candidate:
    return Candidate(
        symbol=symbol,
        name=f"{symbol.title()} Limited",
        sector=sector,
        price=price,
        price_time=NOW - timedelta(hours=age_hours),
        market_cap_cr=cap,
        avg_volume=volume,
        data_date=NOW - timedelta(days=30),
        factors={"quality": quality, "valuation": 60.0, "momentum": 55.0, "risk": 65.0},
        overall=overall,
        signals={
            "roe_pct": 18.0,
            "profit_cagr_3y_pct": 12.0,
            "pe_ratio": 22.0,
            "return_12m_pct": 9.0,
            "volatility_pct": 21.0,
        },
    )


def universe(n: int = 24, price: float = 400.0) -> list[Candidate]:
    return [
        cand(f"STK{i:02d}", SECTORS[i % len(SECTORS)], price + i * 13, 90.0 - i * 1.5)
        for i in range(n)
    ]


UNIVERSE_SYMBOLS = {c.symbol for c in universe()}


def plan(cands: list[Candidate] | None = None, **kwargs):
    defaults = {"budget": 10_000.0, "count": 10}
    return build_stock_plan(cands if cands is not None else universe(), **{**defaults, **kwargs})


def test_allocation_never_exceeds_budget_and_uses_whole_shares():
    result = plan()
    assert result["status"] == "OK"
    assert result["total_invested"] <= 10_000.0
    for row in result["rows"]:
        assert isinstance(row["shares"], int) and row["shares"] >= 1
        assert row["amount_inr"] == pytest.approx(row["shares"] * row["price"], abs=0.01)
    assert result["total_invested"] == pytest.approx(sum(r["amount_inr"] for r in result["rows"]), abs=0.01)


def test_leftover_is_reported_and_balances_the_budget():
    result = plan()
    assert result["leftover"] == pytest.approx(10_000.0 - result["total_invested"], abs=0.01)
    assert result["leftover"] >= 0
    assert any("unused" in c for c in result["caveats"])


def test_every_ticker_comes_from_the_fixture_universe():
    result = plan(count=12)
    assert {row["symbol"] for row in result["rows"]} <= UNIVERSE_SYMBOLS
    assert 10 <= len(result["rows"]) <= 12


def test_stock_priced_above_its_allocation_is_dropped_for_the_next_candidate():
    cands = universe()
    cands.insert(0, cand("PRICEY", "Technology", 48_000.0, 99.0))  # best score, unaffordable
    result = plan(cands)
    symbols = [row["symbol"] for row in result["rows"]]
    assert "PRICEY" not in symbols
    assert "PRICEY" in result["dropped_unaffordable"]
    assert len(symbols) == 10  # replaced by the next-ranked names, not left short


def test_sector_caps_are_respected():
    # The top scorers all sit in one sector; the picker may take at most two of them.
    cands = [cand(f"TECH{i}", "Technology", 300.0 + i, 99.0 - i) for i in range(8)]
    cands += [cand(f"OTH{i}", SECTORS[1 + i % 5], 300.0 + i, 60.0 - i) for i in range(20)]
    result = plan(cands, budget=50_000.0)
    per_sector: dict[str, int] = {}
    target: dict[str, float] = {}
    for row in result["rows"]:
        per_sector[row["sector"]] = per_sector.get(row["sector"], 0) + 1
        target[row["sector"]] = target.get(row["sector"], 0.0) + row["target_weight_pct"]
    assert max(per_sector.values()) <= 2
    assert max(target.values()) <= 30.0 + 0.5  # rounding of each row's 1-decimal weight
    assert per_sector["Technology"] == 2


def test_weights_follow_score_within_bounds():
    result = plan(budget=200_000.0)
    weights = {r["symbol"]: r["target_weight_pct"] for r in result["rows"]}
    n = len(weights)
    assert min(weights.values()) >= 100 * sp.MIN_WEIGHT_OF_EQUAL / n - 0.1
    assert max(weights.values()) <= 100 * max(0.2, 2 / n) + 0.1
    ordered = sorted(result["rows"], key=lambda r: -r["score"])
    assert ordered[0]["target_weight_pct"] >= ordered[-1]["target_weight_pct"]


def test_count_is_clamped_to_three_to_fifteen_and_defaults_to_ten():
    assert sp.clamp_count(None) == 10
    assert sp.clamp_count(100) == 15
    assert sp.clamp_count(1) == 3
    wide = [cand(f"W{i:02d}", f"Sector{i % 9}", 400.0 + i, 90.0 - i) for i in range(30)]
    assert len(plan(wide, count=50, budget=500_000.0)["rows"]) == 15
    # Six sectors x two per sector caps the list at twelve, and the user is told why.
    capped = plan(count=15, budget=500_000.0)
    assert len(capped["rows"]) == 12
    assert any("only 12" in c for c in capped["caveats"])
    assert len(plan(count=None, budget=500_000.0)["rows"]) == 10


def test_beginner_without_a_risk_choice_is_steered_to_large_caps():
    mixed = [cand(f"BIG{i}", SECTORS[i % 6], 500.0, 70.0 - i, cap=90_000) for i in range(12)]
    mixed += [cand(f"MID{i}", SECTORS[i % 6], 500.0, 95.0 - i, cap=20_000) for i in range(10)]
    mixed += [cand(f"SML{i}", SECTORS[i % 6], 500.0, 98.0 - i, cap=6_000) for i in range(10)]
    result = plan(mixed, budget=100_000.0, experience_level="beginner")
    bands = [r["market_cap_band"] for r in result["rows"]]
    assert bands.count("small") == 0
    assert bands.count("mid") <= 2
    assert result["risk_profile"] == "conservative"
    aggressive = plan(mixed, budget=100_000.0, risk_profile="aggressive")
    assert [r["market_cap_band"] for r in aggressive["rows"]].count("small") >= 1


def test_each_row_explains_its_top_two_factors_from_measured_numbers():
    row = plan()["rows"][0]
    assert len(row["why"]) == 2
    assert all("/100" in text for text in row["why"])
    assert row["signals"]["roe_pct"] == 18.0
    assert "target" not in " ".join(row["why"]).lower()


def test_reality_check_always_present_for_small_budgets_and_offers_the_index_fund():
    small = plan(budget=10_000.0, count=12)
    assert small["reality_check"] is not None
    assert "index fund" in small["reality_check"]
    assert "brokerage" in small["reality_check"].lower()
    large = plan(universe(price=300.0), budget=5_000_000.0)
    assert large["reality_check"] is None


def test_plan_carries_data_date_disclaimer_and_no_forecast():
    result = plan()
    assert result["data_as_of"] == (NOW - timedelta(hours=2)).date().isoformat()
    assert "SEBI-registered" in result["disclaimer"]
    assert "not a forecast" in result["growth_note"].lower()
    assert "expected return" in result["growth_note"].lower()


def test_sector_preference_is_honoured_when_enough_names_exist():
    result = plan(sectors_wanted=["technology"], budget=100_000.0, count=3)
    assert {r["sector"] for r in result["rows"]} == {"Technology"} or len(result["rows"]) < 3
    assert any("one sector" in c for c in result["caveats"])


def test_sector_preference_without_enough_names_falls_back_with_a_caveat():
    result = plan(sectors_wanted=["materials"])
    assert result["status"] == "OK"
    assert any("sectors you asked for" in c for c in result["caveats"])


def test_budget_too_small_for_any_diversified_list_is_data_unavailable_not_a_guess():
    result = plan(universe(price=400.0), budget=900.0)
    assert result["status"] == "DATA_UNAVAILABLE"
    assert "index fund" in result["message"]


def test_empty_universe_is_data_unavailable():
    assert plan([])["status"] == "DATA_UNAVAILABLE"


def test_same_inputs_give_the_same_plan():
    assert plan() == plan()


class TestFilters:
    def run(self, cands: list[Candidate]):
        return filter_candidates(
            cands, now=NOW, max_age_hours=36, min_market_cap_cr=5_000, min_avg_volume=100_000
        )

    def test_excludes_missing_stale_missing_fundamentals_penny_and_illiquid(self):
        good = cand("GOOD", "Technology", 500.0, 80.0)
        no_price = cand("NOPRICE", "Technology", 500.0, 80.0)
        no_price.price = None
        stale = cand("STALE", "Energy", 500.0, 80.0, age_hours=100)
        no_fund = cand("NOFUND", "Energy", 500.0, 80.0, quality=None)
        penny = cand("PENNY", "Energy", 3.0, 80.0, cap=800.0)
        thin = cand("THIN", "Energy", 500.0, 80.0, volume=500.0)
        unknown_cap = cand("NOCAP", "Energy", 500.0, 80.0, cap=None)
        kept, excluded = self.run([good, no_price, stale, no_fund, penny, thin, unknown_cap])
        assert [c.symbol for c in kept] == ["GOOD"]
        assert excluded == {
            "missing_price": 1,
            "stale_price": 1,
            "missing_fundamentals": 1,
            "below_market_cap_floor": 2,
            "illiquid": 1,
        }

    def test_unknown_volume_does_not_exclude_when_market_cap_is_large(self):
        kept, _ = self.run([cand("OK1", "Energy", 500.0, 80.0, volume=None)])
        assert len(kept) == 1


def test_score_candidate_computes_factors_in_python_from_stored_rows():
    closes = [100.0 + i * 0.2 for i in range(260)]
    snapshot = {
        "symbol": "ABC",
        "name": "ABC Ltd",
        "sector": "Technology",
        "eps": 5.0,
        "book_value_per_share": 40.0,
        "roe_pct": 22.0,
        "roce_pct": 25.0,
        "debt_to_equity": 0.1,
        "promoter_pledge_pct": 0.0,
        "revenue_growth_3y_cagr_pct": 14.0,
        "profit_growth_3y_cagr_pct": 16.0,
        "market_cap_cr": 80_000.0,
        "data_date": NOW,
    }
    result = sp.score_candidate(snapshot, closes, [300_000.0] * 260, NOW, [18.0, 25.0, 40.0])
    assert result.price == closes[-1]
    assert result.signals["pe_ratio"] == round(closes[-1] / 5.0, 2)
    assert result.overall is not None and 0 <= result.overall <= 100
    assert all(result.factors[f] is not None for f in ("quality", "valuation", "momentum", "risk"))
    assert result.avg_volume == 300_000.0


def test_score_candidate_without_fundamentals_has_no_quality_score():
    result = sp.score_candidate(
        {"symbol": "XYZ", "sector": "Energy"}, [100.0] * 30, [1e6] * 30, NOW, []
    )
    assert result.factors["quality"] is None
