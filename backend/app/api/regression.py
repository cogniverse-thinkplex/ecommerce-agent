from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.regression.models import RegressionBatchCommand, RegressionCaseCreate, RegressionCaseUpdate
from app.regression.service import (
    RegressionBatchNotFound,
    RegressionCaseInvalid,
    RegressionCaseNotFound,
    RegressionService,
)


def create_regression_router(get_service: Callable[[], RegressionService]) -> APIRouter:
    router = APIRouter(prefix="/api/v1/regression", tags=["regression"])

    @router.get("/cases")
    def list_cases(
        status_filter: str | None = Query(None, alias="status"),
        service: RegressionService = Depends(get_service),
    ):
        return service.list_cases(status_filter)

    @router.post("/cases", status_code=status.HTTP_201_CREATED)
    def create_case(command: RegressionCaseCreate, request: Request, service: RegressionService = Depends(get_service)):
        try:
            return service.create_case(request.state.authenticated_user, command)
        except RegressionCaseInvalid as exc:
            raise _invalid(exc) from exc

    @router.patch("/cases/{case_id}")
    def update_case(case_id: str, command: RegressionCaseUpdate, service: RegressionService = Depends(get_service)):
        try:
            return service.update_case(case_id, command)
        except RegressionCaseNotFound as exc:
            raise HTTPException(status_code=404, detail={"code": "regression_case_not_found", "message": "回归用例不存在。"}) from exc
        except RegressionCaseInvalid as exc:
            raise _invalid(exc) from exc

    @router.post("/cases/from-issue/{issue_id}", status_code=status.HTTP_201_CREATED)
    def from_issue(issue_id: str, request: Request, service: RegressionService = Depends(get_service)):
        return _convert(lambda: service.create_from_issue(request.state.authenticated_user, issue_id))

    @router.post("/cases/from-feedback/{feedback_id}", status_code=status.HTTP_201_CREATED)
    def from_feedback(feedback_id: str, request: Request, service: RegressionService = Depends(get_service)):
        return _convert(lambda: service.create_from_feedback(request.state.authenticated_user, feedback_id))

    @router.post("/cases/from-run/{run_id}", status_code=status.HTTP_201_CREATED)
    def from_run(run_id: str, request: Request, service: RegressionService = Depends(get_service)):
        return _convert(lambda: service.create_from_run(request.state.authenticated_user, run_id))

    @router.post("/batches", status_code=status.HTTP_201_CREATED)
    def create_batch(command: RegressionBatchCommand, service: RegressionService = Depends(get_service)):
        try:
            return service.run_batch(**command.model_dump())
        except RegressionCaseInvalid as exc:
            raise _invalid(exc) from exc

    @router.get("/batches/{batch_id}")
    def get_batch(batch_id: str, service: RegressionService = Depends(get_service)):
        try:
            return service.get_batch(batch_id)
        except RegressionBatchNotFound as exc:
            raise HTTPException(status_code=404, detail={"code": "regression_batch_not_found", "message": "回归批次不存在。"}) from exc

    return router


def _invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"code": "invalid_regression_case", "message": str(exc)},
    )


def _convert(operation):
    try:
        return operation()
    except RegressionCaseNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "regression_source_not_found", "message": "来源记录不存在。"}) from exc
    except RegressionCaseInvalid as exc:
        raise _invalid(exc) from exc
