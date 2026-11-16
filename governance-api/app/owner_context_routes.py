from uuid import UUID

from fastapi import APIRouter, Header

from .automatic_classification import classification_state, classify_if_needed
from .owner_context import OwnerContextRequest, save_owner_context


router = APIRouter()


@router.post("/applications/{application_id}/owner-context")
def submit_owner_context(application_id: UUID, payload: OwnerContextRequest,
                         authorization: str | None = Header(default=None)):
    declaration = save_owner_context(application_id, payload, authorization)
    # The declaration commits independently; retryable ML failures do not lose it.
    classification = classify_if_needed(application_id)
    return {"declaration": declaration, "classification": classification}


@router.get("/applications/{application_id}/classification-state")
def get_classification_state(application_id: UUID):
    return classification_state(application_id)


@router.post("/applications/{application_id}/ml-classify-if-needed")
def classify_automatically(application_id: UUID):
    return classify_if_needed(application_id)
