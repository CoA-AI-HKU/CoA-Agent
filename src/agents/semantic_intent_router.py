from __future__ import annotations

import json
import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# Only the categories that actually had ambiguity/negation bugs under keyword
# matching. Safety-critical categories (urgent_safety, medication_or_diagnosis,
# prompt_injection, role_correction) are deliberately excluded — they are
# classified deterministically in src/intent_router.py before this module is
# ever consulted, and must never depend on an LLM being available or correct.
_INTENT_DESCRIPTIONS = {
    "memory_concern": "使用者本人表達記性/記憶方面的憂慮或困擾（第一人稱）。",
    "cognitive_concern_screening": "使用者想了解自己或家人是否需要做認知能力小檢查，或詢問如何分辨正常老化與腦退化症。",
    "caregiver_support": "照顧者描述被照顧者（家人）的記憶或行為變化，尋求照顧建議。",
    "personal_memory": "使用者分享個人喜好、家人稱呼、日常習慣等個人資訊。",
    "reminder_request": "使用者想設定一個未來的提醒（例如幾點提醒佢做某件事）——注意呢個唔係問而家幾點嘅問題。",
    "cancel_reminder": "使用者想取消、清除或刪除已經設定嘅提醒/鬧鐘，唔想再收到提醒。",
    "cognitive_activity": "使用者想做一啲輕鬆嘅認知活動、遊戲，或者話悶，想搵嘢做。",
    "emotional_support": "使用者表達情緒，例如唔開心、擔心、孤單、攰，需要情感支持。",
    "dementia_knowledge": "使用者想知道關於腦退化症/認知障礙嘅事實資訊（症狀、成因、預防等）。",
    "daily_life_support": "使用者想討論日常生活上嘅事（出門、買嘢、煮飯、搭車等）。",
    "casual_conversation": "一般閒聊、問候，或者同認知障礙/照顧無直接關係嘅日常問題，包括問而家幾點、問天氣等事實性問題。",
    "unknown": "以上都唔啱，或者訊息意思唔清楚。",
}
ALLOWED_INTENTS: tuple[str, ...] = tuple(_INTENT_DESCRIPTIONS)
_ALLOWED_INTENT_SET = frozenset(ALLOWED_INTENTS)

# Classification only needs a handful of output tokens, unlike full-answer
# generation (which reuses create_chat_answer's 30s default) — a shorter
# timeout means a hung classification call falls back to the safe, fast
# keyword cascade sooner instead of stalling the whole response.
_CLASSIFICATION_TIMEOUT_SECONDS = 12
# Not taken from the model: LLM self-reported confidence is uncalibrated,
# and nothing in the codebase branches on this value beyond logging it.
_CONFIDENCE = 0.75


def classify_intent_semantic(message: str) -> tuple[str, str] | None:
    """Classify `message` into one of ALLOWED_INTENTS via the configured LLM.

    Returns (intent, reason) on a successfully-parsed, allowlisted result, or
    None if the LLM is unavailable, times out, or returns something that
    can't be trusted (unparseable, or an intent outside the allowlist —
    including a hallucinated safety-critical label like "urgent_safety",
    which only the deterministic hard gates in intent_router.classify_intent
    are allowed to produce). Callers must fall back to keyword classification
    on None; this function never raises.
    """
    normalized = str(message or "").strip()
    if not normalized:
        return None
    try:
        return _cached_classify(normalized)
    except Exception:
        logger.exception("semantic_intent_router: unexpected classification failure")
        return None


@lru_cache(maxsize=256)
def _cached_classify(message: str) -> tuple[str, str] | None:
    # Local import, not module-level: src/pipeline/rag_agent.py imports
    # IntentResult/classify_intent from src/intent_router.py at its own
    # module level, so a top-level import of rag_agent here would create a
    # circular import (intent_router -> this module -> rag_agent ->
    # intent_router). Importing inside the function avoids it, matching
    # rag_agent.py's own pattern for its lazy deps (e.g. `requests`).
    from src.pipeline.rag_agent import build_default_rag_config, create_chat_answer

    try:
        config = build_default_rag_config("mcp")
        answer_callable = create_chat_answer(config, timeout=_CLASSIFICATION_TIMEOUT_SECONDS)
    except Exception:
        logger.exception("semantic_intent_router: failed to build LLM callable")
        return None
    if answer_callable is None:
        return None

    try:
        raw = answer_callable(_build_prompt(message))
    except Exception:
        logger.exception("semantic_intent_router: LLM call failed")
        return None

    return _parse_response(raw)


def _build_prompt(message: str) -> str:
    categories = "\n".join(f'- "{intent}": {desc}' for intent, desc in _INTENT_DESCRIPTIONS.items())
    return (
        "你是一個訊息分類器，負責將使用者訊息分類做以下其中一個類別。"
        "唔好回答問題本身，只需要分類。\n\n"
        f"類別：\n{categories}\n\n"
        "請只回覆一個JSON物件，格式為 "
        '{"intent": "上面其中一個類別名", "reason": "一句簡短原因"}，'
        "唔好加任何其他文字、解釋或code block標記。\n\n"
        f"使用者訊息：{message}"
    )


def _parse_response(raw: str) -> tuple[str, str] | None:
    text = str(raw or "").strip()
    if not text:
        return None

    payload = _try_json_loads(text)
    if payload is None:
        fenced = _strip_code_fence(text)
        if fenced is not None:
            payload = _try_json_loads(fenced)
    if payload is None:
        extracted = _extract_json_object(text)
        if extracted is not None:
            payload = _try_json_loads(extracted)
    if not isinstance(payload, dict):
        return None

    intent = str(payload.get("intent") or "").strip()
    if intent not in _ALLOWED_INTENT_SET:
        if intent:
            logger.warning("semantic_intent_router: rejected out-of-allowlist intent=%r", intent)
        return None

    reason = str(payload.get("reason") or "").strip()
    return intent, reason[:200]


def _try_json_loads(text: str) -> object | None:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


_CODE_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _strip_code_fence(text: str) -> str | None:
    match = _CODE_FENCE_PATTERN.search(text)
    return match.group(1).strip() if match else None


_JSON_OBJECT_PATTERN = re.compile(r"\{.*?\}", re.DOTALL)


def _extract_json_object(text: str) -> str | None:
    match = _JSON_OBJECT_PATTERN.search(text)
    return match.group(0) if match else None
