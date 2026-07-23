from __future__ import annotations

class Task:
    def __init__(self, task_id: str, filename: str):
        self.task_id = task_id
        self.filename = filename

    def to_dict(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "filename": self.filename,
        }

    @classmethod
    def from_dict(cls, data: object) -> Task:
        if not isinstance(data, dict):
            raise ValueError("Task data must be an object")

        task_id = data.get("task_id")
        filename = data.get("filename")
        if filename is None:
            filename = data.get("audio_filename")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("Task id must be a non-empty string")
        if not isinstance(filename, str) or not filename:
            raise ValueError("Task filename must be a non-empty string")

        return cls(
            task_id=task_id,
            filename=filename,
        )
