from __future__ import annotations

from pathlib import Path

import pytest

from src.pipeline.chunker import chunk_document, chunk_text
from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pdf_ingest import convert_pdf_file
from src.pdf_to_markdown import load_pdf_as_markdown
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import get_default_vector_store


def test_pdf_ingest_creates_markdown(tmp_path: Path) -> None:
    if not _has_pdf_extractor():
        pytest.skip("PDF extraction requires PyMuPDF or pypdf")

    pdf_source = Path("data/pdfs/Introducing_computational_linguistics.pdf")
    markdown_path = tmp_path / "data" / "mds" / "test.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    document = load_pdf_as_markdown(pdf_source)
    markdown_path.write_text(document.text, encoding="utf-8")

    assert markdown_path.exists()
    assert markdown_path.read_text(encoding="utf-8").strip() == document.text.strip()


def test_chunk_document_creates_chunks() -> None:
    doc = Document(text="Paragraph one.\n\nParagraph two is longer and should appear in the same chunk if it is short enough.")
    chunks = chunk_document(doc, chunk_size=50, chunk_overlap=10)

    assert len(chunks) >= 1
    assert all(chunk.text for chunk in chunks)
    assert chunks[0].metadata["chunk_index"] == 1


def test_chunk_text_uses_sentence_boundaries() -> None:
    text = "First sentence is short. Second sentence should stay intact. Third sentence starts a new smaller chunk."
    chunks = chunk_text(text, chunk_size=55, chunk_overlap=0)

    assert chunks == [
        "First sentence is short.",
        "Second sentence should stay intact.",
        "Third sentence starts a new smaller chunk.",
    ]


def test_rag_agent_retrieves_and_builds_prompt(tmp_path: Path) -> None:
    documents = [Document(text="This is a sample document.", metadata={"source": "test.md"})]
    store = get_default_vector_store(persist_directory=tmp_path / "chroma_test", collection_name="test_collection")
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=store)
    agent.index_documents(documents)

    retrieved = agent.retrieve("sample")
    assert retrieved
    assert "sample document" in retrieved[0].text

    prompt = agent.build_prompt("What is this?", retrieved)
    assert "Answer the user's question using ONLY the provided context" in prompt
    assert "Answer in 1-3 short sentences" in prompt
    assert "What is this?" in prompt


def test_rag_agent_answer_uses_deepseek_callable(tmp_path: Path) -> None:
    documents = [Document(text="The answer is 42.", metadata={"source": "test.md"})]
    store = get_default_vector_store(persist_directory=tmp_path / "chroma_test2", collection_name="test_collection2")
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=store)
    agent.index_documents(documents)

    def fake_deepseek(prompt: str) -> str:
        assert "The answer is 42." in prompt
        return "42"

    answer = agent.answer("What is the answer?", fake_deepseek)
    assert answer == "42"


def test_rag_agent_answer_with_top_chunk_returns_text(tmp_path: Path) -> None:
    documents = [Document(text="The answer is 42.", metadata={"source": "test.md"})]
    store = get_default_vector_store(persist_directory=tmp_path / "chroma_test3", collection_name="test_collection3")
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=store)
    agent.index_documents(documents)

    answer = agent.answer_with_top_chunk("What is the answer?")
    assert answer == "The answer is 42."


def _has_pdf_extractor() -> bool:
    try:
        import fitz  # noqa: F401

        return True
    except ImportError:
        pass

    try:
        import pypdf  # noqa: F401

        return True
    except ImportError:
        return False
