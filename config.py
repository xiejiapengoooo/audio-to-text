import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "audio-to-text"

    space_id: str | None = os.getenv("SPACE_ID")

    model_download_dir: Path | None = None

    data_dir: Path | None = Path("/data") if space_id else Path.home() / f".{app_name}"
    waiting_dir: Path = data_dir / 'waiting'
    output_dir: Path = data_dir / 'output'


@lru_cache
def get_settings() -> Settings:
    return Settings()
