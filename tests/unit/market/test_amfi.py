"""Tests for the Workstream B, B1 extensions to market/amfi.py: fund house/category
tracking through parse_nav_file, and the deterministic plan/option/sebi_group classifiers."""

from investment_agent.market.amfi import (
    category_index,
    classify_option,
    classify_plan,
    classify_sebi_group,
    parse_nav_file,
)


def test_parse_nav_file_tracks_fund_house_and_category_per_scheme():
    text = (
        "Aditya Birla Sun Life Mutual Fund\n"
        "\n"
        "Open Ended Schemes(Equity Scheme - Large Cap Fund)\n"
        "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
        "119598;INF111;INF222;ABSL Frontline Equity Fund - Direct Plan-Growth;54.5;01-Oct-2026\n"
        "\n"
        "Open Ended Schemes(Equity Scheme - Small Cap Fund)\n"
        "120716;INF333;INF444;ABSL Small Cap Fund - Regular Plan-IDCW;10.0;01-Oct-2026\n"
        "\n"
        "Axis Mutual Fund\n"
        "\n"
        "Open Ended Schemes(Equity Scheme - ELSS)\n"
        "130001;INF555;INF666;Axis Long Term Equity Fund - Direct Plan-Growth;80.0;01-Oct-2026\n"
    )
    rows = parse_nav_file(text)
    assert len(rows) == 3

    large_cap = rows[0]
    assert large_cap["fund_house"] == "Aditya Birla Sun Life Mutual Fund"
    assert large_cap["category"] == "Open Ended Schemes(Equity Scheme - Large Cap Fund)"
    assert large_cap["plan"] == "direct"
    assert large_cap["option"] == "growth"
    assert large_cap["sebi_group"] == "large"

    # Same fund house, new category header -> category updates, fund house carries over.
    small_cap = rows[1]
    assert small_cap["fund_house"] == "Aditya Birla Sun Life Mutual Fund"
    assert small_cap["category"] == "Open Ended Schemes(Equity Scheme - Small Cap Fund)"
    assert small_cap["plan"] == "regular"
    assert small_cap["option"] == "idcw"
    assert small_cap["sebi_group"] == "small"

    # New fund house line -> fund house switches, category also reset by the new header.
    elss = rows[2]
    assert elss["fund_house"] == "Axis Mutual Fund"
    assert elss["category"] == "Open Ended Schemes(Equity Scheme - ELSS)"
    assert elss["sebi_group"] == "elss"


def test_classify_plan():
    assert classify_plan("ABSL Frontline Equity Fund - Direct Plan-Growth") == "direct"
    assert classify_plan("ABSL Frontline Equity Fund - Regular Plan-Growth") == "regular"
    # No "direct"/"regular" mentioned at all -> regular is the safe default, not a guess
    # upgraded to "direct".
    assert classify_plan("Some Old Scheme Name") == "regular"


def test_classify_option():
    assert classify_option("ABSL Small Cap Fund - Regular Plan-IDCW") == "idcw"
    assert classify_option("ABSL Small Cap Fund - Regular Plan-Dividend") == "idcw"
    assert classify_option("ABSL Frontline Equity Fund - Direct Plan-Growth") == "growth"
    assert classify_option("Some Old Scheme Name") == "growth"


def test_category_index_maps_scheme_code_to_the_header_above_it():
    text = (
        "HDFC Mutual Fund\n"
        "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\n"
        "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\n"
        "119598;INF111;INF222;HDFC Flexi Cap Fund;54.5;01-Oct-2026\n"
    )
    assert category_index(text) == {"119598": "Open Ended Schemes(Equity Scheme - Flexi Cap Fund)"}


def test_classify_sebi_group_order_of_precedence():
    # ELSS and index/gold are checked before the cap-based buckets so they don't get
    # misclassified just because "large cap" or similar also appears somewhere in the text.
    assert classify_sebi_group("Equity Scheme - ELSS", "Axis Long Term Equity Fund - Tax Saver") == "elss"
    assert classify_sebi_group("Other Scheme - Index Funds/ETFs", "Nifty 50 Index Fund") == "index"
    assert classify_sebi_group(None, "Gold ETF") == "gold"
    assert classify_sebi_group("Equity Scheme - Large Cap Fund", "ABSL Frontline Equity Fund") == "large"
    assert classify_sebi_group("Equity Scheme - Mid Cap Fund", "ABSL Mid Cap Fund") == "mid"
    assert classify_sebi_group("Equity Scheme - Small Cap Fund", "ABSL Small Cap Fund") == "small"
    assert classify_sebi_group("Equity Scheme - Flexi Cap Fund", "ABSL Flexi Cap Fund") == "flexi"
    assert classify_sebi_group("Hybrid Scheme - Aggressive Hybrid Fund", "ABSL Hybrid Fund") == "hybrid"
    assert classify_sebi_group("Debt Scheme - Liquid Fund", "ABSL Liquid Fund") == "debt"
    assert classify_sebi_group("Solution Oriented Scheme - Retirement Fund", "ABSL Retirement Fund") == "solution"
