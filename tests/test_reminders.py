from __future__ import annotations

import json
from unittest import mock

import pytest

from src.reminders import chat_reminders, scheduler as reminder_scheduler
from src.reminders.chat_reminders import create_reminder_for_user, parse_reminder_request
from src.reminders.database import Patient, Reminder, SessionLocal
from src.reminders.llm_reminder_extractor import ReminderDecision
from src.agents.coordinator_agent import coordinate_message
from src.agents.memory_routine_agent import handle_routine_request
from src.orchestrator import handle_dementia_user_message


@pytest.fixture
def registered_patient(tmp_path, monkeypatch):
    registry_path = tmp_path / "user_registry.json"
    registry_path.write_text(
        json.dumps(
            {"users": {"telegram-reminder-test": {"role": "user", "user_id": "patient-reminder-test", "display_name": "Test Ling"}}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    yield "patient-reminder-test"
    _cleanup_patient("patient-reminder-test")


def _cleanup_patient(external_user_id: str) -> None:
    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == external_user_id).first()
        if patient is not None:
            db.query(Reminder).filter(Reminder.patient_id == patient.id).delete(synchronize_session=False)
            db.query(Patient).filter(Patient.id == patient.id).delete(synchronize_session=False)
            db.commit()
    finally:
        db.close()


def test_parse_reminder_request_extracts_time_and_text():
    parsed = parse_reminder_request("12：28可以提醒我吃藥嗎")
    assert parsed.time == "12:28"
    assert parsed.text == "吃藥"
    assert parsed.days == chat_reminders.ALL_DAYS

    parsed2 = parse_reminder_request("12：28可以提醒我做飯嗎")
    assert parsed2.time == "12:28"
    assert parsed2.text == "做飯"

    assert parse_reminder_request("提醒我食藥") is None


def test_parse_reminder_request_accepts_hour_only_chinese_time():
    parsed = parse_reminder_request("可以9點提醒我食藥嗎")
    assert parsed.time == "09:00"
    assert "食藥" in parsed.text


def test_parse_reminder_request_handles_pm_marker():
    # "下午2:14" is 2:14 PM (14:14), not 02:14 — this was the reported bug.
    parsed = parse_reminder_request("可以下午2：14分提醒我吃飯嗎")
    assert parsed.time == "14:14"
    assert parsed.text == "吃飯"


def test_parse_reminder_request_handles_am_and_evening_markers():
    assert parse_reminder_request("上午11點提醒我食藥").time == "11:00"
    assert parse_reminder_request("上午12點提醒我食藥").time == "00:00"
    assert parse_reminder_request("晚上8點提醒我食藥").time == "20:00"


def test_parse_reminder_request_accepts_chinese_numeral_hour():
    # Regression test: "五點" uses the Chinese numeral 五 ("five"), not the
    # digit 5, for the hour. _TIME_PATTERN's hour group only matched \d, so
    # this previously fell through to "no time found" and the bot asked the
    # user to repeat a time they'd already given — reproduced live in
    # production ("下午五點提醒我喝水號碼" got "可以話我知幾點提醒你嗎？"
    # instead of setting the 17:00 reminder).
    parsed = parse_reminder_request("下午五點提醒我喝水")
    assert parsed.time == "17:00"
    assert parsed.text == "喝水"

    assert parse_reminder_request("五點提醒我食藥").time == "05:00"
    assert parse_reminder_request("十二點提醒我食藥").time == "12:00"
    assert parse_reminder_request("上午十一點提醒我食藥").time == "11:00"


def test_parse_reminder_request_accepts_chinese_numeral_24_hour_and_minute():
    parsed = parse_reminder_request("十七點提醒我食藥")
    assert parsed.time == "17:00"

    parsed2 = parse_reminder_request("下午五點三十分提醒我食飯")
    assert parsed2.time == "17:30"
    assert parsed2.text == "食飯"


def test_parse_reminder_request_chinese_numerals_elsewhere_are_not_mistaken_for_a_time():
    # A Chinese numeral not immediately followed by 點/点 is not a time —
    # only digit-based clock times and relative durations should match.
    assert parse_reminder_request("我有三個蘋果") is None
    assert parse_reminder_request("而家幾點") is None


def test_parse_reminder_request_detects_one_time_phrasing():
    parsed = parse_reminder_request(
        "可以下午2：14分提醒我吃飯嗎，不需要以後每天都提醒，今天提一下就行了"
    )
    assert parsed.time == "14:14"
    assert parsed.text == "吃飯"
    assert parsed.days == chat_reminders.ONE_TIME
    # The recurrence instruction must not leak into the reminder's own text.
    assert "每天" not in parsed.text
    assert "今天" not in parsed.text


def test_parse_reminder_request_handles_trailing_pm_marker():
    # "3:39下午" — the period marker after the time, not before it.
    parsed = parse_reminder_request("不需要每天提醒，今天3：39下午提醒我給手機充電")
    assert parsed.time == "15:39"
    assert parsed.text == "給手機充電"
    assert parsed.days == chat_reminders.ONE_TIME


def test_parse_reminder_request_strips_trailing_confirmation_phrases():
    # Regression test: "喝水好嗎" ("drink water, okay?") only had the bare
    # "嗎" particle stripped, leaving "好" stuck onto the reminder text
    # ("喝水好") — reproduced live in production. "好嗎"/"可以嗎"/etc. must
    # be stripped as whole units, not just their trailing particle.
    from datetime import datetime

    now = datetime(2026, 7, 27, 15, 0)
    parsed = parse_reminder_request("提醒我兩分鐘后喝水好嗎", now=now)
    assert parsed.text == "喝水"

    parsed2 = parse_reminder_request("五點二十六分提醒我喝水可以嗎")
    assert parsed2.text == "喝水"

    parsed3 = parse_reminder_request("12：28可以提醒我吃藥嗎")
    assert parsed3.text == "吃藥"


def test_parse_reminder_request_handles_relative_minutes():
    from datetime import datetime

    now = datetime(2026, 7, 27, 15, 0)
    parsed = parse_reminder_request("兩分鐘后提醒我給手機充電", now=now)
    assert parsed.time == "15:02"
    assert parsed.text == "給手機充電"
    assert parsed.days == chat_reminders.ONE_TIME

    parsed2 = parse_reminder_request("一分鐘后提醒我食飯", now=now)
    assert parsed2.time == "15:01"


def test_parse_reminder_request_handles_relative_hours():
    from datetime import datetime

    now = datetime(2026, 7, 27, 15, 0)
    parsed = parse_reminder_request("3小時後提醒我食藥", now=now)
    assert parsed.time == "18:00"
    assert parsed.days == chat_reminders.ONE_TIME


def test_parse_reminder_request_default_now_is_local_timezone_not_naive_server_clock():
    # Regression test: the droplet's system clock is UTC, but reminders must
    # be computed and matched in the user's real timezone (Hong Kong,
    # UTC+8), or "remind me in 1 minute" silently comes out 8 hours off —
    # confirmed the bot's own confirmation text didn't match the user's
    # actual wall clock. parse_reminder_request(message) with no explicit
    # `now` must default to chat_reminders.LOCAL_TIMEZONE, not naive
    # datetime.now() (which reflects the server's, not the user's, clock).
    from datetime import datetime, timedelta

    assert str(chat_reminders.LOCAL_TIMEZONE) == "Asia/Hong_Kong"

    expected = datetime.now(chat_reminders.LOCAL_TIMEZONE) + timedelta(minutes=1)
    parsed = parse_reminder_request("一分鐘后提醒我食藥")
    actual_hour, actual_minute = (int(part) for part in parsed.time.split(":"))
    actual_total_minutes = actual_hour * 60 + actual_minute
    expected_total_minutes = expected.hour * 60 + expected.minute
    # Allow a 1-minute tolerance for the wall-clock tick between computing
    # `expected` here and the call inside parse_reminder_request.
    diff = min(
        abs(actual_total_minutes - expected_total_minutes),
        1440 - abs(actual_total_minutes - expected_total_minutes),
    )
    assert diff <= 1


def test_parse_reminder_request_handles_right_now():
    from datetime import datetime

    now = datetime(2026, 7, 27, 15, 30)
    parsed = parse_reminder_request("而家提醒我食藥", now=now)
    assert parsed.time == "15:30"
    assert parsed.text == "食藥"


def test_get_or_create_patient_is_idempotent():
    external_id = "pytest-idempotent-user"
    try:
        r1 = create_reminder_for_user(external_id, "Name A", "食藥", "08:00")
        r2 = create_reminder_for_user(external_id, "Name A", "散步", "09:00")
        assert r1.patient_id == r2.patient_id
    finally:
        _cleanup_patient(external_id)


def test_reminder_request_creates_reminder_and_confirms(registered_patient):
    result = handle_dementia_user_message("下午12：28可以提醒我吃藥嗎", registered_patient)

    assert result["route"] == "routine"
    assert "12:28" in result["answer"]
    assert "吃藥" in result["answer"]

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        assert patient is not None
        reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
        assert any(r.time == "12:28" and r.text == "吃藥" for r in reminders)
    finally:
        db.close()


def test_reminder_request_without_time_asks_for_one(registered_patient):
    result = handle_dementia_user_message("可以提醒我食藥嗎", registered_patient)

    assert result["route"] == "routine"
    assert "幾點" in result["answer"] or "time" in result["answer"].lower()


def test_reminder_request_without_registration_asks_to_register():
    result = handle_dementia_user_message("12：28可以提醒我吃藥嗎", None)

    assert result["route"] == "routine"
    assert "register" in result["answer"].lower() or "\\register" in result["answer"]


def test_medication_uncertainty_still_reaches_medical_boundary_not_reminder():
    decision = coordinate_message("我唔記得食咗藥未")
    assert decision.route == "medical_boundary"

    decision2 = coordinate_message("我唔記得今日有冇食藥，係咪食多次？")
    assert decision2.route == "medical_boundary"


def test_explicit_reminder_request_bypasses_medication_boundary():
    decision = coordinate_message("12：28可以提醒我吃藥嗎")
    assert decision.route == "routine"
    assert decision.intent == "reminder_request"


def test_scheduler_delivers_due_reminder_via_telegram(registered_patient, monkeypatch):
    handle_dementia_user_message("上午08:15可以提醒我食藥嗎", registered_patient)

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    sent = {}

    def fake_post(url, json=None, timeout=None):
        sent["url"] = url
        sent["json"] = json

        class Response:
            status_code = 200

        return Response()

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        reminder = db.query(Reminder).filter(Reminder.patient_id == patient.id, Reminder.time == "08:15").first()
        assert reminder is not None

        with mock.patch.object(reminder_scheduler.requests, "post", fake_post):
            delivered = reminder_scheduler._deliver_reminder(patient, reminder)
    finally:
        db.close()

    assert delivered is True
    assert sent["json"]["chat_id"] == "telegram-reminder-test"
    assert "食藥" in sent["json"]["text"]


def test_scheduler_deactivates_one_time_reminder_after_firing(registered_patient, monkeypatch):
    fixed_time = "08:20"
    create_reminder_for_user(
        registered_patient, "Test Ling", "食藥", fixed_time, days=chat_reminders.ONE_TIME
    )
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    class FixedDatetime(reminder_scheduler.datetime):
        @classmethod
        def now(cls, tz=None):
            return reminder_scheduler.datetime(2026, 7, 27, 8, 20)

    def fake_post(url, json=None, timeout=None):
        class Response:
            status_code = 200

        return Response()

    with mock.patch.object(reminder_scheduler, "datetime", FixedDatetime), mock.patch.object(
        reminder_scheduler.requests, "post", fake_post
    ):
        reminder_scheduler.check_and_send_reminders()

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        reminder = db.query(Reminder).filter(
            Reminder.patient_id == patient.id, Reminder.time == fixed_time
        ).first()
        assert reminder is not None
        assert reminder.active is False
        assert reminder.last_triggered is not None
    finally:
        db.close()


def test_bare_time_reply_completes_a_pending_reminder(registered_patient, tmp_path, monkeypatch):
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("PENDING_REMINDER_STATE_PATH", str(tmp_path / "pending_reminders.json"))

    first = handle_incoming_message("提醒我食藥", "telegram-reminder-test", "telegram")
    assert first["route"] == "routine"
    assert "幾點" in first["answer"]

    # 15:41 rather than a bare "3:41" — an in-range 24-hour hour (>12) is
    # unambiguous on its own, keeping this test's focus on the pending-reply
    # mechanism itself rather than also exercising the AM/PM question.
    second = handle_incoming_message("15：41", "telegram-reminder-test", "telegram")
    assert second["route"] == "routine"
    assert "15:41" in second["answer"]
    assert "食藥" in second["answer"]

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        assert patient is not None
        assert any(r.time == "15:41" and r.text == "食藥" for r in db.query(Reminder).filter(Reminder.patient_id == patient.id))
    finally:
        db.close()


def test_unrelated_message_after_a_pending_reminder_is_not_swallowed(registered_patient, tmp_path, monkeypatch):
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("PENDING_REMINDER_STATE_PATH", str(tmp_path / "pending_reminders.json"))

    first = handle_incoming_message("提醒我食藥", "telegram-reminder-test", "telegram")
    assert first["route"] == "routine"

    # No time in this message — pending state must not be force-consumed.
    second = handle_incoming_message("你好", "telegram-reminder-test", "telegram")
    assert second["route"] != "routine" or "食藥" not in second["answer"]


def test_current_time_question_is_not_misrouted_as_a_reminder():
    from src.agents.coordinator_agent import coordinate_message
    from src.orchestrator import handle_dementia_user_message

    for message in ("現在是幾點鐘", "而家幾點", "what time is it"):
        decision = coordinate_message(message)
        assert decision.route != "routine", f"{message!r} should not be treated as a reminder request"

    result = handle_dementia_user_message("現在是幾點鐘", "test-time-question")
    assert result["route"] != "routine"
    assert "提醒" not in result["answer"]


def test_llm_fallback_creates_reminder_when_regex_finds_no_time(registered_patient, monkeypatch):
    # Regression coverage for the fallback added after regex kept missing
    # real phrasings in production ("食完飯後", "遲啲", odd constructions) —
    # only exercised because the message below has no time the regex parser
    # can find at all.
    decision = ReminderDecision(
        is_reminder=True, time="18:45", days=chat_reminders.ONE_TIME, task="食藥", response=None,
    )
    monkeypatch.setattr(
        "src.agents.memory_routine_agent.decide_reminder_via_llm",
        lambda message, now, answer_language: decision,
    )

    result = handle_routine_request("食完飯之後幫我記得食藥呀", registered_patient)

    assert result["route"] == "routine"
    assert "18:45" in result["answer"]
    assert "食藥" in result["answer"]

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
        assert any(r.time == "18:45" and r.text == "食藥" for r in reminders)
    finally:
        db.close()


def test_llm_fallback_declines_without_creating_a_reminder(registered_patient, monkeypatch):
    # The LLM gets the final say on whether this is really a reminder — it
    # must be able to say no and reply in its own words, not be forced to
    # create something just because some time-shaped text was nearby.
    decision = ReminderDecision(
        is_reminder=False, time=None, days=None, task="", response="這聽起來不像是要設定提醒，我理解錯了嗎？",
    )
    monkeypatch.setattr(
        "src.agents.memory_routine_agent.decide_reminder_via_llm",
        lambda message, now, answer_language: decision,
    )

    result = handle_routine_request("提醒我要記得喝水好重要", registered_patient)

    assert result["route"] == "routine"
    assert result["safety_level"] == "reminder_declined_by_model"
    assert result["answer"] == "這聽起來不像是要設定提醒，我理解錯了嗎？"

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all() if patient else []
        assert not reminders
    finally:
        db.close()


def test_llm_fallback_can_ask_its_own_clarifying_question(registered_patient, monkeypatch):
    decision = ReminderDecision(is_reminder=True, time=None, days=None, task="食藥", response="請問想幾點提醒你呢？")
    monkeypatch.setattr(
        "src.agents.memory_routine_agent.decide_reminder_via_llm",
        lambda message, now, answer_language: decision,
    )

    result = handle_routine_request("提醒我食藥好唔好", registered_patient)

    assert result["route"] == "routine"
    assert result["safety_level"] == "reminder_needs_time"
    assert result["answer"] == "請問想幾點提醒你呢？"


def test_llm_fallback_resolves_ambiguous_bare_hour_using_context(registered_patient, monkeypatch):
    # The LLM is now also consulted when regex parses a time but can't tell
    # AM/PM from the bare hour alone — it can use surrounding context the
    # regex can't ("食完晚飯" implies evening) instead of always falling
    # back to asking the user directly.
    decision = ReminderDecision(
        is_reminder=True, time="21:00", days=chat_reminders.ALL_DAYS, task="食藥", response=None,
    )
    monkeypatch.setattr(
        "src.agents.memory_routine_agent.decide_reminder_via_llm",
        lambda message, now, answer_language: decision,
    )

    result = handle_routine_request("食完晚飯九點提醒我食藥", registered_patient)

    assert result["route"] == "routine"
    assert result["safety_level"] == "reminder_created"
    assert "21:00" in result["answer"]

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
        assert any(r.time == "21:00" and r.text == "食藥" for r in reminders)
    finally:
        db.close()


def test_llm_fallback_still_asks_canned_period_question_when_it_also_cant_tell(registered_patient, monkeypatch):
    # If the LLM is consulted for an ambiguous bare hour but also can't
    # resolve AM/PM (time still None), fall back to the specific, structured
    # period question rather than the LLM's own generic "what time?" reply —
    # the regex already extracted the hour, so re-asking for the whole time
    # from scratch would be a worse follow-up than asking just AM/PM.
    decision = ReminderDecision(
        is_reminder=True, time=None, days=None, task="食藥", response="唔知道你想幾點呀，可以講清楚啲嗎？",
    )
    monkeypatch.setattr(
        "src.agents.memory_routine_agent.decide_reminder_via_llm",
        lambda message, now, answer_language: decision,
    )

    result = handle_routine_request("九點提醒我食藥", registered_patient)

    assert result["route"] == "routine"
    assert result["safety_level"] == "reminder_needs_period"
    assert "上午" in result["answer"] and "下午" in result["answer"]


def test_llm_fallback_is_never_consulted_when_regex_already_found_a_time(registered_patient, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("LLM fallback must not run when the regex parser already found a time")

    monkeypatch.setattr("src.agents.memory_routine_agent.decide_reminder_via_llm", fail_if_called)

    result = handle_routine_request("下午12：28可以提醒我吃藥嗎", registered_patient)

    assert result["route"] == "routine"
    assert "12:28" in result["answer"]


def test_scheduler_skips_delivery_when_patient_not_linked_to_a_chat_account():
    external_id = "pytest-unlinked-user"
    try:
        create_reminder_for_user(external_id, "Unlinked", "食藥", "08:00")
        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            reminder = db.query(Reminder).filter(Reminder.patient_id == patient.id).first()
            delivered = reminder_scheduler._deliver_reminder(patient, reminder)
        finally:
            db.close()
        assert delivered is False
    finally:
        _cleanup_patient(external_id)


def test_unregistered_sender_still_gets_reminder_delivered(tmp_path, monkeypatch):
    # Regression test: delivery used to require a completed \register (it
    # reverse-searched the registry for a "user" account whose assigned
    # user_id matched the reminder's external_user_id), so an unregistered
    # sender's reminder was created and confirmed normally but silently
    # never delivered — reproduced live in production. chat_sender_id is
    # now captured directly at creation time, independent of registration.
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    external_id = "unregistered-delivery-test"
    try:
        result = handle_incoming_message("下午12:50提醒我食藥", external_id, "telegram")
        assert result["route"] == "routine"

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            assert patient is not None
            assert patient.chat_sender_id == external_id
            reminder = db.query(Reminder).filter(Reminder.patient_id == patient.id).first()

            sent = {}

            def fake_post(url, json=None, timeout=None):
                sent["json"] = json

                class Response:
                    status_code = 200

                return Response()

            with mock.patch.object(reminder_scheduler.requests, "post", fake_post):
                monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
                delivered = reminder_scheduler._deliver_reminder(patient, reminder)
        finally:
            db.close()

        assert delivered is True
        assert sent["json"]["chat_id"] == external_id
    finally:
        _cleanup_patient(external_id)


def test_delivery_falls_back_to_registry_lookup_for_legacy_rows_without_chat_sender_id(registered_patient, monkeypatch):
    # A reminder created before chat_sender_id existed (or by any other path
    # that didn't pass it) has patient.chat_sender_id == None — delivery
    # must still work for those via the original registry reverse-lookup.
    reminder = create_reminder_for_user(registered_patient, "Test Ling", "食藥", "08:00")

    db = SessionLocal()
    try:
        patient = db.query(Patient).filter(Patient.external_user_id == registered_patient).first()
        assert patient.chat_sender_id is None  # not passed by this call

        sent = {}

        def fake_post(url, json=None, timeout=None):
            sent["json"] = json

            class Response:
                status_code = 200

            return Response()

        with mock.patch.object(reminder_scheduler.requests, "post", fake_post):
            monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
            delivered = reminder_scheduler._deliver_reminder(patient, reminder)
    finally:
        db.close()

    assert delivered is True
    assert sent["json"]["chat_id"] == "telegram-reminder-test"


def test_reminder_correction_updates_time_and_keeps_task_text(tmp_path, monkeypatch):
    # Regression test: "抱歉，我的意思是下午一點二十一" (a follow-up
    # correcting the time) has no reminder-trigger phrase of its own, so it
    # used to fall through to a generic "I don't understand" reply and leave
    # the wrongly-timed reminder untouched — reproduced live in production.
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("LAST_CREATED_REMINDER_STATE_PATH", str(tmp_path / "last_created_reminders.json"))
    external_id = "correction-flow-test"
    try:
        # Both messages include an explicit period marker so this test
        # exercises the correction mechanism itself, not the separate
        # AM/PM-clarification flow that a bare "一點二十分" would now trigger.
        first = handle_incoming_message("下午一點二十提醒我喝水好嗎", external_id, "telegram")
        assert first["route"] == "routine"
        assert first["safety_level"] == "reminder_created"
        assert "13:20" in first["answer"]

        second = handle_incoming_message("抱歉，我的意思是下午一點二十一", external_id, "telegram")
        assert second["route"] == "routine"
        assert second["safety_level"] == "reminder_corrected"
        assert "13:21" in second["answer"]
        assert "喝水" in second["answer"]

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
            # Corrected in place — still exactly one reminder, not a second one.
            assert len(reminders) == 1
            assert reminders[0].time == "13:21"
            assert reminders[0].text == "喝水"
        finally:
            db.close()
    finally:
        _cleanup_patient(external_id)


def test_reminder_correction_does_not_apply_when_followup_is_a_new_request(tmp_path, monkeypatch):
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("LAST_CREATED_REMINDER_STATE_PATH", str(tmp_path / "last_created_reminders.json"))
    external_id = "correction-not-hijacked-test"
    try:
        first = handle_incoming_message("下午一點二十提醒我喝水", external_id, "telegram")
        assert first["safety_level"] == "reminder_created"

        # Has its own "提醒我" trigger phrase — a genuinely new request, must
        # not be swallowed as a correction of the first reminder.
        second = handle_incoming_message("下午五點提醒我食藥", external_id, "telegram")
        assert second["safety_level"] == "reminder_created"

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
            assert len(reminders) == 2
        finally:
            db.close()
    finally:
        _cleanup_patient(external_id)


def test_reminder_correction_expires_after_its_ttl(tmp_path, monkeypatch):
    from src.user import pending_reminder_correction

    state_path = tmp_path / "last_created_reminders.json"
    monkeypatch.setenv("LAST_CREATED_REMINDER_STATE_PATH", str(state_path))

    from datetime import datetime, timedelta, timezone
    stale_entry = {
        "reminder_id": 999999,
        "text": "食藥",
        "answer_language": "zh-Hant",
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    }
    state_path.write_text(json.dumps({"stale-correction-test": stale_entry}), encoding="utf-8")

    result = pending_reminder_correction.consume_reminder_correction("stale-correction-test", "下午一點二十一")
    assert result is None


def test_parse_reminder_request_flags_bare_hour_as_period_ambiguous():
    parsed = parse_reminder_request("一點二十分提醒我喝水")
    assert parsed.time == "01:20"
    assert parsed.period_ambiguous is True

    parsed2 = parse_reminder_request("5:30可以提醒我食藥嗎")
    assert parsed2.time == "05:30"
    assert parsed2.period_ambiguous is True


def test_parse_reminder_request_marked_or_24_hour_times_are_not_ambiguous():
    assert parse_reminder_request("下午5:30可以提醒我食藥嗎").period_ambiguous is False
    assert parse_reminder_request("十七點提醒我食藥").period_ambiguous is False
    assert parse_reminder_request("0點提醒我食藥").period_ambiguous is False


def test_parse_reminder_request_recognizes_wu_hou_and_wu_qian():
    # Regression test: "午後"/"午前" (formal/Japanese-influenced "after
    # noon"/"before noon") weren't in the recognized period-marker set, so
    # "午後兩點十五分提醒我喝水" fell through as ambiguous and asked AM/PM
    # unnecessarily — reproduced live in production.
    parsed = parse_reminder_request("午後兩點十五分提醒我喝水")
    assert parsed.time == "14:15"
    assert parsed.period_ambiguous is False

    parsed2 = parse_reminder_request("午前七點提醒我食藥")
    assert parsed2.time == "07:00"
    assert parsed2.period_ambiguous is False

    assert parse_reminder_request("午后兩點提醒我喝水").time == "14:00"


def test_parse_reminder_request_strips_zhong_filler_after_hour():
    # Regression test: "九點鐘" ("nine o'clock", 鐘 is a filler with no
    # meaning of its own) left "鐘" stuck onto the reminder text ("鐘喝水")
    # because the time pattern stopped matching right after "點" — reproduced
    # live in production.
    parsed = parse_reminder_request("晚上九點鐘提醒我喝水")
    assert parsed.time == "21:00"
    assert parsed.text == "喝水"

    parsed2 = parse_reminder_request("下午5點鐘提醒我食藥")
    assert parsed2.time == "17:00"
    assert parsed2.text == "食藥"


def test_parse_reminder_request_strips_trailing_ho_a_and_ho_ho():
    parsed = parse_reminder_request("下午五點提醒我喝水可以啊")
    assert parsed.text == "喝水"


def test_ambiguous_reminder_asks_am_or_pm_instead_of_guessing(tmp_path, monkeypatch):
    # This is the exact case that bit Ling in production: "一點二十分提醒我
    # 喝水好嗎" silently became 01:20 when 13:20 was meant, discovered only
    # after the wrong-time reminder had already fired.
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("PENDING_REMINDER_PERIOD_STATE_PATH", str(tmp_path / "pending_reminder_periods.json"))
    external_id = "am-pm-question-test"
    try:
        first = handle_incoming_message("一點二十分提醒我喝水好嗎", external_id, "telegram")
        assert first["route"] == "routine"
        assert first["safety_level"] == "reminder_needs_period"
        assert "1點" in first["answer"]
        assert "上午" in first["answer"] and "下午" in first["answer"]

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            assert patient is None  # nothing created while the question is pending
        finally:
            db.close()

        second = handle_incoming_message("下午", external_id, "telegram")
        assert second["route"] == "routine"
        assert second["safety_level"] == "reminder_created"
        assert "13:20" in second["answer"]
        assert "喝水" in second["answer"]

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
            assert len(reminders) == 1
            assert reminders[0].time == "13:20"
            assert reminders[0].text == "喝水"
        finally:
            db.close()
    finally:
        _cleanup_patient(external_id)


def test_pending_reminder_completion_chains_into_period_question_when_still_ambiguous(tmp_path, monkeypatch):
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("PENDING_REMINDER_STATE_PATH", str(tmp_path / "pending_reminders.json"))
    monkeypatch.setenv("PENDING_REMINDER_PERIOD_STATE_PATH", str(tmp_path / "pending_reminder_periods.json"))
    external_id = "pending-then-period-test"
    try:
        first = handle_incoming_message("提醒我食藥", external_id, "telegram")
        assert first["safety_level"] == "reminder_needs_time"

        # The reply that completes the pending "what time?" question is
        # itself a bare, unmarked hour — must chain into the AM/PM question
        # rather than silently guessing.
        second = handle_incoming_message("9點", external_id, "telegram")
        assert second["safety_level"] == "reminder_needs_period"

        third = handle_incoming_message("上午", external_id, "telegram")
        assert third["safety_level"] == "reminder_created"
        assert "09:00" in third["answer"]
        assert "食藥" in third["answer"]
    finally:
        _cleanup_patient(external_id)


def test_pending_period_response_expires_after_its_ttl(tmp_path, monkeypatch):
    from src.user import pending_reminder_period

    state_path = tmp_path / "pending_reminder_periods.json"
    monkeypatch.setenv("PENDING_REMINDER_PERIOD_STATE_PATH", str(state_path))

    from datetime import datetime, timedelta, timezone
    stale_entry = {
        "user_id": "stale-period-user",
        "display_name": "",
        "sender_id": "stale-period-test",
        "hour": 5,
        "minute": 0,
        "text": "食藥",
        "days": chat_reminders.ALL_DAYS,
        "answer_language": "zh-Hant",
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
    }
    state_path.write_text(json.dumps({"stale-period-test": stale_entry}), encoding="utf-8")

    result = pending_reminder_period.consume_pending_period_response("stale-period-test", "下午")
    assert result is None


def test_pending_period_question_does_not_hijack_a_new_complete_request(tmp_path, monkeypatch):
    # Regression test: while an AM/PM question was pending for one reminder,
    # a completely separate, well-formed new request ("晚上九點提醒我喝水
    # 可以啊") was swallowed as if it were just answering "PM" for the
    # *earlier* reminder — silently discarding the new request's own time
    # and task and corrupting the earlier reminder's time instead.
    # Reproduced live in production.
    from src.user.message_router import handle_incoming_message

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "missing_registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("PENDING_REMINDER_PERIOD_STATE_PATH", str(tmp_path / "pending_reminder_periods.json"))
    monkeypatch.setenv("LAST_CREATED_REMINDER_STATE_PATH", str(tmp_path / "last_created_reminders.json"))
    external_id = "period-not-hijacked-test"
    try:
        first = handle_incoming_message("兩點十五分提醒我喝水", external_id, "telegram")
        assert first["safety_level"] == "reminder_needs_period"

        second = handle_incoming_message("晚上九點提醒我食藥可以啊", external_id, "telegram")
        assert second["safety_level"] == "reminder_created"
        assert "21:00" in second["answer"]
        assert "食藥" in second["answer"]

        db = SessionLocal()
        try:
            patient = db.query(Patient).filter(Patient.external_user_id == external_id).first()
            reminders = db.query(Reminder).filter(Reminder.patient_id == patient.id).all()
            # Only the second, complete reminder exists — the first never
            # got created since its AM/PM question was never answered.
            assert len(reminders) == 1
            assert reminders[0].time == "21:00"
            assert reminders[0].text == "食藥"
        finally:
            db.close()
    finally:
        _cleanup_patient(external_id)
