from __future__ import annotations

import secrets
import threading
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from src.user.user_registry import get_user_role, normalize_sender_id, register_account


router = APIRouter(prefix="/v1/auth", tags=["auth"])
_sessions: dict[str, "Session"] = {}
_lock = threading.Lock()


@dataclass(frozen=True)
class Session:
    sender_id: str
    role: str
    expires_at: datetime


class RegisterRequest(BaseModel):
    sender_id: str = Field(min_length=1, max_length=200)
    role: str
    display_name: str = Field(default="", max_length=80)


class LoginRequest(BaseModel):
    sender_id: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 86400
    role: str


def _issue(sender_id: str) -> TokenResponse:
    sender_id = normalize_sender_id(sender_id)
    role = get_user_role(sender_id)
    if role == "unknown":
        raise HTTPException(status_code=401, detail="account is not registered")
    token = secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = Session(sender_id, role, datetime.now(timezone.utc) + timedelta(days=1))
    return TokenResponse(access_token=token, role=role)


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(payload: RegisterRequest) -> TokenResponse:
    try:
        register_account(payload.sender_id, payload.role, payload.display_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _issue(payload.sender_id)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    return _issue(payload.sender_id)


def require_session(authorization: str | None = Header(default=None)) -> Session:
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="bearer token is required")
    service_token = os.getenv("COA_SERVICE_TOKEN", "").strip()
    if service_token and secrets.compare_digest(token, service_token):
        return Session("*", "service", datetime.max.replace(tzinfo=timezone.utc))
    with _lock:
        session = _sessions.get(token)
        if session and session.expires_at <= datetime.now(timezone.utc):
            _sessions.pop(token, None)
            session = None
    if session is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    return session
