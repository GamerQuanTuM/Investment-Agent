from investment_agent.market.tradingview import merge_fundamentals


def test_tradingview_fills_missing_ratios_and_keeps_yahoo_eps():
    merged = merge_fundamentals(
        {"roe_pct": None, "eps": 137.5, "source": "Yahoo Finance company profile"},
        {
            "roe_pct": 47.99,
            "debt_to_equity": 0.1,
            "eps": 1.45,
            "source": "TradingView screener",
        },
    )
    assert merged["roe_pct"] == 47.99
    assert merged["debt_to_equity"] == 0.1
    assert merged["eps"] == 137.5
    assert "Yahoo" in merged["source"]
    assert "TradingView" in merged["source"]
