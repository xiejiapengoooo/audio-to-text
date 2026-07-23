from fastapi import APIRouter, Request

router = APIRouter(prefix="/session")

@router.post("")
async def create_session(request: Request) -> str:
    manager = request.app.state.session_manager
    session = await manager.create()

    return session.session_id
