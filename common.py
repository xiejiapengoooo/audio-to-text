from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, TypeGuard, get_args

from config import get_settings

if TYPE_CHECKING:
    from constants import ProcessEventType


Model = Literal["whisperx"]


type ProcessEvent = dict[str, Any]


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


def create_process_event(event_type: ProcessEventType, **payload: Any) -> ProcessEvent:
    return {"type": event_type, **payload}
