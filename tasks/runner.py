from collections.abc import Mapping

from anyio import sleep, to_thread

from common import ProcessEvent
from config import Settings
from constants import DEFAULT_MODEL, Model
from logger import get_logger
from providers.base import BaseProvider
from sessions.manager import SessionManager

from .manager import TaskManager
from .task import Task, TaskCancelledError


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

            def on_event(event: ProcessEvent) -> None:
                message = event.get("message")
                if isinstance(message, str) and not task.cancel_requested:
                    task.set_status_message(message)

            task.raise_if_cancelled()
            await to_thread.run_sync(provider.run, task, on_event)
            self._logger.info("Task %s completed", task.task_id)
        except TaskCancelledError:
            self._logger.info("Task %s canceled", task.task_id)
        except Exception:
            self._logger.exception("Task %s failed", task.task_id)
        finally:
            await self._task_manager.finish(task)
            try:
                task.filepath.unlink(missing_ok=True)
            except OSError:
                self._logger.exception(
                    "Failed to remove audio for task %s",
                    task.task_id,
                )
