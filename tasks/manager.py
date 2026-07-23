from config import Settings
from logger import get_logger


class TaskManager:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._logger = get_logger("TaskManager")
