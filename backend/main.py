from fastapi import FastAPI

from backend.api import auth, caregiver, chat, health


def create_app() -> FastAPI:
    app = FastAPI(title="CoA-Agent API", version="1.0.0")
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(caregiver.router)
    return app


app = create_app()
