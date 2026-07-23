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
        async with self._lock:
            session_id = str(uuid.uuid4())
            while session_id in self._sessions:
                session_id = str(uuid.uuid4())

            session = Session(session_id=session_id)
            self._sessions[session.session_id] = session

        return session

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            return self._sessions.get(session_id)

    async def remove(self, session_id: str) -> Session | None:
        async with self._lock:
            return self._sessions.pop(session_id, None)
