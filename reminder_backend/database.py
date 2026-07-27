from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# Anchored to the repo root (this file's grandparent directory) rather than
# "./coa_agent.db", which resolves relative to the process's CWD. The API
# (backend/main.py, launched from the repo root — where the existing
# coa_agent.db already lives) and the scheduler (historically launched from
# inside reminder_backend/) resolved that relative path differently and could
# silently read/write two different SQLite files. Anchoring to the repo root
# keeps every launcher pointed at the same, already-existing database file.
DATABASE_PATH = Path(__file__).resolve().parents[1] / "coa_agent.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Caregiver(Base):
    __tablename__ = "caregivers"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    display_name = Column(String)
    phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    caregiver_id = Column(Integer, ForeignKey("caregivers.id"), nullable=True)
    name = Column(String)
    phone = Column(String, nullable=True)
    # Links this row to a patient registered in the main chat app's user
    # registry (src/user/user_registry.py registry_user_id), so a reminder
    # set by talking to the bot and one set via the caregiver dashboard
    # resolve to the same Patient. Nullable/unindexed-unique at the DB level
    # (SQLite ALTER TABLE can't retrofit a UNIQUE constraint on an existing
    # table); uniqueness is instead enforced in chat_reminders.py's
    # find-or-create lookup.
    external_user_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    caregiver = relationship("Caregiver", backref="patients")

class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    text = Column(String)
    time = Column(String)  # "08:00"
    days = Column(String)  # "mon,tue,wed,thu,fri,sat,sun"
    active = Column(Boolean, default=True)
    last_triggered = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    patient = relationship("Patient", backref="reminders")

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    name = Column(String)
    phone = Column(String)
    relationship_type = Column(String)  # 改名避免冲突
    created_at = Column(DateTime, default=datetime.utcnow)

class NotificationLog(Base):
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    reminder_id = Column(Integer, ForeignKey("reminders.id"))
    sent_at = Column(DateTime, default=datetime.utcnow)
    acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, nullable=True)

Base.metadata.create_all(bind=engine)


def _migrate_add_missing_columns() -> None:
    """Add columns introduced after a DB file already exists.

    Base.metadata.create_all only creates missing TABLES, not missing
    COLUMNS on tables that already exist, so a deployed coa_agent.db from
    before external_user_id was added needs this once at import time.
    """
    with engine.connect() as connection:
        existing_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(patients)")
        }
        if "external_user_id" not in existing_columns:
            connection.exec_driver_sql("ALTER TABLE patients ADD COLUMN external_user_id VARCHAR")
            connection.commit()


_migrate_add_missing_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
