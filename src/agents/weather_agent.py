from __future__ import annotations

from typing import Any

from src.agents.types import AgentResult
from src.pipeline.language import AnswerLanguage, detect_answer_language
from src.weather.extreme_conditions import WeatherAlert, evaluate_extreme_conditions
from src.weather.hko_client import fetch_current_weather

# HKO's own reference station, used as "the" temperature when someone just
# asks "how hot is it" without naming a district. Falls back to the highest
# reading among all stations if this one is (rarely) missing from a
# response, rather than reporting nothing.
PRIMARY_STATION = "香港天文台"

WEATHER_UNAVAILABLE_RESPONSE: dict[AnswerLanguage, str] = {
    "zh-Hant": "暫時未能連接天文台資料，請稍後再試。",
    "zh-Hans": "暂时未能连接天文台资料，请稍后再试。",
    "en": "I couldn't reach the Hong Kong Observatory's data just now — please try again shortly.",
}
NO_WARNING_RESPONSE: dict[AnswerLanguage, str] = {
    "zh-Hant": "暫時沒有極端天氣警告。",
    "zh-Hans": "暂时没有极端天气警告。",
    "en": "No extreme weather warnings are in force right now.",
}


def handle_weather_query(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)

    snapshot = fetch_current_weather()
    if snapshot is None:
        return _result(
            answer=WEATHER_UNAVAILABLE_RESPONSE[answer_language],
            safety_level="weather_unavailable",
            answer_language=answer_language,
            debug={"agent": "weather", "hko_available": False},
        )

    temperature = snapshot.temperatures.get(PRIMARY_STATION, snapshot.max_temperature())
    alerts = evaluate_extreme_conditions(snapshot)

    return _result(
        answer=_compose_answer(temperature, alerts, answer_language),
        safety_level="weather_reported",
        answer_language=answer_language,
        debug={
            "agent": "weather",
            "hko_available": True,
            "temperature": temperature,
            "active_alert_kinds": [alert.kind for alert in alerts],
        },
    )


def _compose_answer(
    temperature: float | None, alerts: list[WeatherAlert], answer_language: AnswerLanguage,
) -> str:
    lines: list[str] = []
    if temperature is not None:
        reading = f"{temperature:.0f}"
        if answer_language == "zh-Hans":
            lines.append(f"现时气温大约{reading}度。")
        elif answer_language == "en":
            lines.append(f"The current temperature is about {reading}°C.")
        else:
            lines.append(f"現時氣溫大約{reading}度。")

    if alerts:
        lines.extend(alert.message_for(answer_language) for alert in alerts)
    else:
        lines.append(NO_WARNING_RESPONSE[answer_language])

    return " ".join(lines)


def _result(
    answer: str, safety_level: str, answer_language: AnswerLanguage, debug: dict[str, Any],
) -> dict[str, Any]:
    result = AgentResult(
        answer=answer,
        intent="weather_query",
        safety_level=safety_level,
        found=False,
        sources=[],
        rag_called=False,
        route="weather",
        debug=debug,
    ).to_dict()
    result["answer_language"] = answer_language
    return result
