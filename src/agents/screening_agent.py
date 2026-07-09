from __future__ import annotations

from typing import Any

from src.agents.coordinator_agent import infer_user_role
from src.agents.types import AgentResult
from src.pipeline.language import detect_answer_language


URGENT_RED_FLAGS = [
    "突然混亂",
    "突然糊塗",
    "突然不認得",
    "跌倒",
    "撞親頭",
    "撞到頭",
    "頭部受傷",
    "發燒",
    "发烧",
    "幻覺",
    "幻觉",
    "看見不存在",
    "說話不清",
    "说话不清",
    "手腳無力",
    "手脚无力",
    "半邊身",
    "胸痛",
    "胸口痛",
    "呼吸困難",
    "呼吸困难",
    "突然很嚴重頭痛",
    "突然好嚴重頭痛",
    "sudden confusion",
    "slurred speech",
    "one-sided weakness",
    "chest pain",
    "breathing difficulty",
    "severe headache",
]

URGENT_RESPONSE = (
    "如果是突然混亂、突然不認得人、跌倒後改變、說話不清、手腳無力、發燒、幻覺、"
    "胸痛或呼吸困難，請盡快求醫或聯絡緊急服務。這類情況不應只當作一般記憶問題處理。"
)
SELF_CHECKIN_RESPONSE = (
    "我不能判斷你是否有腦退化症，但可以幫你整理是否值得進一步評估。你可以先想想幾個問題：\n\n"
    "1. 這些記憶或思考上的改變是突然出現，還是慢慢出現？\n"
    "2. 有沒有影響日常生活，例如覆診、煮飯、金錢、出門路線或工作？\n"
    "3. 家人或朋友有沒有也留意到這些改變？\n"
    "4. 情況是否持續出現，還是只在疲倦、壓力大或睡眠不足時出現？\n\n"
    "如果情況持續、變嚴重，或影響日常生活，建議安排醫生或記憶診所評估。"
)
CAREGIVER_CHECKIN_RESPONSE = (
    "我不能判斷你的家人是否有腦退化症，但可以幫你整理是否值得進一步評估。你可以觀察：\n\n"
    "1. 這些改變是最近突然出現，還是慢慢出現？\n"
    "2. 是否比以前更常忘記近期事情、覆診、金錢或熟悉路線？\n"
    "3. 是否影響日常生活或安全？\n"
    "4. 家人是否重複問同一問題、容易迷路，或處理熟悉事情變困難？\n\n"
    "如果改變持續、變嚴重，或影響生活或安全，建議安排醫生或記憶診所評估。"
)
LOW_CONCERN_RESPONSE = (
    "暫時聽起來未必一定是腦退化症。壓力、睡眠不足、情緒、藥物或身體不適都可能影響記憶。"
    "你可以先觀察；如果情況持續或變嚴重，建議向醫生查詢。"
)
MODERATE_CONCERN_RESPONSE = (
    "這些情況如果持續出現，並開始影響日常生活，值得安排醫生或記憶診所作進一步評估。"
    "我不能作診斷，但可以幫你整理要告訴醫生的重點。"
)
URGENT_FOLLOWUP_RESPONSE = (
    "這不像一般慢性記憶變差，可能需要較快求醫。請盡快聯絡醫護人員；"
    "如果有即時危險，請聯絡緊急服務。"
)
SELF_MEMORY_CONCERN_RESPONSE = (
    "記不住很多事情會令人擔心，但這不一定代表是腦退化症。"
    "壓力、睡眠不足、情緒、藥物或身體狀況都可能影響記憶。"
    "你可以先記錄最近什麼時候最容易忘記；如果情況持續、變嚴重，或影響日常生活，"
    "建議和醫生或醫護人員討論。"
)
CAREGIVER_OBSERVATION_GUIDANCE_RESPONSE = (
    "如果你留意到家人最近較常忘記事情，可以先用觀察和記錄的方式了解情況，"
    "不要急著下結論。請記下什麼時候最容易忘記、是否影響日常生活或安全、"
    "是否和睡眠、壓力、情緒、藥物或身體不適有關。"
    "如果情況持續、變嚴重，或影響生活和安全，建議陪同家人向醫生或醫護人員查詢。"
)


def handle_self_memory_concern(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    result = AgentResult(
        answer=SELF_MEMORY_CONCERN_RESPONSE,
        intent="self_memory_concern",
        safety_level="self_memory_concern",
        found=False,
        sources=[],
        rag_called=False,
        route="self_memory_concern",
        debug={
            "agent": "screening",
            "answer_language": answer_language,
            "screening_classification": None,
            "diagnosis_provided": False,
        },
    ).to_dict()
    result["answer_language"] = answer_language
    return result


def handle_caregiver_observation_guidance(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    result = AgentResult(
        answer=CAREGIVER_OBSERVATION_GUIDANCE_RESPONSE,
        intent="caregiver_guidance",
        safety_level="caregiver_observation_guidance",
        found=False,
        sources=[],
        rag_called=False,
        route="caregiver_guidance",
        debug={
            "agent": "caregiver_guidance",
            "answer_language": answer_language,
            "screening_classification": None,
            "diagnosis_provided": False,
        },
    ).to_dict()
    result["answer_language"] = answer_language
    return result


def handle_cognitive_concern_screening(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    user_role = infer_user_role(message)
    red_flags = _matched_terms(message, URGENT_RED_FLAGS)
    classification = _classify_followup(message, red_flags)

    if classification == "urgent_medical_attention":
        answer = URGENT_RESPONSE if red_flags else URGENT_FOLLOWUP_RESPONSE
        safety_level = "urgent_boundary"
    elif classification == "no_clear_concern":
        answer = LOW_CONCERN_RESPONSE
        safety_level = "screening_check_in"
    elif classification == "non_urgent_medical_evaluation":
        answer = MODERATE_CONCERN_RESPONSE
        safety_level = "screening_check_in"
    else:
        answer = CAREGIVER_CHECKIN_RESPONSE if user_role == "caregiver_or_family" else SELF_CHECKIN_RESPONSE
        safety_level = "screening_check_in"

    result = AgentResult(
        answer=answer,
        intent="cognitive_concern_screening",
        safety_level=safety_level,
        found=False,
        sources=[],
        rag_called=False,
        route="screening",
        debug={
            "agent": "screening",
            "answer_language": answer_language,
            "user_role": user_role,
            "red_flags": red_flags,
            "screening_classification": classification,
        },
    ).to_dict()
    result["answer_language"] = answer_language
    return result


def _matched_terms(message: str, terms: list[str]) -> list[str]:
    normalized = message.lower()
    matches = []
    for term in terms:
        haystack = normalized if term.isascii() else message
        needle = term.lower() if term.isascii() else term
        if needle in haystack and term not in matches:
            matches.append(term)
    return matches


def _classify_followup(message: str, red_flags: list[str]) -> str:
    if red_flags:
        return "urgent_medical_attention"

    normalized = message.lower()
    low_context = ["壓力", "压力", "睡眠不足", "瞓得唔好", "疲倦", "偶爾", "偶尔", "stress", "sleep"]
    impact_context = [
        "影響日常",
        "覆診",
        "煮飯",
        "金錢",
        "钱",
        "出門路線",
        "迷路",
        "走失",
        "重複問",
        "重複提問",
        "持續",
        "變嚴重",
        "安全",
        "daily life",
        "getting lost",
        "repeat",
    ]

    if any(term in normalized for term in low_context) and not any(term in normalized for term in impact_context):
        return "no_clear_concern"
    if any(term in normalized for term in impact_context):
        return "non_urgent_medical_evaluation"
    return "monitor"
