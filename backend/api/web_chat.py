from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.conversation import process_user_message


router = APIRouter(tags=["web-chat"])
logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000
AGENT_TIMEOUT_SECONDS = float(os.getenv("COA_WEB_AGENT_TIMEOUT_SECONDS", "30"))


class WebChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    user_id: str = Field(min_length=1, max_length=200)
    session_id: str = Field(min_length=1, max_length=200)
    input_mode: Literal["voice", "text"] = "text"

    class Config:
        extra = "ignore"


class WebChatResponse(BaseModel):
    reply: str
    language: str
    session_id: str


@router.post("/api/chat", response_model=WebChatResponse)
async def web_chat(payload: WebChatRequest) -> dict[str, str] | JSONResponse:
    message = payload.message.strip()
    user_id = payload.user_id.strip()
    if not message:
        return JSONResponse(status_code=400, content={"error": "請先輸入訊息。"})
    if not user_id:
        return JSONResponse(status_code=400, content={"error": "請檢查輸入資料。"})

    logger.info(
        "API request received",
        extra={
            "event": "api_request_received",
            "user_id": user_id,
            "session_id": payload.session_id,
            "input_mode": payload.input_mode,
        },
    )

    # Browser-supplied privilege fields are ignored. Identity and permissions
    # are resolved by the shared server-side message-processing pipeline.
    try:
        response = await process_user_message(
            user_id=user_id,
            message=message,
            channel="web",
            session_id=payload.session_id.strip(),
            timeout_seconds=AGENT_TIMEOUT_SECONDS,
        )
        logger.info(
            "response created",
            extra={"event": "response_created", "session_id": response["session_id"]},
        )
        return response
    except Exception:
        logger.exception(
            "exception fallback used",
            extra={"event": "exception_fallback_used", "session_id": payload.session_id},
        )
        response = {
            "reply": "我暫時未能處理這個訊息。請稍後再試，我會繼續在這裡陪你。",
            "language": "zh-HK",
            "session_id": payload.session_id,
        }
        logger.info(
            "response created",
            extra={"event": "response_created", "session_id": payload.session_id, "fallback": True},
        )
        return response
