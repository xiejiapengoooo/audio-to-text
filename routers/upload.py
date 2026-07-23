import anyio
from pathlib import Path
from tempfile import NamedTemporaryFile
from fastapi import APIRouter, File, HTTPException, Request, UploadFile


router = APIRouter(prefix="/upload")


@router.post("/{session_id}")
async def upload_audio(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> str:
    temporary_path: Path | None = None

    try:
        manager = request.app.state.session_manager
        session = await manager.get(session_id)
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

        stored_filename = f"{session.session_id}_{filename}"
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

        return stored_filename
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        await file.close()
