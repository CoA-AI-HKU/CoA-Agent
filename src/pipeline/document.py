from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class Document:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def copy_with_metadata(self, **metadata_updates: Any) -> "Document":
        metadata = dict(self.metadata)
        metadata.update(metadata_updates)
        return Document(text=self.text, metadata=metadata)
