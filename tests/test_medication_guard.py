from __future__ import annotations

from src.pipeline.rag_agent import answer_question
from src.safety.medication_guard import (
    build_medication_safety_response,
    detect_red_flags,
    is_medication_decision_question,
)


def test_aspirin_cantonese_triggers_guard() -> None:
    assert is_medication_decision_question("頭痛可以食阿司匹林嗎？")


def test_painkiller_cantonese_triggers_guard() -> None:
    assert is_medication_decision_question("我可唔可以食止痛藥？")


def test_double_dose_triggers_guard() -> None:
    assert is_medication_decision_question("我唔記得食咗藥未，可唔可以食多次？")


def test_english_aspirin_triggers_guard() -> None:
    assert is_medication_decision_question("Can I take aspirin for my headache?")


def test_stop_medication_triggers_guard() -> None:
    assert is_medication_decision_question("Can I stop taking donepezil?")


def test_red_flags_detected() -> None:
    assert "chest pain" in detect_red_flags("Can I take aspirin if I have chest pain?")
    assert "講嘢唔清楚" in detect_red_flags("我頭痛，講嘢唔清楚，可以食藥嗎？")


def test_medication_decision_questions_skip_normal_rag(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Medication guardrail must run before normal RAG")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    result = answer_question(
        "頭痛可以食阿司匹林嗎？",
        {
            "chroma_dir": tmp_path / "chroma",
            "auto_index": False,
            "patient_profile": {
                "preferred_name": "眉眉婆婆",
                "caregivers": [{"name": "嘉欣"}, {"name": "Maria"}],
                "emergency_number": "999",
                "primary_language": "Cantonese",
            },
        },
    )

    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "medication_safety"
    assert result["debug"]["normal_rag_skipped"] is True
    assert "我唔可以幫你決定" in result["answer"]
    assert "唔好自己加藥" in result["answer"]
    assert "醫生" in result["answer"]
    assert "藥劑師" in result["answer"]
    assert "嘉欣" in result["answer"]
    assert "Maria" in result["answer"]
    assert result["detected_medicines"][0]["canonical_name"] == "aspirin"


def test_medication_response_mentions_red_flags() -> None:
    response = build_medication_safety_response(
        patient_profile={
            "preferred_name": "眉眉婆婆",
            "caregivers": [{"name": "嘉欣"}, {"name": "Maria"}],
            "emergency_number": "999",
            "primary_language": "Cantonese",
        },
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=["胸口痛"],
    )

    assert "眉眉婆婆" in response
    assert "嘉欣" in response
    assert "Maria" in response
    assert "999" in response
    assert "緊急服務" in response


def test_medication_response_does_not_recommend_yes_or_no() -> None:
    patient_profile = {
        "preferred_name": "眉眉婆婆",
        "caregivers": [
            {"name": "嘉欣", "relationship": "daughter"},
            {"name": "Maria", "relationship": "live-in caregiver"},
        ],
        "emergency_number": "999",
        "primary_language": "Cantonese",
    }

    response = build_medication_safety_response(
        patient_profile=patient_profile,
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=[],
    )

    unsafe_phrases = [
        "可以食阿司匹林",
        "唔建議你食阿司匹林",
        "食一粒",
        "take aspirin",
        "you can take",
        "you should take",
        "you should not take",
    ]

    for phrase in unsafe_phrases:
        assert phrase.lower() not in response.lower()
