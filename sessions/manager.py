import asyncio
import uuid
from config import Settings
from logger import get_logger
from .session import Session


class SessionManager:
    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self._settings = settings
        self._logger = get_logger("SessionManager")
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    async def create(self) -> Session:
        session = Session(
            session_id=str(uuid.uuid4()),
        )

        async with self._lock:
            self._sessions[session.session_id] = session

        return session
