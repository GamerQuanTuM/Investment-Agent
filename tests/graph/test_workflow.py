import pytest

from investment_agent.graph.nodes import utc_now_iso
from investment_agent.graph.state import InvestmentGraphState
from investment_agent.graph.workflow import create_investment_graph


def _sourced_candidate(**overrides: object) -> dict:
    candidate = {
        "symbol": "TCS",
        "name": "Tata Consultancy Services Ltd",
        "asset_type": "stock",
        "sector": "Information Technology",
        "current_price": 4120.0,
        "has_price_data": True,
        "price_retrieved_at": utc_now_iso(),
        "pe_ratio": 29.5,
        "roe_pct": 48.0,
        "roce_pct": 62.0,
        "debt_to_equity": 0.05,
        "promoter_pledge_pct": 0.0,
        "profit_growth_3y_cagr_pct": 10.5,
        "source_name": "Company filing",
        "source_url": "https://www.nseindia.com/companies-listing/corporate-filings-financial-results",
        "source_type": "Company Filing",
        "price_source_name": "INDstocks",
        "price_source_url": "https://api.indstocks.com/market/quotes/ltp",
    }
    candidate.update(overrides)
    return candidate


@pytest.mark.asyncio
async def test_investment_graph_compilation():
    graph = create_investment_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_execution_opportunity_flow():
    graph = create_investment_graph()
    initial_state: InvestmentGraphState = {
        "user_id": "test_user_1",
        "monthly_budget": 20000.0,
        "candidates": [_sourced_candidate()],
        "portfolio": {"cash_available": 0.0, "total_value": 0.0, "holdings": []},
    }
    result = await graph.ainvoke(initial_state)

    assert result["execution_status"] == "VERIFIED"
    assert "recommendation" in result
    rec = result["recommendation"]
    assert rec["decision"] == "OPPORTUNITY"
    assert "report" in rec
    report = rec["report"]
    assert "FACT" in report
    assert "INTERPRETATION" in report
    assert "ASSUMPTION" in report
    assert "UNCERTAINTY" in report
    assert "RISK" in report
    assert "log_entry" in rec
    assert rec["log_entry"]["prediction_id"].startswith("pred_")


@pytest.mark.asyncio
async def test_graph_without_market_data_is_no_action():
    graph = create_investment_graph()
    result = await graph.ainvoke(
        {
            "user_id": "test_user_empty",
            "monthly_budget": 20000.0,
            "portfolio": {"cash_available": 0.0, "total_value": 0.0, "holdings": []},
        }
    )
    assert result["recommendation"]["decision"] == "NO_ACTION"


@pytest.mark.asyncio
async def test_graph_execution_screening_rejection_no_action():
    """If all candidate stocks fail screening, graph routes to NO ACTION."""
    graph = create_investment_graph()
    unsuitable_candidates = [
        _sourced_candidate(
            symbol="RISKYCORP",
            name="Overleveraged Promoters Ltd",
            sector="Industrial",
            current_price=120.0,
            pe_ratio=45.0,
            roe_pct=5.0,
            roce_pct=6.0,
            debt_to_equity=3.8,
            promoter_pledge_pct=35.0,
        )
    ]

    initial_state: InvestmentGraphState = {
        "user_id": "test_user_2",
        "monthly_budget": 15000.0,
        "candidates": unsuitable_candidates,
        "portfolio": {"cash_available": 0.0, "total_value": 0.0, "holdings": []},
    }
    result = await graph.ainvoke(initial_state)

    rec = result["recommendation"]
    assert rec["decision"] == "NO_ACTION"
    assert rec["status"] == "INSUFFICIENT_EVIDENCE"


@pytest.mark.asyncio
async def test_graph_insufficient_evidence_safety():
    """If candidates have missing price data or ratios, system must output INSUFFICIENT_EVIDENCE."""
    graph = create_investment_graph()
    unverifiable_candidate = [
        {
            "symbol": "OPAQUE",
            "name": "Opaque Holdings Ltd",
            "asset_type": "stock",
            "sector": "Miscellaneous",
            "has_price_data": False,
            "current_price": 0.0,
            "pe_ratio": None,
        }
    ]

    initial_state: InvestmentGraphState = {
        "user_id": "test_user_3",
        "candidates": unverifiable_candidate,
        "portfolio": {"cash_available": 0.0, "total_value": 0.0, "holdings": []},
    }
    result = await graph.ainvoke(initial_state)

    assert result["recommendation"]["decision"] == "NO_ACTION"
    assert result["recommendation"]["status"] == "INSUFFICIENT_EVIDENCE"
