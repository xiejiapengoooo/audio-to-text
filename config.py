import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    space_id: str | None = os.getenv("SPACE_ID")

    app_name: str = "audio-to-text"
    host: str = "0.0.0.0" if space_id else "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


    model_download_dir: Path | None = None

    data_dir: Path = Path("/data") if space_id else Path.home() / f".{app_name}"
    waiting_dir: Path = data_dir / 'waiting'
    output_dir: Path = data_dir / 'output'


@lru_cache
def get_settings() -> Settings:
    return Settings()
