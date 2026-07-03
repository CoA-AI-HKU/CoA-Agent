from __future__ import annotations

from src.orchestrator import handle_dementia_user_message


def test_knowledge_question_routes_to_rag(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "腦退化症會影響記憶和日常生活。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True
    assert result["debug"]["coordinator"]["route"] == "rag_qa"


def test_medication_question_routes_to_medical_boundary(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("我可不可以幫媽媽停藥？")

    assert result["route"] == "medical_boundary"
    assert result["rag_called"] is False
    assert result["safety_level"] == "medical_boundary"


def test_safety_question_routes_to_safety(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("媽媽走失了，我找不到她")

    assert result["route"] == "safety"
    assert result["rag_called"] is False
    assert result["safety_level"] == "urgent_boundary"


def test_reminder_question_routes_to_routine_placeholder() -> None:
    result = handle_dementia_user_message("提醒我下午三點飲水")

    assert result["route"] == "routine"
    assert result["rag_called"] is False


def test_personal_memory_routes_to_memory_placeholder() -> None:
    result = handle_dementia_user_message("我女兒叫什麼名字？")

    assert result["route"] == "memory"
    assert result["rag_called"] is False


def test_activity_routes_to_activity_agent() -> None:
    result = handle_dementia_user_message("我好悶，有什麼可以做？")

    assert result["route"] == "activity"
    assert result["rag_called"] is False


def test_unknown_does_not_call_rag(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda message, config: (_ for _ in ()).throw(AssertionError("RAG must not run")),
    )

    result = handle_dementia_user_message("幫我寫一首歌")

    assert result["route"] == "unknown"
    assert result["rag_called"] is False


def test_simplifier_preserves_medical_boundary() -> None:
    result = handle_dementia_user_message("我可以食多一粒藥嗎？")

    assert result["route"] == "medical_boundary"
    assert "不能提供" in result["answer"]
    assert "醫生" in result["answer"]
    assert "藥劑師" in result["answer"]
    assert result["debug"]["simplifier_applied"] is True
