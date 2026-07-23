from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

DATABASE_URL = "sqlite:///./coa_agent.db"

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
    caregiver_id = Column(Integer, ForeignKey("caregivers.id"))
    name = Column(String)
    phone = Column(String, nullable=True)
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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
