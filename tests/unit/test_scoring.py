from investment_agent.portfolio.scoring import (
    build_score_card,
    compute_overall_score,
    score_momentum,
    score_quality,
    score_risk,
    score_valuation,
)


def test_score_quality_strong_company_scores_high():
    block = score_quality(
        roe_pct=25.0,
        roce_pct=25.0,
        debt_to_equity=0.0,
        interest_coverage=10.0,
        fcf=500.0,
        revenue_growth_3y_cagr_pct=20.0,
        profit_growth_3y_cagr_pct=20.0,
    )
    assert block["score"] == 100.0
    assert len(block["inputs"]) == 7
    assert block["inputs"][0]["label"] == "Return on equity"


def test_score_quality_weak_company_scores_low():
    block = score_quality(
        roe_pct=0.0,
        roce_pct=0.0,
        debt_to_equity=3.0,
        interest_coverage=1.0,
        fcf=-50.0,
        revenue_growth_3y_cagr_pct=0.0,
        profit_growth_3y_cagr_pct=0.0,
    )
    assert block["score"] == 0.0


def test_score_quality_too_little_data_is_none():
    # Only 2 of 7 inputs present -> fewer than half -> DATA_UNAVAILABLE, not a thin guess.
    block = score_quality(
        roe_pct=20.0,
        roce_pct=None,
        debt_to_equity=None,
        interest_coverage=None,
        fcf=None,
        revenue_growth_3y_cagr_pct=None,
        profit_growth_3y_cagr_pct=None,
    )
    assert block["score"] is None
    # Every input is still reported (with a None value) so the UI can render "Data unavailable".
    assert len(block["inputs"]) == 7


def test_score_valuation_cheap_vs_history_and_sector_scores_high():
    # calculate_percentile_rank counts values <= the target inclusively, so the P/E must
    # sit *below* every comparison value (not just equal the minimum) to land at the true
    # 0th percentile on both legs.
    block = score_valuation(
        pe_ratio=9.0,
        pe_history=[10.0, 15.0, 20.0, 25.0, 30.0],
        pb_ratio=2.0,
        sector_pe_values=[20.0, 25.0, 30.0],
    )
    assert block["score"] == 100.0


def test_score_valuation_expensive_scores_low():
    block = score_valuation(
        pe_ratio=30.0,
        pe_history=[10.0, 15.0, 20.0, 25.0, 30.0],
        pb_ratio=8.0,
        sector_pe_values=[10.0, 15.0, 20.0],
    )
    assert block["score"] == 0.0


def test_score_valuation_no_peer_data_is_none():
    block = score_valuation(pe_ratio=20.0, pe_history=None, pb_ratio=None, sector_pe_values=None)
    assert block["score"] is None


def test_score_momentum_strong_uptrend_scores_high():
    block = score_momentum(return_6m_pct=30.0, return_12m_pct=50.0, distance_from_52w_high_pct=0.0)
    assert block["score"] == 100.0


def test_score_momentum_downtrend_scores_low():
    block = score_momentum(return_6m_pct=-20.0, return_12m_pct=-30.0, distance_from_52w_high_pct=-40.0)
    assert block["score"] == 0.0


def test_score_risk_low_volatility_no_pledge_scores_high():
    block = score_risk(annualized_volatility_pct=10.0, max_drawdown_pct=-5.0, promoter_pledge_pct=0.0)
    assert block["score"] == 100.0


def test_score_risk_high_volatility_heavy_pledge_scores_low():
    block = score_risk(annualized_volatility_pct=60.0, max_drawdown_pct=-60.0, promoter_pledge_pct=50.0)
    assert block["score"] == 0.0


def test_compute_overall_score_weighted_average():
    quality = score_quality(
        roe_pct=25.0, roce_pct=25.0, debt_to_equity=0.0, interest_coverage=10.0,
        fcf=100.0, revenue_growth_3y_cagr_pct=20.0, profit_growth_3y_cagr_pct=20.0,
    )
    valuation = score_valuation(pe_ratio=5.0, pe_history=[10.0, 30.0], pb_ratio=1.0, sector_pe_values=[30.0])
    momentum = score_momentum(return_6m_pct=30.0, return_12m_pct=50.0, distance_from_52w_high_pct=0.0)
    risk = score_risk(annualized_volatility_pct=10.0, max_drawdown_pct=-5.0, promoter_pledge_pct=0.0)
    # All four sub-scores are 100 -> overall must be 100 regardless of weighting.
    assert compute_overall_score(quality, valuation, momentum, risk) == 100.0


def test_compute_overall_score_renormalizes_when_a_block_is_missing():
    quality = score_quality(
        roe_pct=25.0, roce_pct=25.0, debt_to_equity=0.0, interest_coverage=10.0,
        fcf=100.0, revenue_growth_3y_cagr_pct=20.0, profit_growth_3y_cagr_pct=20.0,
    )
    valuation = score_valuation(pe_ratio=None, pe_history=None, pb_ratio=None, sector_pe_values=None)
    momentum = score_momentum(return_6m_pct=30.0, return_12m_pct=50.0, distance_from_52w_high_pct=0.0)
    risk = score_risk(annualized_volatility_pct=10.0, max_drawdown_pct=-5.0, promoter_pledge_pct=0.0)
    # Valuation is DATA_UNAVAILABLE; the other three are all 100 -> overall must still be
    # 100 (renormalized), not pulled down by treating the missing block as 0.
    assert valuation["score"] is None
    assert compute_overall_score(quality, valuation, momentum, risk) == 100.0


def test_compute_overall_score_all_missing_is_none():
    empty = score_valuation(pe_ratio=None, pe_history=None, pb_ratio=None, sector_pe_values=None)
    assert compute_overall_score(empty, empty, empty, empty) is None


def test_build_score_card_assembles_all_blocks():
    card = build_score_card(
        quality_inputs={
            "roe_pct": 20.0, "roce_pct": 20.0, "debt_to_equity": 0.5, "interest_coverage": 5.0,
            "fcf": 100.0, "revenue_growth_3y_cagr_pct": 10.0, "profit_growth_3y_cagr_pct": 10.0,
        },
        valuation_inputs={"pe_ratio": 20.0, "pe_history": [15.0, 25.0], "pb_ratio": 3.0, "sector_pe_values": [25.0]},
        momentum_inputs={"return_6m_pct": 10.0, "return_12m_pct": 15.0, "distance_from_52w_high_pct": -5.0},
        risk_inputs={"annualized_volatility_pct": 20.0, "max_drawdown_pct": -15.0, "promoter_pledge_pct": 0.0},
    )
    assert set(card.keys()) == {"quality", "valuation", "momentum", "risk", "overall"}
    assert card["overall"] is not None
    assert 0.0 <= card["overall"] <= 100.0
