from __future__ import annotations

import re
from typing import NamedTuple

try:
    from .database import Patient, Reminder, SessionLocal
except ImportError:  # Support running this directory as the application root.
    from database import Patient, Reminder, SessionLocal


ALL_DAYS = "mon,tue,wed,thu,fri,sat,sun"
# Sentinel used in place of a weekday list for a reminder that should fire
# once and then deactivate, rather than recur — see scheduler.py, which
# treats this the same as "any day" for a single delivery.
ONE_TIME = "once"

# Period-of-day markers that disambiguate a bare hour like "2點" into 24-hour
# time. Chinese doesn't otherwise distinguish 2am from 2pm the way "2:14 PM"
# does, so without this "下午2:14" (2:14 PM) was parsed as 02:14 (2:14 AM).
_PERIOD_KIND = {
    "凌晨": "am", "清晨": "am", "早上": "am", "上午": "am",
    "中午": "noon",
    "下午": "pm", "晚上": "pm", "夜晚": "pm", "夜間": "pm", "夜间": "pm", "傍晚": "pm",
}
_PERIOD_ALTERNATION = "|".join(sorted(_PERIOD_KIND, key=len, reverse=True))

_TIME_PATTERN = re.compile(
    rf"(?P<period>{_PERIOD_ALTERNATION})?\s*"
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：時时点點](?P<minute>\d{1,2})?分?(?!\d)"
)

_TRIGGER_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"可以提醒我", r"可唔可以提醒我", r"幫我提醒", r"帮我提醒",
        r"提醒我", r"提我", r"記得提醒我", r"记得提醒我",
        r"remind me to", r"remind me",
    )
]
# Phrases telling us this should fire once, not recur daily — e.g. "不需要
# 以後每天都提醒" (no need to remind every day going forward) or "今天提一下
# 就行了" (just remind me once today). Matched against the message to decide
# recurrence, and also stripped out so they don't end up inside the
# reminder's own text.
_ONE_TIME_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"[，,、]?\s*(唔[使洗]|不[需用]要?|不用)\s*(以後|之後|今後|后)?\s*每[日天]\s*(都)?\s*(提醒)?",
        r"[，,、]?\s*(今[日天]|今次)\s*(提|叫|話|说)?\s*(醒)?\s*(我)?\s*(一)?\s*(下|次)?\s*就\s*(得了|得喇|得|可以|好|行了|行|夠)",
        r"\bonly once\b", r"\bjust once\b", r"\bone[- ]time\b", r"\bjust today\b", r"\bonly today\b",
    )
]
_TRAILING_PARTICLES = re.compile(r"(嗎|吗|呀|啊|喇|啦|呢)\s*$")
_ENGLISH_FILLER = re.compile(r"^(to)\b|\b(at|on|by)$", re.IGNORECASE)
_STRIP_CHARS = " ，,。.?？~！!:：、"


class ParsedReminder(NamedTuple):
    time: str
    text: str
    days: str


def parse_reminder_request(message: str) -> ParsedReminder | None:
    """Extract a time, reminder text, and recurrence from a chat message.

    Returns None if no explicit time-of-day is present. Only recognizes an
    explicit time in the message itself (e.g. "12:28", "下午2:14", "9點");
    it does not infer a time from vague phrasing like "later" or "tonight" —
    callers should ask the user for a specific time in that case.
    """
    match = _TIME_PATTERN.search(message)
    if not match:
        return None
    hour = _adjust_hour_for_period(int(match.group("hour")), match.group("period"))
    minute = int(match.group("minute")) if match.group("minute") else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    time_str = f"{hour:02d}:{minute:02d}"

    remainder = message[: match.start()] + message[match.end() :]
    is_one_time = any(pattern.search(remainder) for pattern in _ONE_TIME_PATTERNS)
    text = _extract_reminder_text(remainder)
    return ParsedReminder(time=time_str, text=text, days=ONE_TIME if is_one_time else ALL_DAYS)


def _adjust_hour_for_period(hour: int, period: str | None) -> int:
    kind = _PERIOD_KIND.get(period or "")
    if kind == "pm" and hour < 12:
        return hour + 12
    if kind == "am" and hour == 12:
        return 0
    return hour


def _extract_reminder_text(remainder: str) -> str:
    text = remainder
    for pattern in (*_TRIGGER_PATTERNS, *_ONE_TIME_PATTERNS):
        text = pattern.sub("", text)
    text = _TRAILING_PARTICLES.sub("", text.strip(_STRIP_CHARS)).strip(_STRIP_CHARS)
    text = _ENGLISH_FILLER.sub("", text).strip(_STRIP_CHARS)
    return text or "提醒"


def get_or_create_patient(db, external_user_id: str, display_name: str = "") -> Patient:
    """Find the Patient row linked to this chat user, creating one if needed.

    external_user_id is the main app's registry_user_id
    (src/user/user_registry.py), not a reminders-native identity — this is
    the bridge between the two previously-separate identity systems.
    """
    patient = (
        db.query(Patient).filter(Patient.external_user_id == external_user_id).first()
    )
    if patient is not None:
        if display_name and patient.name != display_name:
            patient.name = display_name
            db.commit()
        return patient

    patient = Patient(
        external_user_id=external_user_id,
        name=display_name or external_user_id,
        caregiver_id=None,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def create_reminder_for_user(
    external_user_id: str,
    display_name: str,
    text: str,
    time_str: str,
    days: str = ALL_DAYS,
) -> Reminder:
    db = SessionLocal()
    try:
        patient = get_or_create_patient(db, external_user_id, display_name)
        reminder = Reminder(
            patient_id=patient.id,
            text=text,
            time=time_str,
            days=days,
            active=True,
        )
        db.add(reminder)
        db.commit()
        db.refresh(reminder)
        return reminder
    finally:
        db.close()
