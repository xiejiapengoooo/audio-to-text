from typing import Any

from fastapi import APIRouter

from common import get_output_dir
from routers.dependencies import CurrentSession

router = APIRouter()


@router.get("/results")
async def get_results(
    session: CurrentSession,
) -> list[dict[str, Any]]:
    output_dir = get_output_dir()
    results = []
    for file in output_dir.glob(f"{session.session_id}_*"):
        if not file.is_file():
            continue

        file_stat = file.stat()
        results.append(
            {
                "name": file.name,
                "url": f"/output/{file.name}",
                "size": file_stat.st_size,
                "modified_at": file_stat.st_mtime,
            }
        )

    results.sort(key=lambda result: (-result["modified_at"], result["name"]))
    return results
