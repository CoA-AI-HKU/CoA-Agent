from __future__ import annotations

from src.safety.medication_guard import (
    build_short_medication_safety_response,
    detect_red_flags,
    is_medication_decision_question,
)


def test_medication_question_bypasses_rag() -> None:
    assert is_medication_decision_question("頭痛可以食阿司匹林嗎？")
    assert is_medication_decision_question("我唔記得食咗藥未，可唔可以食多次？")
    assert is_medication_decision_question("Can I take aspirin?")


def test_short_medication_response_no_rag_summary() -> None:
    patient_profile = {
        "preferred_name": "眉眉婆婆",
        "caregivers": [{"name": "Maria"}, {"name": "嘉欣"}],
        "emergency_number": "999",
        "primary_language": "Cantonese",
    }

    response = build_short_medication_safety_response(
        patient_profile=patient_profile,
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=[],
    )

    banned = [
        "根據資料庫",
        "資料庫",
        "來源：",
        "dementia-medications.md",
        "what-is-dementia.md",
        "Donepezil 嘅副作用包括",
        "如果你想食",
        "可以食阿司匹林",
        "唔可以食阿司匹林",
        "唔建議你食阿司匹林",
        "食一粒",
        "食半粒",
        "好大機會係",
        "一定係",
    ]

    for phrase in banned:
        assert phrase not in response

    required = [
        "不能提供關於阿司匹林的用藥建議",
        "醫生",
        "藥劑師",
    ]

    for phrase in required:
        assert phrase in response

    assert len(response) <= 140


def test_red_flag_response_mentions_emergency() -> None:
    patient_profile = {
        "preferred_name": "眉眉婆婆",
        "caregivers": [{"name": "Maria"}, {"name": "嘉欣"}],
        "emergency_number": "999",
        "primary_language": "Cantonese",
    }

    red_flags = detect_red_flags("我突然頭好痛，仲睇嘢模糊")
    response = build_short_medication_safety_response(
        patient_profile=patient_profile,
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=red_flags,
    )

    assert "999" in response
    assert "突然或嚴重症狀" in response
