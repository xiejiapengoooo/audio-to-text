from collections import deque
from datetime import datetime, timezone
import json
import os
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from anyio import Condition, to_thread
from config import Settings
from logger import get_logger
from .task import Task


class TaskManager:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._logger = get_logger("TaskManager")
        self._tasks: deque[Task] = deque()
        self._condition = Condition()
        self._tasks_file_path = settings.data_dir / "tasks.json"

    async def start(self) -> None:
        async with self._condition:
            self._load()
            if self._tasks:
                self._condition.notify_all()

    async def create(
        self,
        filename: str,
        session_id: str,
        model: str,
    ) -> Task:
        async with self._condition:
            task_id = str(uuid.uuid4())
            while any(task.task_id == task_id for task in self._tasks):
                task_id = str(uuid.uuid4())

            task = Task(
                task_id=task_id,
                session_id=session_id,
                filename=filename,
                model=model,
            )
            self._tasks.append(task)
            try:
                await self._save()
            except Exception:
                self._tasks.pop()
                raise

            self._condition.notify_all()

        return task

    async def get_next(self) -> Task:
        async with self._condition:
            await self._condition.wait_for(lambda: bool(self._tasks))
            task = self._tasks.popleft()
            try:
                await self._save()
            except Exception:
                self._tasks.appendleft(task)
                raise

            return task

    def _load(self) -> None:
        if not self._tasks_file_path.exists():
            return

        with self._tasks_file_path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("tasks.json must contain an object")

        tasks_data = data.get("tasks")
        if not isinstance(tasks_data, list):
            raise ValueError("tasks.json must contain a tasks array")

        tasks: deque[Task] = deque()
        task_ids: set[str] = set()
        for item in tasks_data:
            task = Task.from_dict(item)
            if task.task_id in task_ids:
                raise ValueError("Task ids must be unique")
            tasks.append(task)
            task_ids.add(task.task_id)

        self._tasks = tasks

    async def _save(self) -> None:
        await to_thread.run_sync(self._save_sync)

    def _save_sync(self) -> None:
        self._tasks_file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        data = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "tasks": [task.to_dict() for task in self._tasks],
        }

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._tasks_file_path.parent,
                prefix=".tasks.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            temporary_path.replace(self._tasks_file_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
