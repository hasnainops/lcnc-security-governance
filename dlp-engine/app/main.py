from fastapi import FastAPI
from pydantic import BaseModel, Field

from .dlp import inspect_content


app = FastAPI(
    title="LCNC DLP Engine",
    version="0.1.0",
)


class InspectionInput(BaseModel):
    content: str = ""
    field_names: list[str] = Field(
        default_factory=list
    )


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "dlp-engine",
        "engine_version": "dlp-v1",
    }


@app.post("/inspect")
def inspect(payload: InspectionInput):
    return inspect_content(
        payload.content,
        payload.field_names,
    )
