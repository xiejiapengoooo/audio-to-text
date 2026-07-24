import uvicorn
from anyio import create_task_group
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from common import get_output_dir
from config import get_settings
from routers.common import router as health_router
from routers.session import router as session_router
from routers.task import router as task_router
from routers.result import router as result_router
from providers.whisperx import WhisperXProvider
from sessions.manager import SessionManager
from tasks.manager import TaskManager
from tasks.runner import TaskRunner

def create_app() -> FastAPI:
    settings = get_settings()
    output_dir = get_output_dir()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        session_manager = SessionManager(
            settings=settings,
        )
        task_manager = TaskManager(
            settings=settings,
        )
        whisperx_provider = WhisperXProvider(settings)
        task_runner = TaskRunner(
            settings=settings,
            task_manager=task_manager,
            session_manager=session_manager,
            providers={"whisperx": whisperx_provider},
        )
        async with create_task_group() as task_group:
              await session_manager.start(task_group)
              await task_manager.start()

              app.state.session_manager = session_manager
              app.state.task_manager = task_manager
              app.state.task_runner = task_runner
              app.state.settings = settings

              task_group.start_soon(
                  task_runner.run,
                  name="task-runner",
              )

              yield

              task_group.cancel_scope.cancel()

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
    app.include_router(task_router)
    app.include_router(result_router)
    app.mount("/output", StaticFiles(directory=output_dir))
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
