from __future__ import annotations

import json
from unittest import mock

import pytest

from src.reminders import chat_reminders, scheduler as reminder_scheduler
from src.reminders.chat_reminders import create_reminder_for_user, parse_reminder_request
from src.reminders.database import Patient, Reminder, SessionLocal
from src.agents.coordinator_agent import coordinate_message
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


def test_get_or_create_patient_is_idempotent():
    external_id = "pytest-idempotent-user"
    try:
        r1 = create_reminder_for_user(external_id, "Name A", "食藥", "08:00")
        r2 = create_reminder_for_user(external_id, "Name A", "散步", "09:00")
        assert r1.patient_id == r2.patient_id
    finally:
        _cleanup_patient(external_id)


def test_reminder_request_creates_reminder_and_confirms(registered_patient):
    result = handle_dementia_user_message("12：28可以提醒我吃藥嗎", registered_patient)

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
    handle_dementia_user_message("08:15可以提醒我食藥嗎", registered_patient)

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
