from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import Session, require_session
from backend.services.conversation import ConversationRequest, ConversationService


router = APIRouter(prefix="/v1", tags=["chat"])


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=10000)
    platform: str = Field(default="api", min_length=1, max_length=40)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    response: str
    tts: str | None = None
    events: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def get_conversation_service() -> ConversationService:
    return ConversationService()


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    session: Session = Depends(require_session),
    service: ConversationService = Depends(get_conversation_service),
) -> ChatResponse:
    if session.role != "service" and session.sender_id != payload.user_id:
        raise HTTPException(status_code=403, detail="session does not belong to user_id")
    try:
        values = payload.model_dump() if hasattr(payload, "model_dump") else payload.dict()
        result = service.respond(ConversationRequest(**values))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ChatResponse(
        response=result.response,
        tts=result.tts,
        events=result.events,
        metadata=result.metadata,
    )
