from __future__ import annotations

import re
from typing import Any, Iterable


ENGLISH_DECISION_PATTERNS = [
    r"\bcan i take\b",
    r"\bshould i take\b",
    r"\bcan .* take\b",
    r"\bshould .* take\b",
    r"\btake aspirin\b",
    r"\bdosage\b",
    r"\bdose\b",
    r"\bmissed dose\b",
    r"\bdouble dose\b",
    r"\bmedicine\b",
    r"\bmedication\b",
]

CHINESE_DECISION_TERMS = [
    "可唔可以食",
    "可以食",
    "要唔要食",
    "食幾多",
    "食多次",
    "藥",
    "止痛藥",
    "阿司匹林",
    "亞士匹靈",
    "阿士匹靈",
    "阿斯匹靈",
]

RED_FLAG_TERMS = [
    "胸痛",
    "心口痛",
    "呼吸困難",
    "氣促",
    "昏迷",
    "暈倒",
    "中風",
    "半身無力",
    "口齒不清",
    "嚴重敏感",
    "面腫",
    "喉嚨腫",
    "大量出血",
    "食多咗",
    "過量",
    "overdose",
    "chest pain",
    "trouble breathing",
    "shortness of breath",
    "fainted",
    "stroke",
    "severe allergic",
    "swelling",
    "heavy bleeding",
]


def is_medication_decision_question(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in ENGLISH_DECISION_PATTERNS):
        return True
    return any(term in text for term in CHINESE_DECISION_TERMS)


def build_medication_safety_response(
    patient_profile: Any,
    detected_medicines: Iterable[Any],
    symptoms: Any,
    caregiver_available: bool,
) -> str:
    caregiver_names = _caregiver_names(patient_profile)
    current_medications = _current_medication_names(patient_profile)
    medicine_names = _medicine_names(detected_medicines)
    has_red_flags = _has_red_flags(symptoms)
    language = _profile_language(patient_profile)

    if language not in {"cantonese", "zh-hk", "yue", "chinese"}:
        return _english_response(medicine_names, current_medications, caregiver_names, caregiver_available, has_red_flags)

    lines = [
        "我唔能夠決定你應唔應該食呢隻藥，亦唔可以提供停藥、加藥、重複食藥或改劑量建議。",
        "請唔好自己加藥、食多次、停藥、改藥量，或者將藥物混埋一齊食。",
    ]
    if medicine_names:
        lines.append(f"你提到嘅藥物包括：{', '.join(medicine_names)}。呢啲都需要由醫生、藥劑師或合資格醫護人員確認。")
    if current_medications:
        lines.append(f"如果服藥紀錄入面有以下藥物，請一齊核對：{', '.join(current_medications)}。")
    if caregiver_names:
        lines.append(f"可以先聯絡照顧者：{', '.join(caregiver_names)}，一齊核對藥袋、覆診紙或服藥紀錄。")
    elif caregiver_available:
        lines.append("如果身邊有照顧者，請先搵佢一齊核對藥袋、覆診紙或服藥紀錄。")
    else:
        lines.append("請盡快聯絡醫生、藥劑師或合資格醫護人員，並核對藥袋、覆診紙或服藥紀錄。")
    if has_red_flags:
        lines.append("如果有胸痛、呼吸困難、昏迷、嚴重敏感、懷疑食多咗藥或其他危急情況，請即刻求助緊急服務。")
    return "\n".join(lines)


def _english_response(
    medicine_names: list[str],
    current_medications: list[str],
    caregiver_names: list[str],
    caregiver_available: bool,
    has_red_flags: bool,
) -> str:
    lines = [
        "I cannot decide whether the patient should take this medicine or give stop, add, repeat, mix, or dosage advice.",
        "Please do not self-medicate or change medicines without professional confirmation.",
    ]
    if medicine_names:
        lines.append(f"Medicines mentioned: {', '.join(medicine_names)}.")
    if current_medications:
        lines.append(f"If these are in the medication record, check them together: {', '.join(current_medications)}.")
    if caregiver_names:
        lines.append(f"Please contact the caregiver first: {', '.join(caregiver_names)}, and check the medication record if available.")
    elif caregiver_available:
        lines.append("Please contact the caregiver and check the medication record if available.")
    else:
        lines.append("Please contact a doctor, pharmacist, or qualified healthcare professional and check the medication record if available.")
    if has_red_flags:
        lines.append("If there are red-flag symptoms such as chest pain, trouble breathing, fainting, severe allergy, suspected overdose, or heavy bleeding, seek emergency help immediately.")
    return "\n".join(lines)


def _profile_language(patient_profile: Any) -> str:
    if isinstance(patient_profile, dict):
        value = patient_profile.get("language") or patient_profile.get("preferred_language")
        if value:
            return str(value).strip().lower()
    return "cantonese"


def _caregiver_names(patient_profile: Any) -> list[str]:
    if not isinstance(patient_profile, dict):
        return []
    caregivers = patient_profile.get("caregivers") or patient_profile.get("caregiver_names") or []
    if isinstance(caregivers, str):
        return [caregivers]
    names: list[str] = []
    if isinstance(caregivers, list):
        for caregiver in caregivers:
            if isinstance(caregiver, str) and caregiver.strip():
                names.append(caregiver.strip())
            elif isinstance(caregiver, dict):
                name = caregiver.get("name") or caregiver.get("display_name")
                if name:
                    names.append(str(name).strip())
    return names


def _current_medication_names(patient_profile: Any) -> list[str]:
    if not isinstance(patient_profile, dict):
        return []
    medications = patient_profile.get("current_medications") or patient_profile.get("medications") or []
    if isinstance(medications, str):
        return [medications]
    names: list[str] = []
    if isinstance(medications, list):
        for medication in medications:
            if isinstance(medication, str) and medication.strip():
                names.append(medication.strip())
            elif isinstance(medication, dict):
                name = medication.get("name") or medication.get("canonical_name")
                if name:
                    names.append(str(name).strip())
    return names


def _medicine_names(detected_medicines: Iterable[Any]) -> list[str]:
    names: list[str] = []
    for medicine in detected_medicines:
        name = getattr(medicine, "canonical_name", None)
        if name is None and isinstance(medicine, dict):
            name = medicine.get("canonical_name") or medicine.get("name")
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _has_red_flags(symptoms: Any) -> bool:
    if symptoms is None:
        return False
    if isinstance(symptoms, str):
        text = symptoms
    elif isinstance(symptoms, Iterable):
        text = " ".join(str(item) for item in symptoms)
    else:
        text = str(symptoms)
    normalized = text.lower()
    return any(term in text or term in normalized for term in RED_FLAG_TERMS)
