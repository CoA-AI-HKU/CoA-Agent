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
# 1. FALLBACK HARDCODED PROFILE (ONLY if JSON fails to load)
# ============================================================
FALLBACK_PROFILE = {
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

# Fallback responses
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
# 2. Load Profile (Dynamic)
# ============================================================
def load_user_profile(user_id: str | None) -> dict[str, Any]:
    if not user_id:
        return {}
    
    # Try to load from JSON file first
    json_profile = _load_user_json(user_id, "profile.json")
    if json_profile:
        return json_profile
    
    # If JSON fails, fallback to hardcoded for test_meimei only
    if user_id == "test_meimei":
        return FALLBACK_PROFILE.copy()
    
    return {}

def load_user_routines(user_id: str | None) -> dict[str, Any]:
    return _load_user_json(user_id, "routines.json")


# ============================================================
# 3. Handlers (ALL THREE are here)
# ============================================================

def handle_personal_memory(message: str, user_id: str | None = None) -> dict[str, Any]:
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)
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

    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["memory"][answer_language],
        intent="personal_memory",
        route="memory",
        safety_level="personal_memory_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine", "profile_loaded": bool(profile)},
    )


def handle_routine_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)

    # --- SAFETY BOUNDARIES (UNIVERSAL) ---
    if "腦退化症" in message and ("係咪" in message or "診斷" in message or "有冇" in message):
        return _placeholder_result(
            answer="呢個問題要由醫生決定㗎。我唔可以幫你診斷，但我可以陪你傾偈。",
            intent="safety_boundary",
            route="safety",
            safety_level="diagnosis_refusal",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "action": "diagnosis_refusal"},
        )

    if "頭暈" in message or "唔舒服" in message or "痛" in message:
        contact = profile.get("safety_contact", {}).get("primary", "照顧者")
        return _placeholder_result(
            answer=f"身體唔舒服要小心呀！你坐低休息吓，我幫你通知{contact}好唔好？",
            intent="safety_boundary",
            route="safety",
            safety_level="symptom_referral",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "action": "symptom_referral"},
        )

    # --- MEDICATION (DYNAMIC) ---
    if re.search(r"藥|食[咗左]?藥|停藥|食多", message):
        if "停藥" in message or "食多" in message:
            contact = profile.get("safety_contact", {}).get("primary", "醫生")
            return _placeholder_result(
                answer=f"食藥嘅問題一定要問醫生或者{contact}。我唔可以幫你決定，但我可以幫你通知佢。",
                intent="safety_boundary",
                route="safety",
                safety_level="medication_refusal",
                answer_language=answer_language,
                debug={"agent": "memory_routine", "action": "medication_refusal"},
            )
        else:
            meds = profile.get("medical", {}).get("medications", {})
            if meds:
                med_list = "、".join([f"{name}（{time}）" for name, time in meds.items()])
                contact = profile.get("safety_contact", {}).get("primary", "照顧者")
                return _placeholder_result(
                    answer=f"藥已經食咗喇，{contact}幫你記低咗。你嘅藥包括：{med_list}。",
                    intent="medication_check",
                    route="routine",
                    safety_level="safe",
                    answer_language=answer_language,
                    debug={"agent": "memory_routine", "meds": meds},
                )
            else:
                return _placeholder_result(
                    answer="你嘅記錄入面冇藥物資料。如果有需要，可以問吓醫生或者照顧者。",
                    intent="medication_check",
                    route="routine",
                    safety_level="safe",
                    answer_language=answer_language,
                    debug={"agent": "memory_routine"},
                )

    # --- COOKING / DAILY ROUTINE ---
    if "煮飯" in message:
        helper = profile.get("family", {}).get("helper") or profile.get("safety_contact", {}).get("in_home", "屋企人")
        return _placeholder_result(
            answer=f"唔使煮飯住，{helper}會幫手準備。你可以坐低睇吓電視先。",
            intent="daily_routine",
            route="routine",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["routine"][answer_language],
        intent="reminder_request",
        route="routine",
        safety_level="reminder_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine"},
    )


def handle_activity_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)

    # --- MUSIC ---
    if "聽" in message and ("歌" in message or "粵曲" in message or "音樂" in message):
        likes = profile.get("likes", {})
        music = likes.get("music", [])
        if music:
            return _placeholder_result(
                answer=f"我哋一齊聽{music[0]}好唔好？你以前好鍾意聽㗎。",
                intent="reminiscence",
                route="activity",
                safety_level="safe",
                answer_language=answer_language,
                debug={"agent": "memory_routine"},
            )
        else:
            return _placeholder_result(
                answer="你想聽咩歌呀？我可以幫你搵吓。",
                intent="reminiscence",
                route="activity",
                safety_level="safe",
                answer_language=answer_language,
                debug={"agent": "memory_routine"},
            )

    # --- PHOTOS / REMINISCENCE ---
    if "相" in message or "舊" in message:
        return _placeholder_result(
            answer="睇舊相好呀！回憶吓以前嘅開心時光。",
            intent="reminiscence",
            route="activity",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    # --- MEMORY EXERCISE ---
    if "記憶練習" in message:
        return _placeholder_result(
            answer="好呀，我哋做一個記憶練習。你記唔記得今日早餐食咗乜嘢？",
            intent="cognitive_activity",
            route="activity",
            safety_level="safe",
            answer_language=answer_language,
            debug={"agent": "memory_routine"},
        )

    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["activity"][answer_language],
        intent="cognitive_activity",
        route="activity",
        safety_level="activity_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine"},
    )


# ============================================================
# 4. THE DYNAMIC "BRAIN"
# ============================================================
def _answer_personal_query(message: str, profile: dict[str, Any]) -> str | None:
    # 1. Name
    if re.search(r"我[叫嗌]?咩[嘢]?名|你記唔記得我[叫嗌]|我個名", message):
        name = profile.get("name", "你")
        return f"當然記得，你係{name}呀！"

    # 2. DYNAMIC FAMILY CHECK
    family = profile.get("family", {})
    relation_map = {
        "daughter": "女兒", "son": "仔", "wife": "太太",
        "husband": "先生", "deceased_husband": "先生", "helper": "姐姐",
        "granddaughter": "孫女", "grandson": "孫仔", "mother": "媽媽", "father": "爸爸"
    }
    for relation, name in family.items():
        if name in message:
            relation_zh = relation_map.get(relation, "家人")
            if relation == "deceased_husband":
                return f"你好掛住{name}叔叔，係咪？佢以前好疼你。我哋一齊睇吓佢嘅相，好嗎？"
            return f"{name}係你嘅{relation_zh}，佢好關心你㗎。"

    # 3. MUSIC
    if "聽" in message and ("歌" in message or "粵曲" in message or "音樂" in message):
        likes = profile.get("likes", {})
        music = likes.get("music", [])
        if music:
            return f"你鍾意聽{music[0]}，仲有{'、'.join(music[1:])}。我哋一齊聽好唔好？"

    # 4. EMOTIONAL SUPPORT
    if "做錯" in message or "錯咗" in message:
        return "你冇做錯嘢，唔使擔心。有時忘記啲嘢好正常，我哋一齊慢慢嚟。"
    if any(k in message for k in ["掛住", "好悶", "孤單", "唔開心", "擔心"]):
        return "唔使擔心，你好安全㗎。我會喺度陪你傾偈。"

    # 5. FORGETTING
    if "忘記" in message or "唔記得" in message:
        return "年紀大咗有時會咁㗎，唔使驚。我哋慢慢嚟，唔使急。"

    # 6. REPEATED PHRASES
    if "講過好多次" in message or "講過幾次" in message:
        return "唔使急，你想講幾多次都得。我會慢慢聽你講。"

    # 7. CONFUSION ABOUT PLACE
    if "喺呢度" in message or "點解我會喺度" in message:
        return "你喺屋企呀，好安全㗎。"

    # 8. LOST ITEMS
    if "唔見" in message or "攞咗" in message:
        return "唔使擔心，我哋慢慢搵吓。可能只係放喺另一個安全嘅地方。"

    return None


# ============================================================
# 5. Internal Helpers (FIXED THE BOM ISSUE HERE!)
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
        # ============================================================
        # 🔥 THE FIX: Changed from "utf-8" to "utf-8-sig"
        # This removes the invisible BOM character that Windows adds.
        # ============================================================
        data = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"DEBUG: Failed to load {path}: {e}")  # Helps debug
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
