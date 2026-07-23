from fastapi import APIRouter

from config import Settings

router = APIRouter()


def _run_provider(settings: Settings) -> None:
    from providers.whisperx import WhisperXProvider

    WhisperXProvider(settings).run()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
