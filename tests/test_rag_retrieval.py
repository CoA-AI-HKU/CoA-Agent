from __future__ import annotations

from src.document import Document
from src.embedder import Embedder
from src.rag_agent import RagAgent
from src.vector_store import InMemoryVectorStore


def test_expected_source_is_retrieved() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Computational linguistics is a scientific and engineering field about language.",
                metadata={"source": "Introducing_computational_linguistics.md"},
            ),
            Document(text="Caregivers can keep a calm tone.", metadata={"source": "dementia.md"}),
        ]
    )

    retrieved = agent.retrieve("What is computational linguistics?", k=8)

    assert retrieved
    assert retrieved[0].metadata["source"] == "Introducing_computational_linguistics.md"


def test_no_chunks_found_does_not_crash() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())

    result = agent.answer_question("What is missing?")

    assert result["found"] is False
    assert result["sources"] == []
