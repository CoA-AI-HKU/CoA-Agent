from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from chromadb import Client
from chromadb.config import Settings

from .document import Document


class ChromaVectorStore:
    def __init__(
        self,
        persist_directory: Optional[Path] = None,
        collection_name: str = "ling_rag",
        client_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
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
            include=['documents', 'metadatas', 'distances', 'ids'],
        )
        output: List[Dict[str, Any]] = []
        if results['documents']:
            for doc, metadata, distance, id_ in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0],
                results['ids'][0],
            ):
                output.append({
                    'id': id_,
                    'text': doc,
                    'metadata': metadata,
                    'distance': distance,
                })
        return output

    def persist(self) -> None:
        if hasattr(self.client, 'persist'):
            self.client.persist()
