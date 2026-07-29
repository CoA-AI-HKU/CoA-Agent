from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import NamedTuple
from zoneinfo import ZoneInfo

try:
    from .database import Patient, Reminder, SessionLocal
    from .trace_logging import log_reminder_checkpoint
except ImportError:  # Support running this directory as the application root.
    from database import Patient, Reminder, SessionLocal
    from trace_logging import log_reminder_checkpoint


# The server's system clock is not guaranteed to be set to the user's local
# timezone (the droplet runs in UTC), so "now" for parsing "in 5 minutes" and
# for the scheduler matching "is it 12:28 yet" must both be computed
# explicitly in the user's real timezone, not naive datetime.now(). This
# defaults to Hong Kong time, matching the Traditional Chinese/Cantonese
# patient-facing content; override with the REMINDER_TIMEZONE env var for a
# different deployment locale.
LOCAL_TIMEZONE = ZoneInfo(os.getenv("REMINDER_TIMEZONE", "Asia/Hong_Kong"))

ALL_DAYS = "mon,tue,wed,thu,fri,sat,sun"
# Sentinel used in place of a weekday list for a reminder that should fire
# once and then deactivate, rather than recur — see scheduler.py, which
# treats this the same as "any day" for a single delivery.
ONE_TIME = "once"

# Period-of-day markers that disambiguate a bare hour like "2點" into 24-hour
# time. Chinese doesn't otherwise distinguish 2am from 2pm the way "2:14 PM"
# does, so without this "下午2:14" (2:14 PM) was parsed as 02:14 (2:14 AM).
# The marker can come either before ("下午2:14") or after ("2:14下午") the
# time, and "今天"/"今日" directly next to a time is absorbed into the same
# match so it doesn't leak into the reminder's own text.
_PERIOD_KIND = {
    "凌晨": "am", "清晨": "am", "早上": "am", "上午": "am", "午前": "am",
    "中午": "noon",
    "下午": "pm", "晚上": "pm", "夜晚": "pm", "夜間": "pm", "夜间": "pm", "傍晚": "pm",
    "午後": "pm", "午后": "pm",
}
_PERIOD_ALTERNATION = "|".join(sorted(_PERIOD_KIND, key=len, reverse=True))
_TODAY_WORD = r"今[天日]"

_TIME_PATTERN = re.compile(
    rf"(?:{_TODAY_WORD})?\s*(?P<period_before>{_PERIOD_ALTERNATION})?\s*"
    # "鐘"/"钟" is an optional colloquial "o'clock" filler ("9點鐘" = "nine
    # o'clock") with no meaning of its own — absorbed here so it doesn't leak
    # into the reminder's own text (previously produced text like "鐘喝水").
    r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：時时点點][鐘钟]?(?P<minute>\d{1,2})?分?(?!\d)"
    rf"\s*(?P<period_after>{_PERIOD_ALTERNATION})?"
)

_CHINESE_DIGITS = {
    "零": 0, "一": 1, "兩": 2, "两": 2, "二": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_NUMBER_WORD = r"[\d一二兩两三四五六七八九十]{1,3}"

# "五點"/"下午五點三十分" — a Chinese-numeral hour ("五" for "5"), not an
# Arabic digit. _TIME_PATTERN's hour group only matches \d, so a message
# like "下午五點提醒我喝水" previously fell through to "no time found" and
# the bot asked the user to repeat themselves with a digit time instead of
# understanding the one they'd already given. Kept as a second pattern
# (tried only when _TIME_PATTERN finds nothing, in parse_reminder_request)
# rather than merged into _TIME_PATTERN, since the two use unrelated hour
# grammars (digit run vs. Chinese numeral word) and the digit path is
# already anchored on punctuation ":：時时点點" while this one only makes
# sense anchored on "點"/"点" — a bare Chinese numeral elsewhere in the
# message must not be mistaken for a time.
_CHINESE_TIME_PATTERN = re.compile(
    rf"(?:{_TODAY_WORD})?\s*(?P<period_before>{_PERIOD_ALTERNATION})?\s*"
    rf"(?P<hour>{_NUMBER_WORD})[點点][鐘钟]?\s*(?P<minute>{_NUMBER_WORD})?分?"
    rf"\s*(?P<period_after>{_PERIOD_ALTERNATION})?"
)
# "N分鐘後"/"N小時後" (in N minutes/hours) — relative durations, resolved
# against the current time at parse time rather than an absolute clock time.
# Requires the full "分鐘"/"分钟" word, not bare "分" — "2:14分" is the
# minutes component of a clock time (2:14), not "in 14 minutes".
_RELATIVE_MINUTES_PATTERN = re.compile(
    rf"({_NUMBER_WORD})\s*(分鐘|分钟)\s*(後|后|之後|之后)?"
)
_RELATIVE_HOURS_PATTERN = re.compile(
    rf"({_NUMBER_WORD})\s*(小時|小时|鐘頭|钟头)\s*(後|后|之後|之后)?"
)
# Excludes "而家幾點"/"現在是幾點鐘" (what time is it right now) — a time
# *question*, not a request to be reminded right now — from matching as a
# "now" relative-time signal.
_RIGHT_NOW_PATTERN = re.compile(r"(?:而家|宜家|依家|現在|现在|馬上|马上|立即|立刻)(?!\s*是?\s*[幾几]點)")

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
# Trailing confirmation-seeking phrases ("喝水好嗎" = "drink water, okay?",
# "喝水可以嗎" = "drink water, is that okay?", Cantonese "得唔得"/"好唔好")
# must be matched as whole units, listed before the bare single-character
# particles they contain — otherwise a leftmost-match on just "嗎" strips
# only the question particle and leaves "好"/"可以" stuck onto the
# reminder's own text (e.g. "喝水好嗎" -> "喝水好" instead of "喝水").
_TRAILING_PARTICLES = re.compile(
    r"(得唔得|好唔好|可唔可以|好嗎|好吗|好啊|可以嗎|可以吗|可以啊|OK嗎|OK吗|嗎|吗|呀|啊|喇|啦|呢)\s*$",
    re.IGNORECASE,
)
_ENGLISH_FILLER = re.compile(r"^(to)\b|\b(at|on|by)$", re.IGNORECASE)
_STRIP_CHARS = " ，,。.?？~！!:：、"


class ParsedReminder(NamedTuple):
    time: str
    text: str
    days: str
    # True when the time was given as a bare 1-12 hour with no 上午/下午/AM/PM
    # marker ("一點", "9點", "5:30") — genuinely ambiguous, since nothing in
    # the message says which half of the day was meant. Always False for
    # in-range 24-hour-notation hours (13-23, or explicit "0點"/midnight) and
    # for relative durations, neither of which need a marker to be
    # unambiguous. Callers (see memory_routine_agent.handle_routine_request)
    # ask the user to clarify instead of silently guessing AM.
    period_ambiguous: bool = False


def parse_reminder_request(message: str, now: datetime | None = None) -> ParsedReminder | None:
    """Extract a time, reminder text, and recurrence from a chat message.

    Returns None if no time — explicit ("12:28", "下午2:14", "9點", "下午五點",
    "十七點三十分") or relative ("兩分鐘後", "而家") — is present. Does not infer a time from
    vague phrasing like "later" or "tonight" with no duration attached;
    callers should ask the user for a specific time in that case.

    `now` is the reference clock time for resolving relative durations
    ("in 5 minutes"); defaults to the real current time and exists mainly so
    tests can pin it. A relative-time or "right now" request is always
    treated as one-time — "remind me in 5 minutes" every day forever isn't
    a sensible default.
    """
    reference = now or datetime.now(LOCAL_TIMEZONE)

    relative = _match_relative_time(message, reference)
    if relative is not None:
        target, span = relative
        remainder = message[: span[0]] + message[span[1] :]
        text = _extract_reminder_text(remainder)
        return ParsedReminder(time=target.strftime("%H:%M"), text=text, days=ONE_TIME)

    match = _TIME_PATTERN.search(message)
    if match:
        period = match.group("period_before") or match.group("period_after")
        hour = _adjust_hour_for_period(int(match.group("hour")), period)
        minute = int(match.group("minute")) if match.group("minute") else 0
        span = (match.start(), match.end())
    else:
        chinese_match = _CHINESE_TIME_PATTERN.search(message)
        if not chinese_match:
            return None
        hour_value = _number_word_to_int(chinese_match.group("hour"))
        minute_text = chinese_match.group("minute")
        minute_value = _number_word_to_int(minute_text) if minute_text else 0
        if hour_value is None or minute_value is None:
            return None
        period = chinese_match.group("period_before") or chinese_match.group("period_after")
        hour = _adjust_hour_for_period(hour_value, period)
        minute = minute_value
        span = (chinese_match.start(), chinese_match.end())

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    time_str = f"{hour:02d}:{minute:02d}"
    # period is None means no marker was given at all — _adjust_hour_for_period
    # is then a no-op, so `hour` here still equals the bare hour as typed.
    period_ambiguous = period is None and 1 <= hour <= 12

    remainder = message[: span[0]] + message[span[1] :]
    is_one_time = any(pattern.search(remainder) for pattern in _ONE_TIME_PATTERNS)
    text = _extract_reminder_text(remainder)
    return ParsedReminder(
        time=time_str, text=text, days=ONE_TIME if is_one_time else ALL_DAYS,
        period_ambiguous=period_ambiguous,
    )


def _match_relative_time(message: str, reference: datetime) -> tuple[datetime, tuple[int, int]] | None:
    now_match = _RIGHT_NOW_PATTERN.search(message)
    if now_match:
        return reference, now_match.span()

    hours_match = _RELATIVE_HOURS_PATTERN.search(message)
    minutes_match = _RELATIVE_MINUTES_PATTERN.search(message)
    # "1小時30分鐘後" — both present and adjacent: combine into one offset
    # and consume the whole span, rather than treating them separately.
    if hours_match and minutes_match and minutes_match.start() <= hours_match.end() + 1:
        hours = _number_word_to_int(hours_match.group(1))
        minutes = _number_word_to_int(minutes_match.group(1))
        if hours is not None and minutes is not None:
            span = (min(hours_match.start(), minutes_match.start()), max(hours_match.end(), minutes_match.end()))
            return reference + timedelta(hours=hours, minutes=minutes), span

    if minutes_match:
        minutes = _number_word_to_int(minutes_match.group(1))
        if minutes is not None:
            return reference + timedelta(minutes=minutes), minutes_match.span()

    if hours_match:
        hours = _number_word_to_int(hours_match.group(1))
        if hours is not None:
            return reference + timedelta(hours=hours), hours_match.span()

    return None


def _number_word_to_int(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        tens = _CHINESE_DIGITS.get(left, 1) if left else 1
        ones = _CHINESE_DIGITS.get(right, 0) if right else 0
        return tens * 10 + ones
    return _CHINESE_DIGITS.get(text)


def _adjust_hour_for_period(hour: int, period: str | None) -> int:
    return adjust_hour_for_period_kind(hour, _PERIOD_KIND.get(period or ""))


def adjust_hour_for_period_kind(hour: int, kind: str | None) -> int:
    """Same adjustment as _adjust_hour_for_period, but takes a resolved kind

    ("am"/"pm"/"noon", e.g. from resolve_period_word) rather than a raw
    marker word — used once a period-clarification reply has been resolved.
    """
    if kind == "pm" and hour < 12:
        return hour + 12
    if kind == "am" and hour == 12:
        return 0
    return hour


def extract_reminder_text_only(message: str) -> str:
    """Strip reminder trigger/recurrence phrasing without requiring a time.

    Used to capture what the user wants to be reminded about when they
    haven't given a time yet, so a follow-up reply containing only a time
    (see src/user/pending_reminder.py) can be combined with it.
    """
    return _extract_reminder_text(message)


def _extract_reminder_text(remainder: str) -> str:
    text = remainder
    for pattern in (*_TRIGGER_PATTERNS, *_ONE_TIME_PATTERNS):
        text = pattern.sub("", text)
    text = _TRAILING_PARTICLES.sub("", text.strip(_STRIP_CHARS)).strip(_STRIP_CHARS)
    text = _ENGLISH_FILLER.sub("", text).strip(_STRIP_CHARS)
    return text or "提醒"


def get_or_create_patient(
    db, external_user_id: str, display_name: str = "", chat_sender_id: str = "",
) -> Patient:
    """Find the Patient row linked to this chat user, creating one if needed.

    external_user_id is the main app's registry_user_id
    (src/user/user_registry.py), not a reminders-native identity — this is
    the bridge between the two previously-separate identity systems.

    chat_sender_id is the actual Telegram/WhatsApp chat identifier, captured
    directly from the message-handling call chain (message_router.py always
    has it) rather than reconstructed later by reverse-searching the user
    registry — see the Patient.chat_sender_id column comment. Refreshed on
    every call (not just at creation) so it stays correct if someone's
    external_user_id gets linked to a different chat later.
    """
    patient = (
        db.query(Patient).filter(Patient.external_user_id == external_user_id).first()
    )
    if patient is not None:
        changed = False
        if display_name and patient.name != display_name:
            patient.name = display_name
            changed = True
        if chat_sender_id and patient.chat_sender_id != chat_sender_id:
            patient.chat_sender_id = chat_sender_id
            changed = True
        if changed:
            db.commit()
        return patient

    patient = Patient(
        external_user_id=external_user_id,
        name=display_name or external_user_id,
        caregiver_id=None,
        chat_sender_id=chat_sender_id or None,
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
    channel: str = "",
    message_id: str = "",
    chat_sender_id: str = "",
) -> Reminder:
    db = SessionLocal()
    try:
        patient = get_or_create_patient(db, external_user_id, display_name, chat_sender_id)
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
        log_reminder_checkpoint(
            "reminder_persisted",
            reminder_id=reminder.id,
            user_id=external_user_id,
            channel=channel,
            message_id=message_id,
            normalized_due_time=time_str,
            days=days,
        )
        # This scheduler polls (see scheduler.py: an every-minute query for
        # active reminders matching the current time), rather than
        # registering a discrete per-reminder job — so "registered" here
        # means the persisted row is now active and will match that query,
        # not that a scheduler job object was created.
        log_reminder_checkpoint(
            "reminder_scheduler_registered",
            reminder_id=reminder.id,
            user_id=external_user_id,
            channel=channel,
            message_id=message_id,
            normalized_due_time=time_str,
            days=days,
            active=reminder.active,
        )
        return reminder
    finally:
        db.close()


def reminder_confirmation_text(time_str: str, text: str, days: str, answer_language: str) -> str:
    one_time = days == ONE_TIME
    if answer_language == "zh-Hans":
        cadence = "今天" if one_time else "每日"
        return f"好的，我会{cadence}{time_str}提醒你「{text}」。如果之后想取消或更改，可以再告诉我。"
    if answer_language == "en":
        cadence = "today" if one_time else "every day"
        return f'Okay, I\'ll remind you {cadence} at {time_str} to "{text}". Let me know if you want to change or cancel it later.'
    cadence = "今天" if one_time else "每日"
    return f"好的，我會{cadence}{time_str}提醒你「{text}」。如果之後想取消或更改，可以再告訴我。"


def has_reminder_trigger_phrase(message: str) -> bool:
    """True if the message itself asks for a reminder, independent of a time being present.

    Used to tell a genuinely new reminder request ("提醒我...") apart from a
    bare follow-up correction ("抱歉，我的意思是下午一點二十一") that only
    makes sense in the context of a reminder just confirmed — the latter
    should update that reminder rather than being treated as a fresh request
    or falling through to a generic reply.
    """
    return any(pattern.search(message) for pattern in _TRIGGER_PATTERNS)


def update_reminder_time(reminder_id: int, time_str: str, days: str) -> Reminder | None:
    """Update an existing reminder's time/recurrence in place, keeping its text.

    Returns None if the reminder no longer exists (e.g. already fired and
    cleaned up) rather than raising, so callers can fall back gracefully.
    """
    db = SessionLocal()
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if reminder is None:
            return None
        reminder.time = time_str
        reminder.days = days
        db.commit()
        db.refresh(reminder)
        log_reminder_checkpoint(
            "reminder_corrected", reminder_id=reminder.id, normalized_due_time=time_str, days=days,
        )
        return reminder
    finally:
        db.close()


def reminder_correction_text(time_str: str, text: str, days: str, answer_language: str) -> str:
    one_time = days == ONE_TIME
    if answer_language == "zh-Hans":
        cadence = "今天" if one_time else "每日"
        return f"好的，已经帮你改成{cadence}{time_str}提醒你「{text}」。"
    if answer_language == "en":
        cadence = "today" if one_time else "every day"
        return f'Got it, I\'ve updated it — I\'ll remind you {cadence} at {time_str} to "{text}".'
    cadence = "今天" if one_time else "每日"
    return f"好的，已經幫你改成{cadence}{time_str}提醒你「{text}」。"


def reminder_period_question_text(hour: int, answer_language: str) -> str:
    """Ask which half of the day a bare, unmarked hour (1-12) means."""
    if answer_language == "zh-Hans":
        return f"你说{hour}点，是想说上午还是下午呢？"
    if answer_language == "en":
        return f"Did you mean {hour} AM or {hour} PM?"
    return f"你話{hour}點，係想話上午定係下午呢？"


# English AM/PM replies to a period-clarification question — separate from
# _PERIOD_KIND (which anchors specifically Chinese period words used inline
# in a time expression like "下午2:14"), since a bare reply here may be just
# "AM"/"PM"/"am"/"pm" with no accompanying time at all.
_ENGLISH_PERIOD_REPLY = re.compile(r"\b(a\.?m\.?|p\.?m\.?)\b", re.IGNORECASE)


def resolve_period_word(message: str) -> str | None:
    """Extract 'am'/'pm'/'noon' from a reply to the AM/PM clarification question.

    Returns None if the reply doesn't contain a recognizable period word, so
    the caller knows not to treat it as an answer.
    """
    for word, kind in _PERIOD_KIND.items():
        if word in message:
            return kind
    english = _ENGLISH_PERIOD_REPLY.search(message)
    if english:
        return "pm" if english.group(1).lower().startswith("p") else "am"
    return None
