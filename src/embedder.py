from __future__ import annotations

import os
from typing import List, Optional, Sequence

from .document import Document


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
            # deterministic, small vectors based on md5 digest
            import hashlib

            out: List[List[float]] = []
            for t in texts:
                digest = hashlib.md5(t.encode("utf-8")).hexdigest()
                vec: List[float] = []
                # split digest into 8 chunks of 4 hex chars
                for i in range(0, 32, 4):
                    chunk = digest[i : i + 4]
                    num = int(chunk, 16)
                    vec.append(num / 65535.0)
                out.append(vec)
            return out

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
