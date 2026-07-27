from __future__ import annotations

from src.agents.semantic_intent_router import ALLOWED_INTENTS, _parse_response


def test_parses_clean_json() -> None:
    result = _parse_response('{"intent": "reminder_request", "reason": "asks to be reminded"}')
    assert result == ("reminder_request", "asks to be reminded")


def test_parses_json_wrapped_in_markdown_fence() -> None:
    raw = '```json\n{"intent": "casual_conversation", "reason": "asking the time"}\n```'
    result = _parse_response(raw)
    assert result == ("casual_conversation", "asking the time")


def test_parses_json_wrapped_in_plain_fence_without_language_tag() -> None:
    raw = '```\n{"intent": "emotional_support", "reason": "feels lonely"}\n```'
    result = _parse_response(raw)
    assert result == ("emotional_support", "feels lonely")


def test_parses_json_with_surrounding_prose() -> None:
    raw = 'Sure, here is the classification: {"intent": "unknown", "reason": "unclear"} hope that helps!'
    result = _parse_response(raw)
    assert result == ("unknown", "unclear")


def test_rejects_hallucinated_safety_critical_intent() -> None:
    # Only the deterministic hard gates in classify_intent may produce these
    # labels — a model that claims one must be treated as untrustworthy,
    # exactly like a parse failure, not honored.
    for fake_intent in ("urgent_safety", "medication_or_diagnosis", "prompt_injection", "role_correction"):
        raw = f'{{"intent": "{fake_intent}", "reason": "trying to claim a safety label"}}'
        assert _parse_response(raw) is None, fake_intent


def test_rejects_unknown_intent_value() -> None:
    assert _parse_response('{"intent": "not_a_real_category"}') is None


def test_rejects_truncated_json() -> None:
    assert _parse_response('{"intent": "reminder_re') is None


def test_rejects_non_json_text() -> None:
    assert _parse_response("I cannot classify this message.") is None


def test_rejects_empty_or_missing_text() -> None:
    assert _parse_response("") is None
    assert _parse_response("   ") is None


def test_missing_reason_defaults_to_empty_string() -> None:
    result = _parse_response('{"intent": "daily_life_support"}')
    assert result == ("daily_life_support", "")


def test_reason_is_truncated_to_a_bounded_length() -> None:
    long_reason = "x" * 500
    result = _parse_response(f'{{"intent": "unknown", "reason": "{long_reason}"}}')
    assert result is not None
    assert len(result[1]) <= 200


def test_allowed_intents_excludes_safety_critical_categories() -> None:
    for forbidden in ("urgent_safety", "medication_or_diagnosis", "prompt_injection", "role_correction"):
        assert forbidden not in ALLOWED_INTENTS
