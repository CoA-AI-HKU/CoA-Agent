from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .document import Document


class InMemoryVectorStore:
    """A tiny in-memory fallback vector store for testing without chromadb.

    It stores texts, metadatas and embeddings and supports a query that computes
    cosine similarity over provided embeddings.
    """

    def __init__(self, persist_directory: Optional[Path] = None, collection_name: str = "ling_rag") -> None:
        self.items: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self.embeddings: List[List[float]] = []

    def add_documents(self, documents: Iterable[Document], embeddings: List[List[float]]) -> None:
        for doc, emb in zip(documents, embeddings):
            self.items.append(doc.text)
            self.metadatas.append(doc.metadata)
            self.embeddings.append(list(emb))

    def query(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
        # naive nearest by dot product (works for small tests)
        if not self.embeddings:
            return []

        # build an embedding for the query using a simple hash-based method
        import hashlib

        digest = hashlib.md5(query_text.encode("utf-8")).hexdigest()
        qvec: List[float] = []
        for i in range(0, 32, 4):
            chunk = digest[i : i + 4]
            num = int(chunk, 16)
            qvec.append(num / 65535.0)

        def dot(a: List[float], b: List[float]) -> float:
            # pad to same length
            n = max(len(a), len(b))
            suma = 0.0
            for i in range(n):
                va = a[i] if i < len(a) else 0.0
                vb = b[i] if i < len(b) else 0.0
                suma += va * vb
            return suma

        scores = [dot(qvec, emb) for emb in self.embeddings]
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:n_results]
        output: List[Dict[str, Any]] = []
        for idx, score in ranked:
            output.append({
                "text": self.items[idx],
                "metadata": self.metadatas[idx],
                "distance": 1.0 - score,
            })
        return output

    def persist(self) -> None:
        return


def get_default_vector_store(persist_directory: Optional[Path] = None, collection_name: str = "ling_rag"):
    try:
        from chromadb import Client
        from chromadb.config import Settings

        # if chromadb is importable, use it
        class ChromaVectorStore:
            def __init__(self, persist_directory: Optional[Path] = None, collection_name: str = "ling_rag", client_settings: Optional[Dict[str, Any]] = None) -> None:
                self.persist_directory = persist_directory
                self.collection_name = collection_name
                self.client_settings = client_settings or {}
                self.client = Client(Settings(**self.client_settings))
                self.collection = self._get_or_create_collection()

            def _get_or_create_collection(self):
                if self.persist_directory is not None:
                    return self.client.get_or_create_collection(
                        name=self.collection_name,
                        metadata={"persist_directory": str(self.persist_directory)},
                    )
                return self.client.get_or_create_collection(name=self.collection_name)

            def add_documents(self, documents: Iterable[Document], embeddings: List[List[float]]) -> None:
                items = [doc.text for doc in documents]
                metadatas = [doc.metadata for doc in documents]
                ids = [f"doc-{i}" for i, _ in enumerate(documents, start=1)]

                self.collection.add(
                    documents=items,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )

            def query(self, query_text: str, n_results: int = 5) -> List[Dict[str, Any]]:
                results = self.collection.query(
                    query_texts=[query_text],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"],
                )
                output: List[Dict[str, Any]] = []
                if results["documents"]:
                    for doc, metadata, distance in zip(
                        results["documents"][0],
                        results["metadatas"][0],
                        results["distances"][0],
                    ):
                        output.append({
                            "text": doc,
                            "metadata": metadata,
                            "distance": distance,
                        })
                return output

            def persist(self) -> None:
                if hasattr(self.client, "persist"):
                    self.client.persist()

        return ChromaVectorStore(persist_directory=persist_directory, collection_name=collection_name)
    except Exception:
        return InMemoryVectorStore(persist_directory=persist_directory, collection_name=collection_name)
