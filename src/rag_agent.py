from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .chunker import chunk_documents
from .document import Document
from .embedder import Embedder
from .vector_store import get_default_vector_store


class RagAgent:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        embedder_model_name: Optional[str] = None,
        embedder_provider: str = "auto",
        offline_embeddings: bool = False,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        top_k: int = 5,
        max_context_chars: int = 3000,
        per_chunk_chars: int = 1000,
    ) -> None:
        self._embedder = embedder
        self.embedder_model_name = embedder_model_name
        self.embedder_provider = embedder_provider
        self.offline_embeddings = offline_embeddings
        self.vector_store = vector_store  # lazily created when needed
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.max_context_chars = max_context_chars
        self.per_chunk_chars = per_chunk_chars

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(
                model_name=self.embedder_model_name,
                provider=self.embedder_provider,
                offline=self.offline_embeddings,
            )
        return self._embedder

    def index_documents(self, documents: List[Document]) -> None:
        if self.vector_store is None:
            self.vector_store = get_default_vector_store()
        chunks = chunk_documents(documents, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        embeddings = self.embedder.encode_documents(chunks)
        self.vector_store.add_documents(chunks, embeddings)
        self.vector_store.persist()

    def retrieve(self, query: str, k: Optional[int] = None) -> List[Document]:
        k = k or self.top_k
        if self.vector_store is None:
            self.vector_store = get_default_vector_store()
        query_embedding = self.embedder.encode([query])[0]
        search_results = self.vector_store.query(query, n_results=k, query_embedding=query_embedding)
        return [Document(text=result['text'], metadata=result['metadata']) for result in search_results]

    def build_prompt(self, query: str, retrieved_docs: List[Document]) -> str:
        parts: List[str] = []
        total = 0
        for doc in retrieved_docs:
            text = doc.text or ""
            if len(text) > self.per_chunk_chars:
                text = text[: self.per_chunk_chars].rstrip() + "..."
            entry = f"Source: {doc.metadata.get('source', 'unknown')}\n{text}"
            entry_len = len(entry)
            if total + entry_len > self.max_context_chars and parts:
                break
            parts.append(entry)
            total += entry_len

        context = "\n\n".join(parts)

        return (
            "You are a helpful assistant.\n"
            "Answer the question using the provided context.\n"
            "If the provided context supports an answer, give a direct answer in your own words.\n"
            "Do not invent information from outside the context.\n"
            "If the context does not contain enough information to answer, say \"I don't know.\"\n\n"
            "Context:\n"
            f"{context}\n\n"
            "Question:\n"
            f"{query}\n\n"
            "Answer:\n"
        )

    def answer(self, query: str, deepseek_callable, k: Optional[int] = None) -> str:
        retrieved = self.retrieve(query, k=k)
        if not retrieved:
            return "No relevant context was retrieved for that question."
        prompt = self.build_prompt(query, retrieved)
        return deepseek_callable(prompt)

    def answer_with_top_chunk(self, query: str, k: Optional[int] = None) -> str:
        retrieved = self.retrieve(query, k=k)
        if not retrieved:
            return "No relevant context was retrieved."
        return retrieved[0].text
