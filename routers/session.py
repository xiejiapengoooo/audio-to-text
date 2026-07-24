from fastapi import APIRouter, Header, Request


router = APIRouter()


@router.post("/session")
async def create_session(
    request: Request,
    session_id: str | None = Header(default=None, alias="session"),
) -> str:
    manager = request.app.state.session_manager
    session = await manager.create(session_id)

    return session.session_id
