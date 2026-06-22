from __future__ import annotations

import os
from typing import Iterable, List, Optional, Sequence

from .document import Document


class Embedder:
    """Pluggable embedding wrapper for local and OpenAI-compatible backends."""

    def __init__(self, model_name: Optional[str] = None, provider: str = "auto"):
        self.model_name = model_name or "all-MiniLM-L6-v2"
        self.provider = provider
        self._local_model = None
        self._openai_client = None
        self._init_backend()

    def _init_backend(self) -> None:
        if self.provider in ("auto", "local"):
            try:
                from sentence_transformers import SentenceTransformer

                self._local_model = SentenceTransformer(self.model_name)
                return
            except ImportError:
                pass

        if self.provider in ("auto", "openai"):
            try:
                import openai

                self._openai_client = openai
                self._openai_client.api_key = os.getenv("OPENAI_API_KEY")
                return
            except ImportError:
                pass

        raise RuntimeError(
            "No embedding backend is available. Install `sentence-transformers` for local embedding "
            "or `openai` for OpenAI-compatible embedding."
        )

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        if self._local_model is not None:
            embeddings = self._local_model.encode(list(texts), show_progress_bar=False, convert_to_numpy=True)
            return [embedding.tolist() for embedding in embeddings]

        if self._openai_client is not None:
            response = self._openai_client.Embedding.create(
                input=list(texts),
                model=self.model_name,
            )
            return [item["embedding"] for item in response["data"]]

        raise RuntimeError("Embedder backend was not initialized.")

    def encode_documents(self, documents: Sequence[Document]) -> List[List[float]]:
        return self.encode([document.text for document in documents])

    def encode_document(self, document: Document) -> List[float]:
        return self.encode([document.text])[0]
