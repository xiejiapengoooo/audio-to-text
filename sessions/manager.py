import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
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
        self._cleanup_event = asyncio.Event()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._sessions_file_path = settings.data_dir / "sessions.json"

    async def start(self) -> None:
        async with self._lock:
            if self._cleanup_task is not None:
                return

            self._load()
            self._remove_expired_and_save()

            self._cleanup_task = asyncio.create_task(
                self._cleanup_expired(),
                name="session-cleanup",
            )

    async def close(self) -> None:
        task = self._cleanup_task
        if task is None:
            return

        self._cleanup_task = None
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def create(self) -> Session:
        async with self._lock:
            session_id = str(uuid.uuid4())
            while session_id in self._sessions:
                session_id = str(uuid.uuid4())

            session = Session(session_id=session_id)
            self._sessions[session.session_id] = session
            try:
                self._save()
            except Exception:
                self._sessions.pop(session.session_id, None)
                raise

        self._cleanup_event.set()

        return session

    async def get(self, session_id: str) -> Session | None:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            now = datetime.now(timezone.utc)
            if session.is_expired(now):
                self._sessions.pop(session_id)
                try:
                    self._save()
                except Exception:
                    self._sessions[session_id] = session
                    raise
                self._cleanup_event.set()
                return None

            previous_expiration = session.expires_at
            session.renew(now)
            try:
                self._save()
            except Exception:
                session.expires_at = previous_expiration
                raise

        self._cleanup_event.set()
        return session

    async def remove(self, session_id: str) -> Session | None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                try:
                    self._save()
                except Exception:
                    self._sessions[session_id] = session
                    raise

        if session is not None:
            self._cleanup_event.set()
        return session

    def _load(self) -> None:
        if not self._sessions_file_path.exists():
            return

        with self._sessions_file_path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            raise ValueError("sessions.json must contain a sessions array")

        sessions = {}
        for item in data["sessions"]:
            session = Session.from_dict(item)
            sessions[session.session_id] = session

        self._sessions = sessions

    def _save(self) -> None:
        self._sessions_file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        data = {
            "sessions": [
                session.to_dict()
                for session in sorted(
                    self._sessions.values(),
                    key=lambda item: item.session_id,
                )
            ],
        }

        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._sessions_file_path.parent,
                prefix=".sessions.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())

            temporary_path.replace(self._sessions_file_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _remove_expired_and_save(self) -> None:
        now = datetime.now(timezone.utc)
        expired_sessions = {
            session_id: session
            for session_id, session in self._sessions.items()
            if session.is_expired(now)
        }
        if not expired_sessions:
            return

        for session_id in expired_sessions:
            self._sessions.pop(session_id)

        try:
            self._save()
        except Exception:
            self._sessions.update(expired_sessions)
            raise

    async def _cleanup_expired(self) -> None:
        while True:
            self._cleanup_event.clear()
            async with self._lock:
                if self._sessions:
                    next_expiration = min(
                        session.expires_at for session in self._sessions.values()
                    )
                    delay = max(
                        0.0,
                        (next_expiration - datetime.now(timezone.utc)).total_seconds(),
                    )
                else:
                    delay = None

            if delay is None:
                await self._cleanup_event.wait()
                continue

            try:
                await asyncio.wait_for(self._cleanup_event.wait(), timeout=delay)
            except TimeoutError:
                try:
                    async with self._lock:
                        self._remove_expired_and_save()
                except Exception:
                    self._logger.exception("Failed to clean up expired sessions")
                    await asyncio.sleep(1)
