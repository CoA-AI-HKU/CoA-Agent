from __future__ import annotations

from typing import Any

from src.agents.coordinator_agent import infer_user_role
from src.agents.types import AgentResult
from src.pipeline.language import detect_answer_language
from src.pipeline.rag_agent import answer_question, build_default_rag_config


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
MEMORY_CONCERN_RESPONSE = (
    "記不住事情會令人很困擾，也可能和壓力、睡眠不足、情緒、藥物、身體狀況或認知變化有關。"
    "你可以先用一些簡單方法幫自己：把重要事情寫下來、用手機提醒、把常用物品放在固定位置、每天保持規律作息。\n\n"
    "如果這種情況最近明顯變多、影響日常生活，或家人也有留意到，建議和醫生或醫護人員討論，找出原因。"
    "你也可以告訴我有什麼事情想記住，我可以幫你整理成簡單提醒。"
)
DEMENTIA_QUESTION_RESPONSE = (
    "單靠這些情況不能判斷是不是腦退化症。記憶變差可能有很多原因。"
    "如果情況持續、變嚴重，或影響日常生活，建議約見醫生或記憶診所作評估。"
)
CAREGIVER_OBSERVATION_GUIDANCE_RESPONSE = (
    "如果你留意到家人最近較常忘記事情，可以先用觀察和記錄的方式了解情況，"
    "不要急著下結論。請記下什麼時候最容易忘記、是否影響日常生活或安全、"
    "是否和睡眠、壓力、情緒、藥物或身體不適有關。"
    "如果情況持續、變嚴重，或影響生活和安全，建議陪同家人向醫生或醫護人員查詢。"
)


def handle_memory_concern(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    answer = DEMENTIA_QUESTION_RESPONSE if _is_explicit_dementia_question(message) else MEMORY_CONCERN_RESPONSE
    result = AgentResult(
        answer=answer,
        intent="self_memory_concern",
        safety_level="memory_concern",
        found=False,
        sources=[],
        rag_called=False,
        route="memory_concern",
        debug={
            "agent": "screening",
            "answer_language": answer_language,
            "screening_classification": None,
            "diagnosis_provided": False,
        },
    ).to_dict()
    result["answer_language"] = answer_language
    return result


def handle_self_memory_concern(message: str, user_id: str | None = None) -> dict[str, Any]:
    return handle_memory_concern(message, user_id)


def handle_caregiver_observation_guidance(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    retrieval_debug: dict[str, Any] = {}
    sources: list[Any] = []
    found = False
    try:
        raw = answer_question(message, build_default_rag_config("mcp"))
        if isinstance(raw, dict):
            raw_debug = raw.get("debug") if isinstance(raw.get("debug"), dict) else {}
            retrieval_debug = dict(raw_debug.get("retrieval") or {})
            sources = list(raw.get("sources") or [])
            found = bool(raw.get("found"))
    except Exception as exc:  # pragma: no cover - care guidance remains available if retrieval fails.
        retrieval_debug = {
            "route": "caregiver_guidance",
            "tools_used": [],
            "keyword_queries": [],
            "semantic_queries": [],
            "chunks_read": [],
            "evidence_sufficient": False,
            "retrieval_failed": True,
            "answer_used_rag": False,
            "error_type": type(exc).__name__,
        }
    result = AgentResult(
        # Retrieved evidence validates the route internally; the stable care
        # wording remains practical, non-diagnostic, and non-shaming.
        answer=CAREGIVER_OBSERVATION_GUIDANCE_RESPONSE,
        intent="caregiver_guidance",
        safety_level="caregiver_observation_guidance",
        found=found,
        sources=sources,
        rag_called=True,
        route="caregiver_guidance",
        debug={
            "agent": "caregiver_guidance",
            "answer_language": answer_language,
            "screening_classification": None,
            "diagnosis_provided": False,
            "retrieval": retrieval_debug,
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


def _is_explicit_dementia_question(message: str) -> bool:
    normalized = message.strip().lower()
    question_terms = [
        "是不是",
        "是否",
        "係咪",
        "係唔係",
        "會唔會",
        "會不會",
        "有冇",
        "有沒有",
        "is this",
        "do i have",
        "am i",
    ]
    dementia_terms = [
        "腦退化症",
        "腦退化",
        "脑退化症",
        "脑退化",
        "認知障礙",
        "认知障碍",
        "dementia",
        "mci",
    ]
    return any(term in normalized for term in question_terms) and any(term in normalized for term in dementia_terms)
