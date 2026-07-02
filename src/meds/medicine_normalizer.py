from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALIAS_PATH = PROJECT_ROOT / "data" / "medicine_aliases.json"


@dataclass(frozen=True)
class MedicineMention:
    canonical_name: str
    matched_alias: str
    confidence: float
    source: str


LOCAL_ALIASES: dict[str, list[str]] = {
    "aspirin": ["aspirin", "ASA", "acetylsalicylic acid", "阿司匹林", "亞士匹靈", "阿士匹靈", "阿斯匹靈"],
    "donepezil": ["donepezil", "Aricept", "多奈哌齊", "多奈哌齐"],
    "paracetamol": ["paracetamol", "acetaminophen", "Panadol", "必理痛", "撲熱息痛", "对乙酰氨基酚"],
    "metformin": ["metformin", "二甲雙胍", "二甲双胍"],
    "amlodipine": ["amlodipine", "Norvasc", "氨氯地平"],
}


ExternalLookup = Callable[[str], list[MedicineMention]]


def normalize_medicine_mentions(
    text: str,
    alias_path: Path = DEFAULT_ALIAS_PATH,
    external_lookup: ExternalLookup | None = None,
) -> list[MedicineMention]:
    """Return medicine mentions using local aliases first.

    External lookup is intentionally opt-in so tests and local runs do not call network services.
    """
    mentions = _match_aliases(text, LOCAL_ALIASES, "local_alias")
    seen = {(mention.canonical_name, mention.matched_alias.lower()) for mention in mentions}

    for mention in _match_aliases(text, _load_aliases(alias_path), "data_aliases"):
        key = (mention.canonical_name, mention.matched_alias.lower())
        if key not in seen:
            mentions.append(mention)
            seen.add(key)

    if not mentions and external_lookup is not None:
        mentions.extend(external_lookup(text))

    return mentions


def _load_aliases(alias_path: Path) -> dict[str, list[str]]:
    if not alias_path.exists():
        return {}
    try:
        data = json.loads(alias_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    aliases: dict[str, list[str]] = {}
    for canonical_name, values in data.items():
        if isinstance(canonical_name, str) and isinstance(values, list):
            aliases[canonical_name] = [value for value in values if isinstance(value, str)]
    return aliases


def _match_aliases(text: str, aliases: dict[str, list[str]], source: str) -> list[MedicineMention]:
    matches: list[MedicineMention] = []
    normalized_text = text.lower()
    alias_entries = [
        (canonical_name, alias)
        for canonical_name, alias_list in aliases.items()
        for alias in alias_list
        if alias.strip()
    ]
    alias_entries.sort(key=lambda item: len(item[1]), reverse=True)

    for canonical_name, alias in alias_entries:
        if _contains_alias(text, normalized_text, alias):
            matches.append(
                MedicineMention(
                    canonical_name=canonical_name,
                    matched_alias=alias,
                    confidence=1.0,
                    source=source,
                )
            )
    return matches


def _contains_alias(text: str, normalized_text: str, alias: str) -> bool:
    if _has_cjk(alias):
        return alias in text
    return re.search(rf"(?<![a-z0-9]){re.escape(alias.lower())}(?![a-z0-9])", normalized_text) is not None


def _has_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))

