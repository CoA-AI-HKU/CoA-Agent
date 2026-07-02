from __future__ import annotations

import hashlib
import math
import os
import re
from typing import List, Optional, Sequence

from .document import Document


DUMMY_EMBEDDING_DIMENSIONS = 384
DUMMY_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "any",
    "are",
    "can",
    "could",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "its",
    "may",
    "more",
    "not",
    "our",
    "out",
    "should",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def _dummy_terms(text: str) -> list[str]:
    terms = []
    for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower()):
        if len(term) < 3 or term in DUMMY_STOPWORDS:
            continue
        terms.append(term)
    cjk_chars = re.findall(r"[\u3400-\u9fff]", text)
    terms.extend("".join(cjk_chars[index : index + 2]) for index in range(len(cjk_chars) - 1))
    terms.extend("".join(cjk_chars[index : index + 3]) for index in range(len(cjk_chars) - 2))
    return terms


def _dummy_vector(text: str) -> list[float]:
    vector = [0.0] * DUMMY_EMBEDDING_DIMENSIONS
    for term in _dummy_terms(text):
        digest = hashlib.md5(term.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % DUMMY_EMBEDDING_DIMENSIONS
        vector[index] += 1.0

    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return vector
    return [value / length for value in vector]


class Embedder:
    """Pluggable embedding wrapper for local and OpenAI-compatible backends."""

    def __init__(self, model_name: Optional[str] = None, provider: str = "auto", offline: bool = False):
        self.model_name = model_name or "all-MiniLM-L6-v2"
        self.provider = provider
        self.offline = offline
        self._local_model = None
        self._openai_client = None
        self._init_backend()

    def _init_backend(self) -> None:
        backend_errors: List[str] = []

        if self.provider in ("auto", "local"):
            try:
                from sentence_transformers import SentenceTransformer

                kwargs = {"local_files_only": True} if self.offline else {}
                self._local_model = SentenceTransformer(self.model_name, **kwargs)
                return
            except ImportError as exc:
                backend_errors.append(f"sentence-transformers is not installed: {exc}")
            except Exception as exc:
                backend_errors.append(f"could not load local sentence-transformers model {self.model_name!r}: {exc}")
                if self.provider == "local":
                    raise RuntimeError(self._format_backend_error(backend_errors)) from exc

        if self.provider in ("auto", "openai"):
            try:
                if not os.getenv("OPENAI_API_KEY"):
                    raise RuntimeError("OPENAI_API_KEY is not set")

                import openai

                self._openai_client = openai
                self._openai_client.api_key = os.getenv("OPENAI_API_KEY")
                return
            except (ImportError, RuntimeError) as exc:
                backend_errors.append(f"could not initialize OpenAI-compatible embeddings: {exc}")

        if self.provider == "dummy":
            # use deterministic lightweight dummy backend
            self._local_model = None
            self._openai_client = None
            return

        raise RuntimeError(self._format_backend_error(backend_errors))

    def _format_backend_error(self, backend_errors: List[str]) -> str:
        details = "\n".join(f"- {error}" for error in backend_errors) if backend_errors else "- no backend was attempted"
        return (
            "No real embedding backend is available.\n"
            f"{details}\n"
            "To run without internet, download the Sentence Transformers model once and pass its local path with "
            "`--embedder-model /path/to/model --offline-embeddings`, or set EMBEDDER_MODEL to that path. "
            "If the model is already cached, use `--offline-embeddings` to avoid Hugging Face network retries."
        )

    def encode(self, texts: Sequence[str]) -> List[List[float]]:
        if self.provider == "dummy":
            return [_dummy_vector(text) for text in texts]

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
