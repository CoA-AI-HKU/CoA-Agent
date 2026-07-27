from __future__ import annotations

import re
from typing import NamedTuple

try:
    from .database import Patient, Reminder, SessionLocal
except ImportError:  # Support running this directory as the application root.
    from database import Patient, Reminder, SessionLocal


ALL_DAYS = "mon,tue,wed,thu,fri,sat,sun"

_TIME_PATTERN = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:：時时点點](\d{2})?(?!\d)")

_TRIGGER_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"可以提醒我", r"可唔可以提醒我", r"幫我提醒", r"帮我提醒",
        r"提醒我", r"提我", r"記得提醒我", r"记得提醒我",
        r"remind me to", r"remind me",
    )
]
_TRAILING_PARTICLES = re.compile(r"(嗎|吗|呀|啊|喇|啦|呢)\s*$")
_ENGLISH_FILLER = re.compile(r"^(to)\b|\b(at|on|by)$", re.IGNORECASE)
_STRIP_CHARS = " ，,。.?？~！!:：、"


class ParsedReminder(NamedTuple):
    time: str
    text: str


def parse_reminder_request(message: str) -> ParsedReminder | None:
    """Extract a time and reminder text from a chat message, or None if no time is present.

    Only recognizes an explicit time-of-day (e.g. "12:28", "12：28", "9點") in
    the message itself; it does not infer a time from vague phrasing like
    "later" or "tonight" — callers should ask the user for a specific time
    in that case.
    """
    match = _TIME_PATTERN.search(message)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2)) if match.group(2) else 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    time_str = f"{hour:02d}:{minute:02d}"

    remainder = message[: match.start()] + message[match.end() :]
    text = _extract_reminder_text(remainder)
    return ParsedReminder(time=time_str, text=text)


def _extract_reminder_text(remainder: str) -> str:
    text = remainder
    for pattern in _TRIGGER_PATTERNS:
        text = pattern.sub("", text)
    text = _TRAILING_PARTICLES.sub("", text.strip(_STRIP_CHARS)).strip(_STRIP_CHARS)
    text = _ENGLISH_FILLER.sub("", text).strip(_STRIP_CHARS)
    return text or "提醒"


def get_or_create_patient(db, external_user_id: str, display_name: str = "") -> Patient:
    """Find the Patient row linked to this chat user, creating one if needed.

    external_user_id is the main app's registry_user_id
    (src/user/user_registry.py), not a reminder_backend-native identity —
    this is the bridge between the two previously-separate identity systems.
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
