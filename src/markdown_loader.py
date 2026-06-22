from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .document import Document


def discover_markdown_files(markdown_root: Path) -> List[Path]:
    return sorted(markdown_root.rglob("*.md"))


def load_markdown_documents(markdown_root: Path, source_type: str = "markdown") -> List[Document]:
    documents: List[Document] = []
    for path in discover_markdown_files(markdown_root):
        text = path.read_text(encoding="utf-8")
        documents.append(
            Document(
                text=text,
                metadata={
                    "source": str(path),
                    "type": source_type,
                },
            )
        )
    return documents
