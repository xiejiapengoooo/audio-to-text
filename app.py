import uvicorn
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings
from routers.common import router as health_router
from routers.session import router as session_router
from routers.upload import router as upload_router
from sessions.manager import SessionManager

def create_app() -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager = SessionManager(
            settings=settings,
        )
        await manager.start()
        app.state.session_manager = manager
        app.state.settings = settings
        try:
            yield
        finally:
            await manager.close()

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(session_router)
    app.include_router(upload_router)
    app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent / "static", html=True))

    return app


def run() -> None:
    settings = get_settings()

    uvicorn.run(
        create_app(),
        host=settings.host,
        port=settings.port,
        reload=False,
    )

if __name__ == "__main__":
    run()
