import os
from pathlib import Path
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "audio-to-text"
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    space_id: str | None = os.getenv("SPACE_ID")

    model_download_dir: Path | None = None

    data_dir: Path = Path("/data") if space_id else Path.home() / f".{app_name}"
    waiting_dir: Path = data_dir / 'waiting'
    output_dir: Path = data_dir / 'output'


@lru_cache
def get_settings() -> Settings:
    return Settings()
