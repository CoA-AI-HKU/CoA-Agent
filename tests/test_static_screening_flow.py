from __future__ import annotations

from pathlib import Path

from src.metrics import MetricsCollector, load_events
from src.screening.tokens import create_screening_token, get_screening_token
from src.web_server import CoARequestHandler


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_github_pages_screening_files_and_privacy_language() -> None:
    directory = PROJECT_ROOT / "docs" / "screening"
    html = (directory / "index.html").read_text(encoding="utf-8")
    script = (directory / "screening.js").read_text(encoding="utf-8")

    assert (directory / "screening.css").is_file()
    assert '<meta charset="utf-8">' in html
    assert "This is not a diagnosis and cannot determine whether someone has dementia." in html
    assert "<a " not in html
    assert "localStorage" not in script
    assert "sessionStorage" not in script
    assert "/api/screening/submit" in script
    assert "raw_answers" not in script


def test_structured_screening_submission_is_dashboard_compatible(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    entry = create_screening_token("patient-1", "self")
    handler = object.__new__(CoARequestHandler)
    response: dict = {}
    handler._json = lambda payload, status=200: response.update(payload=payload, status=status)

    handler._submit_screening(
        {
            "screening_version": entry["screening_version"],
            "result": {"risk_flag": "follow_up_suggested", "total_score": 5, "max_score": 12},
        },
        entry["token"],
        entry,
    )

    event = load_events("patient-1", days=None)[0]
    assert response["payload"]["success"] is True
    assert event["event_type"] == "screening_completed"
    assert event["raw_answers_saved"] is False
    assert "raw_answers" not in event
    assert get_screening_token(entry["token"]) is None
    metrics = MetricsCollector().get_user_metrics("patient-1")
    assert metrics["latest_risk_flag"] == "follow_up_suggested"
    assert metrics["follow_up_suggestion"] == "建議跟進"


def test_invalid_result_does_not_consume_screening_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    entry = create_screening_token("patient-1", "self")
    handler = object.__new__(CoARequestHandler)
    response: dict = {}
    handler._json = lambda payload, status=200: response.update(payload=payload, status=status)

    handler._submit_screening(
        {
            "screening_version": entry["screening_version"],
            "result": {"risk_flag": "unsupported", "total_score": 2, "max_score": 12},
        },
        entry["token"],
        entry,
    )

    assert response["status"] == 400
    assert get_screening_token(entry["token"]) is not None
    assert load_events("patient-1", days=None) == []
