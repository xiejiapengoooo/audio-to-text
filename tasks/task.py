from __future__ import annotations

from collections.abc import Callable
from threading import Event, Lock

from common import Model, is_model, get_waiting_file

type TaskData = dict[str, str | bool]

class TaskCancelledError(Exception):
    pass


class Task:
    def __init__(
        self,
        task_id: str,
        session_id: str,
        filename: str,
        model: Model,
        status_message: str = "",
    ):
        self.task_id = task_id
        self.session_id = session_id
        self.filename = filename
        self.model: Model = model
        self.status_message = status_message
        self._status_message_lock = Lock()
        self._terminal_state_lock = Lock()
        self._cancel_event = Event()
        self._completed = False

    @property
    def filepath(self):
        return get_waiting_file(self.filename)

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_event.is_set()

    def set_status_message(self, message: str) -> None:
        with self._status_message_lock:
            self.status_message = message

    def request_cancel(self) -> bool:
        with self._terminal_state_lock:
            if self._completed:
                return False
            self._cancel_event.set()

        self.set_status_message("Cancellation requested")
        return True

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise TaskCancelledError()

    def commit(self, callback: Callable[[], None]) -> None:
        with self._terminal_state_lock:
            self.raise_if_cancelled()
            callback()
            self._completed = True

    def to_dict(self) -> TaskData:
        status_message = ""
        with self._status_message_lock:
            status_message = self.status_message or ""

        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "model": self.model,
            "status_message": status_message,
            "filename": self.filename,
        }

    @classmethod
    def from_dict(cls, data: object) -> Task:
        if not isinstance(data, dict):
            raise TypeError("Task data must be an object")

        task_id = data.get("task_id")
        filename = data.get("filename")
        session_id = data.get("session_id")
        model = data.get("model")
        status_message = data.get("status_message", "")

        if not isinstance(task_id, str) or not task_id:
            raise ValueError("Task id must be a non-empty string")
        if not isinstance(filename, str) or not filename:
            raise ValueError("Task filename must be a non-empty string")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Task session_id must be a non-empty string")
        if not is_model(model):
            raise ValueError("Task model is not supported")
        if not isinstance(status_message, str):
            raise TypeError("Task status_message must be a string")

        return cls(
            task_id=task_id,
            session_id=session_id,
            filename=filename,
            model=model,
            status_message=status_message,
        )
