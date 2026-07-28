from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from multiprocessing.context import SpawnContext
from multiprocessing.queues import Queue
from pathlib import Path
from queue import Empty
from typing import Any

import torch

from common import ProcessEvent, create_process_event
from config import Settings
from constants import ProcessEventType
from logger import get_logger
from tasks.task import Task

type OnEventCallback = Callable[[ProcessEvent], None]

class BaseProvider(ABC):
    def __init__(self, provider_name: str, settings: Settings):
        self._settings = settings
        self._provider_name = provider_name
        self._logger = get_logger(provider_name)

    def __setstate__(self, state: dict[str, Any]) -> None:
        vars(self).update(state)
        self._logger = get_logger(self._provider_name)

    @abstractmethod
    def run(
        self,
        task: Task,
        on_event: OnEventCallback,
    ) -> None:
        pass

    @staticmethod
    def output(result: Any, output_path: Path) -> None:
        pass

    def _emit_event(
        self,
        event_queue: Queue[ProcessEvent],
        event: ProcessEvent,
    ) -> None:
        event_queue.put(event)

    def _emit_log_event(
        self,
        event_queue: Queue[ProcessEvent],
        message: str,
    ) -> None:
        self._emit_event(event_queue, create_process_event(ProcessEventType.LOG, message=message))

    @staticmethod
    def _run_process(
        ctx: SpawnContext,
        name: str,
        task: Task,
        target: Callable[..., None],
        on_event: OnEventCallback,
        args: Iterable[Any] = (),
    ) -> None:
        task.raise_if_cancelled()

        event_queue = ctx.Queue()
        process = ctx.Process(
            target=target,
            name=name,
            args=(*args, event_queue),
        )

        try:
            process.start()
            while process.is_alive():
                task.raise_if_cancelled()
                try:
                    event = event_queue.get(timeout=0.1)
                except Empty:
                    continue

                on_event(event)

            process.join()
            task.raise_if_cancelled()

            while True:
                try:
                    event = event_queue.get_nowait()
                except Empty:
                    break

                on_event(event)

            task.raise_if_cancelled()
            if process.exitcode != 0:
                raise RuntimeError(
                    f"{name} exit failed，exitcode={process.exitcode}"
                )
        finally:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join()

            process.close()
            event_queue.close()
            event_queue.join_thread()

    @staticmethod
    def _get_device():
        return "cuda" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _get_compute_type():
        return "float16" if torch.cuda.is_available() else "int8"
