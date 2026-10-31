"""Read-only platform status observations; no Docker or business operations run here."""

from fastapi import APIRouter, Response

from .platform_status import read_platform_status
from .functional_status import collect_functional_status


router = APIRouter(prefix="/status", tags=["Platform status"])


@router.get("/platform")
def platform_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return read_platform_status()


@router.get("/functional")
async def functional_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await collect_functional_status()
