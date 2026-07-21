from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.insights import InsightGenerator
from src.metrics import MetricsCollector, load_events
from src.user.user_registry import get_dashboard_patient_accounts
from src.metrics import log_event
from src.screening.tokens import get_screening_token, mark_screening_token_used


WEB_ROOT = Path(__file__).resolve().parents[1] / "web"


def build_dashboard_payload(user_id: str, days: int = 7) -> dict[str, Any]:
    """Return the same live metrics used by the Streamlit dashboard."""
    days = max(1, min(days, 60))
    metrics = MetricsCollector().get_user_metrics(user_id, days=days)
    insights = InsightGenerator()
    events = load_events(user_id=user_id, days=days)
    activity_by_day: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    for event in events:
        stamp = str(event.get("timestamp") or "")[:10]
        if stamp:
            activity_by_day[stamp] = activity_by_day.get(stamp, 0) + 1
        channel = str(event.get("channel") or "unknown").strip() or "unknown"
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
    today = datetime.now(timezone.utc).date()
    daily_activity = []
    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        daily_activity.append({"date": day.isoformat(), "count": activity_by_day.get(day.isoformat(), 0)})
    return {
        "user_id": user_id,
        "days": days,
        "metrics": metrics,
        "summary": insights.get_summary(user_id, days=days),
        "alerts": insights.get_alerts(user_id, days=min(days, 7)),
        "daily_activity": daily_activity,
        "channel_counts": channel_counts,
    }


class CoARequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        access_token = str(query.get("access_token", [""])[0]).strip()
        if parsed.path == "/api/users":
            accounts = get_dashboard_patient_accounts(access_token)
            if not accounts:
                self._json({"error": "invalid, expired, or unpaired caregiver access"}, HTTPStatus.UNAUTHORIZED)
                return
            self._json({"users": accounts})
            return
        if parsed.path == "/api/dashboard":
            user_id = str(query.get("user_id", [""])[0]).strip()
            if not user_id:
                self._json({"error": "user_id is required"}, HTTPStatus.BAD_REQUEST)
                return
            allowed_ids = {account["user_id"] for account in get_dashboard_patient_accounts(access_token)}
            if user_id not in allowed_ids:
                self._json({"error": "caregiver is not authorized for this patient"}, HTTPStatus.FORBIDDEN)
                return
            try:
                days = int(query.get("days", ["7"])[0])
            except ValueError:
                days = 7
            self._json(build_dashboard_payload(user_id, days))
            return
        if parsed.path == "/api/screening-token":
            token = str(query.get("token", [""])[0]).strip()
            entry = get_screening_token(token)
            if entry is None:
                self._json({"valid": False}, HTTPStatus.UNAUTHORIZED)
                return
            self._json({"valid": True, "screening_version": entry["screening_version"]})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/api/screening-complete", "/api/screening/submit"}:
            self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 4096)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "invalid request"}, HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            self._json({"error": "invalid request"}, HTTPStatus.BAD_REQUEST)
            return
        token = str(payload.get("token") or "")
        entry = get_screening_token(token)
        if entry is None:
            self._json({"error": "invalid or expired token"}, HTTPStatus.UNAUTHORIZED)
            return
        if parsed.path == "/api/screening/submit":
            self._submit_screening(payload, token, entry)
            return
        self._submit_legacy_screening(payload, token, entry)

    def _submit_screening(self, payload: dict[str, Any], token: str, entry: dict[str, Any]) -> None:
        version = str(payload.get("screening_version") or "")
        result = payload.get("result")
        if version != entry.get("screening_version") or not isinstance(result, dict):
            self._json({"error": "invalid screening version or result"}, HTTPStatus.BAD_REQUEST)
            return
        allowed_flags = {"no_immediate_concern", "monitor", "follow_up_suggested", "urgent_safety"}
        try:
            risk_flag = str(result.get("risk_flag") or "")
            total_score = int(result.get("total_score"))
            max_score = int(result.get("max_score"))
        except (TypeError, ValueError):
            self._json({"error": "invalid result"}, HTTPStatus.BAD_REQUEST)
            return
        if risk_flag not in allowed_flags or max_score != 12 or not 0 <= total_score <= max_score:
            self._json({"error": "invalid result"}, HTTPStatus.BAD_REQUEST)
            return
        if mark_screening_token_used(token) is None:
            self._json({"error": "invalid or expired token"}, HTTPStatus.UNAUTHORIZED)
            return
        log_event(entry["user_id"], {
            "event_type": "screening_completed",
            "check_version": entry["screening_version"],
            "screening_version": entry["screening_version"],
            "total_score": total_score,
            "max_score": max_score,
            "risk_flag": risk_flag,
            "follow_up_status": risk_flag,
            "raw_answers_saved": False,
            "raw_text_saved": False,
        })
        self._json({"success": True, "risk_flag": risk_flag})

    def _submit_legacy_screening(
        self, payload: dict[str, Any], token: str, entry: dict[str, Any]
    ) -> None:
        try:
            total_score = max(0, min(int(payload.get("total_score", 0)), 5))
        except (TypeError, ValueError):
            self._json({"error": "invalid score"}, HTTPStatus.BAD_REQUEST)
            return
        if mark_screening_token_used(token) is None:
            self._json({"error": "invalid or expired token"}, HTTPStatus.UNAUTHORIZED)
            return
        risk_flag = "normal" if total_score >= 4 else "monitor" if total_score >= 3 else "follow_up_suggested"
        log_event(entry["user_id"], {
            "event_type": "cognitive_check_completed",
            "check_version": entry["screening_version"],
            "screening_version": entry["screening_version"],
            "total_score": total_score,
            "max_score": 5,
            "risk_flag": risk_flag,
            "follow_up_status": "suggested" if risk_flag == "follow_up_suggested" else "monitor",
            "raw_answers_saved": False,
            "raw_text_saved": False,
        })
        self._json({"completed": True, "risk_flag": risk_flag})

    def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the CoA dashboard and screening pages")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CoARequestHandler)
    print(f"CoA web app: http://{args.host}:{args.port}/dashboard.html")
    server.serve_forever()


if __name__ == "__main__":
    main()
