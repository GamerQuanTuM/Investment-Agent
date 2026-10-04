from investment_agent.research.portfolio_insights import (
    SECTOR_CONCENTRATION_THRESHOLD_PCT,
    SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT,
    build_concentration_report,
)


def test_build_concentration_report_empty_portfolio():
    result = build_concentration_report([])
    assert result == {
        "sector_exposure_pct": {},
        "biggest_sector": None,
        "biggest_sector_pct": None,
        "biggest_holding_symbol": None,
        "biggest_holding_pct": None,
        "diversification_score": None,
        "concentration_flags": [],
    }


def test_build_concentration_report_well_diversified_has_no_flags():
    # 5 equal holdings at exactly 20% each: at, not over, the single-holding threshold
    # (the check is strictly "> 20.0"), and the sector split is equally under its own.
    holdings = [
        {"symbol": "A", "sector": "IT", "current_value": 20000.0, "allocation_pct": 20.0},
        {"symbol": "B", "sector": "Banking", "current_value": 20000.0, "allocation_pct": 20.0},
        {"symbol": "C", "sector": "FMCG", "current_value": 20000.0, "allocation_pct": 20.0},
        {"symbol": "D", "sector": "Pharma", "current_value": 20000.0, "allocation_pct": 20.0},
        {"symbol": "E", "sector": "Energy", "current_value": 20000.0, "allocation_pct": 20.0},
    ]
    result = build_concentration_report(holdings)
    assert result["biggest_sector_pct"] == 20.0
    assert result["diversification_score"] == 80.0  # 100 - 20
    assert result["concentration_flags"] == []


def test_build_concentration_report_flags_sector_over_threshold():
    holdings = [
        {"symbol": "A", "sector": "IT", "current_value": 80.0, "allocation_pct": 40.0},
        {"symbol": "B", "sector": "IT", "current_value": 20.0, "allocation_pct": 10.0},
        {"symbol": "C", "sector": "Banking", "current_value": 100.0, "allocation_pct": 50.0},
    ]
    result = build_concentration_report(holdings)
    # IT sector = (80+20)/200 = 50% > threshold
    assert result["biggest_sector"] == "IT"
    assert result["biggest_sector_pct"] == 50.0
    assert any("IT" in flag and str(SECTOR_CONCENTRATION_THRESHOLD_PCT) in flag for flag in result["concentration_flags"])


def test_build_concentration_report_flags_single_holding_over_threshold():
    holdings = [
        {"symbol": "A", "sector": "IT", "current_value": 90.0, "allocation_pct": 90.0},
        {"symbol": "B", "sector": "Banking", "current_value": 10.0, "allocation_pct": 10.0},
    ]
    result = build_concentration_report(holdings)
    assert result["biggest_holding_symbol"] == "A"
    assert result["biggest_holding_pct"] == 90.0
    assert any("A" in flag and str(SINGLE_HOLDING_CONCENTRATION_THRESHOLD_PCT) in flag for flag in result["concentration_flags"])
