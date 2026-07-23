from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import Session, require_session
from src.user.user_registry import create_pairing_code, get_linked_user_ids, redeem_pairing_code, unlink_caregiver


router = APIRouter(prefix="/v1/caregiver", tags=["caregiver"])


class PairRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    replace_existing: bool = False


@router.post("/pairing-code")
def pairing_code(session: Session = Depends(require_session)) -> dict[str, str]:
    try:
        return {"code": create_pairing_code(session.sender_id)}
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/pair")
def pair(payload: PairRequest, session: Session = Depends(require_session)) -> dict[str, str]:
    try:
        return {"user_id": redeem_pairing_code(session.sender_id, payload.code, replace_existing=payload.replace_existing)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/patients")
def patients(session: Session = Depends(require_session)) -> dict[str, list[str]]:
    if session.role != "caregiver":
        raise HTTPException(status_code=403, detail="caregiver session required")
    return {"user_ids": get_linked_user_ids(session.sender_id)}


@router.delete("/patients/{user_id}")
def unlink(user_id: str, session: Session = Depends(require_session)) -> dict[str, int]:
    try:
        return {"removed": unlink_caregiver(session.sender_id, user_id)}
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
