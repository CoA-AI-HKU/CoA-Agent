from __future__ import annotations

from src.pipeline.rag_agent import answer_question
from src.safety.medication_guard import build_medication_safety_response, is_medication_decision_question


MEDICATION_DECISION_QUESTIONS = [
    "可以食阿司匹林嗎？",
    "頭痛可以食止痛藥嗎？",
    "I have a headache, can I take aspirin?",
    "I forgot my medicine, should I take another dose?",
    "我唔記得食咗藥未，可唔可以食多次？",
]


def test_medication_decision_questions_trigger_guard() -> None:
    for question in MEDICATION_DECISION_QUESTIONS:
        assert is_medication_decision_question(question), question


def test_medication_decision_questions_skip_normal_rag(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Medication guardrail must run before normal RAG")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    for question in MEDICATION_DECISION_QUESTIONS:
        result = answer_question(question, {"chroma_dir": tmp_path / "chroma", "auto_index": False})

        assert result["found"] is False
        assert result["sources"] == []
        assert result["debug"]["boundary_handler"] == "medication_safety"
        assert result["debug"]["normal_rag_skipped"] is True
        assert "唔能夠決定" in result["answer"]
        assert "請唔好自己" in result["answer"]
        assert "醫生" in result["answer"]
        assert "藥劑師" in result["answer"]


def test_medication_response_mentions_caregiver_and_red_flags() -> None:
    response = build_medication_safety_response(
        patient_profile={
            "language": "cantonese",
            "caregivers": [{"name": "阿明"}],
            "current_medications": ["donepezil"],
        },
        detected_medicines=[],
        symptoms=["胸痛"],
        caregiver_available=True,
    )

    assert "阿明" in response
    assert "donepezil" in response
    assert "緊急服務" in response
