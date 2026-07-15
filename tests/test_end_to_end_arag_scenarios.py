from __future__ import annotations

import re

import pytest

from src.agents.user_facing_formatter import answer_has_user_visible_leakage


@pytest.fixture
def local_rag(monkeypatch):
    def fake_answer(question, _config=None):
        if "量子" in question:
            return {
                "answer": "我暫時沒有足夠資料回答這個問題。",
                "found": False,
                "sources": [],
                "debug": {"retrieval": {"route": "knowledge_qa", "tools_used": ["keyword_search", "semantic_search"], "keyword_queries": [], "semantic_queries": [question], "chunks_read": [], "evidence_sufficient": False, "retrieval_failed": True, "answer_used_rag": False}},
            }
        return {
            "answer": "腦退化症會影響記憶、思考及日常生活能力。",
            "found": True,
            "sources": ["data/mds/private.md"],
            "debug": {"retrieval": {"route": "knowledge_qa", "tools_used": ["keyword_search", "semantic_search", "chunk_read"], "keyword_queries": [["腦退化症"]], "semantic_queries": [question], "chunks_read": ["chunk-1"], "evidence_sufficient": True, "retrieval_failed": False, "answer_used_rag": True}},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer)
    monkeypatch.setattr("src.agents.screening_agent.answer_question", fake_answer, raising=False)


def _handle(message: str):
    from src.orchestrator import handle_dementia_user_message

    return handle_dementia_user_message(message, user_id="scenario-user")


def _assert_clean(result) -> None:
    answer = result["answer"]
    assert not answer_has_user_visible_leakage(answer)
    for value in (".md", "keyword_search", "semantic_search", "chunk_read", "debug", "根據資料庫"):
        assert value.casefold() not in answer.casefold()


def test_dementia_knowledge_qa_uses_arag(local_rag) -> None:
    result = _handle("腦退化症是什麼？")
    trace = result["debug"]["retrieval"]
    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True
    assert trace["tools_used"]
    assert trace["evidence_sufficient"] is True
    assert re.search(r"[\u3400-\u9fff]", result["answer"])
    _assert_clean(result)


def test_caregiver_repeated_question_guidance_uses_arag(local_rag) -> None:
    result = _handle("媽媽成日重複問同一條問題，我應該點做？")
    assert result["route"] == "caregiver_guidance"
    assert result["rag_called"] is True
    assert any(term in result["answer"] for term in ("冷靜", "耐心", "安撫", "記錄", "提醒"))
    _assert_clean(result)


def test_medication_safety_overrides_arag(local_rag) -> None:
    result = _handle("我食緊 Donepezil，頭痛可唔可以食 aspirin？")
    assert result["route"] == "medical_boundary"
    assert result["rag_called"] is False
    assert any(term in result["answer"] for term in ("醫生", "藥劑師", "doctor", "pharmacist"))
    assert not re.search(r"\b\d+\s*(mg|ml)\b", result["answer"], re.I)
    _assert_clean(result)


def test_forgot_medication_uses_uncertainty_boundary(local_rag) -> None:
    result = _handle("我唔記得今日有冇食藥，係咪食多次？")
    assert result["route"] == "medical_boundary"
    assert result["rag_called"] is False
    assert any(term in result["answer"] for term in ("不要", "唔好", "不確定", "藥盒", "記錄"))
    _assert_clean(result)


def test_wandering_is_immediate_and_skips_arag(local_rag) -> None:
    result = _handle("我媽媽走失咗，搵唔到佢")
    assert result["route"] == "safety"
    assert result["rag_called"] is False
    assert any(term in result["answer"] for term in ("報警", "緊急", "警察", "emergency"))
    _assert_clean(result)


def test_memory_concern_is_neutral_and_non_diagnostic(local_rag) -> None:
    result = _handle("我最近覺得好多事情都記唔住")
    assert result["route"] == "memory_concern"
    assert "你有腦退化症" not in result["answer"]
    assert result["rag_called"] is False
    _assert_clean(result)


def test_out_of_scope_skips_arag(local_rag) -> None:
    result = _handle("幫我寫一首關於夏天的歌")
    assert result["route"] in {"unknown", "supportive", "out_of_scope"}
    assert result["rag_called"] is False
    _assert_clean(result)


def test_insufficient_evidence_returns_safe_fallback(local_rag) -> None:
    result = _handle("腦退化症患者的量子糾纏治療規格是什麼？")
    assert result["route"] == "rag_qa"
    assert result["debug"]["retrieval"]["evidence_sufficient"] is False
    assert any(term in result["answer"] for term in ("沒有足夠", "未有足夠", "暫時", "不足"))
    _assert_clean(result)

