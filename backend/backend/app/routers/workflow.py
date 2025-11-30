from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.workflow import NegotiationRequest, NegotiationResponse
from app.workflows.negotiation import NegotiationWorkflow, get_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("/negotiate", response_model=NegotiationResponse)
async def run_negotiation(
    payload: NegotiationRequest,
    workflow: NegotiationWorkflow = Depends(get_workflow),
) -> NegotiationResponse:
    try:
        return await workflow.run(payload)
    except Exception as exc:  # pragma: no cover - surfaced as 500 otherwise
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"message": "workflow router ready"}
