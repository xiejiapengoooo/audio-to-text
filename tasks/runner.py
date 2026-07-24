from collections.abc import Mapping
from anyio import sleep, to_thread
from config import Settings
from logger import get_logger
from sessions.manager import SessionManager
from .manager import TaskManager
from .task import Task
from providers.base import BaseProvider
from constants import DEFAULT_MODEL, Model
from common import get_waiting_file


class TaskRunner:
    def __init__(
        self,
        settings: Settings,
        task_manager: TaskManager,
        session_manager: SessionManager,
        providers: Mapping[Model, BaseProvider],
    ) -> None:
        self._settings = settings
        self._task_manager = task_manager
        self._session_manager = session_manager
        self._providers = dict(providers)
        self._logger = get_logger("TaskRunner")

    async def run(self) -> None:
        while True:
            try:
                task = await self._task_manager.get_next()
            except Exception:
                self._logger.exception("Failed to get next task")
                await sleep(1)
                continue

            await self._run_task(task)

    async def _run_task(self, task: Task) -> None:
        try:
            session = await self._session_manager.get(task.session_id)
            if session is None:
                self._logger.warning(
                    "Discard task %s because session is missing or expired",
                    task.task_id,
                )
                return

            provider = self._providers.get(task.model)
            if provider is None:
                provider = self._providers.get(DEFAULT_MODEL)
            if provider is None:
                raise RuntimeError("Default task provider is not configured")

            await to_thread.run_sync(provider.run, task)
            self._logger.info("Task %s completed", task.task_id)
        except Exception:
            self._logger.exception("Task %s failed", task.task_id)
        finally:
            try:
                get_waiting_file(task.filename).unlink(missing_ok=True)
            except OSError:
                self._logger.exception(
                    "Failed to remove audio for task %s",
                    task.task_id,
                )
