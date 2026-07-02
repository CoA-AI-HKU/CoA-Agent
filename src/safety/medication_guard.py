from __future__ import annotations

import re
from typing import Any, Iterable


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
    "可不可以食",
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
    "worst headache",
    "severe headache",
    "sudden headache",
    "chest pain",
    "shortness of breath",
    "difficulty breathing",
    "weakness",
    "numbness",
    "confused",
    "vomiting",
    "vision loss",
    "blurred vision",
    "fainted",
    "fell",
    "fall",
    "took extra",
    "overdose",
    "好劇烈",
    "突然好痛",
    "胸口痛",
    "呼吸困難",
    "手腳無力",
    "半邊身",
    "講嘢唔清楚",
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
    normalized = " ".join(text.lower().split())
    if not normalized:
        return False
    if any(re.search(pattern, normalized) for pattern in ENGLISH_DECISION_PATTERNS):
        return True
    return any(term in text for term in CHINESE_DECISION_TERMS)


def detect_red_flags(text: str) -> list[str]:
    normalized = " ".join(text.lower().split())
    matches: list[str] = []
    for term in RED_FLAG_TERMS:
        haystack = normalized if _is_ascii(term) else text
        needle = term.lower() if _is_ascii(term) else term
        if needle in haystack and term not in matches:
            matches.append(term)
    return matches


def build_medication_safety_response(
    patient_profile: dict,
    detected_medicines: Iterable[Any],
    red_flags: list[str],
) -> str:
    patient_name = _preferred_name(patient_profile)
    caregiver_names = _caregiver_names(patient_profile)
    emergency_number = _emergency_number(patient_profile)
    medicine_names = _medicine_names(detected_medicines)
    language = _profile_language(patient_profile)

    if language not in {"cantonese", "zh-hk", "yue", "chinese", "traditional chinese"}:
        return _english_response(medicine_names, caregiver_names, emergency_number, red_flags)

    greeting = f"{patient_name}，" if patient_name else ""
    caregiver_text = " 或 ".join(caregiver_names) if caregiver_names else "照顧者"
    clinician_text = "醫生、藥劑師，或者照顧者"
    medicine_text = f"（你提到：{', '.join(medicine_names)}）" if medicine_names else ""

    response = (
        f"{greeting}我唔可以幫你決定可唔可以食、停、加、重複、混合，或者改劑量呢隻藥{medicine_text}，"
        f"因為呢個要由{clinician_text}幫你確認。"
        "你而家先唔好自己加藥、重複食藥、停藥，或者改藥量。"
        f"請叫 {caregiver_text} 幫你睇藥盒同藥物紀錄，再問醫生或藥劑師確認。"
    )
    if red_flags:
        response += (
            "如果頭痛突然好劇烈，或者有暈、嘔、睇嘢模糊、講嘢唔清楚、手腳無力、胸口痛、呼吸困難，"
            f"就即刻叫 {caregiver_text} 幫你打 {emergency_number}，或者即刻求助緊急服務。"
        )
    return response


def _english_response(
    medicine_names: list[str],
    caregiver_names: list[str],
    emergency_number: str,
    red_flags: list[str],
) -> str:
    caregiver_text = " or ".join(caregiver_names) if caregiver_names else "a caregiver"
    medicine_text = f" Mentioned medicine: {', '.join(medicine_names)}." if medicine_names else ""
    response = (
        "I cannot decide whether the patient should take, stop, add, repeat, mix, or change the dose of that medicine."
        f"{medicine_text} Please do not self-medicate, add medicine, repeat medicine, stop medicine, or change dosage. "
        f"Please ask {caregiver_text} to check the medication box and medication record, then confirm with a doctor or pharmacist."
    )
    if red_flags:
        response += f" If there are red-flag symptoms, seek urgent help or call emergency services at {emergency_number}."
    return response


def _preferred_name(patient_profile: Any) -> str:
    if not isinstance(patient_profile, dict):
        return ""
    value = patient_profile.get("preferred_name") or patient_profile.get("name") or patient_profile.get("display_name")
    return str(value).strip() if value else ""


def _profile_language(patient_profile: Any) -> str:
    if isinstance(patient_profile, dict):
        value = (
            patient_profile.get("primary_language")
            or patient_profile.get("language")
            or patient_profile.get("preferred_language")
        )
        if value:
            return str(value).strip().lower()
    return "cantonese"


def _caregiver_names(patient_profile: Any) -> list[str]:
    if not isinstance(patient_profile, dict):
        return []
    caregivers = patient_profile.get("caregivers") or patient_profile.get("caregiver_names") or []
    if isinstance(caregivers, str):
        return [caregivers.strip()] if caregivers.strip() else []
    names: list[str] = []
    if isinstance(caregivers, list):
        for caregiver in caregivers:
            if isinstance(caregiver, str) and caregiver.strip():
                names.append(caregiver.strip())
            elif isinstance(caregiver, dict):
                name = caregiver.get("name") or caregiver.get("display_name")
                if name and str(name).strip():
                    names.append(str(name).strip())
    return names


def _emergency_number(patient_profile: Any) -> str:
    if isinstance(patient_profile, dict) and patient_profile.get("emergency_number"):
        return str(patient_profile["emergency_number"]).strip()
    return "999"


def _medicine_names(detected_medicines: Iterable[Any]) -> list[str]:
    names: list[str] = []
    for medicine in detected_medicines:
        name = getattr(medicine, "canonical_name", None)
        if name is None and isinstance(medicine, dict):
            name = medicine.get("canonical_name") or medicine.get("name")
        if name and str(name) not in names:
            names.append(str(name))
    return names


def _is_ascii(text: str) -> bool:
    return all(ord(char) < 128 for char in text)
