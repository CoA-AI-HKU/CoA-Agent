from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.user import monitoring_preferences


def test_defaults_preserve_existing_categories_and_require_consent_for_new_ones(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    result = monitoring_preferences.get_monitoring_preferences("never-set-before")
    assert result["safety"] is True
    assert result["cognitive_decline"] is True
    assert result["sleep"] is False
    assert result["daily_activity"] is False
    assert result["routine_adherence"] is False
    assert result["effective"]["sleep"] is False


def test_requested_monitoring_only_becomes_effective_after_patient_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-1", sleep=True)
    assert monitoring_preferences.get_monitoring_preferences("sender-1")["effective"]["sleep"] is False
    result = monitoring_preferences.set_patient_monitoring_consent("sender-1", sleep=True)
    assert result["consent"]["sleep"] is True
    assert result["effective"]["sleep"] is True


def test_partial_updates_do_not_clobber_other_categories(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-2", safety=False)
    monitoring_preferences.set_monitoring_preferences("sender-2", cognitive_decline=False)
    result = monitoring_preferences.get_monitoring_preferences("sender-2")
    assert result["safety"] is False
    assert result["cognitive_decline"] is False
    assert result["sleep"] is False


def test_preferences_are_isolated_per_sender(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-a", sleep=True)
    assert monitoring_preferences.get_monitoring_preferences("sender-b")["sleep"] is False


def test_thresholds_are_configurable_and_validated(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    result = monitoring_preferences.set_monitoring_thresholds("sender-3", sleep=3)
    assert result["thresholds"]["sleep"] == 3
    with pytest.raises(ValueError):
        monitoring_preferences.set_monitoring_thresholds("sender-3", sleep=0)


def test_temporary_pause_disables_all_effective_monitoring(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-4", sleep=True)
    monitoring_preferences.set_patient_monitoring_consent("sender-4", sleep=True)
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    result = monitoring_preferences.set_monitoring_pause("sender-4", future)
    assert result["is_paused"] is True
    assert not any(result["effective"].values())
    resumed = monitoring_preferences.set_monitoring_pause("sender-4", None)
    assert resumed["is_paused"] is False
    assert resumed["effective"]["sleep"] is True
