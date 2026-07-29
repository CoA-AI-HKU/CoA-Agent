from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.pipeline.language import detect_answer_language
from src.reminders.trace_logging import log_reminder_checkpoint

try:
    from src.reminders.chat_reminders import (
        has_reminder_trigger_phrase,
        parse_reminder_request,
        reminder_correction_text,
        update_reminder_time,
    )
except ImportError:  # reminder deps (SQLAlchemy etc.) unavailable in this process
    has_reminder_trigger_phrase = None
    parse_reminder_request = None
    reminder_correction_text = None
    update_reminder_time = None


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "last_created_reminders.json"
# Deliberately much shorter than pending_reminder.py's 30-minute TTL: this
# window exists to catch "wait, I meant X" immediately after confirmation
# ("一點二十分提醒我喝水好嗎" -> "抱歉，我的意思是下午一點二十一"), not to
# reinterpret an unrelated message minutes later as a correction.
CORRECTION_TTL = timedelta(minutes=3)


def store_last_created_reminder(
    sender_id: str, reminder_id: int, text: str, answer_language: str = "zh-Hant",
) -> dict[str, Any]:
    """Remember the reminder just confirmed for this sender, for a short correction window.

    Read by consume_reminder_correction — see there for why a bare follow-up
    like "抱歉，我的意思是下午一點二十一" (no reminder-trigger phrase, so it
    would never route to the reminder handler on its own) should update this
    reminder instead of being silently dropped as an unrelated reply.
    """
    state = _load_state()
    entry = {
        "reminder_id": reminder_id,
        "text": text,
        "answer_language": answer_language,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state[sender_id] = entry
    _save_state(state)
    return entry


def consume_reminder_correction(sender_id: str, message: str, channel: str = "") -> dict[str, Any] | None:
    """Update the just-created reminder if this looks like a same-sender time correction.

    Only engages when: a reminder was created for this sender within the
    last few minutes, AND this new message contains no reminder-trigger
    phrase of its own (a message with one is a genuinely new request and
    must go through normal routing, not silently overwrite the last one),
    AND it parses to an explicit time. Returns None otherwise so the caller
    falls through to normal routing — same convention as
    consume_pending_reminder_response.
    """
    tool_available = (
        has_reminder_trigger_phrase is not None
        and parse_reminder_request is not None
        and update_reminder_time is not None
    )
    if not tool_available:
        return None

    state = _load_state()
    pending = state.get(sender_id)
    if not isinstance(pending, dict):
        return None
    if _is_expired(pending):
        state.pop(sender_id, None)
        _save_state(state)
        return None
    if has_reminder_trigger_phrase(message):
        return None

    parsed = parse_reminder_request(message)
    if parsed is None:
        return None

    reminder_id = pending.get("reminder_id")
    text = str(pending.get("text") or "").strip() or "提醒"
    answer_language = str(pending.get("answer_language") or "") or detect_answer_language(message)

    reminder = update_reminder_time(int(reminder_id), parsed.time, parsed.days)
    if reminder is None:
        state.pop(sender_id, None)
        _save_state(state)
        return None

    # Refresh created_at rather than clearing the entry outright, so a
    # second correction in a row ("actually make it 2pm instead") still
    # applies to the same reminder within the window, instead of only the
    # very first correction being honored.
    state[sender_id] = {**pending, "created_at": datetime.now(timezone.utc).isoformat()}
    _save_state(state)

    log_reminder_checkpoint(
        "reminder_correction_applied",
        reminder_id=reminder.id, user_id=sender_id, channel=channel,
        normalized_due_time=parsed.time, days=parsed.days,
    )

    return {
        "answer": reminder_correction_text(parsed.time, text, parsed.days, answer_language),
        "route": "routine",
        "intent": "reminder_request",
        "sources": [],
        "found": False,
        "rag_called": False,
        "safety_level": "reminder_corrected",
        "answer_language": answer_language,
        "debug": {
            "agent": "pending_reminder_correction",
            "reminder_id": reminder.id,
            "reminder_time": parsed.time,
            "reminder_text": text,
            "reminder_days": parsed.days,
        },
    }


def _is_expired(pending: dict[str, Any]) -> bool:
    try:
        created_at = datetime.fromisoformat(str(pending.get("created_at") or "").replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created_at > CORRECTION_TTL
    except ValueError:
        return True


def _state_path() -> Path:
    return Path(os.getenv("LAST_CREATED_REMINDER_STATE_PATH", str(DEFAULT_STATE_PATH)))


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
