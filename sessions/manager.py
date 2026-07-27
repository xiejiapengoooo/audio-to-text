import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from anyio import Condition, fail_after, sleep, to_thread
from anyio.abc import TaskGroup

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
        self._condition = Condition()
        self._sessions_file_path = settings.data_dir / "sessions.json"

    async def start(self, task_group: TaskGroup) -> None:
        async with self._condition:
            self._load()
            await self._remove_expired()
            task_group.start_soon(
                self._cleanup_expired,
                name="session-cleanup",
            )

    async def create(self, session_id: str | None = None) -> Session:
        async with self._condition:
            now = datetime.now(UTC)
            existing_session = (
                self._sessions.get(session_id) if session_id is not None else None
            )
            if existing_session is not None and not existing_session.is_expired(now):
                previous_expiration = existing_session.expires_at
                existing_session.renew(now)
                try:
                    await self._save()
                except Exception:
                    existing_session.expires_at = previous_expiration
                    raise

                session = existing_session
            else:
                if existing_session is not None:
                    self._sessions.pop(existing_session.session_id)

                new_session_id = str(uuid.uuid4())
                while new_session_id in self._sessions:
                    new_session_id = str(uuid.uuid4())

                session = Session(session_id=new_session_id)
                self._sessions[session.session_id] = session
                try:
                    await self._save()
                except Exception:
                    self._sessions.pop(session.session_id, None)
                    if existing_session is not None:
                        self._sessions[existing_session.session_id] = existing_session
                    raise

            self._condition.notify_all()

        return session

    async def get(self, session_id: str) -> Session | None:
        async with self._condition:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            now = datetime.now(UTC)
            if session.is_expired(now):
                self._sessions.pop(session_id)
                try:
                    await self._save()
                except Exception:
                    self._sessions[session_id] = session
                    raise
                self._condition.notify_all()
                return None

            return session

    async def remove(self, session_id: str) -> Session | None:
        async with self._condition:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                try:
                    await self._save()
                except Exception:
                    self._sessions[session_id] = session
                    raise
                self._condition.notify_all()
        return session

    def _load(self) -> None:
        if not self._sessions_file_path.exists():
            return

        with self._sessions_file_path.open(encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
            raise TypeError("sessions.json must contain a sessions object")

        sessions = {}
        for session_id, item in data["sessions"].items():
            session = Session.from_dict(item)
            if session.session_id != session_id:
                raise ValueError("Session id must match its sessions key")
            sessions[session_id] = session

        self._sessions = sessions

    async def _save(self) -> None:
        await to_thread.run_sync(self._save_sync)

    def _save_sync(self) -> None:
        self._sessions_file_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        data = {
            "updatedAt": datetime.now(UTC).isoformat(),
            "sessions": {
                session_id: session.to_dict()
                for session_id, session in sorted(self._sessions.items())
            },
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

    async def _remove_expired(self) -> None:
        now = datetime.now(UTC)
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
            await self._save()
        except Exception:
            self._sessions.update(expired_sessions)
            raise

    async def _cleanup_expired(self) -> None:
        while True:
            try:
                async with self._condition:
                    if self._sessions:
                        next_expiration = min(
                            session.expires_at for session in self._sessions.values()
                        )
                        delay = max(
                            0.0,
                            (
                                next_expiration - datetime.now(UTC)
                            ).total_seconds(),
                        )
                    else:
                        await self._condition.wait()
                        continue

                    with fail_after(delay):
                        await self._condition.wait()
            except TimeoutError:
                try:
                    async with self._condition:
                        await self._remove_expired()
                except Exception:
                    self._logger.exception("Failed to clean up expired sessions")
                    await sleep(1)
