from __future__ import annotations

import re

from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.prompts import FALLBACK_ANSWER_EN, FALLBACK_ANSWER_ZH_HANS
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def test_answer_question_returns_concise_grounded_answer() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Computational linguistics is the scientific and engineering discipline concerned with written and spoken language.",
                metadata={"source": "Introducing_computational_linguistics.md"},
            )
        ]
    )

    result = agent.answer_question("What is computational linguistics?")

    assert result["found"] is True
    assert "scientific" in result["answer"].lower()
    assert "engineering" in result["answer"].lower()
    assert "language" in result["answer"].lower()
    assert "Sources: Introducing_computational_linguistics.md" in result["answer_with_sources"]
    assert result["sources"] == ["Introducing_computational_linguistics.md"]
    assert result["debug"]["answer_language"] == "en"
    assert _sentence_count(result["answer"]) <= 3


def test_answer_question_falls_back_for_unrelated_question() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Dementia caregivers can respond with a calm voice and reassurance.",
                metadata={"source": "dementia.md"},
            )
        ]
    )

    result = agent.answer_question("What is the capital of France?")

    assert result["found"] is False
    assert result["answer"] == FALLBACK_ANSWER_EN
    assert result["sources"] == []


def test_simplified_question_uses_simplified_fallback_and_source_label() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="脑退化症照顾者可以用平静的语气回应，并用简单句子安抚患者，帮助患者慢慢理解眼前的情况。",
                metadata={"source": "dementia_cn.md"},
            )
        ]
    )

    result = agent.answer_question("脑退化症照顾者可以怎样回应？")

    assert result["debug"]["answer_language"] == "zh-Hans"
    assert "资料来源：dementia_cn.md" in result["answer_with_sources"]

    fallback = agent.answer_question("法国首都是什么？")
    assert fallback["answer"] == FALLBACK_ANSWER_ZH_HANS


def test_fake_answer_callable_receives_cross_language_prompt() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="腦退化症可能影響記憶、思考和日常生活。",
                metadata={"source": "dementia_hk.md"},
            )
        ]
    )

    def fake_answer(prompt: str) -> str:
        assert "Answer only in English." in prompt
        assert "Traditional Chinese, Simplified Chinese, or English" in prompt
        return "Dementia may affect memory, thinking, and daily life."

    result = agent.answer_question("What can dementia affect?", answer_callable=fake_answer)

    assert result["answer"] == "Dementia may affect memory, thinking, and daily life."
    assert result["debug"]["answer_language"] == "en"
