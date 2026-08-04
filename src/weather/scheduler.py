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

# Mirrors src/reminders/scheduler.py's own sys.path bootstrap — needed when
# this file is launched directly (`python src/weather/scheduler.py`) rather
# than imported as part of the src package.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.reminders.chat_reminders import LOCAL_TIMEZONE  # noqa: E402
from src.user.user_registry import iter_sender_records  # noqa: E402
from src.weather.alert_state import already_alerted, mark_alerted, reconcile_dedup_state  # noqa: E402
from src.weather.extreme_conditions import evaluate_extreme_conditions  # noqa: E402
from src.weather.hko_client import fetch_current_weather  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_SEND_ENDPOINT = "https://api.telegram.org/bot{token}/sendMessage"
# Extreme weather doesn't need per-minute freshness the way a reminder's due
# time does, and HKO's own readings only refresh roughly every 10 minutes
# anyway — polling more often than this would just hammer their public API
# for no benefit.
POLL_INTERVAL_MINUTES = 15


def _send_telegram_message(chat_id: str, text: str) -> bool:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token:
        logger.warning("Weather alert not sent: TELEGRAM_BOT_TOKEN not configured")
        return False
    if not chat_id:
        return False
    endpoint = TELEGRAM_SEND_ENDPOINT.format(token=bot_token)
    try:
        response = requests.post(endpoint, json={"chat_id": chat_id, "text": text}, timeout=8)
        return response.status_code < 400
    except requests.RequestException:
        logger.exception("Failed to deliver weather alert via Telegram")
        return False


def _registered_patient_chat_ids() -> list[str]:
    return [
        sender_id
        for sender_id, record in iter_sender_records()
        if str(record.get("role") or "").strip().lower() == "user"
    ]


def check_and_send_weather_alerts() -> None:
    """Poll HKO and push any newly-triggered extreme-weather alert to every registered patient."""
    snapshot = fetch_current_weather()
    if snapshot is None:
        logger.warning("Skipping weather alert check: HKO data unavailable")
        return

    alerts = evaluate_extreme_conditions(snapshot)
    reconcile_dedup_state({alert.kind for alert in alerts})

    today = datetime.now(LOCAL_TIMEZONE).strftime("%Y-%m-%d")
    new_alerts = [alert for alert in alerts if not already_alerted(alert, today)]
    if not new_alerts:
        return

    recipients = _registered_patient_chat_ids()
    for alert in new_alerts:
        # No per-user language preference is stored anywhere in the registry
        # (see src/user/session_preferences.py) — zh-Hant is the same
        # default the rest of the bot falls back to when there's no incoming
        # message to detect a language from, which is always true here.
        text = alert.message_for("zh-Hant")
        delivered_count = sum(1 for chat_id in recipients if _send_telegram_message(chat_id, text))
        logger.info(
            "weather alert broadcast: kind=%s dedup_key=%s recipients=%d delivered=%d",
            alert.kind, alert.dedup_key, len(recipients), delivered_count,
        )
        # Marked regardless of delivery success, same as the reminder
        # scheduler's own fire-and-forget delivery — a misconfigured bot
        # token gets fixed by an operator, not by retry-spamming Telegram
        # every 15 minutes with the same alert.
        mark_alerted(alert, today)


def start_weather_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        check_and_send_weather_alerts,
        trigger=IntervalTrigger(minutes=POLL_INTERVAL_MINUTES),
        id="weather_alert_checker",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Weather alert scheduler started (runs every %d minutes)", POLL_INTERVAL_MINUTES)
    return scheduler


def main() -> None:
    start_weather_scheduler()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
