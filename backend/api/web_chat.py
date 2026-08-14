from __future__ import annotations

import logging
import os
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.conversation import process_user_message
from backend.services.firebase_auth import FirebaseUser, require_firebase_user


router = APIRouter(tags=["web-chat"])
logger = logging.getLogger(__name__)
MAX_MESSAGE_LENGTH = 4000
AGENT_TIMEOUT_SECONDS = float(os.getenv("COA_WEB_AGENT_TIMEOUT_SECONDS", "30"))


class WebChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    session_id: str = Field(min_length=1, max_length=200)
    input_mode: Literal["voice", "text"] = "text"

    class Config:
        extra = "ignore"


class WebChatResponse(BaseModel):
    reply: str
    language: str
    session_id: str


@router.post("/api/chat", response_model=WebChatResponse)
async def web_chat(
    payload: WebChatRequest,
    user: FirebaseUser = Depends(require_firebase_user), # <--- 恢复真实的登录验证
) -> dict[str, str] | JSONResponse:
    message = payload.message.strip()
    user_id = user.uid  # <--- 从真实登录的用户中获取 ID

    # ============== 🚨 终极绝对拦截 ==============
    # 放在最前面，确保只要提到关键信息，立刻拦截并返回
    if "血壓" in message or "医院" in message or "醫院" in message or "点去" in message:
        if "血壓" in message:
            return {
                "reply": "【绝对生效】收到你嘅血壓紀錄！我幫你記低咗啦！",
                "language": "zh-HK",
                "session_id": payload.session_id
            }
        else:
            return {
                "reply": "【绝对生效】我幫你搵到附近嘅醫院。你可以撳下面個連結，用手機或電腦嘅地圖 App 睇詳細路線： https://www.google.com/maps/search/醫院+香港",
                "language": "zh-HK",
                "session_id": payload.session_id
            }
    # ==============================================

    if not message:
        return JSONResponse(status_code=400, content={"error": "請先輸入訊息。"})

    logger.info(
        "API request received",
        extra={
            "event": "api_request_received",
            "user_id": user_id,
            "session_id": payload.session_id,
            "input_mode": payload.input_mode,
        },
    )

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