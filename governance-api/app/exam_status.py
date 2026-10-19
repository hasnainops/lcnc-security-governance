"""Read-only exam observations; no Docker or business operations run here."""

from fastapi import APIRouter, Response

from .platform_status import read_platform_status


router = APIRouter(prefix="/exam", tags=["Exam observations"])


@router.get("/platform-status")
def platform_status(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return read_platform_status()
