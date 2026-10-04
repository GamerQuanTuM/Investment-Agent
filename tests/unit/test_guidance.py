from investment_agent.research.guidance import rule_stance


def test_short_horizon_is_avoid():
    result = rule_stance(
        horizon_years=1, pe_ratio=18, day_change_pct=0.4, range_return_pct=12, span_label="1 year"
    )
    assert result["stance"] == "AVOID"


def test_rich_multiple_waits():
    result = rule_stance(
        horizon_years=5, pe_ratio=60, day_change_pct=1, range_return_pct=8, span_label="5 years"
    )
    assert result["stance"] == "WAIT"


def test_complete_quote_can_be_considered():
    result = rule_stance(
        horizon_years=5, pe_ratio=22, day_change_pct=0.5, range_return_pct=11, span_label="5 years"
    )
    assert result["stance"] == "CONSIDER"
