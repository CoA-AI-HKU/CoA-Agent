from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from src.agents.types import AgentDecision
from src.pipeline.language import detect_answer_language, language_name
from src.pipeline.rag_agent import build_default_rag_config, create_chat_answer
from src.safety.medication_guard import detect_red_flags, is_medication_decision_question

try:
    from src.reminders.chat_reminders import LOCAL_TIMEZONE
except ImportError:  # reminder deps (SQLAlchemy etc.) unavailable in this process
    LOCAL_TIMEZONE = None

logger = logging.getLogger(__name__)

# "What time is it?" is a factual question the LLM cannot reliably answer —
# it has no clock — so it's answered deterministically here rather than
# generated, the same reasoning that keeps medication dosing hardcoded
# rather than left to the model.
_CURRENT_TIME_QUESTION_PATTERNS = [
    re.compile(r"(現在|现在|而家|宜家|依家)\s*(係|系|是)?\s*[幾几]點"),
    re.compile(r"what.?s?\s+the\s+time|what\s+time\s+is\s+it", re.IGNORECASE),
]


EMOTIONAL_SUPPORT_RESPONSE = (
    "我明白你可能有點不安。你可以慢慢說，我會用簡單的方式陪你整理。"
    "如果這件事和健康或安全有關，請同時告訴照顧者或醫護人員。"
)
UNKNOWN_RESPONSE = "我未能清楚理解你的意思。你可以用簡單一句再問一次嗎？"

SAFETY_SOFT_NOTICE = (
    "如果同時有其他不舒服、突然嘅轉變，或者你唔太肯定，"
    "請盡快話俾家人或醫護人員知，等佢哋可以幫你留意。"
)

PERSONA_INSTRUCTIONS = (
    "你係小安，一個幫助長者（包括可能有腦退化症或輕度認知障礙嘅人士）嘅助手。"
    "用簡單、清晰、有耐性嘅語氣回覆，每次回覆用2至3句説話講清楚，唔好講到一半就停。"
    "唔好作出醫療診斷，唔好建議任何藥物劑量或者係咪應該食藥、停藥或轉藥，"
    "呢啲問題一定要建議佢搵醫生、藥劑師或者家人幫手。"
    "如果你唔確定啲資訊係咪啱，就老實講，唔好靠估。"
)

ROUTE_TASK_FRAMING = {
    "daily_life": (
        "使用者想討論一件日常生活上嘅事情（例如出門、買嘢、煮飯、搭車、聯絡家人等）。"
        "請用實際、簡單、鼓勵獨立但注重安全嘅語氣回覆，"
        "適當時提提佢帶電話同鎖匙、話俾家人知去邊，或者如果身體唔舒服就搵人陪同。"
    ),
    "supportive": (
        "使用者可能表達緊情緒（例如唔開心、擔心、孤單、攰）。"
        "請用溫暖、簡單、有耐性嘅語氣回應，畀佢感受到被理解，"
        "如果適合就建議佢可以同家人或熟悉嘅人傾吓。"
    ),
    "general": (
        "使用者想輕鬆傾偈，或者問一啲同認知障礙、照顧無直接關係嘅日常問題。"
        "請用自然、友善、簡單嘅語氣回覆，好似一個細心嘅朋友咁。"
    ),
    "unknown": (
        "呢句說話未必啱任何已知類別，但都係一個合理、安全嘅問題或者陳述。"
        "請盡量理解使用者嘅意思，畀返一個有用、簡單、友善嘅回覆；"
        "如果真係唔清楚佢想講咩，可以禮貌噉請佢再講清楚啲。"
    ),
}

ROUTE_SAFETY_LEVEL = {
    "daily_life": "conditional_daily_life_safety",
    "supportive": "supportive_non_clinical",
    "general": "casual_conversation",
    "unknown": "general_conversation",
}
# Safety levels used by this module, kept distinct from RAG's "normal" so the
# formatter's sentence cap (see user_facing_formatter._compact_answer) can
# give these routes more room without loosening the cap on RAG answers.
GENERAL_CHAT_SAFETY_LEVELS = frozenset(ROUTE_SAFETY_LEVEL.values())


def answer_general_conversation(message: str, decision: AgentDecision, route: str) -> dict[str, Any]:
    """Answer a non-knowledge message with the general LLM, falling back to a fixed response.

    Only called for routes that the medication/urgent-safety gates in
    coordinator_agent.coordinate_message have already cleared, so this never
    sees a message flagged as medical or urgent at the input side. The
    generated answer still gets a soft output-side check (see
    _apply_output_soft_flag) since the input-side keyword gate has known gaps.
    """
    if route == "unknown" and not _is_intelligible(message):
        return _fallback_result(UNKNOWN_RESPONSE, decision, route)

    if _is_current_time_question(message):
        answer_language = detect_answer_language(message)
        return _build_result(_current_time_answer(answer_language), decision, route)

    answer_callable = create_chat_answer(build_default_rag_config("mcp"))
    if answer_callable is not None:
        generated = _generate(message, route, answer_callable)
        if generated:
            return _build_result(generated, decision, route)

    return _fallback_result(_fallback_text(message, route), decision, route)


def _generate(message: str, route: str, answer_callable) -> str:
    answer_language = detect_answer_language(message)
    task_framing = ROUTE_TASK_FRAMING.get(route, ROUTE_TASK_FRAMING["general"])
    prompt = (
        f"{PERSONA_INSTRUCTIONS}\n\n{task_framing}\n\n"
        f"請用{language_name(answer_language)}回覆，用2至3句完整、自然收尾嘅句子回答，唔好突然斷句。\n\n"
        f"使用者：{message}"
    )
    try:
        return answer_callable(prompt).strip()
    except Exception:
        logger.exception("general_chat_agent LLM call failed, falling back to a fixed response")
        return ""


def _build_result(generated: str, decision: AgentDecision, route: str) -> dict[str, Any]:
    answer, debug = _apply_output_soft_flag(generated)
    debug["agent"] = "general_chat"
    return {
        "answer": answer,
        "intent": decision.intent,
        "safety_level": ROUTE_SAFETY_LEVEL.get(route, "normal"),
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": route,
        "debug": debug,
    }


def _apply_output_soft_flag(generated: str) -> tuple[str, dict[str, Any]]:
    red_flags = detect_red_flags(generated)
    if red_flags or is_medication_decision_question(generated):
        return f"{generated}\n\n{SAFETY_SOFT_NOTICE}", {
            "output_soft_flag": True,
            "output_soft_flag_terms": red_flags,
        }
    return generated, {}


def _fallback_result(answer: str, decision: AgentDecision, route: str) -> dict[str, Any]:
    return {
        "answer": answer,
        "intent": decision.intent,
        "safety_level": ROUTE_SAFETY_LEVEL.get(route, "normal"),
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": route,
        "debug": {"agent": "general_chat", "llm_unavailable": True},
    }


def _fallback_text(message: str, route: str) -> str:
    fallback_fn = {
        "daily_life": _daily_life_fallback,
        "supportive": _supportive_fallback,
        "general": _general_fallback,
    }.get(route, _unknown_fallback)
    return fallback_fn(message)


def _daily_life_fallback(message: str) -> str:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("出去走走", "出去散步", "出街行下", "go for a walk")):
        return ("可以呀，出去走走通常可以令人放鬆。出門前可以先看看天氣，帶好電話和鎖匙，"
                 "並告訴家人你會去哪裡；如果你感到頭暈、容易迷路或身體不舒服，最好先請家人陪同。")
    if any(term in normalized for term in ("鎖匙", "鑰匙")):
        return "先別著急，可以依次看看門邊、袋子、外套口袋和最近用過鎖匙的地方；如果仍找不到，可以請家人一起找，並使用備用鎖匙。"
    if any(term in normalized for term in ("煮飯", "cook")):
        return "如果你現在精神和身體狀況良好，可以準備簡單的一餐。開始前先把材料放好，煮食時不要離開爐火；如果感到頭暈、很疲倦或不確定爐具操作，請家人陪同或改吃不用開火的食物。"
    if any(term in normalized for term in ("巴士", "bus")):
        return "可以先查看路線和回程時間，帶好電話、鎖匙和車費，並告訴家人目的地；如果你不熟悉路線、容易迷路或身體不舒服，最好請熟悉路線的人同行。"
    if "打電話" in normalized:
        return "可以呀，你可以現在打給她。如果一時找不到號碼，可以看看通訊錄或請身邊的人幫你找，但不要把密碼或驗證碼告訴別人。"
    return "可以先按自己的能力和當時情況安排。出發前準備好電話和鎖匙，告訴家人目的地；如果身體不舒服、不熟悉路線或感到不安全，就請可信任的人陪同。"


def _supportive_fallback(message: str) -> str:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("你好", "您好", "早晨", "午安", "晚安", "hello", "hi")):
        return "你好！很高興見到你。今天有甚麼想聊，或需要我幫忙整理的事嗎？"
    if any(term in normalized for term in ("好累", "很累", "攰", "疲倦", "tired", "exhausted")):
        return (
            "聽起來你今天很累。可以先讓自己休息一下、喝點水，慢慢來。"
            "如果疲倦持續、突然很嚴重，或同時有其他不適，請告訴家人並向醫護人員查詢。"
        )
    return EMOTIONAL_SUPPORT_RESPONSE


def _general_fallback(message: str) -> str:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("數獨", "数独", "sudoku")):
        return (
            "我覺得數獨幾好玩，尤其是逐步推理、終於填對整個方格時很有滿足感。"
            "如果你喜歡安靜思考，可以由容易級開始玩。"
        )
    if any(term in normalized for term in ("麻將", "麻将", "打牌", "mahjong")):
        return (
            "可以呀，如果你喜歡打麻將，和朋友輕鬆玩一會也可以是很好的社交活動。"
            "記得按自己的精神和時間安排，中途休息一下；如果涉及金錢，就先定好能接受的限額。"
        )
    if any(term in normalized for term in ("吃什麼", "食什麼", "食咩", "晚上吃", "今晚食", "晚餐")):
        return (
            "今晚可以按你的口味選一頓簡單的飯，例如飯或麵配蔬菜，再加你喜歡的蛋、魚或豆腐。"
            "如果你有醫生建議的飲食限制，就以醫護人員的建議為先。"
        )
    return "我明白你的意思。你可以再告訴我多一點，我會陪你慢慢整理。"


def _unknown_fallback(message: str) -> str:
    return (
        "我明白你的要求，但這個功能暫時未能處理。你可以問我記憶支援、腦退化症資訊或日常生活問題。"
        if _is_intelligible(message)
        else UNKNOWN_RESPONSE
    )


def _is_intelligible(message: str) -> bool:
    text = str(message or "")
    cjk_count = sum("㐀" <= char <= "鿿" for char in text)
    latin_words = [word for word in text.split() if word.isalpha()]
    return cjk_count >= 3 or len(latin_words) >= 2


def _is_current_time_question(message: str) -> bool:
    return any(pattern.search(message) for pattern in _CURRENT_TIME_QUESTION_PATTERNS)


def _current_time_answer(answer_language: str) -> str:
    now = datetime.now(LOCAL_TIMEZONE) if LOCAL_TIMEZONE is not None else datetime.now()
    time_str = now.strftime("%H:%M")
    if answer_language == "zh-Hans":
        return f"现在是{time_str}。"
    if answer_language == "en":
        return f"It is currently {time_str}."
    return f"現在是{time_str}。"
