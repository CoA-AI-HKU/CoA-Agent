from datetime import datetime

import pytest
from fastapi import HTTPException

from backend.api import web_account
from backend.services.firebase_auth import FirebaseUser
from src.health.blood_pressure import (
    ParsedBloodPressure,
    delete_blood_pressure_readings,
    list_blood_pressure_readings,
    parse_blood_pressure,
    record_blood_pressure,
    update_blood_pressure_reading,
    delete_blood_pressure_reading,
    get_blood_pressure_retention,
    set_blood_pressure_retention,
)
from src import orchestrator
from src.agents.types import AgentDecision


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("我今日血壓130 80", ParsedBloodPressure(130, 80)),
        ("血壓 125/78", ParsedBloodPressure(125, 78)),
        ("BP 118 over 72", ParsedBloodPressure(118, 72)),
        ("上壓 132，下壓 84", ParsedBloodPressure(132, 84)),
        ("血壓 128/79 脈搏 68 備註 晚飯後", ParsedBloodPressure(128, 79, 68, "晚飯後")),
    ],
)
def test_parse_blood_pressure_formats(message, expected):
    assert parse_blood_pressure(message) == expected


@pytest.mark.parametrize(
    "message",
    ["我今日血壓幾好", "血壓 130", "血壓 80 130", "血壓 999 80"],
)
def test_parse_blood_pressure_rejects_missing_or_invalid_values(message):
    assert parse_blood_pressure(message) is None


def test_valid_reading_gets_recording_confirmation(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "coordinate_message",
        lambda *_args: AgentDecision(route="blood_pressure", intent="blood_pressure_input", confidence=1.0),
    )
    monkeypatch.setattr(
        orchestrator,
        "record_blood_pressure",
        lambda *_args, **_kwargs: type("Reading", (), {"id": 1})(),
    )

    result = orchestrator.handle_dementia_user_message("血壓 138/82", user_id="patient-1", channel="web")

    assert result["answer"] == "收到你嘅血壓記錄，已經幫你記低咗。上壓 138、下壓 82。"
    assert result["route"] == "blood_pressure"
    assert result["safety_level"] == "blood_pressure_recorded"


def test_record_and_list_readings_are_isolated_by_patient():
    patient_a = "pytest-bp-patient-a"
    patient_b = "pytest-bp-patient-b"
    delete_blood_pressure_readings(patient_a)
    delete_blood_pressure_readings(patient_b)
    try:
        record_blood_pressure(
            patient_a,
            ParsedBloodPressure(130, 80),
            source_channel="web",
            measured_at=datetime(2026, 8, 17, 8, 30),
        )
        assert list_blood_pressure_readings(patient_a) == [
            {
                "id": list_blood_pressure_readings(patient_a)[0]["id"],
                "systolic": 130,
                "diastolic": 80,
                "pulse": None,
                "notes": "",
                "measured_at": "2026-08-17T08:30:00Z",
            }
        ]
        assert list_blood_pressure_readings(patient_b) == []
    finally:
        delete_blood_pressure_readings(patient_a)
        delete_blood_pressure_readings(patient_b)


def test_update_and_delete_require_matching_patient_owner():
    patient_a = "pytest-bp-edit-a"
    patient_b = "pytest-bp-edit-b"
    delete_blood_pressure_readings(patient_a)
    delete_blood_pressure_readings(patient_b)
    try:
        reading = record_blood_pressure(patient_a, ParsedBloodPressure(130, 80))
        assert update_blood_pressure_reading(patient_b, reading.id, systolic=125, diastolic=75) is None
        updated = update_blood_pressure_reading(
            patient_a, reading.id, systolic=125, diastolic=75, pulse=68, notes="晚飯後",
        )
        assert updated is not None
        assert (updated["systolic"], updated["diastolic"], updated["pulse"], updated["notes"]) == (125, 75, 68, "晚飯後")
        assert delete_blood_pressure_reading(patient_b, reading.id) is False
        assert delete_blood_pressure_reading(patient_a, reading.id) is True
    finally:
        delete_blood_pressure_readings(patient_a)
        delete_blood_pressure_readings(patient_b)


def test_retention_setting_is_isolated_by_patient():
    patient_a = "pytest-bp-retention-a"
    patient_b = "pytest-bp-retention-b"
    set_blood_pressure_retention(patient_a, 30)
    set_blood_pressure_retention(patient_b, 0)
    assert get_blood_pressure_retention(patient_a) == 30
    assert get_blood_pressure_retention(patient_b) == 0


def test_caregiver_endpoint_uses_link_guard(monkeypatch):
    user = FirebaseUser(uid="caregiver", phone_number=None, display_name=None, email=None)
    monkeypatch.setattr(web_account, "_require_permission", lambda *_args: None)

    def reject_unlinked(_user, _patient_user_id):
        raise HTTPException(status_code=404, detail="patient not found or not linked to this account")

    monkeypatch.setattr(web_account, "_resolve_linked_patient_sender_id", reject_unlinked)
    with pytest.raises(HTTPException) as exc:
        web_account.get_linked_patient_blood_pressure("other-patient", limit=30, user=user)
    assert exc.value.status_code == 404


def test_caregiver_endpoint_returns_only_requested_patients_readings(monkeypatch):
    user = FirebaseUser(uid="caregiver", phone_number=None, display_name=None, email=None)
    monkeypatch.setattr(web_account, "_require_permission", lambda *_args: None)
    monkeypatch.setattr(web_account, "_resolve_linked_patient_sender_id", lambda *_args: "patient-sender")
    monkeypatch.setattr(
        web_account,
        "list_blood_pressure_readings",
        lambda patient_user_id, limit: [{"patient": patient_user_id, "limit": limit}],
    )

    result = web_account.get_linked_patient_blood_pressure("patient-1", limit=12, user=user)
    assert result == {
        "patient_user_id": "patient-1",
        "readings": [{"patient": "patient-1", "limit": 12}],
    }
