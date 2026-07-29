from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

try:
    from .database import NotificationLog, Patient, Reminder, SessionLocal
    from .chat_reminders import ALL_DAYS, LOCAL_TIMEZONE, ONE_TIME
    from .trace_logging import check_reminder_db_write_access, log_reminder_checkpoint
except ImportError:  # Support `cd src/reminders && python scheduler.py`.
    from database import NotificationLog, Patient, Reminder, SessionLocal
    from chat_reminders import ALL_DAYS, LOCAL_TIMEZONE, ONE_TIME
    from trace_logging import check_reminder_db_write_access, log_reminder_checkpoint

# Chat-user lookup lives in src.user, which requires the repo root (two
# levels up from src/reminders/) on sys.path — not automatically the case
# when this file is launched directly as a standalone script rather than
# imported as part of the src package.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.user.user_registry import get_user_record_by_user_id  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_SEND_ENDPOINT = "https://api.telegram.org/bot{token}/sendMessage"


def _send_telegram_message(chat_id: str, text: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        log_reminder_checkpoint("reminder_telegram_send_failed", reason="missing_bot_token")
        return False
    if not chat_id:
        log_reminder_checkpoint("reminder_telegram_send_failed", reason="missing_chat_id")
        return False
    endpoint = TELEGRAM_SEND_ENDPOINT.format(token=bot_token)
    try:
        response = requests.post(endpoint, json={"chat_id": chat_id, "text": text}, timeout=8)
        ok = response.status_code < 400
        if not ok:
            # Telegram error bodies are small structured JSON like
            # {"ok":false,"description":"..."} describing Telegram's own
            # rejection reason (bad token, bot blocked by user, chat not
            # found, etc.) — safe to log, contains no reminder/message text.
            log_reminder_checkpoint(
                "reminder_telegram_send_failed",
                reason="telegram_api_rejected",
                status_code=response.status_code,
                response_body=response.text[:300],
            )
        return ok
    except requests.RequestException as exc:
        logger.exception("Failed to deliver reminder via Telegram")
        log_reminder_checkpoint(
            "reminder_telegram_send_failed", reason="request_exception", error=str(exc)[:300],
        )
        return False


def _deliver_reminder(patient: Patient, reminder: Reminder) -> bool:
    """Resolve the patient's chat identity and push the reminder over Telegram.

    Prefers patient.chat_sender_id — captured directly at reminder-creation
    time, present regardless of whether the account ever completed
    \\register. Falls back to the older registry reverse-lookup only for
    reminders created before this column existed, so those keep working
    without needing a data migration; that path only ever worked for
    registered accounts anyway.
    """
    sender_id = patient.chat_sender_id
    if not sender_id and patient.external_user_id:
        sender_id, _ = get_user_record_by_user_id(patient.external_user_id)
        if sender_id:
            log_reminder_checkpoint(
                "reminder_delivery_used_legacy_lookup", reminder_id=reminder.id,
                user_id=patient.external_user_id,
            )
    if not sender_id:
        logger.warning(
            "Reminder %s for patient %s has no resolvable chat identity; cannot deliver",
            reminder.id, patient.id,
        )
        log_reminder_checkpoint(
            "reminder_delivery_blocked", reminder_id=reminder.id,
            user_id=patient.external_user_id, reason="no_resolvable_chat_identity",
        )
        return False
    return _send_telegram_message(sender_id, f"⏰ 提醒：{reminder.text}")


def check_and_send_reminders() -> None:
    """Called every minute to check for, and deliver, due reminders."""
    db = SessionLocal()
    try:
        # Must match the timezone parse_reminder_request() used to compute
        # reminder.time — the server's own clock is not guaranteed to be in
        # the user's timezone (the droplet runs in UTC), so naive
        # datetime.now() would compare against the wrong wall-clock time.
        now = datetime.now(LOCAL_TIMEZONE)
        current_day = now.strftime("%a").lower()
        current_time = now.strftime("%H:%M")

        reminders = db.query(Reminder).filter(
            Reminder.active == True,  # noqa: E712
            Reminder.time == current_time,
        ).all()

        for reminder in reminders:
            if reminder.days == ONE_TIME:
                day_matches = True
            else:
                days_list = [d.strip() for d in reminder.days.split(",")]
                day_matches = current_day in days_list or reminder.days == ALL_DAYS
            if not day_matches:
                continue
            if reminder.last_triggered and reminder.last_triggered.date() == now.date():
                continue

            patient = db.query(Patient).filter(Patient.id == reminder.patient_id).first()
            if not patient:
                continue

            log_reminder_checkpoint(
                "reminder_triggered",
                reminder_id=reminder.id,
                user_id=patient.external_user_id,
                channel="telegram",  # scheduler delivery is Telegram-only today
                normalized_due_time=reminder.time,
                current_time=current_time,
                current_day=current_day,
                days=reminder.days,
            )
            delivered = _deliver_reminder(patient, reminder)
            log_reminder_checkpoint(
                "reminder_delivery_result",
                reminder_id=reminder.id,
                user_id=patient.external_user_id,
                channel="telegram",
                delivered=delivered,
            )
            logger.info(
                "%s REMINDER: Patient '%s' - '%s' at %s",
                "delivered" if delivered else "undelivered",
                patient.name, reminder.text, reminder.time,
            )

            db.add(NotificationLog(patient_id=reminder.patient_id, reminder_id=reminder.id))
            reminder.last_triggered = now
            if reminder.days == ONE_TIME:
                # Fired once — deactivate so it doesn't keep matching "any
                # day" indefinitely (ONE_TIME isn't a real weekday to filter
                # on, so leaving it active would fire again tomorrow).
                reminder.active = False
            db.commit()
    except Exception:
        logger.exception("Reminder scheduler error")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    write_access = check_reminder_db_write_access()
    if not write_access["writable"]:
        logger.error(
            "Reminder DB path is not writable by this service user — reminders will "
            "silently fail to persist or update: %s",
            write_access["path_checked"],
        )
    log_reminder_checkpoint(
        "reminder_scheduler_startup",
        telegram_bot_token_configured=bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
        **write_access,
    )
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger=IntervalTrigger(minutes=1),
        id="reminder_checker",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Reminder scheduler started (runs every minute)")
    return scheduler


def main() -> None:
    scheduler = start_scheduler()
    # BackgroundScheduler runs its job on a daemon thread, which does not
    # keep the process alive on its own — without this loop the interpreter
    # reaches end-of-script right after start() and the process (and the
    # scheduler with it) exits immediately.
    try:
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    main()
