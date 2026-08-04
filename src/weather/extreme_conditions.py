from __future__ import annotations

from dataclasses import dataclass

from src.weather.hko_client import WeatherSnapshot

# First cut of "extreme," per explicit product decision: a temperature
# reading above 34C, or an active Rainstorm Warning Signal (HKO's "WRAIN"
# warnsum key — Amber/Red/Black). Other warnsum types (fire danger, cold,
# typhoon signals, etc.) are deliberately not alerted on yet.
EXTREME_HEAT_THRESHOLD_C = 34.0
RAIN_WARNING_TYPE = "WRAIN"

# HKO's warnsum "name" field only comes back in whichever single language the
# request used (see hko_client.py, which requests lang=tc) — this lookup lets
# every alert message be properly localized instead of embedding a Chinese
# warning name inside an English sentence. Falls back to the API's own name
# (via _rain_alert's `name` parameter) for any code not listed here.
_RAIN_CODE_NAMES: dict[str, dict[str, str]] = {
    "WRAINA": {"zh-Hant": "黃色暴雨警告", "zh-Hans": "黄色暴雨警告", "en": "Amber Rainstorm Warning Signal"},
    "WRAINR": {"zh-Hant": "紅色暴雨警告", "zh-Hans": "红色暴雨警告", "en": "Red Rainstorm Warning Signal"},
    "WRAINB": {"zh-Hant": "黑色暴雨警告", "zh-Hans": "黑色暴雨警告", "en": "Black Rainstorm Warning Signal"},
}


@dataclass(frozen=True)
class WeatherAlert:
    kind: str  # "extreme_heat" or "rain_warning" — see alert_state.py's dedup key
    dedup_key: str  # what must change before the same alert fires again
    message_zh_hant: str
    message_zh_hans: str
    message_en: str

    def message_for(self, answer_language: str) -> str:
        if answer_language == "zh-Hans":
            return self.message_zh_hans
        if answer_language == "en":
            return self.message_en
        return self.message_zh_hant


def evaluate_extreme_conditions(snapshot: WeatherSnapshot) -> list[WeatherAlert]:
    """Decide which (if any) extreme-weather alerts this snapshot warrants.

    Returns zero, one, or both alert kinds — heat and a rainstorm warning can
    coexist. Callers (the proactive scheduler and the on-demand weather
    query) are both expected to run this on the same snapshot shape, so the
    definition of "extreme" only lives in one place.
    """
    alerts: list[WeatherAlert] = []

    max_temperature = snapshot.max_temperature()
    if max_temperature is not None and max_temperature > EXTREME_HEAT_THRESHOLD_C:
        alerts.append(_heat_alert(max_temperature))

    rain_warning = snapshot.warnings.get(RAIN_WARNING_TYPE)
    if rain_warning is not None:
        alerts.append(_rain_alert(rain_warning.code, rain_warning.name))

    return alerts


def _heat_alert(max_temperature: float) -> WeatherAlert:
    reading = f"{max_temperature:.0f}"
    return WeatherAlert(
        kind="extreme_heat",
        dedup_key="extreme_heat",
        message_zh_hant=f"🌡️ 天氣提示：現時氣溫已達{reading}度，屬於酷熱天氣，請盡量留在室內，多補充水分，避免長時間留在戶外。",
        message_zh_hans=f"🌡️ 天气提示：现时气温已达{reading}度，属于酷热天气，请尽量留在室内，多补充水分，避免长时间留在户外。",
        message_en=f"🌡️ Weather alert: the temperature has reached {reading}°C — extreme heat. Please stay indoors where possible, drink plenty of water, and avoid prolonged time outside.",
    )


def _rain_alert(code: str, name: str) -> WeatherAlert:
    localized = _RAIN_CODE_NAMES.get(code, {})
    zh_hant_name = localized.get("zh-Hant") or name or "暴雨警告"
    zh_hans_name = localized.get("zh-Hans") or name or "暴雨警告"
    en_name = localized.get("en") or name or "Rainstorm Warning Signal"
    return WeatherAlert(
        kind="rain_warning",
        dedup_key=code,
        message_zh_hant=f"🌧️ 天氣提示：天文台已發出「{zh_hant_name}」，請留在安全地方，暫時避免外出。",
        message_zh_hans=f"🌧️ 天气提示：天文台已发出「{zh_hans_name}」，请留在安全地方，暂时避免外出。",
        message_en=f"🌧️ Weather alert: the Hong Kong Observatory has issued the {en_name}. Please stay somewhere safe and avoid going outside for now.",
    )
