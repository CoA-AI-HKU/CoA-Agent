from __future__ import annotations

import asyncio
import os
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.services.conversation import process_user_message


MAX_MESSAGE_LENGTH = 4000
AGENT_TIMEOUT_SECONDS = float(os.getenv("COA_WEB_AGENT_TIMEOUT_SECONDS", "30"))


class WebChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    user_id: str = Field(min_length=1, max_length=200)
    session_id: str | None = Field(default=None, max_length=200)
    input_mode: Literal["voice", "text"] = "text"

    # Browser-supplied role and privilege fields are intentionally ignored.
    class Config:
        extra = "ignore"


class WebChatResponse(BaseModel):
    reply: str
    language: str
    session_id: str


app = FastAPI(title="CoA-Agent Web Voice API", version="1.0.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("COA_WEB_ALLOWED_ORIGINS", "").split(",")
    if origin.strip() and origin.strip() != "*"
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    message_error = any(tuple(error.get("loc", ()))[-1:] == ("message",) for error in exc.errors())
    message = "請先輸入訊息。" if message_error else "請檢查輸入資料。"
    return JSONResponse(status_code=400, content={"error": message})


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat", response_model=WebChatResponse)
async def chat(payload: WebChatRequest) -> dict[str, str]:
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="請先輸入訊息。")
    if not payload.user_id.strip():
        raise HTTPException(status_code=400, detail="請檢查輸入資料。")

    # Prototype identity only: privileges are always resolved inside the server
    # pipeline and never accepted from browser request fields.
    try:
        return await process_user_message(
            user_id=payload.user_id.strip(),
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
