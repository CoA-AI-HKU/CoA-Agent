from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "pending_activities.json"
ACTIVITY_TTL = timedelta(minutes=30)
NAME_THREE_ITEMS_RESPONSE = (
    "很好，你做到了。你剛剛說了蘋果、香蕉和梨子。"
    "先慢慢呼吸一下。你現在覺得好一點嗎？"
)


def store_pending_activity(
    sender_id: str,
    user_id: str,
    activity_type: str,
    prompt: str,
    expected_response: str,
) -> dict[str, str]:
    state = _load_state()
    pending = {
        "pending_activity_type": activity_type,
        "pending_activity_prompt": prompt,
        "pending_activity_expected_response": expected_response,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "sender_id": sender_id,
    }
    state[sender_id] = pending
    _save_state(state)
    return pending


def consume_pending_activity_response(sender_id: str, message: str) -> dict[str, Any] | None:
    state = _load_state()
    pending = state.get(sender_id)
    if not isinstance(pending, dict):
        return None
    if _is_expired(pending):
        state.pop(sender_id, None)
        _save_state(state)
        return None

    if pending.get("pending_activity_type") != "name_three_items":
        return None
    items = _list_items(message)
    if len(items) < 3:
        return None

    state.pop(sender_id, None)
    _save_state(state)
    named = items[:3]
    if named == ["蘋果", "香蕉", "梨子"]:
        answer = NAME_THREE_ITEMS_RESPONSE
    else:
        answer = f"很好，你做到了。你剛剛說了{named[0]}、{named[1]}和{named[2]}。先慢慢呼吸一下。你現在覺得好一點嗎？"
    return {
        "answer": answer,
        "route": "activity_response",
        "intent": "cognitive_activity",
        "sources": [],
        "found": False,
        "rag_called": False,
        "safety_level": "activity_support",
        "debug": {"agent": "pending_activity", "pending_activity_type": "name_three_items"},
    }


def _list_items(message: str) -> list[str]:
    return [item.strip(" 。.!！?？") for item in re.split(r"[，,、;；]+", str(message or "")) if item.strip(" 。.!！?？")]


def _is_expired(pending: dict[str, Any]) -> bool:
    try:
        created_at = datetime.fromisoformat(str(pending.get("created_at") or "").replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created_at > ACTIVITY_TTL
    except ValueError:
        return True


def _state_path() -> Path:
    return Path(os.getenv("PENDING_ACTIVITY_STATE_PATH", str(DEFAULT_STATE_PATH)))


def _load_state() -> dict[str, Any]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
