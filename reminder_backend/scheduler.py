from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from database import SessionLocal, Reminder, NotificationLog, Patient
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_and_send_reminders():
    """Called every minute to check for due reminders"""
    db = SessionLocal()
    try:
        now = datetime.now()
        current_day = now.strftime("%a").lower()
        current_time = now.strftime("%H:%M")
        
        # Find reminders due at this minute
        reminders = db.query(Reminder).filter(
            Reminder.active == True,
            Reminder.time == current_time
        ).all()
        
        for reminder in reminders:
            days_list = [d.strip() for d in reminder.days.split(",")]
            if current_day not in days_list and "mon,tue,wed,thu,fri,sat,sun" != reminder.days:
                continue
            
            # Check if already triggered today
            if reminder.last_triggered and reminder.last_triggered.date() == now.date():
                continue
            
            # Send notification (example: log, you can add SMS/Web Push here)
            patient = db.query(Patient).filter(Patient.id == reminder.patient_id).first()
            logger.info(f"🔔 REMINDER: Patient '{patient.name}' - '{reminder.text}' at {reminder.time}")
            
            # Log notification
            log = NotificationLog(
                patient_id=reminder.patient_id,
                reminder_id=reminder.id
            )
            db.add(log)
            reminder.last_triggered = now
            db.commit()
            
            # TODO: Send push notification / SMS / Email to caregiver and patient
            
    except Exception as e:
        logger.error(f"Reminder scheduler error: {e}")
    finally:
        db.close()

# Start scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(
    check_and_send_reminders,
    trigger=IntervalTrigger(minutes=1),
    id="reminder_checker",
    replace_existing=True
)
scheduler.start()

logger.info("✅ Reminder scheduler started (runs every minute)")
