from __future__ import annotations

import os
from typing import Any

from src.citations import finalize_user_facing_result
from src.agents.caregiver_manager_agent import handle_caregiver_manager_message
from src.agents.patient_user_manager_agent import handle_patient_user_message
from src.agents.user_facing_formatter import (
    answer_has_user_visible_leakage,
    answer_has_user_visible_source_text,
    format_user_facing_answer,
    guard_user_facing_answer,
)
from src.metrics import clear_user_events, detect_concern_signal, infer_event_type, log_event
from src.user.mode_info import format_mode_info
from src.user.pending_activity import consume_pending_activity_response, store_pending_activity
from src.user.user_registry import (
    create_pairing_code,
    create_dashboard_access_token,
    get_linked_user_id,
    get_registry_user_id,
    get_user_record,
    get_user_role,
    normalize_sender_id,
    redeem_pairing_code,
    register_account,
    revoke_caregivers_for_user,
    unlink_caregiver,
)
from src.user.screening_offer import consent_answer, consent_reply, offer_answer, should_offer_screening
from src.user.user_memory import build_memory_for_user_id, build_user_memory


def handle_incoming_message(message: str, sender_id: str, channel: str = "") -> dict[str, Any]:
    normalized_sender_id = normalize_sender_id(sender_id)
    role = get_user_role(normalized_sender_id)
    record = get_user_record(normalized_sender_id)
    account_result = _handle_account_command(message, normalized_sender_id, role)
    if account_result is not None:
        return _finalize_user_output(account_result, message)
    registry_user_id = get_registry_user_id(normalized_sender_id) if role == "user" else None
    session_user_id = registry_user_id or normalized_sender_id
    pending_activity_result = consume_pending_activity_response(normalized_sender_id, message)
    sender_memory = build_user_memory(normalized_sender_id)
    linked_user_id = get_linked_user_id(normalized_sender_id) if role == "caregiver" else None
    linked_user_memory = build_memory_for_user_id(linked_user_id) if linked_user_id else None

    event_user_id = linked_user_id or get_registry_user_id(normalized_sender_id) or normalized_sender_id
    consent = consent_reply(message, event_user_id) if role == "user" and pending_activity_result is None else None
    if pending_activity_result is not None:
        result = pending_activity_result
    elif consent is not None:
        result = _simple_result(consent_answer(message, consent), "screening_consent")
        result["screening_consent"] = consent
    elif _is_mode_info_command(message):
        result = _mode_info_result(normalized_sender_id, role, record)
    elif role == "caregiver":
        result = handle_caregiver_manager_message(message, normalized_sender_id, linked_user_id, channel)
        event_user_id = linked_user_id or normalized_sender_id
    else:
        user_id = registry_user_id or normalized_sender_id
        result = handle_patient_user_message(message, normalized_sender_id, user_id, channel)
        event_user_id = user_id

    if result.get("route") == "activity" and "三種水果" in str(result.get("answer") or ""):
        store_pending_activity(
            normalized_sender_id,
            str(event_user_id or session_user_id),
            "name_three_items",
            str(result.get("answer") or ""),
            "three comma-separated item names",
        )

    output = dict(result)
    output["role"] = role
    output["sender_id"] = normalized_sender_id
    output["channel"] = channel
    if role == "user":
        output["user_id"] = event_user_id
    if role == "caregiver":
        output["linked_user_id"] = linked_user_id
    output["memory"] = {
        "sender": sender_memory,
        "linked_user": linked_user_memory,
    }

    debug = dict(output.get("debug", {}))
    debug["message_router"] = {
        "sender_id": normalized_sender_id,
        "role": role,
        "channel": channel,
        "linked_user_id": linked_user_id or None,
        "memory_loaded": True,
    }

    try:
        event = {
            "user_id": event_user_id,
            "sender_id": normalized_sender_id,
            "channel": channel,
            "role": role,
            "intent": output.get("intent"),
            "route": output.get("route"),
            "safety_level": output.get("safety_level"),
            "medication_status": output.get("medication_status"),
            "rag_called": output.get("rag_called"),
        }
        concern_signal = detect_concern_signal(message, role, output)
        if concern_signal:
            event.update(concern_signal)
        elif output.get("intent") == "screening_consent":
            event["event_type"] = "screening_accepted" if output.get("screening_consent") else "screening_declined"
        else:
            event["event_type"] = infer_event_type(output)
        log_event(event_user_id, event)
        if role == "user" and should_offer_screening(event_user_id, concern_signal):
            output["answer"] = f'{str(output.get("answer") or "").rstrip()}\n\n{offer_answer(message)}'
            log_event(event_user_id, {
                "sender_id": normalized_sender_id,
                "channel": channel,
                "role": role,
                "intent": "cognitive_concern_screening",
                "route": "screening",
                "event_type": "screening_offer",
            })
    except Exception as exc:  # pragma: no cover - defensive; user response must continue.
        debug["metrics_warning"] = str(exc)

    output["debug"] = debug
    output = _finalize_user_output(output, message)
    return output


def _handle_account_command(message: str, sender_id: str, role: str) -> dict[str, Any] | None:
    text = str(message or "").strip()
    parts = text.split(maxsplit=2)
    command = _normalize_command(parts[0]) if parts else ""
    try:
        if command == "\\register":
            if len(parts) < 2:
                return _simple_result("Usage: \\register patient NAME or \\register caregiver NAME", "account_help")
            requested = parts[1].lower()
            role_name = "user" if requested in {"patient", "user"} else requested
            display_name = parts[2] if len(parts) == 3 else ""
            record = register_account(sender_id, role_name, display_name)
            if role_name == "user":
                return _simple_result("Registration complete. You are registered as the patient account. Use \\paircode when you want to invite a caregiver.", "account_registration")
            return _simple_result("Registration complete. You are registered as a caregiver. Ask the patient for a pairing code, then send \\link CODE.", "account_registration")
        if command == "\\paircode":
            code = create_pairing_code(sender_id)
            return _simple_result(f"Your one-time caregiver pairing code is {code}. It expires in 15 minutes. Share it only with the caregiver you choose.", "account_pairing")
        if command == "\\link":
            if len(parts) < 2:
                return _simple_result("Usage: \\link CODE", "account_help")
            redeem_pairing_code(sender_id, parts[1])
            return _simple_result("The caregiver and patient accounts are now linked.", "account_pairing")
        if command == "\\relink":
            if len(parts) < 2:
                return _simple_result("Usage: \\relink CODE", "account_help")
            redeem_pairing_code(sender_id, parts[1], replace_existing=True)
            return _simple_result("Your previous patient link was replaced with the new pairing.", "account_pairing")
        if command == "\\unlink":
            if role == "caregiver":
                target = parts[1] if len(parts) >= 2 else None
                removed = unlink_caregiver(sender_id, target)
                return _simple_result(f"Unlinked {removed} patient account(s).", "account_pairing")
            if role == "user":
                removed = revoke_caregivers_for_user(sender_id)
                return _simple_result(f"Revoked access for {removed} caregiver account(s).", "account_pairing")
            raise ValueError("register before unlinking an account")
        if command == "\\clearhistory":
            if role != "user":
                raise ValueError("only the patient account can clear its retained history")
            if len(parts) < 2 or parts[1].lower() != "confirm":
                return _simple_result("This deletes all structured chat-derived history used for your analysis. Send \\clearhistory confirm to continue.", "account_history")
            user_id = get_registry_user_id(sender_id) or sender_id
            removed = clear_user_events(user_id)
            return _simple_result(f"Your retained chat-derived history has been cleared ({removed} event(s) deleted).", "account_history")
        if command == "\\accountcommands":
            return _simple_result(
                "Account commands:\n\\register patient NAME\n\\register caregiver NAME\n\\paircode\n\\link CODE\n\\relink CODE\n\\unlink [PATIENT_ID]\n\\dashboard\n\\clearhistory confirm",
                "account_help",
            )
        if command == "\\dashboard":
            token = create_dashboard_access_token(sender_id)
            base_url = os.getenv("DASHBOARD_PUBLIC_URL", "http://localhost:8080/dashboard.html")
            separator = "&" if "?" in base_url else "?"
            return _simple_result(
                f"Open your caregiver dashboard here: {base_url}{separator}access_token={token}\n\nThis private link expires in 30 minutes.",
                "account_dashboard",
            )
    except ValueError as exc:
        return _simple_result(str(exc), "account_pairing")
    return None


def _normalize_command(token: str) -> str:
    """Use backslash commands while accepting slash-form transport compatibility."""
    value = str(token or "").strip().lower()
    if value.startswith("/"):
        value = f"\\{value[1:]}"
    if value.startswith("\\") and "@" in value:
        value = value.split("@", 1)[0]
    return value


def _simple_result(answer: str, intent: str) -> dict[str, Any]:
    return {
        "answer": answer,
        "route": "account" if intent.startswith("account_") else "screening",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": intent,
        "safety_level": "normal",
        "debug": {"agent": "message_router"},
    }


def _is_mode_info_command(message: str) -> bool:
    parts = str(message or "").strip().split(maxsplit=1)
    return bool(parts) and _normalize_command(parts[0]) == "\\whichroleami"


def _mode_info_result(sender_id: str, role: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": format_mode_info(sender_id, role, record),
        "role": role,
        "route": "mode_info",
        "manager": "message_router",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": "mode_info",
        "safety_level": "normal",
        "debug": {"agent": "message_router", "mode_info": True},
    }


def _finalize_user_output(result: dict[str, Any], message: str) -> dict[str, Any]:
    output = dict(result)
    if answer_has_user_visible_source_text(str(output.get("answer") or "")):
        output = format_user_facing_answer(output, show_sources=False)
    output = guard_user_facing_answer(output, message)
    answer = str(output.get("answer") or "")
    if answer_has_user_visible_leakage(answer):
        debug = dict(output.get("debug", {}))
        debug["router_final_guard_retry"] = True
        output["debug"] = debug
        output = guard_user_facing_answer(output, message)
    # This is deliberately unconditional and last: screening text and any
    # source-appending logic above have already completed.
    return finalize_user_facing_result(output)
