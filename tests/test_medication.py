
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
                "caregivers": [{"name": "Maria"}, {"name": "嘉欣"}],
                "emergency_number": "999",
                "primary_language": "Cantonese",
            },
        },
    )

    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "medication_safety"
    assert result["debug"]["normal_rag_skipped"] is True
    assert "根據資料庫" not in result["answer"]
    assert "來源：" not in result["answer"]
    assert "不能提供關於阿司匹林的用藥建議" in result["answer"]
    assert "醫生" in result["answer"]
    assert "藥劑師" in result["answer"]
    assert "Maria" in result["answer"]
    assert "嘉欣" in result["answer"]
    assert result["detected_medicines"][0]["canonical_name"] == "aspirin"


def test_medication_response_mentions_red_flags() -> None:
    response = build_medication_safety_response(
        patient_profile={
            "preferred_name": "眉眉婆婆",
            "caregivers": [{"name": "Maria"}, {"name": "嘉欣"}],
            "emergency_number": "999",
            "primary_language": "Cantonese",
        },
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=["胸口痛"],
    )

    assert "眉眉婆婆" in response
    assert "Maria" in response
    assert "嘉欣" in response
    assert "999" in response
    assert "不能提供關於阿司匹林的用藥建議" in response


def test_medication_response_does_not_recommend_yes_or_no() -> None:
    response = build_medication_safety_response(
        patient_profile={
            "preferred_name": "眉眉婆婆",
            "caregivers": [{"name": "Maria"}, {"name": "嘉欣"}],
            "emergency_number": "999",
            "primary_language": "Cantonese",
        },
        detected_medicines=[{"canonical_name": "aspirin", "matched_alias": "阿司匹林"}],
        red_flags=[],
    )

    unsafe_phrases = [
        "可以食阿司匹林",
        "唔可以食阿司匹林",
        "唔建議你食阿司匹林",
        "食一粒",
        "食半粒",
        "take aspirin",
        "you can take",
        "you should take",
        "you should not take",
        "不要自己吃",
        "唔好自己食",
    ]

    for phrase in unsafe_phrases:
        assert phrase.lower() not in response.lower()


# Medicine normalization

from src.meds.medicine_normalizer import normalize_medicine_mentions


def test_normalize_aspirin_chinese() -> None:
    meds = normalize_medicine_mentions("可以食阿司匹林嗎？")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_aspirin_hk_variant() -> None:
    meds = normalize_medicine_mentions("可以食亞士匹靈嗎？")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_asa() -> None:
    meds = normalize_medicine_mentions("Can I take ASA?")
    assert any(m["canonical_name"] == "aspirin" for m in meds)


def test_normalize_panadol() -> None:
    meds = normalize_medicine_mentions("可以食必理痛嗎？")
    assert any(m["canonical_name"] == "paracetamol" for m in meds)


def test_normalize_donepezil_brand() -> None:
    meds = normalize_medicine_mentions("Can I stop Aricept?")
    assert any(m["canonical_name"] == "donepezil" for m in meds)


# Short medication responses

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
