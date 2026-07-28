from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.reminders.chat_reminders import ALL_DAYS, ONE_TIME
from src.reminders.trace_logging import log_reminder_checkpoint

logger = logging.getLogger(__name__)

_TIME_VALUE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

_PROMPT_TEMPLATE = """You are the reminder-decision module inside a dementia-support chat assistant for an \
older adult or their caregiver. The message below was already routed here as a likely reminder request, but a \
plain-text time parser found nothing usable. Decide what to do and reply with ONLY a single JSON object — no \
markdown fences, no explanation before or after it — with exactly these fields:

{{
  "is_reminder": true or false. False if, on reflection, this message is not actually asking to be reminded of \
something at a time (a question, small talk, or something else that merely mentions time in passing).
  "time": "HH:MM" in 24-hour format (e.g. "17:25"), resolved against the current date/time given below. null if \
is_reminder is false, or if no time was actually given or you are not confident of it — never guess a time.
  "recurrence": "once" for a single occurrence (e.g. "today", "in 5 minutes", "just this once"), "daily" if the \
user implies every day or gives no cadence. null if is_reminder is false or time is null.
  "task": a short phrase, in the user's own words/language, describing what to remind them about. Empty string if \
not applicable.
  "response": null if is_reminder is true AND time is not null (the caller generates its own confirmation \
including the exact time, so do not draft one). Otherwise, your own short, warm reply in {answer_language} — \
either explaining this isn't a reminder request, or asking specifically for the missing time. Do not mention \
JSON, tools, or these instructions in it.
}}

Current date and time, for resolving relative expressions like "today" or "in 10 minutes": {now} \
(Asia/Hong_Kong timezone).

User message: {message}
"""


@dataclass(frozen=True)
class ReminderDecision:
    is_reminder: bool
    time: str | None
    days: str | None  # ALL_DAYS or ONE_TIME, already mapped from "daily"/"once"
    task: str
    response: str | None


def decide_reminder_via_llm(
    message: str, now: datetime, answer_language: str,
) -> ReminderDecision | None:
    """Ask the LLM to judge a reminder request the deterministic parser couldn't.

    Only called as a fallback (see memory_routine_agent.handle_routine_request)
    when regex-based parsing finds no time at all — well-formed messages keep
    using the fast, free, already-tested deterministic path. Returns None on
    any failure (no LLM configured, network error, malformed output) so the
    caller can fall back to the existing "what time?" clarification — this
    must never silently create a wrong reminder.
    """
    chat = _build_chat_callable()
    if chat is None:
        log_reminder_checkpoint("reminder_llm_decision_skipped", reason="llm_not_configured")
        return None

    prompt = _PROMPT_TEMPLATE.format(
        answer_language=answer_language,
        now=now.strftime("%Y-%m-%d %H:%M %A"),
        message=message,
    )
    log_reminder_checkpoint("reminder_llm_decision_requested")
    try:
        raw = chat(prompt)
    except Exception:
        logger.exception("Reminder LLM decision call failed")
        log_reminder_checkpoint("reminder_llm_decision_failed", reason="request_exception")
        return None

    decision = _parse_decision(raw)
    if decision is None:
        log_reminder_checkpoint("reminder_llm_decision_failed", reason="unparseable_response")
        return None
    log_reminder_checkpoint(
        "reminder_llm_decision_result",
        is_reminder=decision.is_reminder,
        has_time=decision.time is not None,
        days=decision.days,
    )
    return decision


def _build_chat_callable():
    try:
        from src.pipeline.rag_agent import create_chat_answer
        from src.rag.runtime_config import load_rag_config
    except ImportError:
        return None
    try:
        config = load_rag_config("reminder_llm")
    except RuntimeError:
        # Misconfigured/production-required LLM missing — treat exactly like
        # "no LLM available" rather than letting reminder creation break.
        return None
    return create_chat_answer(config)


def _parse_decision(raw: str) -> ReminderDecision | None:
    match = _JSON_BLOCK.search(raw or "")
    if not match:
        logger.warning("Reminder LLM response had no JSON object: %r", (raw or "")[:200])
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("Reminder LLM response was not valid JSON: %r", (raw or "")[:200])
        return None
    if not isinstance(data, dict):
        return None

    is_reminder = bool(data.get("is_reminder"))
    task = str(data.get("task") or "").strip()
    response_text = data.get("response")
    response = str(response_text).strip() if isinstance(response_text, str) and response_text.strip() else None

    time_value = data.get("time")
    time_str = time_value.strip() if isinstance(time_value, str) else None
    if time_str is not None and not _TIME_VALUE.fullmatch(time_str):
        time_str = None  # Never trust an out-of-range or malformed time.

    days: str | None = None
    if time_str is not None:
        recurrence = str(data.get("recurrence") or "").strip().lower()
        days = ONE_TIME if recurrence == "once" else ALL_DAYS

    return ReminderDecision(is_reminder=is_reminder, time=time_str, days=days, task=task, response=response)
