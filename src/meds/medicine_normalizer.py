from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALIAS_PATH = PROJECT_ROOT / "data" / "medicine_aliases.json"


def normalize_medicine_mentions(text: str) -> list[dict]:
    aliases = _load_aliases(DEFAULT_ALIAS_PATH)
    mentions: list[dict] = []
    seen: set[tuple[str, str]] = set()

    alias_entries = [
        (canonical_name, alias)
        for canonical_name, values in aliases.items()
        for alias in values.get("aliases", [])
        if isinstance(alias, str) and alias.strip()
    ]
    alias_entries.sort(key=lambda item: len(item[1]), reverse=True)

    normalized_text = text.lower()
    for canonical_name, alias in alias_entries:
        if not _contains_alias(text, normalized_text, alias):
            continue
        key = (canonical_name, alias.lower())
        if key in seen:
            continue
        mentions.append(
            {
                "canonical_name": canonical_name,
                "matched_alias": alias,
                "confidence": 1.0,
                "source": "local_alias_dictionary",
            }
        )
        seen.add(key)
    return mentions


def _load_aliases(alias_path: Path) -> dict[str, dict[str, Any]]:
    if not alias_path.exists():
        return {}
    try:
        data = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        canonical_name: values
        for canonical_name, values in data.items()
        if isinstance(canonical_name, str) and isinstance(values, dict)
    }


def _contains_alias(text: str, normalized_text: str, alias: str) -> bool:
    if _has_cjk(alias):
        return alias in text
    return re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", normalized_text) is not None


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))
