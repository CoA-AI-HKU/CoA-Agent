from __future__ import annotations

import re
from typing import Any

from ..pipeline.language import AnswerLanguage


ENGLISH_DECISION_PATTERNS = [
    r"\bcan i take\b",
    r"\bshould i take\b",
    r"\bis it safe to take\b",
    r"\bcan i stop\b",
    r"\bshould i stop\b",
    r"\bmissed dose\b",
    r"\bdouble dose\b",
    r"\btake another\b",
    r"\bdosage\b",
    r"\bdose\b",
    r"\bmix with\b",
    r"\bmedicine\b",
    r"\bmedication\b",
    r"\bpainkiller\b",
]

CHINESE_DECISION_TERMS = [
    "可唔可以食",
    "可以食",
    "應唔應該食",
    "要唔要食",
    "食唔食得",
    "食幾多",
    "食多次",
    "加藥",
    "停藥",
    "改藥",
    "藥",
    "止痛藥",
    "頭痛藥",
    "阿司匹林",
    "亞士匹靈",
    "阿士匹靈",
    "阿斯匹靈",
]

RED_FLAG_TERMS = [
    "severe headache",
    "sudden headache",
    "worst headache",
    "chest pain",
    "shortness of breath",
    "difficulty breathing",
    "weakness",
    "numbness",
    "vomiting",
    "blurred vision",
    "vision loss",
    "fainted",
    "fell",
    "fall",
    "took extra",
    "overdose",
    "好劇烈",
    "突然好痛",
    "突然頭好痛",
    "胸口痛",
    "呼吸困難",
    "手腳無力",
    "半邊身",
    "講嘢唔清楚",
    "睇嘢模糊",
    "睇唔清",
    "視力模糊",
    "嘔",
    "暈",
    "跌倒",
    "食多咗藥",
    "食錯藥",
    "過量",
]


def is_medication_decision_question(text: str) -> bool:
    """
    Return True if the user asks whether they can take, stop, repeat,
    add, mix, or change the dose of medication.
    """
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in ENGLISH_DECISION_PATTERNS):
        return True
    return any(term in text for term in CHINESE_DECISION_TERMS)


def detect_red_flags(text: str) -> list[str]:
    """Return detected emergency warning signs."""
    normalized = " ".join(text.lower().split())
    matches: list[str] = []
    for term in RED_FLAG_TERMS:
        haystack = normalized if _is_ascii(term) else text
        needle = term.lower() if _is_ascii(term) else term
        if needle in haystack and term not in matches:
            matches.append(term)
    return matches


def build_short_medication_safety_response(
    patient_profile: dict,
    detected_medicines: list[dict],
    red_flags: list[str],
    answer_language: AnswerLanguage = "zh-Hant",
) -> str:
    """
    Build the final short medication-safety response.
    This function controls the final wording and does not call RAG/LLM.
    """
    name = _get_patient_name(patient_profile)
    caregivers = _get_caregiver_text(patient_profile)
    emergency_number = _get_emergency_number(patient_profile)
    medicine = _get_medicine_display(detected_medicines)

    if answer_language == "en":
        if red_flags:
            return (
                f"{name}, I can't give medication advice about {medicine}.\n\n"
                f"Please contact {caregivers}, a doctor, or a pharmacist now. "
                f"If there are severe or sudden symptoms, call {emergency_number}."
            )
        return (
            f"{name}, I can't give medication advice about {medicine}.\n\n"
            f"Please ask {caregivers}, a doctor, or a pharmacist."
        )

    if answer_language == "zh-Hans":
        if red_flags:
            return (
                f"{name}，我不能提供关于{medicine}的用药建议。\n\n"
                f"请现在联系 {caregivers}、医生或药剂师。"
                f"如果有突然或严重症状，请打 {emergency_number}。"
            )
        return (
            f"{name}，我不能提供关于{medicine}的用药建议。\n\n"
            f"请询问 {caregivers}、医生或药剂师。"
        )

    if red_flags:
        return (
            f"{name}，我不能提供關於{medicine}的用藥建議。\n\n"
            f"請現在聯絡 {caregivers}、醫生或藥劑師。"
            f"如果有突然或嚴重症狀，請打 {emergency_number}。"
        )

    return (
        f"{name}，我不能提供關於{medicine}的用藥建議。\n\n"
        f"請詢問 {caregivers}、醫生或藥劑師。"
    )


def build_medication_safety_response(
    patient_profile: dict,
    detected_medicines: list[dict],
    red_flags: list[str],
    answer_language: AnswerLanguage = "zh-Hant",
) -> str:
    return build_short_medication_safety_response(patient_profile, detected_medicines, red_flags, answer_language)


def _get_patient_name(patient_profile: dict) -> str:
    if not isinstance(patient_profile, dict):
        return "你"
    return str(patient_profile.get("preferred_name") or patient_profile.get("name") or "你").strip()


def _get_caregiver_text(patient_profile: dict) -> str:
    if not isinstance(patient_profile, dict):
        return "照顧者"
    caregivers = patient_profile.get("caregivers", [])
    if isinstance(caregivers, str):
        return caregivers.strip() or "照顧者"
    names = []
    if isinstance(caregivers, list):
        for caregiver in caregivers:
            if isinstance(caregiver, dict) and caregiver.get("name"):
                names.append(str(caregiver["name"]).strip())
            elif isinstance(caregiver, str) and caregiver.strip():
                names.append(caregiver.strip())
    names = [name for name in names if name]
    if not names:
        return "照顧者"
    if len(names) == 1:
        return names[0]
    return " 或 ".join(names[:2])


def _get_emergency_number(patient_profile: dict) -> str:
    if isinstance(patient_profile, dict) and patient_profile.get("emergency_number"):
        return str(patient_profile["emergency_number"]).strip()
    return "999"


def _get_medicine_display(detected_medicines: list[dict]) -> str:
    if detected_medicines:
        medicine = detected_medicines[0]
        return str(medicine.get("matched_alias") or medicine.get("canonical_name") or "呢隻藥")
    return "呢隻藥"


def _is_ascii(text: str) -> bool:
    return all(ord(char) < 128 for char in text)
