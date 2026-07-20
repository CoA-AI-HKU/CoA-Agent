from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "session_preferences.json"


def set_avoid_patient_framing(sender_id: str) -> None:
    state = _load()
    state[str(sender_id)] = {
        "avoid_patient_framing": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _save(state)


def get_session_preferences(sender_id: str) -> dict[str, Any]:
    value = _load().get(str(sender_id), {})
    return value if isinstance(value, dict) else {}


def _path() -> Path:
    return Path(os.getenv("SESSION_PREFERENCES_PATH", str(DEFAULT_PATH)))


def _load() -> dict[str, Any]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(state: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
