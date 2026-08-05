from __future__ import annotations

from src.user import monitoring_preferences


def test_defaults_are_both_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    assert monitoring_preferences.get_monitoring_preferences("never-set-before") == {
        "safety": True,
        "cognitive_decline": True,
    }


def test_set_preferences_persists_and_is_read_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    result = monitoring_preferences.set_monitoring_preferences("sender-1", safety=False)
    assert result == {"safety": False, "cognitive_decline": True}
    assert monitoring_preferences.get_monitoring_preferences("sender-1") == {
        "safety": False,
        "cognitive_decline": True,
    }


def test_partial_update_does_not_clobber_the_other_preference(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-2", safety=False)
    monitoring_preferences.set_monitoring_preferences("sender-2", cognitive_decline=False)
    assert monitoring_preferences.get_monitoring_preferences("sender-2") == {
        "safety": False,
        "cognitive_decline": False,
    }


def test_preferences_are_isolated_per_sender(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    monitoring_preferences.set_monitoring_preferences("sender-a", safety=False, cognitive_decline=False)
    assert monitoring_preferences.get_monitoring_preferences("sender-b") == {
        "safety": True,
        "cognitive_decline": True,
    }
