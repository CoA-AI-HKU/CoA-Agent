from __future__ import annotations

import json
from datetime import datetime
from unittest import mock

import pytest

from src.agents.coordinator_agent import coordinate_message
from src.agents.weather_agent import handle_weather_query
from src.orchestrator import handle_dementia_user_message
from src.weather import alert_state, scheduler as weather_scheduler
from src.weather.extreme_conditions import (
    EXTREME_HEAT_THRESHOLD_C,
    evaluate_extreme_conditions,
)
from src.weather.hko_client import WeatherSnapshot, WeatherWarning, _parse_temperatures, _parse_warnings


RHRREAD_FIXTURE = {
    "temperature": {
        "data": [
            {"place": "香港天文台", "value": 33, "unit": "C"},
            {"place": "京士柏", "value": 35, "unit": "C"},
        ],
        "recordTime": "2026-08-04T16:00:00+08:00",
    },
}
WARNSUM_EMPTY: dict = {}
WARNSUM_WITH_RAIN = {
    "WRAIN": {
        "code": "WRAINB",
        "actionCode": "ISSUE",
        "issueTime": "2026-08-04T16:00:00+08:00",
        "name": "黑色暴雨警告",
        "type": "WRAIN",
    },
}


@pytest.fixture(autouse=True)
def _isolated_alert_state(tmp_path, monkeypatch):
    monkeypatch.setenv("WEATHER_ALERT_STATE_PATH", str(tmp_path / "weather_alert_state.json"))
    yield


def test_parse_temperatures_extracts_place_and_value():
    temperatures = _parse_temperatures(RHRREAD_FIXTURE)
    assert temperatures["香港天文台"] == 33.0
    assert temperatures["京士柏"] == 35.0


def test_parse_temperatures_tolerates_malformed_input():
    assert _parse_temperatures({}) == {}
    assert _parse_temperatures({"temperature": {"data": "not-a-list"}}) == {}
    assert _parse_temperatures("not-a-dict") == {}


def test_parse_warnings_extracts_active_warnings():
    warnings = _parse_warnings(WARNSUM_WITH_RAIN)
    assert "WRAIN" in warnings
    assert warnings["WRAIN"].code == "WRAINB"
    assert warnings["WRAIN"].name == "黑色暴雨警告"


def test_parse_warnings_empty_object_means_no_active_warnings():
    assert _parse_warnings(WARNSUM_EMPTY) == {}


def test_fetch_current_weather_combines_both_endpoints(monkeypatch):
    def fake_get(url, timeout=None):
        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return RHRREAD_FIXTURE if "rhrread" in url else WARNSUM_WITH_RAIN

        return Response()

    monkeypatch.setattr("src.weather.hko_client.requests.get", fake_get)

    from src.weather.hko_client import fetch_current_weather

    snapshot = fetch_current_weather()
    assert snapshot is not None
    assert snapshot.temperatures["香港天文台"] == 33.0
    assert "WRAIN" in snapshot.warnings


def test_fetch_current_weather_returns_none_on_network_failure(monkeypatch):
    import requests

    def fake_get(url, timeout=None):
        raise requests.RequestException("boom")

    monkeypatch.setattr("src.weather.hko_client.requests.get", fake_get)

    from src.weather.hko_client import fetch_current_weather

    assert fetch_current_weather() is None


def test_evaluate_extreme_conditions_detects_heat_above_threshold():
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 35.0})
    alerts = evaluate_extreme_conditions(snapshot)
    assert len(alerts) == 1
    assert alerts[0].kind == "extreme_heat"
    assert "35" in alerts[0].message_zh_hant


def test_evaluate_extreme_conditions_does_not_flag_temperature_at_or_below_threshold():
    snapshot = WeatherSnapshot(
        fetched_at=datetime.now(), temperatures={"香港天文台": EXTREME_HEAT_THRESHOLD_C},
    )
    assert evaluate_extreme_conditions(snapshot) == []


def test_evaluate_extreme_conditions_detects_rain_warning():
    warning = WeatherWarning(warning_type="WRAIN", code="WRAINR", name="紅色暴雨警告", issue_time="")
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), warnings={"WRAIN": warning})
    alerts = evaluate_extreme_conditions(snapshot)
    assert len(alerts) == 1
    assert alerts[0].kind == "rain_warning"
    assert alerts[0].dedup_key == "WRAINR"
    assert "紅色暴雨警告" in alerts[0].message_zh_hant
    assert "Red Rainstorm Warning Signal" in alerts[0].message_en


def test_evaluate_extreme_conditions_can_flag_both_at_once():
    warning = WeatherWarning(warning_type="WRAIN", code="WRAINB", name="黑色暴雨警告", issue_time="")
    snapshot = WeatherSnapshot(
        fetched_at=datetime.now(), temperatures={"香港天文台": 36.0}, warnings={"WRAIN": warning},
    )
    kinds = {alert.kind for alert in evaluate_extreme_conditions(snapshot)}
    assert kinds == {"extreme_heat", "rain_warning"}


def test_alert_state_dedups_by_day_for_heat_and_by_code_for_rain():
    warning = WeatherWarning(warning_type="WRAIN", code="WRAINA", name="黃色暴雨警告", issue_time="")
    snapshot = WeatherSnapshot(
        fetched_at=datetime.now(), temperatures={"香港天文台": 35.0}, warnings={"WRAIN": warning},
    )
    heat_alert, rain_alert = evaluate_extreme_conditions(snapshot)
    today = "2026-08-04"

    assert alert_state.already_alerted(heat_alert, today) is False
    assert alert_state.already_alerted(rain_alert, today) is False

    alert_state.mark_alerted(heat_alert, today)
    alert_state.mark_alerted(rain_alert, today)

    assert alert_state.already_alerted(heat_alert, today) is True
    # Same day, still hot: must not re-alert.
    assert alert_state.already_alerted(heat_alert, today) is True
    # A new day resets the heat dedup.
    assert alert_state.already_alerted(heat_alert, "2026-08-05") is False

    assert alert_state.already_alerted(rain_alert, today) is True
    # Escalation to a different code alerts again.
    escalated = WeatherWarning(warning_type="WRAIN", code="WRAINR", name="紅色暴雨警告", issue_time="")
    escalated_snapshot = WeatherSnapshot(fetched_at=datetime.now(), warnings={"WRAIN": escalated})
    escalated_alert = evaluate_extreme_conditions(escalated_snapshot)[0]
    assert alert_state.already_alerted(escalated_alert, today) is False


def test_alert_state_reconcile_clears_stale_warning_so_it_can_re_fire():
    warning = WeatherWarning(warning_type="WRAIN", code="WRAINB", name="黑色暴雨警告", issue_time="")
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), warnings={"WRAIN": warning})
    rain_alert = evaluate_extreme_conditions(snapshot)[0]
    today = "2026-08-04"

    alert_state.mark_alerted(rain_alert, today)
    assert alert_state.already_alerted(rain_alert, today) is True

    # Warning cancelled: no active kinds this poll.
    alert_state.reconcile_dedup_state(set())
    assert alert_state.already_alerted(rain_alert, today) is False


def test_check_and_send_weather_alerts_broadcasts_to_registered_patients_only(monkeypatch, tmp_path):
    registry_path = tmp_path / "user_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "users": {
                    "telegram-patient-1": {"role": "user", "user_id": "patient-1", "display_name": "A"},
                    "telegram-patient-2": {"role": "user", "user_id": "patient-2", "display_name": "B"},
                    "telegram-caregiver-1": {
                        "role": "caregiver", "linked_user_ids": ["patient-1"], "display_name": "C",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 36.0})
    monkeypatch.setattr(weather_scheduler, "fetch_current_weather", lambda: snapshot)

    sent_to: list[str] = []

    def fake_post(url, json=None, timeout=None):
        sent_to.append(json["chat_id"])

        class Response:
            status_code = 200

        return Response()

    with mock.patch.object(weather_scheduler.requests, "post", fake_post):
        weather_scheduler.check_and_send_weather_alerts()

    assert set(sent_to) == {"telegram-patient-1", "telegram-patient-2"}
    assert "telegram-caregiver-1" not in sent_to


def test_check_and_send_weather_alerts_does_not_resend_the_same_day(monkeypatch, tmp_path):
    registry_path = tmp_path / "user_registry.json"
    registry_path.write_text(
        json.dumps({"users": {"telegram-patient-1": {"role": "user", "display_name": "A"}}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")

    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 36.0})
    monkeypatch.setattr(weather_scheduler, "fetch_current_weather", lambda: snapshot)

    call_count = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        call_count["n"] += 1

        class Response:
            status_code = 200

        return Response()

    with mock.patch.object(weather_scheduler.requests, "post", fake_post):
        weather_scheduler.check_and_send_weather_alerts()
        weather_scheduler.check_and_send_weather_alerts()

    assert call_count["n"] == 1


def test_handle_weather_query_reports_temperature_and_no_warnings(monkeypatch):
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 30.0})
    monkeypatch.setattr("src.agents.weather_agent.fetch_current_weather", lambda: snapshot)

    result = handle_weather_query("今日天氣點呀")
    assert result["route"] == "weather"
    assert result["safety_level"] == "weather_reported"
    assert "30" in result["answer"]
    assert "沒有極端天氣警告" in result["answer"]


def test_handle_weather_query_reports_extreme_heat(monkeypatch):
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 36.0})
    monkeypatch.setattr("src.agents.weather_agent.fetch_current_weather", lambda: snapshot)

    result = handle_weather_query("而家幾多度")
    assert "36" in result["answer"]
    assert "酷熱" in result["answer"]


def test_handle_weather_query_respects_answer_language(monkeypatch):
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 30.0})
    monkeypatch.setattr("src.agents.weather_agent.fetch_current_weather", lambda: snapshot)

    result = handle_weather_query("what's the weather like today")
    assert result["answer_language"] == "en"
    assert "current temperature" in result["answer"].lower()


def test_handle_weather_query_falls_back_when_hko_unavailable(monkeypatch):
    monkeypatch.setattr("src.agents.weather_agent.fetch_current_weather", lambda: None)

    result = handle_weather_query("今日天氣點呀")
    assert result["safety_level"] == "weather_unavailable"


def test_weather_query_intent_routes_correctly():
    for message in ("今日天氣點呀", "而家幾多度", "會唔會落雨", "will it rain today", "what's the weather"):
        decision = coordinate_message(message)
        assert decision.intent == "weather_query", message
        assert decision.route == "weather", message


def test_weather_query_end_to_end(monkeypatch):
    snapshot = WeatherSnapshot(fetched_at=datetime.now(), temperatures={"香港天文台": 31.0})
    monkeypatch.setattr("src.agents.weather_agent.fetch_current_weather", lambda: snapshot)

    result = handle_dementia_user_message("今日天氣點呀", "some-user")
    assert result["route"] == "weather"
    assert result["intent"] == "weather_query"


def test_bare_temperature_mention_does_not_misroute_as_weather():
    # A fever/body-temperature mention must not be swallowed by the weather
    # keyword list — it deliberately only matches compound, weather-specific
    # phrases, not a bare degree number.
    decision = coordinate_message("佢成日話唔舒服，體溫38度")
    assert decision.intent != "weather_query"
