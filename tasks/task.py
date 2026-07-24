from __future__ import annotations
from common import Model, is_model


class Task:
    def __init__(
        self,
        task_id: str,
        session_id: str,
        filename: str,
        model: Model,
    ):
        self.task_id = task_id
        self.session_id = session_id
        self.filename = filename
        self.model: Model = model

    def to_dict(self) -> dict[str, str | None]:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
            "session_id": self.session_id,
            "model": self.model,
        }

    @classmethod
    def from_dict(cls, data: object) -> Task:
        if not isinstance(data, dict):
            raise ValueError("Task data must be an object")

        task_id = data.get("task_id")
        filename = data.get("filename")
        session_id = data.get("session_id")
        model = data.get("model")
        if filename is None:
            filename = data.get("audio_filename")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("Task id must be a non-empty string")
        if not isinstance(filename, str) or not filename:
            raise ValueError("Task filename must be a non-empty string")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Task session_id must be a non-empty string")
        if not is_model(model):
            raise ValueError("Task model is not supported")

        return cls(
            task_id=task_id,
            filename=filename,
            session_id=session_id,
            model=model,
        )
