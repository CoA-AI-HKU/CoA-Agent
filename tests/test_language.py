from __future__ import annotations

import pytest

from src.pipeline.language import detect_answer_language


def test_detect_answer_language_for_supported_inputs() -> None:
    assert detect_answer_language("腦退化症有什麼症狀？") == "zh-Hant"
    assert detect_answer_language("脑退化症有什么症状？") == "zh-Hans"
    assert detect_answer_language("What are dementia symptoms?") == "en"


def test_detect_answer_language_defaults_ambiguous_chinese_to_traditional() -> None:
    assert detect_answer_language("媽媽走失了") == "zh-Hant"


def test_detect_answer_language_accepts_override() -> None:
    assert detect_answer_language("What are dementia symptoms?", "zh-Hans") == "zh-Hans"


def test_detect_answer_language_rejects_unknown_override() -> None:
    with pytest.raises(ValueError):
        detect_answer_language("hello", "fr")
