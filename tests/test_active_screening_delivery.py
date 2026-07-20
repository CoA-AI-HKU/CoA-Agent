from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.metrics import load_events, log_event
from src.screening.screening_offer_policy import should_offer_screening
from src.screening.tokens import create_screening_token, get_screening_token
from src.user.message_router import handle_incoming_message
from src.user.user_registry import (
    create_pairing_code,
    load_user_registry,
    redeem_pairing_code,
    register_account,
    save_user_registry,
)


def _paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("SCREENING_OUTBOX_PATH", str(tmp_path / "outbox.jsonl"))
    monkeypatch.setenv("SCREENING_PUBLIC_URL", "https://ako-saka.github.io/CoA-Agent/screening/")


def test_one_mild_memory_concern_does_not_offer_screening(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    register_account("patient", "user", "Patient")

    result = handle_incoming_message("最近有些事情想不起來", "patient", "telegram")

    assert "你想現在開始嗎" not in result["answer"]
    assert not any(event.get("event_type") == "screening_offered" for event in load_events(days=7))


def test_repeated_memory_concerns_trigger_consent_offer(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    patient = register_account("patient", "user", "Patient")
    log_event(patient["user_id"], {"event_type": "memory_concern"})

    result = handle_incoming_message("最近又有些事情想不起來", "patient", "telegram")

    assert "你想現在開始嗎" in result["answer"]
    offered = [event for event in load_events(patient["user_id"], days=7) if event.get("event_type") == "screening_offered"]
    assert offered and offered[-1]["raw_text_saved"] is False
    assert "reason" in offered[-1]


def test_explicit_check_in_request_offers_screening(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    register_account("patient", "user", "Patient")

    result = handle_incoming_message("我想做記憶測試", "patient", "telegram")

    assert "你想現在開始嗎" in result["answer"]
    assert "診斷" in result["answer"]


def test_medication_and_safety_routes_take_priority() -> None:
    events = [{"event_type": "memory_concern"}, {"event_type": "memory_concern"}]
    medication = should_offer_screening("u", "user", {"route": "medical_boundary"}, events)
    safety = should_offer_screening("u", "user", {"route": "safety"}, events)

    assert medication["offer"] is False
    assert medication["reason"] == "medical boundary takes priority"
    assert safety["offer"] is False
    assert safety["urgency"] == "urgent_safety"


def test_yes_creates_token_and_no_logs_decline(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    patient = register_account("patient", "user", "Patient")
    log_event(patient["user_id"], {
        "event_type": "screening_offered", "created_by": "self", "raw_text_saved": False
    })

    accepted = handle_incoming_message("okay", "patient", "telegram")

    assert "?token=" in accepted["answer"]
    assert "腦退化症診斷" not in accepted["answer"]
    tokens = load_user_registry()["screening_tokens"]
    assert len(tokens) == 1
    assert next(iter(tokens.values()))["used"] is False

    log_event(patient["user_id"], {
        "event_type": "screening_offered", "created_by": "system", "raw_text_saved": False
    })
    declined = handle_incoming_message("遲啲", "patient", "telegram")
    assert "?token=" not in declined["answer"]
    assert any(event.get("event_type") == "screening_declined" for event in load_events(patient["user_id"], days=7))


def test_caregiver_request_requires_pairing_and_queues_patient_consent(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    patient = register_account("patient_sender", "user", "Patient")
    register_account("caregiver_sender", "caregiver", "Caregiver")

    unpaired = handle_incoming_message("\\send_screening", "caregiver_sender", "telegram")
    assert "先與使用者完成配對" in unpaired["answer"]

    redeem_pairing_code("caregiver_sender", create_pairing_code("patient_sender"))
    requested = handle_incoming_message("\\start_check", "caregiver_sender", "telegram")

    assert "對方同意後" in requested["answer"]
    assert requested["outbound_messages"][0]["recipient_sender_id"] == "patient_sender"
    assert "這不是診斷" in requested["outbound_messages"][0]["message"]
    events = load_events(patient["user_id"], days=7)
    assert any(event.get("event_type") == "screening_requested_by_caregiver" for event in events)


def test_screening_link_never_sent_in_group(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    patient = register_account("patient", "user", "Patient")
    log_event(patient["user_id"], {"event_type": "screening_offered", "created_by": "self"})

    result = handle_incoming_message("yes", "patient", "telegram_group")

    assert "私人聊天" in result["answer"]
    assert "?token=" not in result["answer"]
    assert "screening_tokens" not in load_user_registry()


def test_screening_token_expires(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    entry = create_screening_token("patient_1", "caregiver", "caregiver_1")
    registry = load_user_registry()
    registry["screening_tokens"][entry["token"]]["expires_at"] = (
        datetime.now(timezone.utc) - timedelta(seconds=1)
    ).isoformat()
    save_user_registry(registry)

    assert get_screening_token(entry["token"]) is None


def test_screening_events_are_structured_only(tmp_path, monkeypatch) -> None:
    _paths(tmp_path, monkeypatch)
    log_event("patient", {
        "event_type": "screening_offered",
        "reason": "repeated cognitive concern signals within 7 days",
        "raw_text_saved": False,
        "message": "raw user message must not be stored",
    })

    event = load_events("patient", days=7)[0]
    assert event["raw_text_saved"] is False
    assert "message" not in event
