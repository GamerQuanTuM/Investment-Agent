from investment_agent.research.outcome_scoring import classify_outcome


def test_classify_outcome_opportunity_price_rose_is_correct():
    result = classify_outcome("OPPORTUNITY", entry_price=100.0, current_price=110.0)
    assert result["outcome_status"] == "CORRECT"
    assert "+10.00%" in result["evaluation_notes"]


def test_classify_outcome_opportunity_price_fell_is_incorrect():
    result = classify_outcome("OPPORTUNITY", entry_price=100.0, current_price=90.0)
    assert result["outcome_status"] == "INCORRECT"
    assert "-10.00%" in result["evaluation_notes"]


def test_classify_outcome_opportunity_flat_price_is_incorrect():
    # Flat (0% change) counts as INCORRECT -- "worth watching" implied some upside.
    result = classify_outcome("OPPORTUNITY", entry_price=100.0, current_price=100.0)
    assert result["outcome_status"] == "INCORRECT"


def test_classify_outcome_no_action_is_not_applicable():
    result = classify_outcome("NO_ACTION", entry_price=100.0, current_price=110.0)
    assert result["outcome_status"] == "NOT_APPLICABLE"


def test_classify_outcome_missing_entry_price_is_inconclusive():
    result = classify_outcome("OPPORTUNITY", entry_price=None, current_price=110.0)
    assert result["outcome_status"] == "INCONCLUSIVE"


def test_classify_outcome_missing_current_price_is_inconclusive():
    result = classify_outcome("OPPORTUNITY", entry_price=100.0, current_price=None)
    assert result["outcome_status"] == "INCONCLUSIVE"


def test_classify_outcome_unrecognized_decision_is_inconclusive():
    result = classify_outcome("SOMETHING_ELSE", entry_price=100.0, current_price=110.0)
    assert result["outcome_status"] == "INCONCLUSIVE"
