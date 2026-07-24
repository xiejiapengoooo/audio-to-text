from collections.abc import Callable, Iterable
from multiprocessing.context import SpawnContext
from typing import Any
import torch
from config import Settings
from logger import get_logger

class BaseProvider:
    def __init__(self, provider_name: str, settings: Settings):
        self._settings = settings
        self._logger = get_logger(provider_name)

    def _get_waiting_dir(self):
        self._settings.waiting_dir.mkdir(parents=True, exist_ok=True)
        return self._settings.waiting_dir

    def _get_waiting_file(self, filename: str):
        return self._get_waiting_dir() / filename

    def _get_output_dir(self):
        self._settings.output_dir.mkdir(parents=True, exist_ok=True)
        return self._settings.output_dir

    @staticmethod
    def _run_process(
        ctx: SpawnContext,
        target: Callable[..., None],
        name: str,
        args: Iterable[Any] = (),
    ) -> None:
        process = ctx.Process(target=target, name=name, args=args)

        try:
            process.start()
            process.join()

            if process.exitcode != 0:
                raise RuntimeError(
                    f"{name} exit failed，exitcode={process.exitcode}"
                )
        finally:
            if process.is_alive():
                process.terminate()
                process.join()

            process.close()

    @staticmethod
    def _get_device():
        return "cuda" if torch.cuda.is_available() else "cpu"

    @staticmethod
    def _get_compute_type():
        return "float16" if torch.cuda.is_available() else "int8"
