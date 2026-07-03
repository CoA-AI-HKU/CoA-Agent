from __future__ import annotations

from src.orchestrator import handle_dementia_user_message


def test_knowledge_question_calls_rag(monkeypatch) -> None:
    calls = []

    def fake_answer_question(message, config):
        calls.append((message, config))
        return {
            "answer": "腦退化症可能影響記憶、思考和日常生活。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症有什麼症狀？")

    assert calls
    assert result["intent"] == "knowledge_qa"
    assert result["rag_called"] is True
    assert result["safety_level"] == "normal"
    assert result["debug"]["source_count"] == 1


def test_medication_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Medication boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我可不可以幫媽媽停藥？")

    assert result["intent"] == "medication_or_diagnosis"
    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"
    assert result["sources"] == []


def test_english_medication_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Medication boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("Can I take aspirin?")

    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"
    assert result["answer_language"] == "en"
    assert "any medication advice" in result["answer"]


def test_safety_question_does_not_call_normal_rag(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Safety boundary route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("媽媽走失了，我找不到她")

    assert result["intent"] == "safety_sensitive"
    assert result["rag_called"] is False
    assert result["safety_level"] == "urgent_boundary"
    assert result["sources"] == []


def test_cognitive_activity_returns_activity_response(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Activity placeholder route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我好悶，有什麼可以做？")

    assert result["intent"] == "cognitive_activity"
    assert result["rag_called"] is False
    assert "三種水果" in result["answer"]
    assert result["answer_language"] == "zh-Hant"


def test_static_responses_follow_simplified_input(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Static activity route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("我好无聊，有什么可以做？")

    assert result["intent"] == "cognitive_activity"
    assert result["answer_language"] == "zh-Hans"
    assert "三种水果" in result["answer"]
    assert result["debug"]["answer_language"] == "zh-Hans"


def test_static_responses_follow_english_input(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Static activity route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("I am bored, what can I do?")

    assert result["intent"] == "cognitive_activity"
    assert result["answer_language"] == "en"
    assert "three fruits" in result["answer"]


def test_unknown_does_not_invent_dementia_knowledge(monkeypatch) -> None:
    def fail_answer_question(message, config):
        raise AssertionError("Unknown route must not call normal RAG")

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fail_answer_question)

    result = handle_dementia_user_message("幫我寫一首歌")

    assert result["intent"] == "unknown"
    assert result["rag_called"] is False
    assert result["found"] is False
    assert "腦退化" not in result["answer"]
