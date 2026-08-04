from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

# Hong Kong Observatory's free, no-key-required Open Data API — see
# https://data.weather.gov.hk. "rhrread" is the latest 10-minute mean
# readings (temperature, humidity, rainfall per station); "warnsum" is the
# set of currently *active* warnings, keyed by warning type ("WRAIN" for the
# Rainstorm Warning Signal, "WFIRE" for fire danger, etc.) — an empty object
# means no warnings are in force, not an error.
RHRREAD_ENDPOINT = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=tc"
WARNSUM_ENDPOINT = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=tc"
REQUEST_TIMEOUT_SECONDS = 8


@dataclass(frozen=True)
class WeatherWarning:
    warning_type: str  # e.g. "WRAIN" — the warnsum object's own key, stable across languages
    code: str  # e.g. "WRAINB" — the specific signal/level, used to detect escalation
    name: str  # human-readable name in whatever `lang` the request used
    issue_time: str


@dataclass(frozen=True)
class WeatherSnapshot:
    fetched_at: datetime
    temperatures: dict[str, float] = field(default_factory=dict)  # station name -> Celsius
    warnings: dict[str, WeatherWarning] = field(default_factory=dict)  # warning_type -> warning

    def max_temperature(self) -> float | None:
        return max(self.temperatures.values()) if self.temperatures else None


def fetch_current_weather() -> WeatherSnapshot | None:
    """Fetch the latest HKO readings and active warnings.

    Returns None on any failure (network error, timeout, malformed response)
    so callers — both the on-demand weather query and the proactive alert
    poller — can fall back gracefully instead of crashing or, worse, silently
    treating "couldn't reach HKO" as "no extreme weather."
    """
    try:
        rhrread_response = requests.get(RHRREAD_ENDPOINT, timeout=REQUEST_TIMEOUT_SECONDS)
        rhrread_response.raise_for_status()
        rhrread = rhrread_response.json()
    except (requests.RequestException, ValueError):
        logger.exception("Failed to fetch HKO rhrread data")
        return None

    try:
        warnsum_response = requests.get(WARNSUM_ENDPOINT, timeout=REQUEST_TIMEOUT_SECONDS)
        warnsum_response.raise_for_status()
        warnsum = warnsum_response.json()
    except (requests.RequestException, ValueError):
        logger.exception("Failed to fetch HKO warnsum data")
        return None

    return WeatherSnapshot(
        fetched_at=datetime.now(),
        temperatures=_parse_temperatures(rhrread),
        warnings=_parse_warnings(warnsum),
    )


def _parse_temperatures(rhrread: object) -> dict[str, float]:
    if not isinstance(rhrread, dict):
        return {}
    temperature_block = rhrread.get("temperature")
    if not isinstance(temperature_block, dict):
        return {}
    entries = temperature_block.get("data")
    if not isinstance(entries, list):
        return {}
    temperatures: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        place = str(entry.get("place") or "").strip()
        value = entry.get("value")
        if not place or not isinstance(value, (int, float)):
            continue
        temperatures[place] = float(value)
    return temperatures


def _parse_warnings(warnsum: object) -> dict[str, WeatherWarning]:
    if not isinstance(warnsum, dict):
        return {}
    warnings: dict[str, WeatherWarning] = {}
    for warning_type, entry in warnsum.items():
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("code") or "").strip()
        if not code:
            continue
        warnings[str(warning_type)] = WeatherWarning(
            warning_type=str(warning_type),
            code=code,
            name=str(entry.get("name") or "").strip(),
            issue_time=str(entry.get("issueTime") or "").strip(),
        )
    return warnings
