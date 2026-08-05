from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from src.safety.medication_guard import detect_red_flags
from src.user.conversation_flags_database import ConversationFlag, SessionLocal
from src.user.monitoring_preferences import get_monitoring_preferences

logger = logging.getLogger(__name__)

RETENTION_DAYS = 14

_DECLINE_CLASSIFIER_PROMPT = (
    "你係一個小心、保守嘅分類助手。淨係睇下面呢句使用者訊息（同少量對話背景），"
    "判斷入面係咪有*明顯、具體*嘅認知變差跡象，例如：喺呢個對話入面重複問返同一個已經答咗嘅問題、"
    "對時間/地點/身邊人明顯感到混亂、講嘢突然語無倫次或前後矛盾、對走失或唔記得重要嘢表達出不尋常嘅驚慌。"
    "唔好淨係因為使用者提到記性唔好、腦退化症或者一般日常擔心就當係跡象——呢啲好常見，唔算特別訊號。"
    "如果唔確定，答「否」。\n\n"
    "背景（可能為空）：\n{context}\n\n"
    "使用者訊息：{message}\n\n"
    "請只用呢個格式回覆，唔好講其他嘢：\n"
    "FLAG: 是 或 否\n"
    "REASON: 一句簡短原因（用中文，如果 FLAG 係否可以留空）"
)


def _purge_old(db) -> None:
    cutoff = datetime.utcnow() - timedelta(days=RETENTION_DAYS)
    db.query(ConversationFlag).filter(ConversationFlag.created_at < cutoff).delete(synchronize_session=False)


def _record(sender_id: str, flag_type: str, reason: str) -> None:
    db = SessionLocal()
    try:
        _purge_old(db)
        db.add(ConversationFlag(sender_id=sender_id, flag_type=flag_type, reason=reason.strip()[:280]))
        db.commit()
    finally:
        db.close()


def _classify_decline_signs(message: str, context: str, answer_callable) -> str | None:
    prompt = _DECLINE_CLASSIFIER_PROMPT.format(context=context or "（無）", message=message)
    try:
        raw = answer_callable(prompt).strip()
    except Exception:
        logger.exception("conversation_flags decline classifier call failed")
        return None
    flagged = False
    reason = ""
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("FLAG:"):
            flagged = "是" in line or "yes" in line.lower()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip() if ":" in line else ""
    if flagged and reason:
        return reason
    return None


def maybe_flag_turn(
    sender_id: str,
    message: str,
    *,
    context: str = "",
    answer_callable=None,
) -> None:
    """Look at one user message (plus optional short prior-turn context) and
    record a flag if — and only if — something worth a caregiver's
    attention shows up. Never raises: called from the main chat path, and a
    classification failure must never break an actual reply.

    answer_callable is the same LLM call used to generate the chat reply
    (see src/agents/general_chat_agent.py) — passed in rather than built
    here so this never needs its own opinion about which provider/config to
    use, and so it can be skipped entirely (None) when no LLM is configured.

    Each flag category is independently gated by this sender's own
    monitoring preferences (see src/user/monitoring_preferences.py) — a
    caregiver and patient may decide together to turn either one off, e.g.
    a caregiver who finds the cognitive-decline classifier too noisy for
    their situation without wanting to also lose safety alerts.
    """
    sender_id = str(sender_id or "").strip()
    message = str(message or "").strip()
    if not sender_id or not message:
        return

    try:
        preferences = get_monitoring_preferences(sender_id)
        red_flags = detect_red_flags(message) if preferences["safety"] else []
        if red_flags:
            _record(sender_id, "safety", f"提及：{'、'.join(red_flags[:3])}")
            return  # a safety flag already covers this turn; skip the decline check

        if preferences["cognitive_decline"] and answer_callable is not None:
            reason = _classify_decline_signs(message, context, answer_callable)
            if reason:
                _record(sender_id, "cognitive_decline", reason)
    except Exception:
        logger.exception("maybe_flag_turn failed for sender_id=%s", sender_id)


def get_recent_flags(sender_id: str, days: int = RETENTION_DAYS) -> list[dict[str, Any]]:
    sender_id = str(sender_id or "").strip()
    db = SessionLocal()
    try:
        _purge_old(db)
        db.commit()
        if not sender_id:
            return []
        cutoff = datetime.utcnow() - timedelta(days=days)
        rows = (
            db.query(ConversationFlag)
            .filter(ConversationFlag.sender_id == sender_id, ConversationFlag.created_at >= cutoff)
            .order_by(ConversationFlag.created_at.desc())
            .all()
        )
        return [
            {
                "flag_type": row.flag_type,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in rows
        ]
    finally:
        db.close()


def delete_flags_for_sender(sender_id: str) -> None:
    """Remove every flag for a sender — used when an account is deleted
    outright (see backend/api/web_account.py's delete-patient-account
    endpoint), not part of the normal 14-day retention flow.
    """
    sender_id = str(sender_id or "").strip()
    if not sender_id:
        return
    db = SessionLocal()
    try:
        db.query(ConversationFlag).filter(ConversationFlag.sender_id == sender_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
