from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String

from src.reminders.database import Base, SessionLocal, engine


MIN_SYSTOLIC = 50
MAX_SYSTOLIC = 260
MIN_DIASTOLIC = 30
MAX_DIASTOLIC = 160

_LABELED_PATTERN = re.compile(
    r"(?:上壓|收縮壓|systolic)\s*[:：]?\s*"
    r"(?P<systolic>\d{2,3}).{0,20}?"
    r"(?:下壓|舒張壓|舒张压|diastolic)\s*[:：]?\s*"
    r"(?P<diastolic>\d{2,3})",
    re.IGNORECASE,
)
_PAIR_PATTERN = re.compile(
    r"(?:血壓|血压|blood\s*pressure|\bbp\b)\D{0,20}"
    r"(?P<systolic>\d{2,3})\s*(?:/|\\|、|,|，|over|\s)\s*"
    r"(?P<diastolic>\d{2,3})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedBloodPressure:
    systolic: int
    diastolic: int


class BloodPressureReading(Base):
    __tablename__ = "blood_pressure_readings"

    id = Column(Integer, primary_key=True, index=True)
    patient_user_id = Column(String, nullable=False, index=True)
    systolic = Column(Integer, nullable=False)
    diastolic = Column(Integer, nullable=False)
    measured_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_channel = Column(String, nullable=False, default="")


# The reminders database owns the shared SQLAlchemy metadata. Creating this
# one missing table is non-destructive for existing reminders and patients.
Base.metadata.create_all(bind=engine)


def parse_blood_pressure(message: str) -> ParsedBloodPressure | None:
    text = " ".join(str(message or "").strip().split())
    for pattern in (_LABELED_PATTERN, _PAIR_PATTERN):
        match = pattern.search(text)
        if match:
            return _validated_pair(match.group("systolic"), match.group("diastolic"))
    return None


def _validated_pair(systolic_text: str, diastolic_text: str) -> ParsedBloodPressure | None:
    systolic = int(systolic_text)
    diastolic = int(diastolic_text)
    if not MIN_SYSTOLIC <= systolic <= MAX_SYSTOLIC:
        return None
    if not MIN_DIASTOLIC <= diastolic <= MAX_DIASTOLIC:
        return None
    if systolic <= diastolic:
        return None
    return ParsedBloodPressure(systolic=systolic, diastolic=diastolic)


def record_blood_pressure(
    patient_user_id: str,
    parsed: ParsedBloodPressure,
    *,
    source_channel: str = "",
    measured_at: datetime | None = None,
) -> BloodPressureReading:
    user_id = str(patient_user_id or "").strip()
    if not user_id:
        raise ValueError("patient_user_id is required")
    reading = BloodPressureReading(
        patient_user_id=user_id,
        systolic=parsed.systolic,
        diastolic=parsed.diastolic,
        measured_at=(measured_at or datetime.now(timezone.utc)).replace(tzinfo=None),
        source_channel=str(source_channel or "").strip().lower(),
    )
    db = SessionLocal()
    try:
        db.add(reading)
        db.commit()
        db.refresh(reading)
        return reading
    finally:
        db.close()


def list_blood_pressure_readings(patient_user_id: str, *, limit: int = 30) -> list[dict[str, object]]:
    bounded_limit = max(1, min(int(limit), 90))
    db = SessionLocal()
    try:
        readings = (
            db.query(BloodPressureReading)
            .filter(BloodPressureReading.patient_user_id == str(patient_user_id or "").strip())
            .order_by(BloodPressureReading.measured_at.desc(), BloodPressureReading.id.desc())
            .limit(bounded_limit)
            .all()
        )
        return [
            {
                "id": reading.id,
                "systolic": reading.systolic,
                "diastolic": reading.diastolic,
                "measured_at": f"{reading.measured_at.isoformat()}Z",
            }
            for reading in readings
        ]
    finally:
        db.close()


def delete_blood_pressure_readings(patient_user_id: str) -> int:
    db = SessionLocal()
    try:
        deleted = (
            db.query(BloodPressureReading)
            .filter(BloodPressureReading.patient_user_id == str(patient_user_id or "").strip())
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted)
    finally:
        db.close()
