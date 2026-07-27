from __future__ import annotations

from src.agents.coordinator_agent import coordinate_message
from src.agents.general_chat_agent import (
    UNKNOWN_RESPONSE,
    answer_general_conversation,
)
from src.orchestrator import handle_dementia_user_message


def _decision_for(message: str):
    return coordinate_message(message)


def test_llm_answer_passes_through_untouched(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.general_chat_agent.create_chat_answer",
        lambda config: (lambda prompt: "今日天氣唔錯，出去行下都幾好。"),
    )
    decision = _decision_for("我想出去走走，可以嗎？")
    result = answer_general_conversation("我想出去走走，可以嗎？", decision, "daily_life")

    assert result["answer"] == "今日天氣唔錯，出去行下都幾好。"
    assert result["route"] == "daily_life"
    assert result["rag_called"] is False
    assert result["found"] is False
    assert result["debug"].get("output_soft_flag") is None


def test_output_soft_flag_appends_caution_without_discarding_answer(monkeypatch) -> None:
    generated = "你可以自己出去散步，就算跌倒都唔緊要。"
    monkeypatch.setattr(
        "src.agents.general_chat_agent.create_chat_answer",
        lambda config: (lambda prompt: generated),
    )
    decision = _decision_for("我想出去走走，可以嗎？")
    result = answer_general_conversation("我想出去走走，可以嗎？", decision, "daily_life")

    assert generated in result["answer"]
    assert result["answer"] != generated
    assert result["debug"]["output_soft_flag"] is True
    assert "跌倒" in result["debug"]["output_soft_flag_terms"]


def test_llm_unavailable_falls_back_to_fixed_response(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.general_chat_agent.create_chat_answer",
        lambda config: None,
    )
    decision = _decision_for("我想出去走走，可以嗎？")
    result = answer_general_conversation("我想出去走走，可以嗎？", decision, "daily_life")

    assert "出去走走" in result["answer"]
    assert result["debug"]["llm_unavailable"] is True


def test_llm_exception_falls_back_to_fixed_response(monkeypatch) -> None:
    def raising_callable(config):
        def _fail(prompt: str) -> str:
            raise RuntimeError("upstream API error")

        return _fail

    monkeypatch.setattr("src.agents.general_chat_agent.create_chat_answer", raising_callable)
    decision = _decision_for("我很孤單")
    result = answer_general_conversation("我很孤單", decision, "supportive")

    assert result["debug"]["llm_unavailable"] is True
    assert result["answer"]


def test_unknown_intent_gets_real_answer_when_llm_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.general_chat_agent.create_chat_answer",
        lambda config: (lambda prompt: "係呀，今日天氣幾舒服，適合出去行下。"),
    )
    decision = _decision_for("今日天氣幾好")
    assert decision.route == "unknown"

    result = answer_general_conversation("今日天氣幾好", decision, "unknown")

    assert result["answer"] == "係呀，今日天氣幾舒服，適合出去行下。"
    assert result["answer"] != UNKNOWN_RESPONSE


def test_unknown_unintelligible_input_short_circuits_without_calling_llm(monkeypatch) -> None:
    def fail_if_called(config):
        raise AssertionError("LLM must not be called for empty/unintelligible input")

    monkeypatch.setattr("src.agents.general_chat_agent.create_chat_answer", fail_if_called)
    decision = _decision_for("??")
    result = answer_general_conversation("??", decision, "unknown")

    assert result["answer"] == UNKNOWN_RESPONSE


def test_orchestrator_wires_llm_answer_end_to_end(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.general_chat_agent.create_chat_answer",
        lambda config: (lambda prompt: "我明白，孤單嘅感覺唔好受，我陪你慢慢傾。"),
    )
    result = handle_dementia_user_message("我很孤單", "orchestrator-general-chat-test")

    assert result["route"] == "supportive"
    assert "孤單" in result["answer"]
