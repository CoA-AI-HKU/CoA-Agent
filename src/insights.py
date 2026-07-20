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
        seven_day_events = load_events(user_id=user_id, days=7)
        if not events and not seven_day_events:
            return [
                {
                    "level": "info",
                    "icon": "⚠️",
                    "code": "no_recent_events",
                    "message": "最近沒有互動記錄。這不是診斷。",
                }
            ]

        alerts: list[dict[str, str]] = []
        if any(event.get("event_type") == "wandering_safety" for event in seven_day_events):
            alerts.append(
                {
                    "level": "urgent",
                    "icon": "⚠️",
                    "code": "caregiver_followup_recommended",
                    "message": "最近出現走失或安全相關訊號，建議照顧者立即跟進安全安排。這不是診斷。",
                }
            )
        elif any(event.get("event_type") == "safety_alert" or event.get("route") == "safety" for event in events):
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "code": "caregiver_followup_recommended",
                    "message": "最近出現安全相關訊號，建議照顧者留意。這不是診斷。",
                }
            )
        if any(
            event.get("event_type") == "medication_uncertainty"
            or str(event.get("medication_status") or "").strip().lower() == "unsure"
            for event in seven_day_events
        ):
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "code": "caregiver_followup_recommended",
                    "message": "最近有使用者表示不確定是否已服藥，建議照顧者協助核對。這不是診斷。",
                }
            )
        concern_count = sum(
            1
            for event in seven_day_events
            if event.get("event_type") in {"memory_concern", "orientation_confusion"}
        )
        if concern_count >= 3:
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "code": "follow_up_suggested",
                    "message": "最近出現多次記憶或方向感相關擔憂。這不是診斷，但建議照顧者留意。",
                }
            )
        if any(event.get("event_type") == "caregiver_reported_worsening" for event in seven_day_events):
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "code": "caregiver_followup_recommended",
                    "message": "照顧者最近提到情況有所轉變，建議持續記錄並考慮向醫護人員查詢。這不是診斷。",
                }
            )

        latest_risk_flag = str(
            self.collector.get_user_metrics(user_id, days=7).get("latest_risk_flag") or ""
        )
        if latest_risk_flag == "follow_up_suggested":
            alerts.append(
                {
                    "level": "warning",
                    "icon": "⚠️",
                    "code": "follow_up_suggested",
                    "message": "最近的簡單認知小練習出現多項困難。這不是診斷，但建議照顧者留意，並考慮安排專業評估。",
                }
            )
        elif latest_risk_flag == "monitor":
            alerts.append(
                {
                    "level": "info",
                    "icon": "ℹ️",
                    "code": "follow_up_suggested",
                    "message": "最近的簡單認知小練習顯示部分項目較困難，建議持續觀察。這不是診斷。",
                }
            )
        return alerts

    def get_summary(self, user_id: str, days: int = 7) -> dict[str, Any]:
        metrics = self.collector.get_user_metrics(user_id, days=days)
        avg_mood = metrics.get("avg_mood")
        avg_cognitive = metrics.get("avg_cognitive")
        medication_adherence = metrics.get("medication_adherence")
        latest_risk_flag = metrics.get("latest_risk_flag")
        return {
            "mood_status": _mood_status(avg_mood),
            "cognitive_status": _cognitive_status(avg_cognitive),
            "cognitive_check_status": _cognitive_check_status(latest_risk_flag),
            "medication_status": _medication_status(medication_adherence),
            "avg_mood": avg_mood,
            "avg_cognitive": avg_cognitive,
            "medication_adherence": medication_adherence,
            "latest_risk_flag": latest_risk_flag,
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


def _cognitive_check_status(risk_flag: Any) -> str:
    flag = str(risk_flag or "").strip()
    if not flag:
        return "尚無小練習記錄"
    if flag == "normal":
        return "未見即時關注"
    if flag == "monitor":
        return "建議留意"
    if flag == "follow_up_suggested":
        return "建議跟進"
    if flag == "urgent_safety":
        return "安全問題需即時處理"
    return "尚無小練習記錄"


def _medication_status(medication_adherence: float | None) -> str:
    if medication_adherence is None:
        return "尚無用藥回覆記錄"
    if medication_adherence >= 0.8:
        return "提醒回覆穩定"
    if medication_adherence >= 0.5:
        return "可留意"
    return "建議協助核對"
