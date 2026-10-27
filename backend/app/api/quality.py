from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from app.telemetry.quality import QualityService


def create_quality_router(get_service: Callable[[], QualityService]) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["quality"])

    @router.get("/quality/overview")
    def overview(
        range: str = Query("24h", pattern="^(24h|7d|30d|all)$"),
        service: QualityService = Depends(get_service),
    ):
        return service.overview(range)

    @router.get("/quality/tools")
    def tools(
        range: str = Query("24h", pattern="^(24h|7d|30d|all)$"),
        service: QualityService = Depends(get_service),
    ):
        return {"items": service.overview(range).tools}

    @router.get("/quality/trends")
    def trends(
        range: str = Query("7d", pattern="^(24h|7d|30d|all)$"),
        service: QualityService = Depends(get_service),
    ):
        return {"items": service.trends(range)}

    @router.get("/quality/operations")
    def operations(
        range: str = Query("24h", pattern="^(24h|7d|30d|all)$"),
        service: QualityService = Depends(get_service),
    ):
        return service.operations(range)

    @router.get("/runs")
    def list_runs(
        limit: int = Query(50, ge=1, le=100),
        offset: int = Query(0, ge=0),
        source: str | None = None,
        status: str | None = None,
        planner_type: str | None = None,
        service: QualityService = Depends(get_service),
    ):
        return service.list_runs(
            limit=limit,
            offset=offset,
            source=source,
            status=status,
            planner_type=planner_type,
        )

    @router.get("/runs/{run_id}")
    def get_run(run_id: str, service: QualityService = Depends(get_service)):
        try:
            return service.get_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    return router
