from __future__ import annotations

from src.agents.user_facing_formatter import format_user_facing_answer
from src.orchestrator import handle_dementia_user_message


SOURCE_HEAVY_MEDICATION_ANSWER = """資料庫冇提到阿司匹林，所以我冇辦法話你知食唔食得。

資料庫嘅指引係清楚嘅：

「使用非處方藥物、保健食品、營養補充劑和中成藥前，請諮詢醫護人員或藥劑師」
（來源：dementia-medications-358f15bdfa.md）

「切勿自行購買藥物服用，以免出現不良的藥物反應」
（來源：what-is-dementia-2135bc8c1d.md）

請打電話問醫生或藥劑師，唔好自己決定食。"""


def _assert_no_source_dump(answer: str) -> None:
    blocked = [
        "根據資料庫",
        "根據文件",
        "來源",
        ".md",
        "資料庫提到",
        "資料庫嘅指引",
        "文件嘅指引",
        "source:",
    ]
    for phrase in blocked:
        assert phrase not in answer


def test_sources_are_removed_from_final_answer() -> None:
    result = {
        "answer": SOURCE_HEAVY_MEDICATION_ANSWER,
        "answer_with_sources": SOURCE_HEAVY_MEDICATION_ANSWER,
        "sources": ["dementia-medications-358f15bdfa.md", "what-is-dementia-2135bc8c1d.md"],
        "found": True,
        "debug": {"retrieved_count": 2},
        "rag_called": True,
    }

    formatted = format_user_facing_answer(result)

    _assert_no_source_dump(formatted["answer"])
    _assert_no_source_dump(formatted["answer_with_sources"])
    assert formatted["answer_with_sources"] == formatted["answer"]
    assert formatted["sources"] == ["dementia-medications-358f15bdfa.md", "what-is-dementia-2135bc8c1d.md"]
    assert formatted["found"] is True
    assert formatted["debug"]["retrieved_count"] == 2
    assert formatted["debug"]["raw_answer_before_formatting"] == SOURCE_HEAVY_MEDICATION_ANSWER


def test_sources_requested_are_metadata_not_answer_filenames() -> None:
    result = {
        "answer": "這是簡短回答。",
        "sources": ["abc.md"],
        "found": True,
        "debug": {},
        "rag_called": True,
    }

    formatted = format_user_facing_answer(result, show_sources=True)

    assert formatted["sources"] == ["abc.md"]
    assert formatted["sources_available"] is True
    assert formatted["source_count"] == 1
    assert ".md" not in formatted["answer"]
    assert "來源" not in formatted["answer"]
    assert ".md" not in formatted["answer_with_sources"]
    assert "來源" not in formatted["answer_with_sources"]


def test_aspirin_answer_is_short_and_no_sources() -> None:
    result = {
        "answer": SOURCE_HEAVY_MEDICATION_ANSWER,
        "answer_with_sources": SOURCE_HEAVY_MEDICATION_ANSWER,
        "sources": ["dementia-medications-358f15bdfa.md"],
        "found": True,
        "debug": {"user_message": "我有點頭疼該吃阿司匹林嗎？"},
        "rag_called": True,
        "route": "rag_qa",
    }

    formatted = format_user_facing_answer(result)

    assert "不能判斷你是否適合吃阿司匹林" in formatted["answer"]
    assert "醫生或藥劑師" in formatted["answer"]
    _assert_no_source_dump(formatted["answer"])
    assert "資料庫" not in formatted["answer"]
    assert len(formatted["answer"]) <= 250


def test_orchestrator_final_output_uses_formatter(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "根據資料庫嘅資料，腦退化症會影響日常生活。\n\n「引用內容」\n（來源：abc.md）",
            "answer_with_sources": "根據資料庫嘅資料，腦退化症會影響日常生活。\n\n來源：abc.md",
            "sources": ["abc.md"],
            "found": True,
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    _assert_no_source_dump(result["answer"])
    _assert_no_source_dump(result["answer_with_sources"])
    assert result["sources"] == ["abc.md"]
    assert result["debug"]["raw_answer_before_formatting"]


def test_wandering_answer_is_concise_and_has_no_source_filename() -> None:
    result = handle_dementia_user_message("媽媽走失了怎麼辦？")

    assert "報警" in result["answer"] or "緊急" in result["answer"]
    assert "近照" in result["answer"] or "衣著" in result["answer"]
    _assert_no_source_dump(result["answer"])
    assert len(result["answer"]) <= 250
    assert "sources" in result
    assert "debug" in result


def test_medication_uncertainty_answer_is_safe_and_has_no_source_dump() -> None:
    result = handle_dementia_user_message("我忘記了我有沒有吃過藥怎麼辦？")

    assert "不要自行再服一次" in result["answer"] or "不要自行补吃" in result["answer"]
    assert "照顧者" in result["answer"] or "照顾者" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    _assert_no_source_dump(result["answer"])
    assert "sources" in result
    assert "debug" in result


def test_aspirin_question_boundary_has_warning_signs_and_no_source_dump() -> None:
    result = handle_dementia_user_message("我有點頭疼該吃阿司匹林嗎？")

    assert "不能判斷" in result["answer"] or "不能判断" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    assert "立即求醫" in result["answer"] or "立即求医" in result["answer"]
    assert "可以吃阿司匹林" not in result["answer"]
    assert "不可以吃阿司匹林" not in result["answer"]
    _assert_no_source_dump(result["answer"])
