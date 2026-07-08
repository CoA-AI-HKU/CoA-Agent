from __future__ import annotations

from src.agents.coordinator_agent import infer_user_role
from src.orchestrator import handle_dementia_user_message


BLOCKED_ASSUMPTIONS = [
    "因為你有腦退化症",
    "你的腦退化症",
    "作為腦退化症患者",
    "因為你記性不好",
    "你的照顧者",
]


def _assert_no_blocked_assumptions(answer: str) -> None:
    for phrase in BLOCKED_ASSUMPTIONS:
        assert phrase not in answer


def test_user_role_defaults_to_unknown() -> None:
    assert infer_user_role("") == "unknown"
    assert infer_user_role("下午三點") == "unknown"


def test_general_dementia_question_does_not_assume_user_has_dementia(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "腦退化症會影響記憶和日常生活。你有腦退化症時，你的照顧者可以協助。",
            "found": True,
            "sources": ["dementia.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    assert "腦退化症" in result["answer"]
    _assert_no_blocked_assumptions(result["answer"])
    assert "你有腦退化症" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "general_user"


def test_older_adult_daily_question_stays_neutral() -> None:
    result = handle_dementia_user_message("我今日要做咩？")

    _assert_no_blocked_assumptions(result["answer"])
    assert "腦退化" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "unknown"


def test_caregiver_question_refers_to_family_not_speaker(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "如果這是腦退化症照顧情境，家人重複提問時可以保持平靜，回應媽媽的感受。",
            "found": True,
            "sources": ["care.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("我媽媽成日重複問同一條問題，我應該點做？")

    assert "媽媽" in result["answer"] or "家人" in result["answer"]
    assert "你有腦退化症" not in result["answer"]
    assert "你的腦退化症" not in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "caregiver_or_family"


def test_medication_uncertainty_does_not_invent_dementia_context() -> None:
    result = handle_dementia_user_message("我唔知我食咗藥未")

    _assert_no_blocked_assumptions(result["answer"])
    assert "唔好自行補食" in result["answer"] or "不要自行补吃" in result["answer"]
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]


def test_explicit_self_disclosure_can_be_acknowledged_without_stigma(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "你有腦退化症這個情況時，可以用固定時間和清楚提示幫自己記得食飯。因為你記性不好，要小心。",
            "found": True,
            "sources": ["routine.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("醫生話我有腦退化症，我成日唔記得食飯")

    assert "你有腦退化症" in result["answer"]
    assert "因為你記性不好" not in result["answer"]
    assert "可以" in result["answer"]
    assert result["debug"]["coordinator"]["user_role"] == "self_with_cognitive_concern"
