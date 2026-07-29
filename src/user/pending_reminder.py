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
        create_reminder_for_user,
        parse_reminder_request,
        reminder_confirmation_text,
        reminder_period_question_text,
    )
except ImportError:  # reminder deps (SQLAlchemy etc.) unavailable in this process
    create_reminder_for_user = None
    parse_reminder_request = None
    reminder_confirmation_text = None
    reminder_period_question_text = None


DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "pending_reminders.json"
REMINDER_TTL = timedelta(minutes=30)


def store_pending_reminder(
    sender_id: str, user_id: str, display_name: str, text: str, answer_language: str = "zh-Hant"
) -> dict[str, str]:
    """Remember that we just asked this sender what time to set a reminder for.

    Mirrors src/user/pending_activity.py's pattern: a message like "3:41"
    on its own doesn't contain any reminder trigger word, so classify_intent
    would never route it to the reminder handler — this lets the *next*
    message be interpreted as the answer to "what time?" instead of a fresh,
    unrelated message. answer_language is carried over from the message that
    triggered the "what time?" prompt, since a bare time reply like "3:41"
    has no CJK characters to detect a language from on its own.
    """
    state = _load_state()
    pending = {
        "pending_reminder_text": text,
        "user_id": user_id,
        "display_name": display_name,
        "sender_id": sender_id,
        "answer_language": answer_language,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    state[sender_id] = pending
    _save_state(state)
    return pending


def consume_pending_reminder_response(sender_id: str, message: str, channel: str = "") -> dict[str, Any] | None:
    """Complete a pending reminder if this message supplies a time; else None.

    Returning None means "not consumed" — the caller should fall through to
    normal routing, same convention as consume_pending_activity_response.
    """
    tool_available = create_reminder_for_user is not None and parse_reminder_request is not None
    if not tool_available:
        log_reminder_checkpoint(
            "reminder_tool_available",
            user_id=sender_id, channel=channel, available=False, flow="pending_reminder_followup",
        )
        return None

    state = _load_state()
    pending = state.get(sender_id)
    if not isinstance(pending, dict):
        return None
    if _is_expired(pending):
        state.pop(sender_id, None)
        _save_state(state)
        return None

    parsed = parse_reminder_request(message)
    if parsed is None:
        return None

    state.pop(sender_id, None)
    _save_state(state)

    text = str(pending.get("pending_reminder_text") or "").strip() or "提醒"
    user_id = str(pending.get("user_id") or "")
    display_name = str(pending.get("display_name") or "")
    answer_language = str(pending.get("answer_language") or "") or detect_answer_language(message)

    if parsed.period_ambiguous:
        # The time that completes a pending "what time?" question can
        # itself be ambiguous ("5點" in reply to "幾點提醒你？") — chain
        # into the AM/PM question instead of guessing. message_router.py
        # reads the same debug keys handle_routine_request uses for this,
        # so both paths arm the pending-period state identically.
        # (the pending "needs time" entry was already popped above)
        raw_hour, raw_minute = (int(part) for part in parsed.time.split(":"))
        return {
            "answer": reminder_period_question_text(raw_hour, answer_language),
            "route": "routine",
            "intent": "reminder_request",
            "sources": [],
            "found": False,
            "rag_called": False,
            "safety_level": "reminder_needs_period",
            "answer_language": answer_language,
            "debug": {
                "agent": "pending_reminder",
                "reason": "period_ambiguous",
                "reminder_pending_period_hour": raw_hour,
                "reminder_pending_period_minute": raw_minute,
                "reminder_pending_period_text": text,
                "reminder_pending_period_days": parsed.days,
                "reminder_pending_language": answer_language,
            },
        }

    log_reminder_checkpoint(
        "reminder_tool_available",
        user_id=user_id, channel=channel, available=True, flow="pending_reminder_followup",
    )
    log_reminder_checkpoint(
        "reminder_tool_invoked",
        user_id=user_id, channel=channel, flow="pending_reminder_followup",
        normalized_due_time=parsed.time, days=parsed.days,
    )
    try:
        reminder = create_reminder_for_user(
            user_id, display_name, text, parsed.time, days=parsed.days, channel=channel,
            chat_sender_id=sender_id,
        )
    except Exception:
        return None

    return {
        "answer": reminder_confirmation_text(parsed.time, text, parsed.days, answer_language),
        "route": "routine",
        "intent": "reminder_request",
        "sources": [],
        "found": False,
        "rag_called": False,
        "safety_level": "reminder_created",
        "answer_language": answer_language,
        "debug": {
            "agent": "pending_reminder",
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
        return datetime.now(timezone.utc) - created_at > REMINDER_TTL
    except ValueError:
        return True


def _state_path() -> Path:
    return Path(os.getenv("PENDING_REMINDER_STATE_PATH", str(DEFAULT_STATE_PATH)))


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
