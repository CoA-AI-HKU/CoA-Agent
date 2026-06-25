from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

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

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        # naive nearest by dot product (works for small tests)
        if not self.embeddings:
            return []

        if query_embedding is None:
            # Fallback for callers that do not provide an embedder-backed query vector.
            import hashlib

            digest = hashlib.md5(query_text.encode("utf-8")).hexdigest()
            qvec: List[float] = []
            for i in range(0, 32, 4):
                chunk = digest[i : i + 4]
                num = int(chunk, 16)
                qvec.append(num / 65535.0)
        else:
            qvec = query_embedding

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

    def count(self) -> int:
        return len(self.items)

    def clear(self) -> None:
        self.items.clear()
        self.metadatas.clear()
        self.embeddings.clear()


class ChromaVectorStore:
    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "ling_rag",
        client_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        from chromadb import PersistentClient
        from chromadb.config import Settings

        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.client_settings = client_settings or {}
        settings = Settings(**self.client_settings)
        if self.persist_directory is not None:
            self.client = PersistentClient(path=str(self.persist_directory), settings=settings)
        else:
            from chromadb import Client

            self.client = Client(settings)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def add_documents(self, documents: Iterable[Document], embeddings: List[List[float]]) -> None:
        docs = list(documents)
        items = [doc.text for doc in docs]
        metadatas = [doc.metadata for doc in docs]
        ids = [
            f"{doc.metadata.get('source', 'doc')}-{doc.metadata.get('chunk_index', index)}-{uuid4().hex}"
            for index, doc in enumerate(docs, start=1)
        ]

        self.collection.add(
            documents=items,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

    def query(
        self,
        query_text: str,
        n_results: int = 5,
        query_embedding: Optional[List[float]] = None,
    ) -> List[Dict[str, Any]]:
        query_args: Dict[str, Any] = {
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if query_embedding is not None:
            query_args["query_embeddings"] = [query_embedding]
        else:
            query_args["query_texts"] = [query_text]

        results = self.collection.query(**query_args)
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

    def count(self) -> int:
        return self.collection.count()

    def clear(self) -> None:
        self.client.delete_collection(name=self.collection_name)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)


def get_default_vector_store(persist_directory: Optional[Path] = None, collection_name: str = "ling_rag"):
    try:
        return ChromaVectorStore(persist_directory=persist_directory, collection_name=collection_name)
    except Exception:
        return InMemoryVectorStore(persist_directory=persist_directory, collection_name=collection_name)
