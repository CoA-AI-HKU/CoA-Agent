from __future__ import annotations

from pathlib import Path

from src.document import Document
from src.vector_store import ChromaVectorStore


def test_chroma_vector_store_add_and_query(tmp_path: Path) -> None:
    store = ChromaVectorStore(persist_directory=tmp_path / "chroma_store", collection_name="vector_store_test")
    documents = [
        Document(text="A short document about linguistics.", metadata={"source": "one.md"}),
        Document(text="A second document about computational linguistics.", metadata={"source": "two.md"}),
    ]
    embeddings = [[0.1] * 384, [0.2] * 384]

    store.add_documents(documents, embeddings)
    results = store.query("computational linguistics", n_results=1)

    assert len(results) == 1
    assert results[0]["metadata"]["source"] == "two.md"
