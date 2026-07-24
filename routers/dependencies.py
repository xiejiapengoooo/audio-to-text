from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request
from sessions.session import Session


async def get_current_session(
    request: Request,
    session_id: Annotated[str, Header(alias="session")],
) -> Session:
    manager = request.app.state.session_manager
    session = await manager.get(session_id)

    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return session


CurrentSession = Annotated[Session, Depends(get_current_session)]
