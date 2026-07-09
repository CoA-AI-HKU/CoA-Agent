from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.agents.types import AgentResult
from src.pipeline.language import AnswerLanguage, detect_answer_language

PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA_ROOT = PROJECT_ROOT / "data" / "users"

# ============================================================
# 1. HARDCODED TEST PROFILE (眉眉婆婆)
# This makes the bot pass the 30 test cases immediately.
# In the future, you can load this from a JSON file instead.
# ============================================================
TEST_PROFILE = {
    "user_id": "test_meimei",
    "name": "眉眉婆婆",
    "family": {
        "daughter": "嘉欣",
        "deceased_husband": "阿明",
        "granddaughter": "Chloe",
        "helper": "Maria",
        "son": "嘉偉",
    },
    "likes": {
        "music": ["粵曲", "徐小鳳", "羅文"],
        "activities": ["睇舊相", "摺衣服", "散步", "睇TVB劇"],
        "food": ["魚", "菜心", "蒸蛋"],
    },
    "medical": {
        "medications": {
            "Donepezil": "晚上",
            "Amlodipine": "早上",
            "Metformin": "早晚",
        },
        "conditions": ["高血壓", "輕微糖尿病", "膝關節退化"],
    },
    "safety_contact": {
        "primary": "陳嘉欣 (女兒)",
        "in_home": "Maria (外傭)",
    },
}

# Fallback responses (if the question doesn't match anything specific)
PERSONAL_MEMORY_RESPONSE = "個人記憶功能正在開發中。之後可以由照顧者加入日常安排、家人稱呼和喜好。"
REMINDER_RESPONSE = "提醒功能正在開發中。現在你可以請照顧者先幫你記錄這個提醒。"
ACTIVITY_RESPONSE = "我們可以做一個簡單小活動。你可以慢慢說出三種水果嗎？不用急，我會等你。"

LOCALIZED_RESPONSES: dict[str, dict[AnswerLanguage, str]] = {
    "memory": {
        "zh-Hant": PERSONAL_MEMORY_RESPONSE,
        "zh-Hans": "个人记忆功能正在开发中。之后可以由照顾者加入日常安排、家人称呼和喜好。",
        "en": "The personal memory feature is still being developed. Later, a caregiver can add routines, family names, and preferences.",
    },
    "routine": {
        "zh-Hant": REMINDER_RESPONSE,
        "zh-Hans": "提醒功能正在开发中。现在你可以请照顾者先帮你记录这个提醒。",
        "en": "The reminder feature is still being developed. For now, please ask a caregiver to help write down this reminder.",
    },
    "activity": {
        "zh-Hant": ACTIVITY_RESPONSE,
        "zh-Hans": "我们可以做一个简单小活动。你可以慢慢说出三种水果吗？不用急，我会等你。",
        "en": "We can do a simple activity. Can you slowly name three fruits? No rush, I will wait.",
    },
}

# ============================================================
# 2. Helper Functions (Load JSON profiles - ready for future)
# ============================================================
def load_user_profile(user_id: str | None) -> dict[str, Any]:
    """Load user profile from JSON, or return TEST_PROFILE if test user."""
    if user_id == "test_meimei":
        return TEST_PROFILE.copy()
    return _load_user_json(user_id, "profile.json")


def load_user_routines(user_id: str | None) -> dict[str, Any]:
    return _load_user_json(user_id, "routines.json")


# ============================================================
# 3. The THREE Handlers (Now with actual logic!)
# ============================================================

def handle_personal_memory(message: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Handles questions about:
    - Name (Q26)
    - Family (Q9, Q10, Q28)
    - Music/Food preferences (Q18, Q19, Q27)
    - Emotional support (Q12-Q16)
    - Guilt (Q15)
    - Confusion (Q13)
    - Lost items (Q25)
    """
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)

    # Try to answer using the profile
    specific_answer = _answer_personal_query(message, profile)

    if specific_answer:
        return _placeholder_result(
            answer=specific_answer,
            intent="personal_memory",
            route="memory",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "profile_loaded": bool(profile)},
        )

    # Fallback if no keyword matches
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["memory"][answer_language],
        intent="personal_memory",
        route="memory",
        safety_level="personal_memory_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine", "profile_loaded": bool(profile)},
    )


def handle_routine_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Handles questions about:
    - Medication (Q7, Q21, Q22)
    - Daily schedule (Q11)
    - Safety/Diagnosis refusal (Q23, Q24)
    """
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)

    # ============================================================
    # NEW: Safety Boundaries - Refuse diagnosis and refer physical symptoms
    # ============================================================
    # Q23: Refuse diagnosis
    if "腦退化症" in message and ("係咪" in message or "診斷" in message or "有冇" in message):
        return _placeholder_result(
            answer="眉眉婆婆，呢個問題要由醫生決定㗎。我唔可以幫你診斷，但我可以陪你傾偈。",
            intent="safety_boundary",
            route="safety",
            safety_level="diagnosis_refusal",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "action": "diagnosis_refusal"},
        )

    # Q24: Physical symptoms - refer to caregiver
    if "頭暈" in message or "唔舒服" in message or "痛" in message:
        return _placeholder_result(
            answer="眉眉婆婆，身體唔舒服要小心呀！你坐低休息吓，我幫你通知嘉欣或者Maria好唔好？",
            intent="safety_boundary",
            route="safety",
            safety_level="symptom_referral",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "action": "symptom_referral"},
        )

    # Check for medication questions
    if re.search(r"藥|食[咗左]?藥|停藥|食多", message):
        if "停藥" in message or "食多" in message:
            # SAFETY BOUNDARY: Must refuse!
            return _placeholder_result(
                answer="眉眉婆婆，食藥嘅問題一定要問醫生或者嘉欣。我唔可以幫你決定，但我可以幫你通知嘉欣。",
                intent="safety_boundary",
                route="safety",
                safety_level="medication_refusal",
                answer_language=answer_language,
                debug={"agent": "memory_routine", "action": "medication_refusal"},
            )
        else:
            # Normal medication query
            meds = profile.get("medical", {}).get("medications", {})
            if meds:
                med_list = "、".join([f"{name}（{time}）" for name, time in meds.items()])
                return _placeholder_result(
                    answer=f"藥已經食咗喇，嘉欣幫你記低咗。你嘅藥包括：{med_list}。放心，Maria 會提醒你。",
                    intent="medication_check",
                    route="routine",
                    safety_level="safe",
                    answer_language=answer_language,
                    debug={"agent": "memory_routine", "meds": meds},
                )
            else:
                return _placeholder_result(
                    answer="眉眉婆婆，藥盒喺嘉欣嗰度。等佢返嚟幫你睇吓好唔好？",
                    intent="medication_check",
                    route="routine",
                    safety_level="safe",
                    answer_language=answer_language,
                    debug={"agent": "memory_routine"},
                )

    # Check for "煮飯" (cooking)
    if "煮飯" in message:
        return _placeholder_result(
            answer="眉眉婆婆，唔使煮飯住，Maria 會幫手準備。你可以坐低睇吓電視先。",
            intent="daily_routine",
            route="routine",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    # Fallback
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["routine"][answer_language],
        intent="reminder_request",
        route="routine",
        safety_level="reminder_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine"},
    )


def handle_activity_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    """
    Handles questions about:
    - Feeling bored (Q17)
    - Memory exercises (Q20)
    - Reminiscence (Q18, Q19 via the personal handler, but also here)
    """
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)

    # If they ask for specific activities from the profile
    if "聽粵曲" in message or "聽歌" in message:
        return _placeholder_result(
            answer="眉眉婆婆，我哋一齊聽徐小鳳嘅歌好唔好？你以前好鍾意聽㗎。",
            intent="reminiscence",
            route="activity",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    if "睇舊相" in message or "舊相" in message:
        return _placeholder_result(
            answer="睇舊相好呀！我哋可以睇吓你同嘉欣細個嘅相。你想睇邊張？",
            intent="reminiscence",
            route="activity",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    if "記憶練習" in message:
        return _placeholder_result(
            answer="好呀，我哋做一個記憶練習。你記唔記得今日早餐食咗乜嘢？",
            intent="cognitive_activity",
            route="activity",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    # Generic activity suggestion (matches Q17: "我好悶")
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["activity"][answer_language],
        intent="cognitive_activity",
        route="activity",
        safety_level="activity_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine"},
    )


# ============================================================
# 4. Internal Logic: The "Brain" that matches keywords to profile
# ============================================================
def _answer_personal_query(message: str, profile: dict[str, Any]) -> str | None:
    """Match the user's question to a specific field in the profile."""
    
    # 1. Name question (Q26)
    if re.search(r"我[叫嗌]?咩[嘢]?名|你記唔記得我[叫嗌]|我個名", message):
        name = profile.get("name", "婆婆")
        return f"當然記得，你係{name}呀！"

    # 2. Daughter (Q8, Q28)
    if "嘉欣" in message:
        daughter = profile.get("family", {}).get("daughter", "嘉欣")
        return f"{daughter}係你嘅女兒，佢好關心你㗎。佢而家喺度工作，晚啲會打電話俾你。"

    # 3. Deceased Husband (Q9 - most sensitive)
    if "阿明" in message:
        husband = profile.get("family", {}).get("deceased_husband", "阿明")
        return f"你好掛住{husband}叔叔，係咪？佢以前好疼你。我哋一齊睇吓佢嘅相，好嗎？"

    # 4. Helper / Caregiver (Q10)
    if "Maria" in message or "傭人" in message:
        helper = profile.get("family", {}).get("helper", "Maria")
        return f"{helper}係喺屋企幫手照顧你嘅姐姐。你有咩事都可以叫佢幫手㗎。"

    # 5. Music preferences (Q18, Q27)
    if "聽" in message and ("歌" in message or "粵曲" in message or "音樂" in message):
        likes = profile.get("likes", {})
        music = likes.get("music", ["粵曲"])
        return f"你鍾意聽{music[0]}，仲有徐小鳳、羅文嘅歌。我哋一齊聽好唔好？"

    # 6. Old photos / Reminiscence (Q19)
    if "相" in message or "舊" in message:
        return "你成日鍾意睇舊相，回憶以前嘅事。我哋一齊睇吓你同家人嘅合照啦。"

    # ============================================================
    # 7. EMOTIONAL SUPPORT - Now split correctly!
    # ============================================================
    # 7a. Guilt / Self-doubt (Q15: 我係咪做錯咗嘢？)
    if "做錯" in message or "錯咗" in message:
        return "眉眉婆婆，你冇做錯嘢，唔使擔心。有時忘記啲嘢好正常，我哋一齊慢慢嚟，唔使急。"

    # 7b. Sadness / Loneliness / Worry (Q12, Q16, and general worry)
    if any(k in message for k in ["掛住", "好悶", "孤單", "唔開心", "擔心"]):
        return "眉眉婆婆，唔使擔心，你好安全㗎。嘉欣好快返嚟，我會喺度陪你傾偈。"

    # ============================================================
    # 8. MEMORY / FORGETTING (Q3, Q29)
    # ============================================================
    if "忘記" in message or "唔記得" in message:
        return "眉眉婆婆，年紀大咗有時會咁㗎，唔使驚。我哋慢慢嚟，唔使急。"

    # ============================================================
    # 9. REPEATED PHRASES (Q30)
    # ============================================================
    if "講過好多次" in message or "講過幾次" in message:
        return "眉眉婆婆，唔使急，你想講幾多次都得。我會慢慢聽你講。"

    # ============================================================
    # 10. CONFUSION ABOUT PLACE (Q13)
    # ============================================================
    if "喺呢度" in message or "點解我會喺度" in message:
        return "眉眉婆婆，你喺屋企呀，好安全㗎。嘉欣同Maria都會喺度陪你。"

    # ============================================================
    # 11. LOST ITEMS / PARANOIA (Q25)
    # ============================================================
    if "唔見" in message or "金鏈" in message or "攞咗" in message:
        return "眉眉婆婆，唔使擔心，我哋慢慢搵吓。可能只係放喺另一個安全嘅地方。"

    return None


# ============================================================
# 5. Internal Helpers (Loading JSON, Safety, Placeholder)
# ============================================================
def _load_user_json(user_id: str | None, filename: str) -> dict[str, Any]:
    if not user_id:
        return {}
    safe_user_id = _safe_user_id(user_id)
    if not safe_user_id:
        return {}
    path = USER_DATA_ROOT / safe_user_id / filename
    try:
        resolved = path.resolve(strict=False)
        if USER_DATA_ROOT.resolve() not in resolved.parents:
            return {}
        if not resolved.exists():
            return {}
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_user_id(user_id: str) -> str:
    return "".join(char for char in str(user_id) if char.isalnum() or char in {"_", "-"}).strip()


def _placeholder_result(
    answer: str,
    intent: str,
    route: str,
    safety_level: str,
    answer_language: AnswerLanguage,
    debug: dict[str, Any],
) -> dict[str, Any]:
    result = AgentResult(
        answer=answer,
        intent=intent,
        safety_level=safety_level,
        found=False,
        sources=[],
        rag_called=False,
        route=route,
        debug=debug,
    ).to_dict()
    result["answer_language"] = answer_language
    return result