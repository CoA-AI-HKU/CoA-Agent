from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.services.accounts_database import SessionLocal, WebContact
from backend.services.firebase_auth import FirebaseUser, is_configured, verify_id_token

router = APIRouter(prefix="/api/account", tags=["account"])


def require_firebase_user(authorization: str | None = Header(default=None)) -> FirebaseUser:
    if not is_configured():
        raise HTTPException(status_code=503, detail="account sign-in is not set up on this server yet")
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="bearer ID token is required")
    user = verify_id_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired sign-in")
    return user


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=200)


class ContactResponse(BaseModel):
    id: int
    name: str
    detail: str

    class Config:
        from_attributes = True


@router.get("/me")
def me(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, str | None]:
    return {"uid": user.uid, "phone_number": user.phone_number, "display_name": user.display_name}


@router.get("/contacts", response_model=list[ContactResponse])
def list_contacts(user: FirebaseUser = Depends(require_firebase_user)) -> list[WebContact]:
    db = SessionLocal()
    try:
        return (
            db.query(WebContact)
            .filter(WebContact.firebase_uid == user.uid)
            .order_by(WebContact.id)
            .all()
        )
    finally:
        db.close()


@router.post("/contacts", response_model=ContactResponse, status_code=201)
def add_contact(payload: ContactRequest, user: FirebaseUser = Depends(require_firebase_user)) -> WebContact:
    db = SessionLocal()
    try:
        contact = WebContact(firebase_uid=user.uid, name=payload.name.strip(), detail=payload.detail.strip())
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return contact
    finally:
        db.close()


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    db = SessionLocal()
    try:
        deleted = (
            db.query(WebContact)
            .filter(WebContact.id == contact_id, WebContact.firebase_uid == user.uid)
            .delete(synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="contact not found")
    return {"removed": deleted}
