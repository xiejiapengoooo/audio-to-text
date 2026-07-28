import json
import os
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from anyio import Condition, to_thread

from common import OutputFileType
from config import Settings
from constants import Model
from logger import get_logger

from .task import Task, TaskData


class TaskManager:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._logger = get_logger("TaskManager")
        self._tasks: deque[Task] = deque()
        self._running_task: Task | None = None
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
        model: Model,
        output_file_type: OutputFileType,
        temporary_audio_path: Path,
    ) -> Task:
        async with self._condition:
            task_id = str(uuid.uuid4())
            while (
                any(task.task_id == task_id for task in self._tasks)
                or (
                    self._running_task is not None
                    and self._running_task.task_id == task_id
                )
            ):
                task_id = str(uuid.uuid4())

            task = Task(
                task_id=task_id,
                session_id=session_id,
                filename=f"{session_id}_{task_id}_{filename}",
                model=model,
                output_file_type=output_file_type,
            )
            self._settings.waiting_dir.mkdir(parents=True, exist_ok=True)
            temporary_audio_path.replace(task.filepath)
            self._tasks.append(task)
            try:
                await self._save()
            except Exception:
                self._tasks.pop()
                try:
                    task.filepath.unlink(missing_ok=True)
                except OSError:
                    self._logger.exception(
                        "Failed to remove audio for rolled back task %s",
                        task.task_id,
                    )
                raise

            self._condition.notify_all()

        return task

    async def get_next(self) -> Task:
        async with self._condition:
            await self._condition.wait_for(
                lambda: bool(self._tasks) and self._running_task is None
            )
            task = self._tasks.popleft()
            self._running_task = task
            try:
                await self._save()
            except Exception:
                self._running_task = None
                self._tasks.appendleft(task)
                raise

            return task

    async def get_current_task(self, session_id: str) -> Task | None:
        async with self._condition:
            task = self._running_task
            if task is None or task.session_id != session_id:
                return None

            return task

    async def cancel(
        self,
        task_id: str,
        session_id: str,
    ) -> TaskData | None:
        async with self._condition:
            running_task = self._running_task
            if (
                running_task is not None
                and running_task.task_id == task_id
                and running_task.session_id == session_id
            ):
                if not running_task.request_cancel():
                    return None
                return running_task.to_dict()

            for index, task in enumerate(self._tasks):
                if task.task_id != task_id or task.session_id != session_id:
                    continue

                self._tasks.remove(task)
                try:
                    await self._save()
                except Exception:
                    self._tasks.insert(index, task)
                    raise

                try:
                    task.filepath.unlink(missing_ok=True)
                except OSError:
                    self._logger.exception(
                        "Failed to remove audio for canceled task %s",
                        task.task_id,
                    )

                return task.to_dict()

            return None

    async def finish(self, task: Task) -> None:
        async with self._condition:
            if self._running_task is not task:
                self._logger.warning(
                    "Ignore finish for task %s because it is not running",
                    task.task_id,
                )
                return

            self._running_task = None
            self._condition.notify_all()

    async def get_tasks(self, session_id: str) -> list[Task]:
        async with self._condition:
            return [
                task for task in self._tasks if task.session_id == session_id
            ]

    def _load(self) -> None:
        if not self._tasks_file_path.exists():
            return

        with self._tasks_file_path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise TypeError("tasks.json must contain an object")

        tasks_data = data.get("tasks")
        if not isinstance(tasks_data, list):
            raise TypeError("tasks.json must contain a tasks array")

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
            "updatedAt": datetime.now(UTC).isoformat(),
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
