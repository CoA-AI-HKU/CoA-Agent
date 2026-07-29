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
        adjust_hour_for_period_kind,
        create_reminder_for_user,
        reminder_confirmation_text,
        resolve_period_word,
    )
except ImportError:  # reminder deps (SQLAlchemy etc.) unavailable in this process
    adjust_hour_for_period_kind = None
    create_reminder_for_user = None
    reminder_confirmation_text = None
    resolve_period_word = None


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "pending_reminder_periods.json"
# Short, like pending_reminder_correction.py's window — this is a direct
# follow-up to a question just asked ("你話5點，係想話上午定係下午呢？"),
# not something that should still apply to an unrelated "下午" mentioned
# in a different conversation ten minutes later.
PERIOD_TTL = timedelta(minutes=5)


def store_pending_reminder_period(
    sender_id: str,
    user_id: str,
    display_name: str,
    hour: int,
    minute: int,
    text: str,
    days: str,
    answer_language: str = "zh-Hant",
) -> dict[str, Any]:
    """Remember that we just asked this sender AM or PM for a bare hour they gave.

    hour/minute are the *unadjusted* values (e.g. hour=5 for "5點") — the
    reply only needs to supply which half of the day, not the whole time
    again. See resolve_period_word for how the reply is interpreted, and
    chat_reminders.ParsedReminder.period_ambiguous for how this gets armed.
    """
    state = _load_state()
    pending = {
        "user_id": user_id,
        "display_name": display_name,
        "sender_id": sender_id,
        "hour": hour,
        "minute": minute,
        "text": text,
        "days": days,
        "answer_language": answer_language,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state[sender_id] = pending
    _save_state(state)
    return pending


def consume_pending_period_response(sender_id: str, message: str, channel: str = "") -> dict[str, Any] | None:
    """Finish creating a reminder once this message answers a pending AM/PM question.

    Returning None means "not consumed" — the caller falls through to
    normal routing, same convention as consume_pending_reminder_response.
    """
    tool_available = (
        adjust_hour_for_period_kind is not None
        and create_reminder_for_user is not None
        and resolve_period_word is not None
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

    kind = resolve_period_word(message)
    if kind is None:
        return None

    state.pop(sender_id, None)
    _save_state(state)

    hour = adjust_hour_for_period_kind(int(pending.get("hour") or 0), kind)
    minute = int(pending.get("minute") or 0)
    time_str = f"{hour:02d}:{minute:02d}"
    text = str(pending.get("text") or "").strip() or "提醒"
    days = str(pending.get("days") or "")
    user_id = str(pending.get("user_id") or "")
    display_name = str(pending.get("display_name") or "")
    answer_language = str(pending.get("answer_language") or "") or detect_answer_language(message)

    log_reminder_checkpoint(
        "reminder_tool_invoked",
        user_id=user_id, channel=channel, flow="pending_period_followup",
        normalized_due_time=time_str, days=days,
    )
    try:
        reminder = create_reminder_for_user(
            user_id, display_name, text, time_str, days=days, channel=channel,
            chat_sender_id=sender_id,
        )
    except Exception:
        return None

    return {
        "answer": reminder_confirmation_text(time_str, text, days, answer_language),
        "route": "routine",
        "intent": "reminder_request",
        "sources": [],
        "found": False,
        "rag_called": False,
        "safety_level": "reminder_created",
        "answer_language": answer_language,
        "debug": {
            "agent": "pending_reminder_period",
            "reminder_id": reminder.id,
            "reminder_time": time_str,
            "reminder_text": text,
            "reminder_days": days,
        },
    }


def _is_expired(pending: dict[str, Any]) -> bool:
    try:
        created_at = datetime.fromisoformat(str(pending.get("created_at") or "").replace("Z", "+00:00"))
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - created_at > PERIOD_TTL
    except ValueError:
        return True


def _state_path() -> Path:
    return Path(os.getenv("PENDING_REMINDER_PERIOD_STATE_PATH", str(DEFAULT_STATE_PATH)))


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
