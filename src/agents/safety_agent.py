from __future__ import annotations

from src.agents.types import AgentDecision, AgentResult
from src.pipeline.language import detect_answer_language
from src.safety.medication_guard import build_short_medication_safety_response, detect_red_flags
from src.meds.medicine_normalizer import normalize_medicine_mentions


SAFETY_RESPONSES = {
    "zh-Hant": "這個情況可能需要即時協助。請先確保安全，並盡快聯絡照顧者、醫護人員或緊急服務。",
    "zh-Hans": "这个情况可能需要即时协助。请先确保安全，并尽快联系照顾者、医护人员或紧急服务。",
    "en": "This situation may need immediate help. Please make sure everyone is safe and contact a caregiver, clinician, or emergency services as soon as possible.",
}

MEDICAL_BOUNDARY_RESPONSES = {
    "zh-Hant": "我不能提供診斷或任何用藥建議。請詢問醫生、藥劑師或合資格醫護人員。",
    "zh-Hans": "我不能提供诊断或任何用药建议。请询问医生、药剂师或合资格医护人员。",
    "en": "I can't provide diagnosis or any medication advice. Please ask a doctor, pharmacist, or qualified clinician.",
}


def handle_safety(message: str, decision: AgentDecision) -> dict:
    answer_language = detect_answer_language(message)
    return AgentResult(
        answer=SAFETY_RESPONSES[answer_language],
        intent=decision.intent,
        safety_level="urgent_boundary",
        found=False,
        sources=[],
        rag_called=False,
        route="safety",
        debug={"agent": "safety", "answer_language": answer_language},
    ).to_dict()


def handle_medical_boundary(message: str, decision: AgentDecision) -> dict:
    answer_language = detect_answer_language(message)
    detected_medicines = normalize_medicine_mentions(message)
    red_flags = detect_red_flags(message)
    if detected_medicines or red_flags:
        answer = build_short_medication_safety_response(
            patient_profile={},
            detected_medicines=detected_medicines,
            red_flags=red_flags,
            answer_language=answer_language,
        )
    else:
        answer = MEDICAL_BOUNDARY_RESPONSES[answer_language]

    return AgentResult(
        answer=answer,
        intent=decision.intent,
        safety_level="medical_boundary",
        found=False,
        sources=[],
        rag_called=False,
        route="medical_boundary",
        debug={
            "agent": "safety",
            "answer_language": answer_language,
            "detected_medicines": detected_medicines,
            "red_flags": red_flags,
        },
    ).to_dict()
