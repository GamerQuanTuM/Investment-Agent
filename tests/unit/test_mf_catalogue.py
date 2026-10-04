from investment_agent.market.mfapi import fund_house_name, scheme_category_label


def test_fund_house_name_stops_before_fund():
    assert fund_house_name("HDFC Flexi Cap Fund - Direct Plan - Growth") == "HDFC Flexi Cap"


def test_scheme_category_label_reads_the_cap_from_the_name():
    assert scheme_category_label("HDFC Small Cap Fund - Direct Growth") == "Small cap"
    assert scheme_category_label("Benchmark Short Term Fund") == "Debt"
    assert scheme_category_label("Principal Nifty 100 Equal Weight Fund") == "Index"
    assert scheme_category_label("Aditya Birla Sun Life Tax Plan") == "ELSS"
    assert scheme_category_label("HDFC Balanced Advantage Fund") == "Hybrid"
    assert scheme_category_label("SBI Gold Fund") == "Gold"
    assert scheme_category_label("Goldman Sachs India Equity Fund - Growth Plan") == "Equity"
    assert scheme_category_label("IDBI GOLD FUND Direct") == "Gold"
    assert scheme_category_label("Some Equity Opportunities") == "Equity"
    assert scheme_category_label("Aditya Birla Sun Life MNC Fund") == "Equity"
    assert scheme_category_label("JM G-Sec Fund - Growth Option") == "Debt"
    assert scheme_category_label("Franklin India Taxshield 96") == "ELSS"
    assert scheme_category_label("Franklin India Retirement Fund") == "Solution"
    assert scheme_category_label("ABSL MNC Fund", "Open Ended Schemes(Equity Scheme - Sectoral/Thematic Fund)") == "Equity"
    assert fund_house_name("Some Scheme-Growth") == "Some Scheme"
