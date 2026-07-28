import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

from backend.api import auth, caregiver, chat, health, web_chat


logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# uvicorn backend.main:app is the one always-on, singly-supervised process in
# this deployment (the Nanobot-launched MCP stdio server is respawned by
# Nanobot's own lifecycle, which makes it an unreliable home for a
# long-running background poller). Reminders were previously never
# delivered in production because nothing called start_scheduler() from any
# entrypoint. Guarded by an env var so an operator running the scheduler as
# its own separate systemd unit can opt out here instead of double-firing
# reminders from two processes polling the same SQLite table.
REMINDER_SCHEDULER_AUTOSTART = (
    os.getenv("REMINDER_SCHEDULER_AUTOSTART", "true").strip().lower() in {"1", "true", "yes", "on"}
    # Never spin up a real background poller (and its APScheduler thread) as
    # a side effect of importing this module under pytest / TestClient. Checked
    # via sys.modules (set as soon as the pytest process starts, unlike
    # PYTEST_CURRENT_TEST, which pytest only sets once a test is running —
    # too late for this module-import-time check).
    and "pytest" not in sys.modules
)


def create_app() -> FastAPI:
    app = FastAPI(title="CoA-Agent Web API", version="1.0.0")
    app.include_router(health.router)
    app.include_router(web_chat.router)
    app.include_router(chat.router)
    app.include_router(auth.router)
    app.include_router(caregiver.router)

    if REMINDER_SCHEDULER_AUTOSTART:
        @app.on_event("startup")
        def _start_reminder_scheduler() -> None:
            from src.reminders.scheduler import start_scheduler

            app.state.reminder_scheduler = start_scheduler()

        @app.on_event("shutdown")
        def _stop_reminder_scheduler() -> None:
            scheduler = getattr(app.state, "reminder_scheduler", None)
            if scheduler is not None:
                scheduler.shutdown()

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
