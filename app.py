import whisperx
import torch
from .config import get_settings


settings = get_settings()


def get_device():
    return "cuda" if torch.cuda.is_available() else "cpu"


def get_compute_type():
    return "float16" if torch.cuda.is_available() else "int8"


def get_transcription_model(device, compute_type):
    return whisperx.load_model(
        settings.model_name,
        device=get_device(),
        compute_type=get_compute_type(),
        download_root=str(settings.model_download_dir) if settings.model_download_dir else None,
        local_files_only=bool(settings.model_download_dir),
    )


def get_align_model(language_code: str, device):
    return whisperx.load_align_model(
        language_code=language_code,
        device=get_device(),
        model_dir=str(settings.model_download_dir) if settings.model_download_dir else None,
        model_cache_only=bool(settings.model_download_dir),
    )
