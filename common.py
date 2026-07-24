from typing import Literal, TypeGuard, get_args, Any
from config import get_settings


Model = Literal["whisperx"]


def is_model(value: Any) -> TypeGuard[Model]:
    return isinstance(value, str) and value in get_args(Model)


def get_waiting_dir():
    get_settings().waiting_dir.mkdir(parents=True, exist_ok=True)
    return get_settings().waiting_dir


def get_waiting_file(filename: str):
    return get_waiting_dir() / filename


def get_output_dir():
    get_settings().output_dir.mkdir(parents=True, exist_ok=True)
    return get_settings().output_dir
