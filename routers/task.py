from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Annotated

import anyio
from fastapi import APIRouter, Form, HTTPException, Request, UploadFile

from common import OutputFileType
from constants import DEFAULT_MODEL, DEFAULT_OUTPUT_FILE_TYPE, Model
from routers.dependencies import CurrentSession
from tasks.task import TaskData

router = APIRouter()


@router.get("/task")
async def get_task(
    request: Request,
    session: CurrentSession,
) -> TaskData | None:
    task_manager = request.app.state.task_manager
    task = await task_manager.get_current_task(session.session_id)
    if task is None:
        return None

    return task.to_dict()


@router.get("/tasks")
async def get_tasks(
    request: Request,
    session: CurrentSession,
) -> list[TaskData]:
    task_manager = request.app.state.task_manager
    tasks = await task_manager.get_tasks(session.session_id)

    return [task.to_dict() for task in tasks]


@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    request: Request,
    session: CurrentSession,
) -> TaskData:
    task_manager = request.app.state.task_manager
    taskData = await task_manager.cancel(task_id, session.session_id)
    if taskData is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return taskData


@router.post("/task")
async def create_task(
    request: Request,
    session: CurrentSession,
    file: UploadFile,
    model: Annotated[Model, Form()] = DEFAULT_MODEL,
    output_file_type: Annotated[OutputFileType, Form()] = DEFAULT_OUTPUT_FILE_TYPE,
) -> str:
    temporary_path: Path | None = None

    try:
        filename = Path((file.filename or "").replace("\\", "/")).name
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        suffix = Path(filename).suffix.lower()
        content_type = (file.content_type or "").lower()
        if (
            suffix not in {
                ".aac",
                ".flac",
                ".m4a",
                ".mp3",
                ".ogg",
                ".opus",
                ".wav",
            }
            or not content_type.startswith("audio/")
        ):
            raise HTTPException(
                status_code=415,
                detail="Only audio files are supported",
            )

        waiting_dir = request.app.state.settings.waiting_dir
        uploading_dir = waiting_dir / ".uploading"
        uploading_dir.mkdir(parents=True, exist_ok=True)

        with NamedTemporaryFile(
            dir=uploading_dir,
            suffix=".part",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        async with await anyio.open_file(temporary_path, "wb") as output:
            while chunk := await file.read(1024 * 1024):
                await output.write(chunk)

        task_manager = request.app.state.task_manager
        task = await task_manager.create(
            filename=filename,
            session_id=session.session_id,
            model=model,
            output_file_type=output_file_type,
            temporary_audio_path=temporary_path,
        )

        return task.task_id
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()
