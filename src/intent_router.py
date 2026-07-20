from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Intent = Literal[
    "knowledge_qa",
    "self_memory_concern",
    "caregiver_support",
    "cognitive_concern_screening",
    "personal_memory",
    "reminder_request",
    "cognitive_activity",
    "emotional_support",
    "safety_sensitive",
    "medication_or_diagnosis",
    "unknown",
]


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    matched_terms: list[str]
    reason: str


SAFETY_TERMS = [
    "走失",
    "不見",
    "找不到",
    "跌倒",
    "摔倒",
    "受傷",
    "流血",
    "突然混亂",
    "突然糊塗",
    "突然不認得",
    "幻覺",
    "看見不存在",
    "聽到聲音",
    "自殺",
    "自殘",
    "傷害自己",
    "傷害別人",
    "自残",
    "伤害自己",
    "伤害别人",
    "打人",
    "暴力",
    "緊急",
    "危險",
    "紧急",
    "危险",
    "急救",
    "送院",
    "救命",
    "走丟",
    "失蹤",
    "失踪",
    "emergency",
    "urgent",
    "danger",
    "fall",
    "fell",
    "fallen",
    "bleeding",
    "missing",
    "lost",
    "wandering",
    "hallucination",
    "hallucinations",
    "suicide",
    "self-harm",
    "self harm",
    "hurt myself",
    "hurt herself",
    "hurt himself",
    "abuse",
    "violence",
]

NONURGENT_SAFETY_CONTEXT_TERMS = [
    "預防",
    "避免",
    "減少",
    "防止",
    "風險",
    "準備",
    "安全貼士",
    "照顧技巧",
    "點預防",
    "如何預防",
    "怎樣預防",
    "预防",
    "减少",
    "风险",
    "准备",
    "怎样预防",
    "prevent",
    "prevention",
    "avoid",
    "reduce risk",
    "safety tips",
]

URGENT_SAFETY_CONTEXT_TERMS = [
    "了",
    "咗",
    "而家",
    "現在",
    "现在",
    "即刻",
    "立即",
    "已經",
    "已经",
    "正在",
    "突然",
    "找不到",
    "不見",
    "失蹤",
    "不见",
    "失踪",
    "救命",
    "緊急",
    "危險",
    "紧急",
    "危险",
    "急救",
    "送院",
    "now",
    "right now",
    "already",
    "currently",
    "suddenly",
    "missing",
    "emergency",
    "urgent",
    "danger",
    "help",
]

HIGH_ACUITY_SAFETY_TERMS = [
    "自殺",
    "自殘",
    "傷害自己",
    "傷害別人",
    "自残",
    "伤害自己",
    "伤害别人",
    "打人",
    "暴力",
    "流血",
    "急救",
    "救命",
    "suicide",
    "self-harm",
    "self harm",
    "hurt myself",
    "hurt herself",
    "hurt himself",
    "bleeding",
    "abuse",
    "violence",
]

MEDICATION_DIAGNOSIS_TERMS = [
    "停藥",
    "加藥",
    "減藥",
    "藥量",
    "劑量",
    "停药",
    "加药",
    "减药",
    "药量",
    "剂量",
    "副作用",
    "可不可以食",
    "可否食",
    "應該食幾多",
    "應該吃多少",
    "吃多少",
    "食幾多",
    "診斷",
    "诊断",
    "是不是有腦退化",
    "是否有腦退化",
    "是不是腦退化",
    "是否腦退化",
    "是不是有認知障礙",
    "是否有認知障礙",
    "是不是有脑退化",
    "是否有脑退化",
    "是不是脑退化",
    "是否脑退化",
    "是不是有认知障碍",
    "是否有认知障碍",
    "病情惡化",
    "確診",
    "斷症",
    "确诊",
    "有冇腦退化",
    "diagnosis",
    "diagnose",
    "diagnosed",
    "dosage",
    "dose",
    "side effect",
    "side effects",
    "stop medication",
    "stop medicine",
    "start medication",
    "increase medication",
    "reduce medication",
    "has dementia",
]

COGNITIVE_CONCERN_SCREENING_TERMS = [
    "我是不是有腦退化症",
    "我是否有腦退化症",
    "我會不會有認知障礙",
    "我會唔會有認知障礙",
    "我最近成日唔記得嘢",
    "我最近記性差咗",
    "我媽媽是不是有腦退化症",
    "我媽媽是不是有認知障礙",
    "我媽媽最近成日唔記得嘢",
    "我媽媽係咪腦退化",
    "我爸爸是不是有腦退化症",
    "點樣知道係正常老化定腦退化",
    "怎樣知道是正常老化還是腦退化",
    "正常老化定腦退化",
    "正常老化還是腦退化",
    "腦退化症測試",
    "腦退化測試",
    "認知障礙測試",
    "記憶測試",
    "記憶力測試",
    "記性差",
    "記性差咗",
    "忘記東西",
    "忘記嘢",
    "cognitive screening",
    "dementia test",
    "memory test",
    "memory screening",
    "cognitive test",
]

SELF_MEMORY_CONCERN_TERMS = [
    "想不起來",
    "想不起来",
    "記不起",
    "记不起",
    "忘記",
    "忘记",
    "我最近覺得好多事情都記唔住",
    "我最近覺得很多事情記不住",
    "我最近覺得很多事情好像都有點記不住",
    "我成日唔記得嘢",
    "最近記性差",
    "我好似忘記好多事",
    "我經常忘記事情",
    "我是不是有腦退化症",
    "這是不是腦退化症",
    "最近好多嘢記唔住",
    "好多嘢記唔住",
    "好多事情記不住",
    "很多事情記不住",
    "記不住很多事情",
    "我覺得自己記性差",
    "我覺得自己記憶力變差",
    "我常常忘記事情",
    "我成日唔記得",
    "我成日唔記得嘢",
    "我最近記憶力變差",
    "我最近記性變差",
    "最近記憶力變差",
    "最近記性變差",
    "我是不是有腦退化症",
    "我是否有腦退化症",
    "我會不會有腦退化症",
    "我係咪有腦退化症",
    "我係唔係有腦退化症",
    "我是不是有認知障礙",
    "我是否有認知障礙",
    "我會不會有認知障礙",
    "我是不是有mci",
    "我是否有mci",
    "最近很多事情好像都有點記不住",
    "最近覺得很多事情好像都有點記不住",
    "i keep forgetting things",
    "i keep forgetting",
    "i forget things",
    "my memory is getting worse",
    "am i getting dementia",
    "do i have dementia",
]

CAREGIVER_SUPPORT_TERMS = [
    "我媽媽",
    "我媽咪",
    "媽媽記唔住",
    "媽媽記不住",
    "爸爸記唔住",
    "爸爸記不住",
    "家人記唔住",
    "家人記不住",
    "媽媽是不是有腦退化症",
    "爸爸是不是有腦退化症",
    "家人是不是有腦退化症",
    "媽媽係咪有腦退化症",
    "爸爸係咪有腦退化症",
    "媽媽成日重複問",
    "爸爸成日重複問",
    "家人成日重複問",
]

REMINDER_TERMS = [
    "提醒",
    "提我",
    "記得",
    "幾點",
    "覆診",
    "約了",
    "約咗",
    "吃藥",
    "食藥",
    "飲水",
    "记得",
    "几点",
    "复诊",
    "约了",
    "吃药",
    "喝水",
    "喝水",
    "下午茶",
    "散步",
    "schedule",
    "remind",
    "reminder",
    "appointment",
]

PERSONAL_MEMORY_TERMS = [
    "我叫什麼",
    "我叫咩",
    "我女兒",
    "我兒子",
    "我太太",
    "我先生",
    "我喜歡",
    "我鍾意",
    "我通常",
    "今天有什麼安排",
    "今日有咩安排",
    "我的家人",
    "我女儿",
    "我儿子",
    "我喜欢",
    "今天有什么安排",
    "我的家人",
    "屋企人",
    "personal",
    "routine",
    "my daughter",
    "my son",
    "my wife",
    "my husband",
    "my family",
]

ACTIVITY_TERMS = [
    "悶",
    "無聊",
    "无聊",
    "玩遊戲",
    "記憶遊戲",
    "腦部訓練",
    "活動",
    "陪我聊天",
    "同我傾計",
    "做什麼",
    "做咩",
    "可以做",
    "聊天",
    "玩游戏",
    "记忆游戏",
    "脑部训练",
    "活动",
    "做什么",
    "傾計",
    "exercise",
    "activity",
    "game",
    "bored",
    "chat",
]

EMOTIONAL_TERMS = [
    "很鬱悶",
    "很郁闷",
    "鬱悶",
    "郁闷",
    "很煩",
    "很烦",
    "不知道怎麼辦",
    "不知道怎麽辦",
    "不知道怎么办",
    "擔心",
    "害怕",
    "驚",
    "孤單",
    "寂寞",
    "不開心",
    "唔開心",
    "難過",
    "煩",
    "焦慮",
    "緊張",
    "担心",
    "难过",
    "烦",
    "焦虑",
    "紧张",
    "sad",
    "lonely",
    "worried",
    "worry",
    "anxious",
    "scared",
    "afraid",
    "frustrated",
]

KNOWLEDGE_TERMS = [
    "腦退化",
    "認知障礙",
    "輕度認知障礙",
    "脑退化",
    "认知障碍",
    "轻度认知障碍",
    "mci",
    "dementia",
    "阿茲海默",
    "阿爾茲海默",
    "阿茨海默",
    "症狀",
    "照顧者",
    "照顧",
    "記憶力",
    "溝通",
    "重複問",
    "重複提問",
    "症状",
    "照顾者",
    "照顾",
    "记忆力",
    "沟通",
    "重复问",
    "重复提问",
    "走失",
    "日常生活",
    "caregiver",
    "caregiving",
    "memory",
    "repeat the same question",
    "repeats the same question",
    "symptom",
    "symptoms",
    "alzheimer",
    "alzheimers",
    "alzheimer's",
]


def classify_intent(message: str) -> IntentResult:
    normalized = _normalize(message)
    if not normalized:
        return IntentResult(
            intent="unknown",
            confidence=0.0,
            matched_terms=[],
            reason="Message is empty after normalization.",
        )

    safety_matches = _matched_terms(normalized, SAFETY_TERMS)
    if _is_urgent_safety_match(normalized, safety_matches):
        return IntentResult(
            intent="safety_sensitive",
            confidence=_confidence(0.95, len(safety_matches)),
            matched_terms=safety_matches,
            reason="Matched urgent or current safety-risk terms.",
        )

    caregiver_matches = _matched_terms(normalized, CAREGIVER_SUPPORT_TERMS)
    screening_matches = _matched_terms(normalized, COGNITIVE_CONCERN_SCREENING_TERMS)
    if caregiver_matches and screening_matches:
        return IntentResult(
            intent="cognitive_concern_screening",
            confidence=_confidence(0.92, len(screening_matches)),
            matched_terms=screening_matches,
            reason="Matched a caregiver-reported screening or diagnosis concern.",
        )

    priority_rules: list[tuple[Intent, list[str], float, str]] = [
        (
            "caregiver_support",
            CAREGIVER_SUPPORT_TERMS,
            0.9,
            "Matched caregiver observation or support terms.",
        ),
        (
            "self_memory_concern",
            SELF_MEMORY_CONCERN_TERMS,
            0.94,
            "Matched first-person memory concern terms.",
        ),
        (
            "cognitive_concern_screening",
            COGNITIVE_CONCERN_SCREENING_TERMS,
            0.92,
            "Matched cognitive concern screening terms.",
        ),
        (
            "medication_or_diagnosis",
            MEDICATION_DIAGNOSIS_TERMS,
            0.95,
            "Matched medication or diagnosis boundary terms.",
        ),
        ("reminder_request", REMINDER_TERMS, 0.85, "Matched reminder or schedule terms."),
        ("personal_memory", PERSONAL_MEMORY_TERMS, 0.8, "Matched personal memory terms."),
        ("cognitive_activity", ACTIVITY_TERMS, 0.8, "Matched activity or engagement terms."),
        ("emotional_support", EMOTIONAL_TERMS, 0.8, "Matched emotional support terms."),
        ("knowledge_qa", KNOWLEDGE_TERMS, 0.7, "Matched dementia knowledge terms."),
    ]

    for intent, terms, confidence, reason in priority_rules:
        matched_terms = _matched_terms(normalized, terms)
        if matched_terms:
            return IntentResult(
                intent=intent,
                confidence=_confidence(confidence, len(matched_terms)),
                matched_terms=matched_terms,
                reason=reason,
            )

    return IntentResult(
        intent="unknown",
        confidence=0.2,
        matched_terms=[],
        reason="No configured intent terms matched.",
    )


def _normalize(message: str) -> str:
    return " ".join(message.strip().lower().split())


def _matched_terms(normalized_message: str, terms: list[str]) -> list[str]:
    matches: list[str] = []
    seen: set[str] = set()
    for term in terms:
        normalized_term = _normalize(term)
        if normalized_term and normalized_term in normalized_message and normalized_term not in seen:
            matches.append(term)
            seen.add(normalized_term)
    return matches


def _is_urgent_safety_match(normalized_message: str, matched_terms: list[str]) -> bool:
    if not matched_terms:
        return False
    if _matched_terms(normalized_message, HIGH_ACUITY_SAFETY_TERMS):
        return True
    if _matched_terms(normalized_message, NONURGENT_SAFETY_CONTEXT_TERMS):
        return False
    return bool(_matched_terms(normalized_message, URGENT_SAFETY_CONTEXT_TERMS))


def _confidence(base_confidence: float, matched_count: int) -> float:
    if matched_count <= 1:
        return base_confidence
    return min(0.99, base_confidence + (matched_count - 1) * 0.03)
