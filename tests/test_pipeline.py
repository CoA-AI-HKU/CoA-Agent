from __future__ import annotations

from pathlib import Path

from src.chunker import chunk_document
from src.document import Document
from src.pdf_ingest import convert_pdf_file
from src.pdf_to_markdown import load_pdf_as_markdown
from src.rag_agent import RagAgent
from src.vector_store import ChromaVectorStore


def test_pdf_ingest_creates_markdown(tmp_path: Path) -> None:
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


def test_rag_agent_retrieves_and_builds_prompt(tmp_path: Path) -> None:
    documents = [Document(text="This is a sample document.", metadata={"source": "test.md"})]
    store = ChromaVectorStore(persist_directory=tmp_path / "chroma_test", collection_name="test_collection")
    agent = RagAgent(vector_store=store)
    agent.index_documents(documents)

    retrieved = agent.retrieve("sample")
    assert retrieved
    assert "sample document" in retrieved[0].text

    prompt = agent.build_prompt("What is this?", retrieved)
    assert "Answer using only the provided context" in prompt
    assert "What is this?" in prompt


def test_rag_agent_answer_uses_deepseek_callable(tmp_path: Path) -> None:
    documents = [Document(text="The answer is 42.", metadata={"source": "test.md"})]
    store = ChromaVectorStore(persist_directory=tmp_path / "chroma_test2", collection_name="test_collection2")
    agent = RagAgent(vector_store=store)
    agent.index_documents(documents)

    def fake_deepseek(prompt: str) -> str:
        assert "The answer is 42." in prompt
        return "42"

    answer = agent.answer("What is the answer?", fake_deepseek)
    assert answer == "42"
