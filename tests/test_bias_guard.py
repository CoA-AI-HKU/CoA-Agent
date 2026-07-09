from __future__ import annotations

from src.agents.coordinator_agent import infer_user_role
from src.orchestrator import handle_dementia_user_message


BLOCKED_ASSUMPTIONS = [
    "因為你有腦退化症",
    "你的腦退化症",
    "作為腦退化症患者",
    "因為你記性不好",
    "你的照顧者",
    "你有記憶力問題",
    "你需要照顧者",
    "你不能自己",
    "你無能力",
]


def _assert_no_blocked_assumptions(answer: str) -> None:
    for phrase in BLOCKED_ASSUMPTIONS:
        assert phrase not in answer


def test_user_role_defaults_to_unknown() -> None:
    assert infer_user_role("") == "unknown"
    assert infer_user_role("下午三點") == "unknown"
    assert infer_user_role("我唔記得我食咗藥未") == "unknown"
    assert infer_user_role("我忘記了今天要做什麼") == "unknown"


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
    assert (
        "不要自行再服一次" in result["answer"]
        or "唔好自行補食" in result["answer"]
        or "不要自行补吃" in result["answer"]
    )
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


def test_final_answer_removes_memory_caregiver_and_capacity_assumptions(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": (
                "你有記憶力問題，所以你需要照顧者。"
                "你不能自己處理這件事，因為你無能力判斷。"
            ),
            "found": True,
            "sources": ["care.md"],
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("記憶力有什麼支援方法？")

    _assert_no_blocked_assumptions(result["answer"])
    assert "如有需要，可以請家人、照顧者或醫護人員協助" in result["answer"]


def test_memory_concern_uses_neutral_template_without_sources() -> None:
    result = handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")
    answer = result["answer"]

    assert result["route"] == "memory_concern"
    assert "來源" not in answer
    assert ".md" not in answer
    assert "資料庫" not in answer
    assert "腦退化症好常見" not in answer
    assert "病情" not in answer
    assert "你之前都問過" not in answer
    assert "手機提醒" in answer
    assert "固定位置" in answer
    assert "醫生" in answer or "醫護人員" in answer
    assert "影響日常生活" in answer


def test_repeated_memory_concern_is_not_called_out() -> None:
    handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")
    second = handle_dementia_user_message("我最近覺得很多事情好像都有點記不住")

    assert "你之前都問過" not in second["answer"]
    assert "你重複問" not in second["answer"]
    assert "重複" not in second["answer"]


def test_am_i_dementia_is_non_diagnostic_and_recommends_assessment() -> None:
    result = handle_dementia_user_message("我是不是有腦退化症？")
    answer = result["answer"]

    assert "不能判斷" in answer
    assert "醫生" in answer or "記憶診所" in answer
    assert "作評估" in answer or "評估" in answer
    assert "你有腦退化症" not in answer
    assert "確診" not in answer


def test_explicit_disclosure_memory_concern_has_no_source_or_stigma() -> None:
    result = handle_dementia_user_message("醫生話我有腦退化症，我最近成日唔記得嘢")
    answer = result["answer"]

    assert "來源" not in answer
    assert ".md" not in answer
    assert "資料庫" not in answer
    assert "作為腦退化症患者" not in answer
    assert "病情" not in answer
    assert "你之前都問過" not in answer
