import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.api import auth, caregiver, chat, health, web_chat
from reminder_backend.app import app as reminder_app


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def create_app() -> FastAPI:
    app = FastAPI(title="CoA-Agent Web API", version="1.0.0")
    app.include_router(health.router)
    app.include_router(web_chat.router)
    app.include_router(chat.router)
    app.include_router(auth.router)
    app.include_router(caregiver.router)
    app.include_router(reminder_app.router)

    @app.get("/", include_in_schema=False)
    async def frontend() -> FileResponse:
        return FileResponse(PROJECT_ROOT / "index.html")

    @app.get("/privacy.html", include_in_schema=False)
    async def privacy() -> FileResponse:
        return FileResponse(PROJECT_ROOT / "privacy.html")

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "exception fallback used",
            extra={"event": "exception_fallback_used", "path": request.url.path},
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "message": "服務暫時未能處理這個要求，請稍後再試。",
            },
        )
    return app


app = create_app()
