from __future__ import annotations

import hashlib
import os

from fastapi import APIRouter, Depends

from app.agent.session_service import AgentSessionService
from app.agent.proposal_generator import LLMProposalGenerator
from app.persistence.sqlite import SqliteUnitOfWork


class SystemStatusService:
    def __init__(self, agent: AgentSessionService, unit: SqliteUnitOfWork) -> None:
        self._agent = agent
        self._unit = unit

    def status(self) -> dict:
        backend = self._agent.tool_backend
        tool_error = None
        try:
            tools = self._agent.list_tools()
        except Exception as exc:
            tools = []
            tool_error = type(exc).__name__
        policy = self._agent.policy
        migrations = self._unit.applied_migrations()
        generator = self._agent.proposal_generator
        planner_type = "llm" if isinstance(generator, LLMProposalGenerator) else "rule"
        issues, issue_count = self._unit.runtime_issues.list_filtered(limit=100, offset=0)
        return {
            "status": "ok",
            "agent": {
                "planner_type": planner_type,
                "model": generator.model if isinstance(generator, LLMProposalGenerator) else None,
                "policy_loaded": bool(policy.strip()),
                "policy_version": hashlib.sha256(policy.encode()).hexdigest()[:12] if policy else None,
            },
            "tools": {
                "backend_kind": backend.kind,
                "backend_name": backend.name,
                "managed_by_mcp": backend.managed_by_mcp,
                "tool_count": len(tools),
                "status": "unavailable" if tool_error else ("available" if tools else "degraded"),
                "error_type": tool_error,
            },
            "database": {
                "engine": "sqlite",
                "status": "available",
                "migration_version": max(migrations, default=0),
            },
            "data": {
                "run_count": len(self._unit.agent_runs.list_all()),
                "regression_case_count": len(self._unit.regression_cases.list_all()),
                "issue_count": issue_count,
                "open_critical_issue_count": sum(item.status == "open" and item.severity == "critical" for item in issues),
            },
        }


def create_system_router(get_service) -> APIRouter:
    router = APIRouter(prefix="/api/v1/system", tags=["system"])

    @router.get("/status")
    def status(service: SystemStatusService = Depends(get_service)):
        return service.status()

    return router
