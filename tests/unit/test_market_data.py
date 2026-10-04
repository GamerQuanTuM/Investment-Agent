from investment_agent.market.amfi import parse_nav_file
from investment_agent.market.indstocks import (
    equity_cash_available,
    parse_equity_instruments,
    parse_index_instruments,
    scrip_code,
)


def test_scrip_code():
    assert scrip_code("nse", "3045") == "NSE_3045"


def test_parse_equity_instruments_keeps_eq_series():
    csv_text = (
        "EXCH,SEGMENT,SECURITY_ID,INSTRUMENT_NAME,EXPIRY_CODE,TRADING_SYMBOL,LOT_UNITS,"
        "CUSTOM_SYMBOL,EXPIRY_DATE,STRIKE_PRICE,OPTION_TYPE,TICK_SIZE,EXPIRY_FLAG,"
        "SEM_EXCH_INSTRUMENT_TYPE,SERIES,SYMBOL_NAME\n"
        "NSE,E,11536,EQUITY,0,TCS,1,TCS,,,,,,EQUITY,EQ,TCS\n"
        "NSE,E,999,EQUITY,0,TCSBL,1,TCSBL,,,,,,EQUITY,BL,TCS\n"
    )
    rows = parse_equity_instruments(csv_text)
    assert len(rows) == 1
    assert rows[0]["symbol_name"] == "TCS"
    assert rows[0]["security_id"] == "11536"


def test_parse_index_instruments_reads_name_positionally():
    csv_text = "EXCH,SEGMENT,SECURITY_ID\nNSE,NIFTY 50,40000001\n"
    rows = parse_index_instruments(csv_text)
    assert rows == [{"exchange": "NSE", "name": "NIFTY 50", "security_id": "40000001"}]


def test_equity_cash_uses_cnc_balance():
    funds = {"detailed_avl_balance": {"eq_cnc": 2980.4}, "withdrawal_balance": 10}
    assert equity_cash_available(funds) == 2980.4


def test_parse_nav_file_filters_scheme_codes():
    text = (
        "Open Ended Schemes(Equity Scheme)\n"
        "119598;INF111;INF222;Sample Fund - Growth;54.5;01-Oct-2026\n"
        "120716;INF333;INF444;Other Fund - Growth;10.0;01-Oct-2026\n"
    )
    rows = parse_nav_file(text, {"119598"})
    assert len(rows) == 1
    assert rows[0]["scheme_code"] == "119598"
    assert rows[0]["nav"] == 54.5
