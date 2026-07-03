from __future__ import annotations

from typing import Literal


AnswerLanguage = Literal["zh-Hant", "zh-Hans", "en"]


TRADITIONAL_CHINESE_CHARS = set(
    "腦認礙輕顧記憶藥劑醫護聯絡資資料來麼個問題這點說會"
    "診斷開發緊急服務癡呆長者應該現請聽見視覺"
)
SIMPLIFIED_CHINESE_CHARS = set(
    "脑认碍轻顾记忆药剂医护联络资资料来么个问题这点说会"
    "诊断开发紧急服务痴呆长者应该现请听见视觉"
)

SUPPORTED_ANSWER_LANGUAGES: tuple[AnswerLanguage, ...] = ("zh-Hant", "zh-Hans", "en")


def detect_answer_language(text: str, override: str | None = None) -> AnswerLanguage:
    """Choose the single output language/script for an answer."""
    if override and override != "auto":
        if override not in SUPPORTED_ANSWER_LANGUAGES:
            raise ValueError(f"Unsupported answer_language: {override}")
        return override  # type: ignore[return-value]

    if not text or not text.strip():
        return "zh-Hant"

    cjk_chars = [char for char in text if "\u3400" <= char <= "\u9fff"]
    if not cjk_chars:
        return "en"

    traditional_score = sum(char in TRADITIONAL_CHINESE_CHARS for char in cjk_chars)
    simplified_score = sum(char in SIMPLIFIED_CHINESE_CHARS for char in cjk_chars)
    if simplified_score > traditional_score:
        return "zh-Hans"
    return "zh-Hant"


def language_name(answer_language: AnswerLanguage) -> str:
    return {
        "zh-Hant": "Traditional Chinese",
        "zh-Hans": "Simplified Chinese",
        "en": "English",
    }[answer_language]
