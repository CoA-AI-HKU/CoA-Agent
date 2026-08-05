from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# Mirrors src/user/session_preferences.py's own pattern (a small JSON store
# keyed by sender_id) — deliberately not a column on backend's
# WebAccountProfile: that table only exists for accounts that have signed
# into the web app, but flagging (see src/user/conversation_flags.py) runs
# for every patient, Telegram-only or not. Keeping this in src/user/ keeps
# it usable from both, with no dependency on the web backend.
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "monitoring_preferences.json"

# Both on by default — matches the flagging behavior that already existed
# before this toggle did, so nobody's monitoring silently stops until a
# caregiver and patient explicitly decide together to turn a category off.
DEFAULT_PREFERENCES: dict[str, bool] = {"safety": True, "cognitive_decline": True}


def get_monitoring_preferences(sender_id: str) -> dict[str, bool]:
    stored = _load().get(str(sender_id).strip(), {})
    return {
        "safety": bool(stored.get("safety", True)),
        "cognitive_decline": bool(stored.get("cognitive_decline", True)),
    }


def set_monitoring_preferences(
    sender_id: str, *, safety: bool | None = None, cognitive_decline: bool | None = None,
) -> dict[str, bool]:
    sender_id = str(sender_id).strip()
    state = _load()
    current = dict(DEFAULT_PREFERENCES, **state.get(sender_id, {}))
    if safety is not None:
        current["safety"] = bool(safety)
    if cognitive_decline is not None:
        current["cognitive_decline"] = bool(cognitive_decline)
    state[sender_id] = current
    _save(state)
    return current


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
