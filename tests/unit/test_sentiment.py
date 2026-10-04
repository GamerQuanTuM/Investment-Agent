from investment_agent.research.sentiment import aggregate_sentiment, score_headline


def test_score_headline_counts_positive_words():
    assert score_headline("TCS shares surge after wins contract from global bank") == 2


def test_score_headline_counts_negative_words():
    assert score_headline("TCS faces probe over client data fraud allegations") == -2


def test_score_headline_neutral_text_is_zero():
    assert score_headline("TCS to hold quarterly earnings call next week") == 0


def test_aggregate_sentiment_no_articles_is_data_unavailable():
    result = aggregate_sentiment([])
    assert result == {
        "label": "DATA_UNAVAILABLE",
        "score": None,
        "positive_count": 0,
        "negative_count": 0,
        "total_articles": 0,
    }


def test_aggregate_sentiment_mixed_headlines_nets_to_a_label():
    articles = [
        {"title": "TCS shares surge after wins contract from global bank"},  # +2
        {"title": "TCS faces probe over client data fraud allegations"},  # -2
        {"title": "TCS to hold quarterly earnings call next week"},  # 0
    ]
    result = aggregate_sentiment(articles)
    assert result["label"] == "NEUTRAL"  # net score = 0
    assert result["positive_count"] == 1
    assert result["negative_count"] == 1
    assert result["total_articles"] == 3


def test_aggregate_sentiment_all_positive_is_positive_label():
    articles = [{"title": "Company reports record high profit and strong growth"}]
    result = aggregate_sentiment(articles)
    assert result["label"] == "POSITIVE"
    assert result["score"] > 0


def test_aggregate_sentiment_all_negative_is_negative_label():
    articles = [{"title": "Company under investigation for fraud, shares crash"}]
    result = aggregate_sentiment(articles)
    assert result["label"] == "NEGATIVE"
    assert result["score"] < 0


def test_aggregate_sentiment_missing_title_field_does_not_crash():
    result = aggregate_sentiment([{"link": "https://example.com"}])
    assert result["label"] == "NEUTRAL"


def test_score_headline_word_boundary_prevents_substring_false_positive():
    # "ban" (negative) must not match inside "bank" -- a plain substring check did exactly
    # this during development and silently flipped a positive headline to score 1 instead
    # of the correct 2 ("surge" + "wins contract", with no actual "ban" mention).
    assert score_headline("TCS shares surge after wins contract from global bank") == 2
