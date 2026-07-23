from fastapi import APIRouter, Request

router = APIRouter(prefix="/task")

@router.post("create")
async def create_session(request: Request):
    pass
