from __future__ import annotations

import re

from src.document import Document
from src.embedder import Embedder
from src.prompts import FALLBACK_ANSWER
from src.rag_agent import RagAgent
from src.vector_store import InMemoryVectorStore


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
    assert "資料來源：Introducing_computational_linguistics.md" in result["answer_with_sources"]
    assert result["sources"] == ["Introducing_computational_linguistics.md"]
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
    assert result["answer"] == FALLBACK_ANSWER
    assert result["sources"] == []
