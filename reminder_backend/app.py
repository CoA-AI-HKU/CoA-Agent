from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

try:
    from .database import get_db, Caregiver, Patient, Reminder, EmergencyContact, NotificationLog, engine
    from .auth import get_password_hash, authenticate_caregiver, create_access_token, get_current_caregiver, verify_password
except ImportError:  # Support `cd reminder_backend && uvicorn app:app`.
    from database import get_db, Caregiver, Patient, Reminder, EmergencyContact, NotificationLog, engine
    from auth import get_password_hash, authenticate_caregiver, create_access_token, get_current_caregiver, verify_password

app = FastAPI(title="CoA-Agent Reminder API")

# In production Nginx gives the browser one origin. This CORS setting only
# supports direct development access to the reminder API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080", "http://127.0.0.1:8080"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ============================================================
# Pydantic Models
# ============================================================
class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str
    phone: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    caregiver_id: int
    display_name: str

class PatientCreate(BaseModel):
    name: str
    phone: Optional[str] = None

class PatientResponse(BaseModel):
    id: int
    name: str
    phone: Optional[str]
    created_at: datetime

class ReminderCreate(BaseModel):
    patient_id: int
    text: str
    time: str  # "08:00"
    days: str  # "mon,tue,wed"

class ReminderResponse(BaseModel):
    id: int
    patient_id: int
    text: str
    time: str
    days: str
    active: bool
    last_triggered: Optional[datetime]

class EmergencyContactCreate(BaseModel):
    patient_id: int
    name: str
    phone: str
    relationship: str

# ============================================================
# Auth Endpoints
# ============================================================
@app.post("/api/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(Caregiver).filter(Caregiver.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    caregiver = Caregiver(
        username=req.username,
        password_hash=get_password_hash(req.password),
        display_name=req.display_name,
        phone=req.phone
    )
    db.add(caregiver)
    db.commit()
    db.refresh(caregiver)
    
    token = create_access_token({"sub": caregiver.username})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        caregiver_id=caregiver.id,
        display_name=caregiver.display_name
    )

@app.post("/api/auth/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    caregiver = authenticate_caregiver(db, req.username, req.password)
    if not caregiver:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_access_token({"sub": caregiver.username})
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        caregiver_id=caregiver.id,
        display_name=caregiver.display_name
    )

@app.get("/api/auth/me")
def get_me(caregiver: Caregiver = Depends(get_current_caregiver)):
    return {
        "id": caregiver.id,
        "username": caregiver.username,
        "display_name": caregiver.display_name,
        "phone": caregiver.phone
    }

# ============================================================
# Patient Endpoints
# ============================================================
@app.post("/api/patients", response_model=PatientResponse)
def create_patient(req: PatientCreate, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    patient = Patient(
        caregiver_id=caregiver.id,
        name=req.name,
        phone=req.phone
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

@app.get("/api/patients", response_model=List[PatientResponse])
def get_patients(caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    return db.query(Patient).filter(Patient.caregiver_id == caregiver.id).all()

@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: int, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.caregiver_id == caregiver.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    db.delete(patient)
    db.commit()
    return {"status": "ok"}

# ============================================================
# Reminder Endpoints
# ============================================================
@app.post("/api/reminders", response_model=ReminderResponse)
def create_reminder(req: ReminderCreate, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    # Verify patient belongs to this caregiver
    patient = db.query(Patient).filter(Patient.id == req.patient_id, Patient.caregiver_id == caregiver.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found or not yours")
    
    reminder = Reminder(
        patient_id=req.patient_id,
        text=req.text,
        time=req.time,
        days=req.days
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder

@app.get("/api/reminders", response_model=List[ReminderResponse])
def get_reminders(caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    return db.query(Reminder).join(Patient).filter(Patient.caregiver_id == caregiver.id).all()

@app.put("/api/reminders/{reminder_id}")
def toggle_reminder(reminder_id: int, active: bool, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    reminder = db.query(Reminder).join(Patient).filter(
        Reminder.id == reminder_id,
        Patient.caregiver_id == caregiver.id
    ).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    reminder.active = active
    db.commit()
    return {"status": "ok"}

@app.delete("/api/reminders/{reminder_id}")
def delete_reminder(reminder_id: int, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    reminder = db.query(Reminder).join(Patient).filter(
        Reminder.id == reminder_id,
        Patient.caregiver_id == caregiver.id
    ).first()
    if not reminder:
        raise HTTPException(status_code=404, detail="Reminder not found")
    db.delete(reminder)
    db.commit()
    return {"status": "ok"}

# ============================================================
# Emergency Contact Endpoints
# ============================================================
@app.post("/api/emergency")
def create_emergency_contact(req: EmergencyContactCreate, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == req.patient_id, Patient.caregiver_id == caregiver.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    
    contact = EmergencyContact(
        patient_id=req.patient_id,
        name=req.name,
        phone=req.phone,
        relationship=req.relationship
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact

@app.get("/api/emergency/{patient_id}")
def get_emergency_contacts(patient_id: int, caregiver: Caregiver = Depends(get_current_caregiver), db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == patient_id, Patient.caregiver_id == caregiver.id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.query(EmergencyContact).filter(EmergencyContact.patient_id == patient_id).all()

# ============================================================
# Patient-facing endpoints (for the actual user)
# ============================================================
@app.get("/api/patient/reminders/{patient_id}")
def get_patient_reminders(patient_id: int, db: Session = Depends(get_db)):
    """Get active reminders for a patient (used by the patient's app)"""
    now = datetime.now()
    current_day = now.strftime("%a").lower()  # mon, tue, etc.
    current_time = now.strftime("%H:%M")
    
    reminders = db.query(Reminder).filter(
        Reminder.patient_id == patient_id,
        Reminder.active == True
    ).all()
    
    # Filter by day
    result = []
    for r in reminders:
        days_list = [d.strip() for d in r.days.split(",")]
        if current_day in days_list or "mon,tue,wed,thu,fri,sat,sun" == r.days:
            result.append({
                "id": r.id,
                "text": r.text,
                "time": r.time,
                "days": r.days
            })
    return result

@app.get("/api/patient/check_reminders/{patient_id}")
def check_reminders(patient_id: int, db: Session = Depends(get_db)):
    """Called by patient app to check if a reminder is due now"""
    now = datetime.now()
    current_day = now.strftime("%a").lower()
    current_time = now.strftime("%H:%M")
    
    reminder = db.query(Reminder).filter(
        Reminder.patient_id == patient_id,
        Reminder.active == True,
        Reminder.time == current_time
    ).first()
    
    if not reminder:
        return {"due": False}
    
    # Check if day matches
    days_list = [d.strip() for d in reminder.days.split(",")]
    if current_day not in days_list and "mon,tue,wed,thu,fri,sat,sun" != reminder.days:
        return {"due": False}
    
    # Check if already triggered today
    last = reminder.last_triggered
    if last and last.date() == now.date():
        return {"due": False}
    
    # Log notification
    log = NotificationLog(
        patient_id=patient_id,
        reminder_id=reminder.id
    )
    db.add(log)
    reminder.last_triggered = now
    db.commit()
    
    return {
        "due": True,
        "reminder_id": reminder.id,
        "text": reminder.text,
        "time": reminder.time
    }

@app.post("/api/patient/acknowledge_reminder/{reminder_id}")
def acknowledge_reminder(reminder_id: int, db: Session = Depends(get_db)):
    """Patient acknowledges they received the reminder"""
    log = db.query(NotificationLog).filter(
        NotificationLog.reminder_id == reminder_id,
        NotificationLog.acknowledged == False
    ).order_by(NotificationLog.sent_at.desc()).first()
    
    if log:
        log.acknowledged = True
        log.acknowledged_at = datetime.utcnow()
        db.commit()
    
    return {"status": "ok"}


# ============================================================
# Start the server
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
