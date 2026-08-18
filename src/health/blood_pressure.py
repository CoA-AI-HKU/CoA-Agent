from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, inspect, text

from src.reminders.database import Base, SessionLocal, engine


MIN_SYSTOLIC = 50
MAX_SYSTOLIC = 260
MIN_DIASTOLIC = 30
MAX_DIASTOLIC = 160
MIN_PULSE = 30
MAX_PULSE = 250
ALLOWED_RETENTION_DAYS = {0, 30, 90, 180, 365}

_LABELED_PATTERN = re.compile(
    r"(?:上壓|收縮壓|systolic)\s*[:：]?\s*"
    r"(?P<systolic>\d{2,3}).{0,20}?"
    r"(?:下壓|舒張壓|舒张压|diastolic)\s*[:：]?\s*"
    r"(?P<diastolic>\d{2,3})",
    re.IGNORECASE,
)
_PAIR_PATTERN = re.compile(
    r"(?:血壓|血压|blood\s*pressure|\bbp\b)\D{0,20}"
    r"(?P<systolic>\d{2,3})\s*(?:/|\\|、|,|，|度|同|和|至|到|over|\s)\s*"
    r"(?P<diastolic>\d{2,3})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedBloodPressure:
    systolic: int
    diastolic: int
    pulse: int | None = None
    notes: str = ""


class BloodPressureReading(Base):
    __tablename__ = "blood_pressure_readings"

    id = Column(Integer, primary_key=True, index=True)
    patient_user_id = Column(String, nullable=False, index=True)
    systolic = Column(Integer, nullable=False)
    diastolic = Column(Integer, nullable=False)
    measured_at = Column(DateTime, nullable=False)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    source_channel = Column(String, nullable=False, default="")
    pulse = Column(Integer, nullable=True)
    notes = Column(String, nullable=False, default="")


class BloodPressureRetention(Base):
    __tablename__ = "blood_pressure_retention"

    patient_user_id = Column(String, primary_key=True)
    retention_days = Column(Integer, nullable=False, default=0)


# The reminders database owns the shared SQLAlchemy metadata. Creating this
# one missing table is non-destructive for existing reminders and patients.
Base.metadata.create_all(bind=engine)


def _migrate_existing_table() -> None:
    columns = {column["name"] for column in inspect(engine).get_columns("blood_pressure_readings")}
    with engine.begin() as connection:
        if "pulse" not in columns:
            connection.execute(text("ALTER TABLE blood_pressure_readings ADD COLUMN pulse INTEGER"))
        if "notes" not in columns:
            connection.execute(text("ALTER TABLE blood_pressure_readings ADD COLUMN notes VARCHAR NOT NULL DEFAULT ''"))


_migrate_existing_table()


def parse_blood_pressure(message: str) -> ParsedBloodPressure | None:
    text = " ".join(str(message or "").strip().split())
    for pattern in (_LABELED_PATTERN, _PAIR_PATTERN):
        match = pattern.search(text)
        if match:
            parsed = _validated_pair(match.group("systolic"), match.group("diastolic"))
            if parsed is None:
                return None
            pulse_match = re.search(r"(?:脈搏|脉搏|心跳|pulse)\s*[:：]?\s*(\d{2,3})", text, re.IGNORECASE)
            pulse = int(pulse_match.group(1)) if pulse_match else None
            if pulse is not None and not MIN_PULSE <= pulse <= MAX_PULSE:
                return None
            note_match = re.search(r"(?:備註|备注|note)\s*[:：]?\s*(.{1,500})$", text, re.IGNORECASE)
            return ParsedBloodPressure(parsed.systolic, parsed.diastolic, pulse, note_match.group(1).strip() if note_match else "")
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
        pulse=parsed.pulse,
        notes=parsed.notes[:500],
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
    purge_expired_blood_pressure_readings(patient_user_id)
    bounded_limit = max(1, min(int(limit), 10000))
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
                "pulse": reading.pulse,
                "notes": reading.notes or "",
                "measured_at": f"{reading.measured_at.isoformat()}Z",
            }
            for reading in readings
        ]
    finally:
        db.close()


def update_blood_pressure_reading(patient_user_id: str, reading_id: int, *, systolic: int, diastolic: int,
                                  pulse: int | None = None, notes: str = "") -> dict[str, object] | None:
    parsed = _validated_pair(str(systolic), str(diastolic))
    if parsed is None or (pulse is not None and not MIN_PULSE <= pulse <= MAX_PULSE):
        raise ValueError("invalid blood pressure or pulse")
    if len(notes) > 500:
        raise ValueError("notes must be 500 characters or fewer")
    db = SessionLocal()
    try:
        reading = db.query(BloodPressureReading).filter(
            BloodPressureReading.id == reading_id,
            BloodPressureReading.patient_user_id == str(patient_user_id).strip(),
        ).first()
        if reading is None:
            return None
        reading.systolic, reading.diastolic, reading.pulse, reading.notes = systolic, diastolic, pulse, notes.strip()
        db.commit()
        db.refresh(reading)
        return {
            "id": reading.id, "systolic": reading.systolic, "diastolic": reading.diastolic,
            "pulse": reading.pulse, "notes": reading.notes or "", "measured_at": f"{reading.measured_at.isoformat()}Z",
        }
    finally:
        db.close()


def delete_blood_pressure_reading(patient_user_id: str, reading_id: int) -> bool:
    db = SessionLocal()
    try:
        deleted = db.query(BloodPressureReading).filter(
            BloodPressureReading.id == reading_id,
            BloodPressureReading.patient_user_id == str(patient_user_id).strip(),
        ).delete(synchronize_session=False)
        db.commit()
        return bool(deleted)
    finally:
        db.close()


def get_blood_pressure_retention(patient_user_id: str) -> int:
    db = SessionLocal()
    try:
        setting = db.query(BloodPressureRetention).filter_by(patient_user_id=str(patient_user_id).strip()).first()
        return int(setting.retention_days) if setting else 0
    finally:
        db.close()


def set_blood_pressure_retention(patient_user_id: str, retention_days: int) -> int:
    if retention_days not in ALLOWED_RETENTION_DAYS:
        raise ValueError("unsupported retention period")
    db = SessionLocal()
    try:
        user_id = str(patient_user_id).strip()
        setting = db.query(BloodPressureRetention).filter_by(patient_user_id=user_id).first()
        if setting is None:
            setting = BloodPressureRetention(patient_user_id=user_id, retention_days=retention_days)
            db.add(setting)
        else:
            setting.retention_days = retention_days
        db.commit()
    finally:
        db.close()
    purge_expired_blood_pressure_readings(patient_user_id)
    return retention_days


def purge_expired_blood_pressure_readings(patient_user_id: str) -> int:
    from datetime import timedelta
    days = get_blood_pressure_retention(patient_user_id)
    if days == 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=days)
    db = SessionLocal()
    try:
        deleted = db.query(BloodPressureReading).filter(
            BloodPressureReading.patient_user_id == str(patient_user_id).strip(),
            BloodPressureReading.measured_at < cutoff,
        ).delete(synchronize_session=False)
        db.commit()
        return int(deleted)
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
