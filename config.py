import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    space_id: str | None = os.getenv("SPACE_ID")
    model_name: str = "large-v3"
    model_download_dir: Path | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
