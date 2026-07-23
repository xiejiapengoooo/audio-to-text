import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
import uuid
from anyio import to_thread
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
        self._tasks: dict[str, Task] = {}
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._started = False
        self._tasks_file_path = settings.data_dir / "tasks.json"

    async def start(self) -> None:
        async with self._lock:
            if self._started:
                return

            self._load()
            for task in self._tasks.values():
                self._queue.put_nowait(task)
            self._started = True

    async def create(self, filename: str) -> Task:
        async with self._lock:
            task_id = str(uuid.uuid4())
            while task_id in self._tasks:
                task_id = str(uuid.uuid4())

            task = Task(
                task_id=task_id,
                filename=filename,
            )
            self._tasks[task.task_id] = task
            try:
                await self._save()
            except Exception:
                self._tasks.pop(task.task_id, None)
                raise

            self._queue.put_nowait(task)

        return task

    async def get_next(self) -> Task:
        return await self._queue.get()

    def _load(self) -> None:
        if not self._tasks_file_path.exists():
            return

        with self._tasks_file_path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict) or not isinstance(data.get("tasks"), dict):
            raise ValueError("tasks.json must contain a tasks object")

        tasks = {}
        for task_id, item in data["tasks"].items():
            task = Task.from_dict(item)
            if task.task_id != task_id:
                raise ValueError("Task id must match its tasks key")
            tasks[task_id] = task

        self._tasks = tasks

    async def _save(self) -> None:
        await to_thread.run_sync(self._save_sync)

    def _save_sync(self) -> None:
        self._tasks_file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        data = {
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "tasks": {
                task_id: task.to_dict()
                for task_id, task in self._tasks.items()
            },
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
