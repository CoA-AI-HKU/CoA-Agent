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
except ImportError:  # Support `cd reminder_backend && python scheduler.py`.
    from database import NotificationLog, Patient, Reminder, SessionLocal

# Chat-user lookup lives in the main app (src/), a sibling package to
# reminder_backend/, not necessarily on sys.path when this file is launched
# directly (e.g. `cd reminder_backend && python scheduler.py`).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.user.user_registry import get_user_record_by_user_id  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_SEND_ENDPOINT = "https://api.telegram.org/bot{token}/sendMessage"
ALL_DAYS = "mon,tue,wed,thu,fri,sat,sun"


def _send_telegram_message(chat_id: str, text: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token or not chat_id:
        return False
    endpoint = TELEGRAM_SEND_ENDPOINT.format(token=bot_token)
    try:
        response = requests.post(endpoint, json={"chat_id": chat_id, "text": text}, timeout=8)
        return response.status_code < 400
    except requests.RequestException:
        logger.exception("Failed to deliver reminder via Telegram")
        return False


def _deliver_reminder(patient: Patient, reminder: Reminder) -> bool:
    """Resolve the patient's chat identity and push the reminder over Telegram."""
    if not patient.external_user_id:
        logger.warning(
            "Reminder %s for patient %s has no linked chat account; cannot deliver",
            reminder.id, patient.id,
        )
        return False
    sender_id, _ = get_user_record_by_user_id(patient.external_user_id)
    if not sender_id:
        logger.warning(
            "No chat account found for external_user_id=%s (reminder %s)",
            patient.external_user_id, reminder.id,
        )
        return False
    return _send_telegram_message(sender_id, f"⏰ 提醒：{reminder.text}")


def check_and_send_reminders() -> None:
    """Called every minute to check for, and deliver, due reminders."""
    db = SessionLocal()
    try:
        now = datetime.now()
        current_day = now.strftime("%a").lower()
        current_time = now.strftime("%H:%M")

        reminders = db.query(Reminder).filter(
            Reminder.active == True,  # noqa: E712
            Reminder.time == current_time,
        ).all()

        for reminder in reminders:
            days_list = [d.strip() for d in reminder.days.split(",")]
            if current_day not in days_list and reminder.days != ALL_DAYS:
                continue
            if reminder.last_triggered and reminder.last_triggered.date() == now.date():
                continue

            patient = db.query(Patient).filter(Patient.id == reminder.patient_id).first()
            if not patient:
                continue

            delivered = _deliver_reminder(patient, reminder)
            logger.info(
                "%s REMINDER: Patient '%s' - '%s' at %s",
                "delivered" if delivered else "undelivered",
                patient.name, reminder.text, reminder.time,
            )

            db.add(NotificationLog(patient_id=reminder.patient_id, reminder_id=reminder.id))
            reminder.last_triggered = now
            db.commit()
    except Exception:
        logger.exception("Reminder scheduler error")
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
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
