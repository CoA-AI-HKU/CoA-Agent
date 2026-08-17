from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "monitoring_preferences.json"
CATEGORIES = ("safety", "cognitive_decline", "sleep", "daily_activity", "routine_adherence")
DEFAULT_REQUESTED = {"safety": True, "cognitive_decline": True, "sleep": False, "daily_activity": False, "routine_adherence": False}
DEFAULT_CONSENT = dict(DEFAULT_REQUESTED)
DEFAULT_THRESHOLDS = {category: 1 for category in CATEGORIES}


def _future(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > datetime.now(timezone.utc)
    except (TypeError, ValueError):
        return False


def _normalized(stored: dict[str, Any] | None = None) -> dict[str, Any]:
    stored = dict(stored or {})
    requested = dict(DEFAULT_REQUESTED)
    requested.update(stored.get("requested") or {})
    for category in ("safety", "cognitive_decline"):
        if category in stored:  # original flat JSON format
            requested[category] = bool(stored[category])
    consent = dict(DEFAULT_CONSENT)
    consent.update(stored.get("consent") or {})
    thresholds = dict(DEFAULT_THRESHOLDS)
    thresholds.update(stored.get("thresholds") or {})
    thresholds = {key: max(1, min(int(value), 10)) for key, value in thresholds.items() if key in CATEGORIES}
    pause_until = str(stored.get("pause_until") or "")
    paused = _future(pause_until)
    effective = {key: bool(requested[key] and consent[key] and not paused) for key in CATEGORIES}
    return {**requested, "requested": requested, "consent": consent, "effective": effective,
            "thresholds": thresholds, "pause_until": pause_until if paused else "", "is_paused": paused}


def get_monitoring_preferences(sender_id: str) -> dict[str, Any]:
    return _normalized(_load().get(str(sender_id).strip(), {}))


def _update(sender_id: str, section: str, updates: dict[str, Any]) -> dict[str, Any]:
    sender_id = str(sender_id).strip()
    state = _load()
    current = _normalized(state.get(sender_id, {}))
    value = dict(current[section])
    value.update({key: item for key, item in updates.items() if key in CATEGORIES and item is not None})
    stored = {name: current[name] for name in ("requested", "consent", "thresholds", "pause_until")}
    stored[section] = value
    state[sender_id] = stored
    _save(state)
    return get_monitoring_preferences(sender_id)


def set_monitoring_preferences(sender_id: str, **updates: bool | None) -> dict[str, Any]:
    return _update(sender_id, "requested", {key: bool(value) if value is not None else None for key, value in updates.items()})


def set_patient_monitoring_consent(sender_id: str, **updates: bool | None) -> dict[str, Any]:
    return _update(sender_id, "consent", {key: bool(value) if value is not None else None for key, value in updates.items()})


def set_monitoring_thresholds(sender_id: str, **updates: int | None) -> dict[str, Any]:
    for value in updates.values():
        if value is not None and not 1 <= int(value) <= 10:
            raise ValueError("monitoring thresholds must be between 1 and 10")
    return _update(sender_id, "thresholds", {key: int(value) if value is not None else None for key, value in updates.items()})


def set_monitoring_pause(sender_id: str, pause_until: str | None) -> dict[str, Any]:
    sender_id = str(sender_id).strip()
    state = _load()
    current = _normalized(state.get(sender_id, {}))
    state[sender_id] = {name: current[name] for name in ("requested", "consent", "thresholds")}
    state[sender_id]["pause_until"] = str(pause_until or "")
    _save(state)
    return get_monitoring_preferences(sender_id)


def _path() -> Path:
    return Path(os.getenv("MONITORING_PREFERENCES_PATH", str(DEFAULT_PATH)))


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(state: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
