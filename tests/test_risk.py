from risk import assess_risk


def test_detects_each_sensational_phrase():
    for phrase in ("breaking", "shocking", "share before deleted"):
        result = assess_risk(f"Please read: {phrase}", "https://example.com")
        assert "sensational" in result["risk_flags"]


def test_sensational_detection_is_case_insensitive():
    result = assess_risk("SHOCKING update", "https://example.com")
    assert "sensational" in result["risk_flags"]


def test_sensational_phrase_allows_repeated_whitespace():
    result = assess_risk("Share   before\t deleted", "https://example.com")
    assert "sensational" in result["risk_flags"]


def test_shouting_triggers_above_fifty_percent():
    result = assess_risk("ABCde", "https://example.com")
    assert "shouting" in result["risk_flags"]


def test_shouting_does_not_trigger_at_exactly_fifty_percent():
    result = assess_risk("HELLO world", "https://example.com")
    assert "shouting" not in result["risk_flags"]


def test_shouting_does_not_trigger_without_alphabetic_characters():
    result = assess_risk("⚠️ 123 !!!", "https://example.com")
    assert "shouting" not in result["risk_flags"]


def test_missing_or_blank_source_url_is_unsourced():
    assert "unsourced" in assess_risk("A claim")["risk_flags"]
    assert "unsourced" in assess_risk("A claim", "   ")["risk_flags"]


def test_valid_source_url_is_not_unsourced():
    result = assess_risk("A claim", "https://example.com/source")
    assert "unsourced" not in result["risk_flags"]


def test_two_base_flags_are_high_risk():
    result = assess_risk("BREAKING update", "https://example.com")
    assert result["risk_score"] == 2
    assert result["high_risk"] is True


def test_three_base_flags_are_high_risk():
    result = assess_risk("SHOCKING BREAKING NEWS")
    assert result["risk_score"] == 3
    assert result["high_risk"] is True


def test_one_base_flag_is_not_high_risk():
    result = assess_risk("breaking update", "https://example.com")
    assert result["risk_score"] == 1
    assert result["high_risk"] is False
