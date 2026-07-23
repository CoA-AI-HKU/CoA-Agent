from fastapi import FastAPI

from backend.api import health, web_chat


def create_app() -> FastAPI:
    app = FastAPI(title="CoA-Agent Web API", version="1.0.0")
    app.include_router(health.router)
    app.include_router(web_chat.router)
    return app


app = create_app()
