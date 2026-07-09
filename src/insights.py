from __future__ import annotations

from typing import Any

try:
    from metrics import MetricsCollector, load_events
except ImportError:  # pragma: no cover - package import path.
    from src.metrics import MetricsCollector, load_events


class InsightGenerator:
    def __init__(self, collector: MetricsCollector | None = None) -> None:
        self.collector = collector or MetricsCollector()

    def get_alerts(self, user_id: str, days: int = 3) -> list[dict[str, str]]:
        events = load_events(user_id=user_id, days=days)
        if not events:
            return [
                {
                    "level": "info",
                    "icon": "⚠️",
                    "message": "最近沒有互動記錄。",
                }
            ]

        alerts: list[dict[str, str]] = []
        if any(event.get("event_type") == "safety_alert" or event.get("route") == "safety" for event in events):
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "message": "最近出現安全相關訊號，建議照顧者留意。",
                }
            )
        if any(
            event.get("event_type") == "medication_uncertainty"
            or str(event.get("medication_status") or "").strip().lower() == "unsure"
            for event in events
        ):
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "message": "最近有使用者表示不確定是否已服藥，建議照顧者協助核對。",
                }
            )
        return alerts

    def get_summary(self, user_id: str, days: int = 7) -> dict[str, Any]:
        metrics = self.collector.get_user_metrics(user_id, days=days)
        avg_mood = metrics.get("avg_mood")
        avg_cognitive = metrics.get("avg_cognitive")
        medication_adherence = metrics.get("medication_adherence")
        return {
            "mood_status": _mood_status(avg_mood),
            "cognitive_status": _cognitive_status(avg_cognitive),
            "medication_status": _medication_status(medication_adherence),
            "avg_mood": avg_mood,
            "avg_cognitive": avg_cognitive,
            "medication_adherence": medication_adherence,
        }


def _mood_status(avg_mood: float | None) -> str:
    if avg_mood is None:
        return "尚無情緒記錄"
    if avg_mood >= 4:
        return "穩定"
    if avg_mood >= 3:
        return "可留意"
    return "建議關注"


def _cognitive_status(avg_cognitive: float | None) -> str:
    if avg_cognitive is None:
        return "尚無活動記錄"
    if avg_cognitive >= 4:
        return "活動表現穩定"
    if avg_cognitive >= 3:
        return "可持續觀察"
    return "建議照顧者留意"


def _medication_status(medication_adherence: float | None) -> str:
    if medication_adherence is None:
        return "尚無用藥回覆記錄"
    if medication_adherence >= 0.8:
        return "提醒回覆穩定"
    if medication_adherence >= 0.5:
        return "可留意"
    return "建議協助核對"
