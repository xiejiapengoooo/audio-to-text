import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile

import anyio
from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

router = APIRouter(prefix="/task")


@router.post("/create")
async def create_task(
    request: Request,
    session_id: str = Header(..., alias="session"),
    file: UploadFile = File(...),
) -> str:
    temporary_path: Path | None = None

    try:
        session_manager = request.app.state.session_manager
        session = await session_manager.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session not found")

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

        stored_filename = f"{uuid.uuid4()}_{filename}"
        audio_path = waiting_dir / stored_filename
        with NamedTemporaryFile(
            dir=uploading_dir,
            suffix=".part",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        async with await anyio.open_file(temporary_path, "wb") as output:
            while chunk := await file.read(1024 * 1024):
                await output.write(chunk)

        temporary_path.replace(audio_path)

        task_manager = request.app.state.task_manager
        try:
            task = await task_manager.create(
                stored_filename,
                session.session_id,
            )
        except Exception:
            audio_path.unlink(missing_ok=True)
            raise

        return task.task_id
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()
