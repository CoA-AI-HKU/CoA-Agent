from __future__ import annotations

import asyncio
import os
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.conversation import process_user_message


router = APIRouter(tags=["web-chat"])
MAX_MESSAGE_LENGTH = 4000
AGENT_TIMEOUT_SECONDS = float(os.getenv("COA_WEB_AGENT_TIMEOUT_SECONDS", "30"))


class WebChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    user_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
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

    # Browser-supplied privilege fields are ignored. Identity and permissions
    # are resolved by the shared server-side message-processing pipeline.
    try:
        return await process_user_message(
            user_id=user_id,
            message=message,
            channel="web",
            session_id=(payload.session_id or "").strip() or None,
            timeout_seconds=AGENT_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "CoA-Agent 暫時無法處理這個訊息，請稍後再試。"},
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "CoA-Agent 暫時無法處理這個訊息，請稍後再試。"},
        )
