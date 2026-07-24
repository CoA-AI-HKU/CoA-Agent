from __future__ import annotations

import pytest

from src.agents.user_facing_formatter import format_user_facing_answer


def _format(answer: str, safety_level: str | None = None) -> str:
    return format_user_facing_answer(
        {
            "answer": answer,
            "sources": [],
            "found": True,
            "rag_called": True,
            "safety_level": safety_level,
        }
    )["answer"]


def test_long_knowledge_answer_keeps_two_to_three_complete_sentences() -> None:
    sentences = [
        "腦退化症會影響記憶、思考和日常生活能力，但每個人的表現和進展速度都可能不同。",
        "常見情況包括記憶力下降、語言表達困難，以及處理熟悉事情時需要較多時間。",
        "若這些轉變持續影響生活，可以記下具體例子並向合資格醫護人員查詢。",
        "及早了解原因有助安排合適支援，也能排除其他可能造成相似變化的健康因素。",
    ]

    answer = _format("".join(sentences) * 2)

    assert 2 <= sum(answer.count(mark) for mark in "。！？!?") <= 3
    assert len(answer) <= 220
    assert answer[-1] in "。！？!?"


@pytest.mark.parametrize("ending", ["，", ",", "：", ":"])
def test_truncated_answer_never_ends_with_comma_or_colon(ending: str) -> None:
    answer = _format("這是一個沒有句號的很長說明" * 30 + ending)

    assert answer[-1] == "。"
    assert len(answer) <= 220


def test_final_chinese_punctuation_is_preserved() -> None:
    assert _format("這是已經完整的簡短回答。") == "這是已經完整的簡短回答。"


def test_already_short_answer_remains_unchanged() -> None:
    answer = "腦退化症並不是正常老化的一部分。"
    assert _format(answer) == answer


def test_short_knowledge_answer_still_keeps_at_most_three_sentences() -> None:
    answer = _format("第一句完整。第二句完整。第三句完整。第四句不應保留。")

    assert answer == "第一句完整。第二句完整。第三句完整。"


@pytest.mark.parametrize(
    ("safety_level", "limit"),
    [("urgent_boundary", 250), ("medical_boundary", 250)],
)
def test_urgent_and_medical_routes_retain_existing_limits(safety_level: str, limit: int) -> None:
    answer = _format("請立即聯絡合資格醫護人員處理這個情況" * 30, safety_level)

    assert len(answer) <= limit
    assert answer[-1] in "。！？!?"
