from __future__ import annotations

from collections.abc import Callable
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.observability.models import FeedbackReview, IssueReview
from app.observability.service import ObservabilityConflict, ObservabilityService, ObservabilityNotFound


class ClientErrorRequest(BaseModel):
    error_code: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=500)
    path: str = Field(min_length=1, max_length=300)
    status_code: int | None = None
    severity: Literal["warning", "error"] = "error"


def create_observability_router(get_service: Callable[[], ObservabilityService]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/observability", tags=["observability"])

    @router.get("/feedback")
    def list_feedback(request: Request, status: str | None = None, rating: str | None = None, category: str | None = None, query: str | None = None, limit: int = Query(50, le=100), offset: int = Query(0, ge=0), service=Depends(get_service)):
        return service.list_feedback_for_developer(_actor(request), status=status, rating=rating, category=category, query=query, limit=limit, offset=offset)

    @router.get("/feedback/{feedback_id}")
    def get_feedback(feedback_id: str, request: Request, service=Depends(get_service)):
        try: return service.get_feedback_for_developer(_actor(request), feedback_id)
        except ObservabilityNotFound: raise _not_found()

    @router.patch("/feedback/{feedback_id}")
    def review_feedback(feedback_id: str, command: FeedbackReview, request: Request, service=Depends(get_service)):
        try: return service.review_feedback(_actor(request), feedback_id, status=command.status, developer_note=command.developer_note)
        except (ObservabilityNotFound, KeyError): raise _not_found()

    @router.get("/issues")
    def list_issues(request: Request, status: str | None = None, severity: str | None = None, source: str | None = None, query: str | None = None, limit: int = Query(50, le=100), offset: int = Query(0, ge=0), service=Depends(get_service)):
        return service.list_issues_for_developer(_actor(request), status=status, severity=severity, source=source, query=query, limit=limit, offset=offset)

    @router.get("/issues/{issue_id}")
    def get_issue(issue_id: str, request: Request, service=Depends(get_service)):
        try: return service.get_issue_for_developer(_actor(request), issue_id)
        except ObservabilityNotFound: raise _not_found()

    @router.patch("/issues/{issue_id}")
    def review_issue(issue_id: str, command: IssueReview, request: Request, service=Depends(get_service)):
        try: return service.review_issue(_actor(request), issue_id, status=command.status, developer_note=command.developer_note)
        except (ObservabilityNotFound, KeyError): raise _not_found()
        except ObservabilityConflict as exc: raise HTTPException(status_code=409, detail={"code":"regression_verification_required","message":str(exc),"recoverable":True}) from exc

    @router.get("/overview")
    def overview(request: Request, service=Depends(get_service)):
        return service.overview(_actor(request))

    @router.post("/client-errors", status_code=202)
    def client_error(command: ClientErrorRequest, request: Request, service=Depends(get_service)):
        user = _actor(request)
        service.capture_issue(source="frontend", severity=command.severity, error_code=command.error_code, request_id=request.headers.get("x-request-id"), context={"path": command.path, "status_code": command.status_code, "component": "support-ui"})
        return {"accepted": True, "user_id": user.user_id}

    return router


def _actor(request: Request):
    return request.state.authenticated_user


def _not_found():
    return HTTPException(status_code=404, detail={"code":"not_found","message":"未找到记录。","recoverable":False})
