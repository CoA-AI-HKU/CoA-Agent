from __future__ import annotations

import logging

import pytest

from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.language import detect_answer_language
from src.pipeline.query_normalization import normalize_retrieval_query
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore
from src.user.message_router import handle_incoming_message


QUERIES = ("腦退化症是什麼", "腦退化症是什麽", "脑退化是什么")


def _definition_agent() -> RagAgent:
    agent = RagAgent(
        embedder=Embedder(provider="dummy"),
        vector_store=InMemoryVectorStore(),
        min_relevance_score=0.0,
    )
    agent.index_documents([
        Document(
            text="腦退化症是一種會影響記憶、思考、語言和日常生活能力的疾病。",
            metadata={"source": "dementia-definition.md", "heading": "腦退化症是什麼"},
        ),
        Document(
            text="照顧者可安排規律活動並使用平靜語氣溝通。",
            metadata={"source": "care-tips.md", "heading": "照顧提示"},
        ),
    ])
    return agent


def test_confirmed_chinese_variants_normalize_identically() -> None:
    assert {normalize_retrieval_query(query) for query in QUERIES} == {"腦退化症是什麼"}


@pytest.mark.parametrize("query", QUERIES)
def test_all_variants_retrieve_definition_without_fallback(query: str) -> None:
    result = _definition_agent().answer_question(query, answer_callable=lambda prompt: "腦退化症會影響多方面能力。")

    assert result["found"] is True
    assert result["sources"][0] == "dementia-definition.md"
    assert "找不到足夠資料" not in result["answer"]


def test_simplified_input_keeps_simplified_answer_language() -> None:
    assert detect_answer_language("脑退化是什么") == "zh-Hans"
    result = _definition_agent().answer_question("脑退化是什么", answer_callable=lambda prompt: "这是简体回答。")
    assert result["debug"]["answer_language"] == "zh-Hans"


@pytest.mark.parametrize("sender_id", ["diagnostic-new-sender", "8830339339"])
def test_repeated_same_sender_still_invokes_retrieval_path(monkeypatch, tmp_path, sender_id) -> None:
    calls = []
    agent = _definition_agent()

    def fake_patient_handler(message, sender_id, user_id, channel):
        calls.append((message, sender_id))
        result = agent.answer_question(message, answer_callable=lambda prompt: "腦退化症會影響多方面能力。")
        return {**result, "route": "rag_qa", "intent": "knowledge_qa", "safety_level": "normal"}

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr("src.user.message_router.handle_patient_user_message", fake_patient_handler)

    first = handle_incoming_message("腦退化症是什麽", sender_id, "telegram")
    second = handle_incoming_message("腦退化症是什麽", sender_id, "telegram")

    assert len(calls) == 2
    assert first["sources"] == second["sources"] == ["dementia-definition.md"]
    assert first["found"] is second["found"] is True


def test_query_logs_include_codepoints_only_in_debug_mode(monkeypatch, caplog) -> None:
    monkeypatch.setenv("RAG_DEBUG", "true")
    caplog.set_level(logging.INFO)

    _definition_agent().retrieve("脑退化是什么", k=1)

    assert "retrieval_query" in caplog.text
    assert "unicode_code_points=" in caplog.text
    assert "retrieval_query_changed=True" in caplog.text
