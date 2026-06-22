from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .chunker import chunk_documents
from .document import Document
from .embedder import Embedder
from .vector_store import ChromaVectorStore


class RagAgent:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> None:
        self.embedder = embedder or Embedder()
        self.vector_store = vector_store or ChromaVectorStore()
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def index_documents(self, documents: List[Document]) -> None:
        chunks = chunk_documents(documents, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        embeddings = self.embedder.encode_documents(chunks)
        self.vector_store.add_documents(chunks, embeddings)
        self.vector_store.persist()

    def retrieve(self, query: str, k: int = 5) -> List[Document]:
        search_results = self.vector_store.query(query, n_results=k)
        return [Document(text=result['text'], metadata=result['metadata']) for result in search_results]

    def build_prompt(self, query: str, retrieved_docs: List[Document]) -> str:
        context = "\n\n".join(
            f"Source: {doc.metadata.get('source', 'unknown')}\n{doc.text}" for doc in retrieved_docs
        )
        return (
            "You are a helpful assistant.\n"
            "Answer using only the provided context. If the answer is not contained in the context, respond with \"I don't know.\"\n\n"
            "Context:\n"
            f"{context}\n\n"
            "Question:\n"
            f"{query}"
        )

    def answer(self, query: str, deepseek_callable) -> str:
        retrieved = self.retrieve(query)
        prompt = self.build_prompt(query, retrieved)
        return deepseek_callable(prompt)
