from investment_agent.market.board import page_movers, rank_movers


def test_rank_movers_uses_absolute_session_move():
    ranked = rank_movers(
        [
            {"symbol": "AAA", "day_change_percentage": 1.2, "volume": 10},
            {"symbol": "BBB", "day_change_percentage": -4.5, "volume": 5},
            {"symbol": "CCC", "day_change_percentage": 4.5, "volume": 9},
        ]
    )
    assert [row["symbol"] for row in ranked] == ["CCC", "BBB", "AAA"]


def test_page_movers_returns_the_next_offset():
    rows = [{"symbol": str(i)} for i in range(12)]
    page = page_movers(rows, offset=5, limit=5)
    assert [row["symbol"] for row in page["items"]] == ["5", "6", "7", "8", "9"]
    assert page["next_offset"] == 10
    assert page_movers(rows, offset=10, limit=5)["next_offset"] is None
