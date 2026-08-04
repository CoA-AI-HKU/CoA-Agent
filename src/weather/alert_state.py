from __future__ import annotations

import json
import os
from pathlib import Path

from src.weather.extreme_conditions import WeatherAlert

# Global, not per-user — every registered patient sees the same regional HKO
# reading, so there's exactly one "have we already told everyone about this"
# state, unlike src/user/pending_reminder.py's per-sender_id state.
DEFAULT_STATE_PATH = Path(__file__).resolve().parents[2] / "data" / "weather_alert_state.json"


def already_alerted(alert: WeatherAlert, today: str) -> bool:
    """True if this exact alert was already sent and shouldn't repeat.

    Extreme heat dedupes per calendar day (today == a stored "YYYY-MM-DD"),
    so a temperature that stays above the threshold across many poll cycles
    only triggers one push a day. A rain warning dedupes on its code
    (e.g. "WRAINB") so it re-alerts on escalation (Amber -> Red -> Black)
    but not on every poll while the same signal stays up.
    """
    entry = _load().get(alert.kind)
    if not isinstance(entry, dict):
        return False
    if alert.kind == "extreme_heat":
        return entry.get("date") == today
    return entry.get("dedup_key") == alert.dedup_key


def mark_alerted(alert: WeatherAlert, today: str) -> None:
    state = _load()
    state[alert.kind] = (
        {"date": today} if alert.kind == "extreme_heat" else {"dedup_key": alert.dedup_key}
    )
    _save(state)


def reconcile_dedup_state(active_kinds: set[str]) -> None:
    """Drop dedup state for any non-heat alert kind that's no longer active.

    Without this, a rain warning that gets cancelled and later reissued at
    the exact same signal level (same code) would never alert a second time,
    since already_alerted() would still see the stale stored code. Heat is
    excluded — its dedup key is the date, which already rolls over on its
    own tomorrow with no help needed here.
    """
    state = _load()
    changed = False
    for kind in list(state.keys()):
        if kind != "extreme_heat" and kind not in active_kinds:
            state.pop(kind, None)
            changed = True
    if changed:
        _save(state)


def _path() -> Path:
    return Path(os.getenv("WEATHER_ALERT_STATE_PATH", str(DEFAULT_STATE_PATH)))


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(state: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)
