from datetime import datetime, timedelta, timezone


class Session:
    lifetime = timedelta(days=1)

    def __init__(self, session_id: str, expires_at: datetime | None = None):
        self.session_id = session_id
        self.expires_at = expires_at or self._next_expiration()

    def renew(self, now: datetime | None = None) -> None:
        self.expires_at = self._next_expiration(now)

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at <= (now or datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, str]:
        return {
            "session_id": self.session_id,
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: object) -> "Session":
        if not isinstance(data, dict):
            raise ValueError("Session data must be an object")

        session_id = data.get("session_id")
        expires_at_value = data.get("expires_at")
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("Session id must be a non-empty string")
        if not isinstance(expires_at_value, str):
            raise ValueError("Session expiration must be a string")

        expires_at = datetime.fromisoformat(expires_at_value)
        if expires_at.tzinfo is None:
            raise ValueError("Session expiration must include a timezone")

        return cls(
            session_id=session_id,
            expires_at=expires_at.astimezone(timezone.utc),
        )

    @classmethod
    def _next_expiration(cls, now: datetime | None = None) -> datetime:
        return (now or datetime.now(timezone.utc)) + cls.lifetime
