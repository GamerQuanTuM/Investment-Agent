from investment_agent.research.alerts import generate_portfolio_alerts


def test_generate_portfolio_alerts_empty_portfolio_has_no_alerts():
    assert generate_portfolio_alerts([]) == []


def test_generate_portfolio_alerts_flags_drawdown():
    holdings = [
        {"symbol": "A", "sector": "IT", "current_value": 100.0, "allocation_pct": 50.0, "unrealized_pnl_pct": -20.0},
        {"symbol": "B", "sector": "Banking", "current_value": 100.0, "allocation_pct": 50.0, "unrealized_pnl_pct": 5.0},
    ]
    alerts = generate_portfolio_alerts(holdings)
    drawdown_alerts = [a for a in alerts if a["kind"] == "DRAWDOWN"]
    assert len(drawdown_alerts) == 1
    assert drawdown_alerts[0]["symbol"] == "A"
    assert drawdown_alerts[0]["severity"] == "WARNING"


def test_generate_portfolio_alerts_does_not_flag_small_drawdown():
    holdings = [{"symbol": "A", "sector": "IT", "current_value": 100.0, "allocation_pct": 100.0, "unrealized_pnl_pct": -5.0}]
    alerts = generate_portfolio_alerts(holdings)
    assert not any(a["kind"] == "DRAWDOWN" for a in alerts)


def test_generate_portfolio_alerts_flags_single_holding_concentration():
    holdings = [{"symbol": "A", "sector": "IT", "current_value": 100.0, "allocation_pct": 90.0, "unrealized_pnl_pct": 0.0}]
    alerts = generate_portfolio_alerts(holdings)
    concentration_alerts = [a for a in alerts if a["kind"] == "CONCENTRATION"]
    assert len(concentration_alerts) == 1
    assert concentration_alerts[0]["symbol"] == "A"
    assert concentration_alerts[0]["severity"] == "INFO"


def test_generate_portfolio_alerts_missing_pnl_field_does_not_crash():
    # 5 equal, differently-sectored holdings at 20% each (at, not over, either
    # threshold) with `unrealized_pnl_pct` entirely absent -- must not crash, and
    # nothing here should cross a threshold either.
    holdings = [
        {"symbol": s, "sector": sector, "current_value": 20.0, "allocation_pct": 20.0}
        for s, sector in [("A", "IT"), ("B", "Banking"), ("C", "FMCG"), ("D", "Pharma"), ("E", "Energy")]
    ]
    assert generate_portfolio_alerts(holdings) == []
