from __future__ import annotations

import os
import logging
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
from src.screening.outbox import queue_screening_message
from src.user.mode_info import format_mode_info
from src.user.onboarding_state import begin_onboarding, consume_onboarding_reply
from src.user.pending_activity import consume_pending_activity_response, store_pending_activity
from src.user.security import is_admin_sender
from src.user.session_preferences import set_avoid_patient_framing
from src.user.user_registry import (
    create_pairing_code,
    create_dashboard_access_token,
    get_linked_user_id,
    get_linked_user_ids,
    get_registry_user_id,
    get_user_record,
    get_user_role,
    get_user_record_by_user_id,
    normalize_sender_id,
    redeem_pairing_code,
    register_account,
    revoke_caregivers_for_user,
    unlink_caregiver,
)
from src.user.screening_offer import consent_answer, consent_reply, latest_offer_context, offer_answer, screening_offer_decision
from src.user.user_memory import build_memory_for_user_id, build_user_memory


logger = logging.getLogger(__name__)


def handle_incoming_message(
    message: str,
    sender_id: str,
    channel: str = "",
    telegram_username: str = "",
) -> dict[str, Any]:
    logger.info(
        "message router started",
        extra={"event": "message_router_started", "sender_id": sender_id, "channel": channel},
    )
    normalized_sender_id = normalize_sender_id(sender_id)
    role = get_user_role(normalized_sender_id)
    record = get_user_record(normalized_sender_id)
    admin = is_admin_sender(normalized_sender_id, telegram_username)
    account_result = _handle_account_command(message, normalized_sender_id, role, admin)
    if account_result is not None:
        return _finalize_user_output(account_result, message)
    caregiver_screening = _handle_caregiver_screening_command(message, normalized_sender_id, role, channel)
    if caregiver_screening is not None:
        return _finalize_user_output(caregiver_screening, message)
    onboarding_result = _handle_onboarding_reply(message, normalized_sender_id)
    if onboarding_result is not None:
        return _finalize_user_output(onboarding_result, message)
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
    elif consent is not None and _is_group_channel(channel):
        result = _screening_privacy_result()
        consent = None
    elif consent is not None:
        context = latest_offer_context(event_user_id)
        result = _simple_result(
            consent_answer(
                message,
                consent,
                event_user_id,
                created_by=str(context.get("created_by") or "self"),
                caregiver_id=str(context.get("caregiver_id") or ""),
            ),
            "screening_consent",
        )
        result["screening_consent"] = consent
        result["screening_version"] = "cognitive_concern_screening_v1"
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
    if result.get("intent") == "role_correction":
        set_avoid_patient_framing(normalized_sender_id)

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
            event["screening_version"] = "cognitive_concern_screening_v1"
            event["raw_text_saved"] = False
        else:
            event["event_type"] = infer_event_type(output)
        log_event(event_user_id, event)
        policy_signal = dict(concern_signal or {})
        policy_signal["route"] = str(output.get("route") or "")
        policy_signal["explicit_request"] = output.get("intent") == "cognitive_concern_screening"
        decision = screening_offer_decision(event_user_id, role, policy_signal)
        if role == "caregiver" and decision["offer"] and linked_user_id and not _is_group_channel(channel):
            patient_sender_id, _ = get_user_record_by_user_id(linked_user_id)
            if patient_sender_id:
                queued = queue_screening_message(
                    patient_sender_id,
                    linked_user_id,
                    offer_answer(message, caregiver_requested=True),
                )
                output.setdefault("outbound_messages", []).append(queued)
                output["answer"] = (
                    f'{str(output.get("answer") or "").rstrip()}\n\n'
                    "我會先向使用者發送一段簡短說明，並在對方同意後提供小檢查連結。"
                )
                log_event(linked_user_id, {
                    "event_type": "screening_offered",
                    "caregiver_id": normalized_sender_id,
                    "created_by": "caregiver",
                    "reason": decision["reason"],
                    "urgency": decision["urgency"],
                    "screening_version": "cognitive_concern_screening_v1",
                    "raw_text_saved": False,
                })
        elif role != "caregiver" and decision["offer"]:
            if _is_group_channel(channel):
                output["answer"] = (
                    f'{str(output.get("answer") or "").rstrip()}\n\n'
                    "為了保護私隱，小檢查連結只會在私人聊天中發送。請先私訊我。"
                )
            else:
                output["answer"] = f'{str(output.get("answer") or "").rstrip()}\n\n{offer_answer(message)}'
            log_event(event_user_id, {
                "sender_id": normalized_sender_id,
                "channel": channel,
                "role": role,
                "intent": "cognitive_concern_screening",
                "route": "screening",
                "event_type": "screening_offered",
                "reason": decision["reason"],
                "urgency": decision["urgency"],
                "created_by": "self" if decision["reason"].startswith("user explicitly") else "system",
                "screening_version": "cognitive_concern_screening_v1",
                "raw_text_saved": False,
            })
    except Exception as exc:  # pragma: no cover - defensive; user response must continue.
        debug["metrics_warning"] = str(exc)

    output["debug"] = debug
    output = _finalize_user_output(output, message)
    return output


def _handle_account_command(message: str, sender_id: str, role: str, admin: bool = False) -> dict[str, Any] | None:
    text = str(message or "").strip()
    parts = text.split(maxsplit=2)
    command = _normalize_command(parts[0]) if parts else ""
    try:
        if command == "\\initiate":
            if not admin:
                return _security_refusal()
            begin_onboarding(sender_id)
            return _onboarding_result(sender_id, "unknown", {})
        if command == "\\start":
            if role == "unknown":
                begin_onboarding(sender_id)
            return _onboarding_result(sender_id, role, get_user_record(sender_id))
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


def _handle_caregiver_screening_command(
    message: str, sender_id: str, role: str, channel: str
) -> dict[str, Any] | None:
    parts = str(message or "").strip().split(maxsplit=1)
    command = _normalize_command(parts[0]) if parts else ""
    if command not in {"\\send_screening", "\\start_check"}:
        return None
    if role != "caregiver":
        return _simple_result("只有已登記並完成配對的照顧者可以提出小檢查邀請。", "screening_caregiver_request")
    if _is_group_channel(channel):
        return _screening_privacy_result()
    linked_ids = get_linked_user_ids(sender_id)
    if not linked_ids:
        return _simple_result("請先與使用者完成配對，才可以提出小檢查邀請。", "screening_caregiver_request")
    requested_id = parts[1].strip() if len(parts) == 2 else ""
    if len(linked_ids) > 1 and not requested_id:
        choices = "\n".join(f"\\send_screening {user_id}" for user_id in linked_ids)
        return _simple_result(f"你已連結多位使用者。請選擇一位：\n{choices}", "screening_caregiver_request")
    user_id = requested_id or linked_ids[0]
    if user_id not in linked_ids:
        return _simple_result("你只能為已配對的使用者提出小檢查邀請。", "screening_caregiver_request")
    patient_sender_id, _ = get_user_record_by_user_id(user_id)
    if not patient_sender_id:
        return _simple_result("暫時找不到已配對使用者的私人聊天帳戶。", "screening_caregiver_request")
    patient_message = offer_answer(message, caregiver_requested=True)
    queued = queue_screening_message(patient_sender_id, user_id, patient_message)
    common = {
        "user_id": user_id,
        "caregiver_id": sender_id,
        "created_by": "caregiver",
        "screening_version": "cognitive_concern_screening_v1",
        "raw_text_saved": False,
    }
    log_event(user_id, {**common, "event_type": "screening_requested_by_caregiver"})
    log_event(user_id, {
        **common,
        "event_type": "screening_offered",
        "reason": "caregiver requested non-diagnostic check-in",
        "urgency": "suggested",
    })
    result = _simple_result(
        "我會先向使用者發送一段簡短說明，並在對方同意後提供小檢查連結。",
        "screening_caregiver_request",
    )
    result["outbound_messages"] = [queued]
    return result


def _is_group_channel(channel: str) -> bool:
    return str(channel or "").strip().lower() in {
        "group", "supergroup", "telegram_group", "telegram_supergroup"
    }


def _screening_privacy_result() -> dict[str, Any]:
    result = _simple_result(
        "為了保護私隱，小檢查連結只會在私人聊天中發送。請先私訊我。",
        "screening_privacy",
    )
    result["route"] = "screening_privacy"
    return result


def _onboarding_result(sender_id: str, role: str, record: dict[str, Any]) -> dict[str, Any]:
    display_name = str(record.get("display_name") or "").strip()
    if role == "caregiver":
        greeting = f"你好，{display_name}。" if display_name else "你好。"
        answer = (
            f"{greeting}我是小安，一個提供日常照護資訊和簡單支援的聊天助手。"
            "我不會作出診斷，也不能代替醫護人員或緊急服務。\n\n"
            "你已登記為照顧者。你可以輸入 \\paircode 相關指令與使用者配對，"
            "或輸入 \\whichroleami 查看目前身份。"
        )
    elif role == "user":
        greeting = f"你好，{display_name}。" if display_name else "你好。"
        answer = (
            f"{greeting}我是小安。我可以用簡單、清楚的方式提供日常支援，"
            "也可以陪你做輕鬆的小活動。你可以按自己的步調慢慢說。\n\n"
            "我不會作出診斷，也不能代替醫護人員或緊急服務。"
            "你已完成使用者登記；輸入 \\whichroleami 可以查看目前身份。"
        )
    else:
        answer = (
            "你好，我是小安。我可以提供簡單的記憶與日常生活支援，也可以陪你做一些輕鬆的小活動。\n"
            "我不會作出診斷，也不能代替醫生或緊急服務。\n"
            "在開始之前，請問你希望以哪個身份使用？\n"
            "使用者\n"
            "照顧者\n"
            "請回覆「使用者」或「照顧者」。"
        )
    return {
        "answer": answer,
        "route": "onboarding",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": "onboarding",
        "safety_level": "normal",
        "sender_id": sender_id,
        "debug": {"agent": "message_router", "onboarding": True},
    }


def _handle_onboarding_reply(message: str, sender_id: str) -> dict[str, Any] | None:
    reply = consume_onboarding_reply(sender_id, message)
    if reply is None:
        return None
    if reply["action"] == "ask_name":
        return _onboarding_message("謝謝。請問我可以怎樣稱呼你？", "onboarding_name")
    record = register_account(sender_id, reply["role"], reply["display_name"])
    role_label = "使用者" if record["role"] == "user" else "照顧者"
    return _onboarding_message(f"謝謝，登記完成。你目前以{role_label}身份使用。", "account_registration")


def _onboarding_message(answer: str, intent: str) -> dict[str, Any]:
    return {
        "answer": answer,
        "route": "onboarding",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": intent,
        "safety_level": "normal",
        "debug": {"agent": "message_router", "onboarding": True},
    }


def _security_refusal() -> dict[str, Any]:
    return {
        "answer": "為了保護帳戶和資料安全，我不能執行更改系統規則、刪除資料或繞過安全限制的要求。",
        "route": "security_boundary",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": "security_sensitive",
        "safety_level": "security_boundary",
        "debug": {"agent": "message_router", "security_blocked": True},
    }


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
    parts = str(message or "").strip().split()
    if not parts:
        return False
    command = _normalize_command(parts[0])
    if command == "\\whichroleami":
        return True
    # Recover the common accidental split: "\\whichroleam i".
    return len(parts) == 2 and _normalize_command(f"{parts[0]}{parts[1]}") == "\\whichroleami"


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


def _finalize_user_output(
    result: dict[str, Any],
    message: str,
) -> dict[str, Any]:
    output = dict(result)

    logger.warning(
        "ROUTER_FINALIZE_START "
        "answer_length=%d found=%r rag_called=%r route=%r",
        len(str(output.get("answer") or "")),
        output.get("found"),
        output.get("rag_called"),
        output.get("route"),
    )

    if answer_has_user_visible_source_text(
        str(output.get("answer") or "")
    ):
        logger.warning("ROUTER_SOURCE_FORMATTING_TRIGGERED")
        output = format_user_facing_answer(
            output,
            show_sources=False,
        )

    before_guard = str(output.get("answer") or "")

    output = guard_user_facing_answer(output, message)

    after_guard = str(output.get("answer") or "")

    logger.warning(
        "ROUTER_GUARD_RESULT "
        "before_length=%d after_length=%d changed=%s "
        "before_preview=%r after_preview=%r",
        len(before_guard),
        len(after_guard),
        before_guard != after_guard,
        before_guard[:200],
        after_guard[:200],
    )

    answer = str(output.get("answer") or "")

    if answer_has_user_visible_leakage(answer):
        logger.warning("ROUTER_LEAKAGE_RETRY_TRIGGERED")

        debug = dict(output.get("debug", {}))
        debug["router_final_guard_retry"] = True
        output["debug"] = debug

        retry_before = str(output.get("answer") or "")
        output = guard_user_facing_answer(output, message)
        retry_after = str(output.get("answer") or "")

        logger.warning(
            "ROUTER_GUARD_RETRY_RESULT "
            "before_length=%d after_length=%d changed=%s",
            len(retry_before),
            len(retry_after),
            retry_before != retry_after,
        )

    finalized = finalize_user_facing_result(output)

    logger.warning(
        "ROUTER_FINALIZE_COMPLETED answer_length=%d",
        len(str(finalized.get("answer") or "")),
    )

    return finalized