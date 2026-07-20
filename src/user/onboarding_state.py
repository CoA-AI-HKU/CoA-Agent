from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "onboarding_sessions.json"
SESSION_TTL = timedelta(hours=1)


def begin_onboarding(sender_id: str) -> None:
    _set(sender_id, {"step": "role", "created_at": datetime.now(timezone.utc).isoformat()})


def consume_onboarding_reply(sender_id: str, message: str) -> dict[str, str] | None:
    state = _load()
    session = state.get(sender_id)
    if not isinstance(session, dict) or _expired(session):
        if sender_id in state:
            state.pop(sender_id, None)
            _save(state)
        return None

    text = str(message or "").strip()
    step = session.get("step")
    if step == "role":
        roles = {"使用者": "user", "用戶": "user", "患者": "user", "照顧者": "caregiver", "照顾者": "caregiver"}
        role = roles.get(text)
        if role is None:
            return None
        session["step"] = "name"
        session["role"] = role
        state[sender_id] = session
        _save(state)
        return {"action": "ask_name", "role": role}

    if step == "name" and text and not text.startswith(("/", "\\")):
        state.pop(sender_id, None)
        _save(state)
        return {"action": "register", "role": str(session.get("role") or ""), "display_name": text[:80]}
    return None


def _set(sender_id: str, value: dict[str, Any]) -> None:
    state = _load()
    state[sender_id] = value
    _save(state)


def _path() -> Path:
    return Path(os.getenv("ONBOARDING_STATE_PATH", str(DEFAULT_STATE_PATH)))


def _load() -> dict[str, Any]:
    try:
        value = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _save(state: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _expired(session: dict[str, Any]) -> bool:
    try:
        created = datetime.fromisoformat(str(session.get("created_at") or "").replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created > SESSION_TTL
    except ValueError:
        return True
