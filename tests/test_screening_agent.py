from __future__ import annotations

from src.intent_router import classify_intent
from src.orchestrator import handle_dementia_user_message


def _assert_no_diagnosis(answer: str) -> None:
    blocked = ["你有腦退化症", "你可能有腦退化症", "你很可能有腦退化症", "風險百分比", "risk score"]
    for phrase in blocked:
        assert phrase not in answer


def test_self_screening_question_routes_to_check_in() -> None:
    intent = classify_intent("我是不是有腦退化症？")
    result = handle_dementia_user_message("我是不是有腦退化症？")

    assert intent.intent == "self_memory_concern"
    assert result["route"] == "memory_concern"
    assert result["intent"] == "self_memory_concern"
    assert "不能判斷是不是腦退化症" in result["answer"]
    assert "醫生或記憶診所" in result["answer"]
    _assert_no_diagnosis(result["answer"])


def test_caregiver_screening_question_uses_family_framing() -> None:
    result = handle_dementia_user_message("我媽媽最近成日唔記得嘢，係咪腦退化？")

    assert result["route"] == "screening"
    assert "你的家人" in result["answer"] or "家人" in result["answer"]
    assert "你可以觀察" in result["answer"]
    assert "影響日常生活或安全" in result["answer"]
    assert "醫生或記憶診所評估" in result["answer"]
    assert "你有腦退化症" not in result["answer"]


def test_urgent_red_flag_gets_safety_escalation() -> None:
    result = handle_dementia_user_message("爸爸今天突然很混亂，還說看見不存在的人")

    assert result["route"] == "safety"
    assert result["safety_level"] == "urgent_boundary"
    assert "請盡快求醫" in result["answer"] or "緊急服務" in result["answer"]
    assert "不應只當作一般記憶問題處理" in result["answer"]


def test_stress_related_memory_concern_does_not_over_pathologize() -> None:
    result = handle_dementia_user_message("我最近壓力好大，偶爾忘記東西")

    assert result["route"] == "screening"
    assert "未必一定是腦退化症" in result["answer"]
    assert "壓力" in result["answer"]
    assert "睡眠不足" in result["answer"]
    assert "持續或變嚴重" in result["answer"]
    _assert_no_diagnosis(result["answer"])


def test_formal_test_request_offers_check_in_not_score() -> None:
    result = handle_dementia_user_message("我想做一個腦退化症測試")

    assert result["route"] == "screening"
    assert "我不能判斷你是否有腦退化症" in result["answer"]
    assert "進一步評估" in result["answer"]
    assert "1." in result["answer"]
    assert "分數" not in result["answer"]
    assert "風險" not in result["answer"]
    _assert_no_diagnosis(result["answer"])
