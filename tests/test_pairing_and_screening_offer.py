from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.metrics import clear_user_events, load_events, log_event
from src.user.screening_offer import consent_reply, should_offer_screening
from src.user.user_registry import (
    create_pairing_code,
    create_dashboard_access_token,
    get_dashboard_patient_accounts,
    get_linked_user_id,
    redeem_pairing_code,
    register_account,
    revoke_caregivers_for_user,
    unlink_caregiver,
)
from src.dementia_rag_mcp_server import handle_incoming_message_tool
from src.user.message_router import handle_incoming_message


def test_patient_generated_code_links_registered_caregiver_once(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient = register_account("patient_sender", "user", "Patient")
    register_account("caregiver_sender", "caregiver", "Caregiver")
    code = create_pairing_code("patient_sender")

    assert redeem_pairing_code("caregiver_sender", code) == patient["user_id"]
    assert get_linked_user_id("caregiver_sender") == patient["user_id"]

    try:
        redeem_pairing_code("caregiver_sender", code)
    except ValueError as exc:
        assert "invalid or expired" in str(exc)
    else:
        raise AssertionError("pairing code was reusable")


def test_screening_offer_requires_separate_days_or_related_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    log_event("patient_1", {"timestamp": yesterday, "event_type": "memory_concern"})

    assert should_offer_screening("patient_1", {"event_type": "memory_concern"}) is True


def test_screening_consent_only_applies_to_unanswered_offer(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    log_event("patient_1", {"event_type": "screening_offer"})
    assert consent_reply("yes", "patient_1") is True
    log_event("patient_1", {"event_type": "screening_accepted"})
    assert consent_reply("yes", "patient_1") is None


def test_repair_unlink_revoke_and_scoped_history_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    first = register_account("patient_a", "user", "A")
    second = register_account("patient_b", "user", "B")
    register_account("caregiver", "caregiver", "C")
    redeem_pairing_code("caregiver", create_pairing_code("patient_a"))
    redeem_pairing_code("caregiver", create_pairing_code("patient_b"), replace_existing=True)
    assert get_linked_user_id("caregiver") == second["user_id"]
    assert revoke_caregivers_for_user("patient_b") == 1
    assert get_linked_user_id("caregiver") is None
    redeem_pairing_code("caregiver", create_pairing_code("patient_a"))
    assert unlink_caregiver("caregiver") == 1

    log_event(first["user_id"], {"event_type": "memory_concern"})
    log_event(second["user_id"], {"event_type": "interaction"})
    assert clear_user_events(first["user_id"]) == 1
    assert load_events(first["user_id"], days=7) == []
    assert len(load_events(second["user_id"], days=7)) == 1


def test_telegram_commands_accept_slash_backslash_and_bot_suffix(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))

    registered = handle_incoming_message("\\register patient Mei", "telegram_patient", "telegram")
    assert registered["intent"] == "account_registration"
    code_result = handle_incoming_message("/paircode@CoAHelperBot", "telegram_patient", "telegram")
    assert "expires in 15 minutes" in code_result["answer"]
    help_result = handle_incoming_message_tool("\\accountcommands", "telegram_patient", "telegram")
    assert help_result["intent"] == "account_help"
    assert "\\relink CODE" in help_result["answer"]


def test_incomplete_internal_command_does_not_fall_through_to_rag(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    result = handle_incoming_message("/register@CoAHelperBot", "new_user", "telegram")
    assert result["intent"] == "account_help"
    assert result["rag_called"] is False


def test_caregiver_dashboard_token_only_exposes_paired_patient(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    first = register_account("patient_1", "user", "First")
    register_account("patient_2", "user", "Second")
    register_account("caregiver", "caregiver", "Caregiver")
    redeem_pairing_code("caregiver", create_pairing_code("patient_1"))

    token = create_dashboard_access_token("caregiver")
    assert get_dashboard_patient_accounts(token) == [{"user_id": first["user_id"], "display_name": "First"}]
    assert get_dashboard_patient_accounts("wrong-token") == []
