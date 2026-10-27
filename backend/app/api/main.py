from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.agent.nodes.confirmation_node import ConfirmationNodeResult
from app.agent.audit import SessionAudit
from app.agent.nodes.tool_node import ToolCallRequest, ToolNodeResult
from app.agent.nodes.tool_proposal_node import ToolProposal, ToolProposalResult
from app.agent.proposal_generator import (
    LLMProposalGenerator,
    LiteLLMClient,
    ModelProviderError,
    ProposalGenerator,
    RuleBasedProposalGenerator,
)
from app.agent.runtime import AgentRuntime, BaselineAgentRuntime, LLMPlannerRuntime
from app.agent.skills import SkillRegistry, default_skill_registry
from app.agent.session_service import (
    AgentAutoRunResult,
    AgentSessionService,
    AgentTurnResult,
    ConfirmAndContinueResult,
    RuntimeResetResult,
    SessionIndexItem,
)
from app.agent.state import AgentEvent, CustomerAgentState
from app.agent.trace import SessionTrace
from app.agent.session_store import PersistentSessionStore
from app.evaluation.results_compare import (
    EvaluationComparison,
    compare_evaluation_runs,
)
from app.evaluation.results_index import EvaluationRunIndex, list_evaluation_runs
from app.evaluation.results_summary import EvaluationSummary, summarize_run_dir
from app.evaluation.runtime_task_runner import (
    RuntimePlannerType,
    RuntimeSubsetArtifact,
    RuntimeTaskRunResult,
    load_runtime_task_subset_artifact,
    run_retail_task_subset,
    save_runtime_task_subset_artifact,
)
from app.evaluation.session_task_check import SessionTaskCheck, compare_session_to_task
from app.evaluation.smoke_compare import SmokeComparison, compare_smoke_runs
from app.evaluation.tau_retail_tasks import RetailTaskSummary, load_retail_task_summaries
from app.evaluation.tau_retail_tasks import load_retail_task_summary
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.mcp_retail_adapter import McpTransportError
from app.tools.retail_port import RetailToolDefinition, ToolBackendInfo
from app.tools.tool_backend_factory import build_retail_tool_port
from app.persistence.sqlite import SqliteUnitOfWork
from app.api.support import create_support_router
from app.api.handoffs import create_handoff_router
from app.api.auth import COOKIE_NAME, create_auth_router
from app.api.admin import create_admin_router
from app.api.observability import create_observability_router
from app.api.quality import create_quality_router
from app.api.regression import create_regression_router
from app.api.system import SystemStatusService, create_system_router
from app.api.orders import create_orders_router
from app.api.help import create_help_router
from app.api.rag import create_rag_router
from app.auth.service import AuthService, AuthenticationError
from app.auth.retail_identity import RetailIdentityResolver
from app.observability.service import ObservabilityService
from app.telemetry.service import RunTelemetryService
from app.telemetry.quality import QualityService
from app.regression.service import RegressionService
from app.support.service import SupportService
from app.support.handoff import HumanHandoffService
from app.help.service import HelpService
from app.rag.embedding import SentenceTransformerEmbeddingProvider
from app.rag.ingestion import PolicyIngestionService
from app.rag.retrieval import PolicyRetrievalService
from app.operations.config import validate_runtime_config
from app.operations.health import ReadinessChecker
from app.operations.http import log_request, normalize_request_id, request_timer, security_headers
from app.operations.rate_limit import LoginRateLimiter


class CreateSessionRequest(BaseModel):
    conversation_id: str = Field(min_length=1)


class UserMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class AutoRunRequest(BaseModel):
    content: str = Field(min_length=1)
    max_steps: int = Field(default=6, ge=1, le=12)


class ConfirmationRequest(BaseModel):
    confirmed: bool
    user_text: str = Field(min_length=1)


class ConfirmAndContinueRequest(ConfirmationRequest):
    objective: str = Field(min_length=1)
    max_steps: int = Field(default=6, ge=1, le=12)


class ToolCatalogResponse(BaseModel):
    backend: ToolBackendInfo
    tools: list[RetailToolDefinition]


class PolicyResponse(BaseModel):
    policy: str


class EventsResponse(BaseModel):
    events: list[AgentEvent]


class SessionsIndexResponse(BaseModel):
    sessions: list[SessionIndexItem]


class RetailTasksResponse(BaseModel):
    tasks: list[RetailTaskSummary]


class AppConfigResponse(BaseModel):
    planner_type: str
    proposal_model: str | None
    tool_backend: ToolBackendInfo
    policy_summary: str


class RuntimeSubsetRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1, max_length=20)
    planner_type: RuntimePlannerType = "rule"
    split: str | None = "base"
    max_steps: int = Field(default=6, ge=1, le=12)
    verify_outcome_execution: bool = False
    save_artifact: bool = False
    run_name: str | None = None


class RuntimeSubsetResponse(BaseModel):
    results: list[RuntimeTaskRunResult]
    artifact: RuntimeSubsetArtifact | None = None
    artifact_url: str | None = None


def create_app(
    service: AgentSessionService | None = None,
    support_service: SupportService | None = None,
    handoff_service: HumanHandoffService | None = None,
    auth_service: AuthService | None = None,
    observability_service: ObservabilityService | None = None,
    quality_service: QualityService | None = None,
    regression_service: RegressionService | None = None,
    system_status_service: SystemStatusService | None = None,
    help_service: HelpService | None = None,
    readiness_checker: Any | None = None,
    login_limiter: LoginRateLimiter | None = None,
    auth_required: bool | None = None,
) -> FastAPI:
    validate_runtime_config(os.environ)
    app = FastAPI(title="Adaptive E-commerce Agent API")
    app.state.agent_service = service or _default_service()
    app.state.support_service = support_service
    app.state.handoff_service = handoff_service
    app.state.auth_service = auth_service or _default_auth_service()
    app.state.observability_service = observability_service or _default_observability_service()
    app.state.quality_service = quality_service or _default_quality_service()
    app.state.regression_service = regression_service or _default_regression_service()
    app.state.system_status_service = system_status_service or _default_system_status_service(app.state.agent_service)
    app.state.help_service = help_service or _default_help_service()
    app.state.readiness_checker = readiness_checker
    app.state.login_limiter = login_limiter or LoginRateLimiter(
        max_failures=int(os.getenv("ECOM_LOGIN_MAX_FAILURES", "5")),
        window_seconds=int(os.getenv("ECOM_LOGIN_WINDOW_SECONDS", "300")),
        block_seconds=int(os.getenv("ECOM_LOGIN_BLOCK_SECONDS", "900")),
    )
    app.state.auth_required = (
        os.getenv("ECOM_AUTH_REQUIRED", "true").strip().lower() == "true"
        if auth_required is None
        else auth_required
    )
    app.mount(
        "/dashboard",
        StaticFiles(directory=_dashboard_dir(), html=True),
        name="dashboard",
    )
    app.mount(
        "/support",
        StaticFiles(directory=_support_dir(), html=True),
        name="support",
    )
    app.mount(
        "/account",
        StaticFiles(directory=_account_dir(), html=True),
        name="account",
    )
    app.mount("/orders", StaticFiles(directory=_orders_dir(), html=True), name="orders")
    app.mount("/help", StaticFiles(directory=_help_dir(), html=True), name="help")
    app.mount("/auth", StaticFiles(directory=_auth_dir()), name="auth-static")

    def get_service() -> AgentSessionService:
        return app.state.agent_service

    def get_support_service() -> SupportService:
        if app.state.support_service is None:
            app.state.support_service = _default_support_service(
                app.state.agent_service, get_handoff_service()
            )
        return app.state.support_service

    def get_handoff_service() -> HumanHandoffService:
        if app.state.handoff_service is None:
            app.state.handoff_service = _default_handoff_service()
        return app.state.handoff_service

    def get_auth_service() -> AuthService:
        return app.state.auth_service

    def get_observability_service() -> ObservabilityService:
        return app.state.observability_service

    def get_quality_service() -> QualityService:
        return app.state.quality_service

    def get_regression_service() -> RegressionService:
        return app.state.regression_service

    def get_system_status_service() -> SystemStatusService:
        return app.state.system_status_service

    def get_help_service() -> HelpService:
        return app.state.help_service

    app.include_router(create_support_router(get_support_service, get_observability_service))
    app.include_router(create_orders_router(get_auth_service, get_support_service))
    app.include_router(create_help_router(get_help_service, get_support_service))
    app.include_router(create_rag_router(get_help_service))
    app.include_router(create_handoff_router(get_handoff_service))
    app.include_router(create_auth_router(get_auth_service, lambda: app.state.login_limiter))
    app.include_router(create_admin_router(get_auth_service))
    app.include_router(create_observability_router(get_observability_service))
    app.include_router(create_quality_router(get_quality_service))
    app.include_router(create_regression_router(get_regression_service))
    app.include_router(create_system_router(get_system_status_service))

    @app.middleware("http")
    async def authorize_request(request: Request, call_next):
        if not app.state.auth_required or _is_public_path(request.url.path):
            return await call_next(request)
        token = request.cookies.get(COOKIE_NAME)
        try:
            user = app.state.auth_service.authenticate(token)
        except AuthenticationError:
            if _expects_json(request.url.path):
                return JSONResponse(
                    status_code=401,
                    content={"detail": {"code": "authentication_required", "message": "请先登录。", "recoverable": True}},
                )
            return RedirectResponse("/login/")
        request.state.authenticated_user = user
        if user.must_change_password and not _is_password_change_path(request.url.path):
            if _expects_json(request.url.path):
                return JSONResponse(
                    status_code=409,
                    content={"detail": {"code": "password_change_required", "message": "首次登录需要修改密码。", "recoverable": True}},
                )
            return RedirectResponse("/change-password/")
        if request.url.path.startswith("/support") and user.role == "developer":
            return RedirectResponse("/dashboard/")
        if request.url.path.startswith("/account") and user.role == "developer":
            return RedirectResponse("/dashboard/")
        if request.url.path.startswith("/orders") and user.role == "developer":
            return RedirectResponse("/dashboard/")
        if request.url.path.startswith("/help") and user.role == "developer":
            return RedirectResponse("/dashboard/")
        if request.url.path.startswith("/dashboard") and user.role == "customer":
            return RedirectResponse("/support/")
        if _is_engineering_path(request.url.path) and user.role != "developer":
            return JSONResponse(
                status_code=403,
                content={"detail": {"code": "forbidden", "message": "需要开发人员权限。", "recoverable": False}},
            )
        if request.url.path == "/":
            target = "/dashboard/" if user.role == "developer" else "/support/"
            return RedirectResponse(target)
        request_id = getattr(request.state, "request_id", normalize_request_id(request.headers.get("x-request-id")))
        try:
            response = await call_next(request)
        except Exception as exc:
            issue_source = _exception_source(exc)
            app.state.observability_service.capture_issue(
                source=issue_source,
                severity="error",
                error_code=f"UNHANDLED_{issue_source.upper()}_EXCEPTION",
                exception=exc, request_id=request_id,
                context={"path": request.url.path, "method": request.method},
            )
            raise
        response.headers["x-request-id"] = request_id
        return response

    @app.middleware("http")
    async def operational_request_context(request: Request, call_next):
        request_id = normalize_request_id(request.headers.get("x-request-id"))
        request.state.request_id = request_id
        started = request_timer()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["x-request-id"] = request_id
            for name, value in security_headers().items():
                response.headers[name] = value
            return response
        finally:
            log_request(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                started=started,
            )

    @app.get("/health")
    def health(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> dict[str, str]:
        planner_type = (
            "llm"
            if isinstance(agent_service.proposal_generator, LLMProposalGenerator)
            else "rule"
        )
        return {
            "status": "ok",
            "database": os.getenv("ECOM_AGENT_STORE", "memory").strip().lower(),
            "model": planner_type,
            "tool_backend": agent_service.tool_backend.name,
        }

    @app.get("/ready")
    def ready(agent_service: AgentSessionService = Depends(get_service)) -> JSONResponse:
        checker = app.state.readiness_checker or ReadinessChecker(agent_service.list_tools)
        result = checker.check()
        return JSONResponse(
            status_code=200 if result["status"] == "ready" else 503,
            content=result,
        )

    @app.get("/login/", include_in_schema=False)
    def login_page() -> FileResponse:
        return FileResponse(_auth_dir() / "login.html")

    @app.get("/customer-shell.css", include_in_schema=False)
    def customer_shell_css() -> FileResponse:
        return FileResponse(_frontend_dir() / "shared" / "customer-shell.css")

    @app.get("/customer-shell.js", include_in_schema=False)
    def customer_shell_js() -> FileResponse:
        return FileResponse(
            _frontend_dir() / "shared" / "customer-shell.js",
            media_type="text/javascript",
        )

    @app.get("/register/", include_in_schema=False)
    def register_page() -> FileResponse:
        return FileResponse(_auth_dir() / "register.html")

    @app.get("/change-password/", include_in_schema=False)
    def change_password_page() -> FileResponse:
        return FileResponse(_auth_dir() / "change-password.html")

    @app.get("/tools", response_model=ToolCatalogResponse)
    def list_tools(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> ToolCatalogResponse:
        return ToolCatalogResponse(
            backend=agent_service.tool_backend,
            tools=agent_service.list_tools(),
        )

    @app.get("/policy", response_model=PolicyResponse)
    def get_policy(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> PolicyResponse:
        return PolicyResponse(policy=agent_service.policy)

    @app.get("/config", response_model=AppConfigResponse)
    def get_config(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> AppConfigResponse:
        generator = agent_service.proposal_generator
        planner_type = "llm" if isinstance(generator, LLMProposalGenerator) else "rule"
        return AppConfigResponse(
            planner_type=planner_type,
            proposal_model=(
                generator.model
                if isinstance(generator, LLMProposalGenerator)
                else None
            ),
            tool_backend=agent_service.tool_backend,
            policy_summary=agent_service.policy,
        )

    @app.get("/retail/tasks", response_model=RetailTasksResponse)
    def list_retail_tasks(
        split: str | None = "base",
        limit: int = Query(default=10, ge=1, le=200),
    ) -> RetailTasksResponse:
        return RetailTasksResponse(
            tasks=load_retail_task_summaries(split=split, limit=limit)
        )

    @app.get("/retail/tasks/{task_id}", response_model=RetailTaskSummary)
    def get_retail_task(task_id: str, split: str | None = "base") -> RetailTaskSummary:
        try:
            return load_retail_task_summary(task_id, split=split)
        except KeyError as exc:
            raise _not_found(exc)

    @app.get("/evaluations", response_model=EvaluationRunIndex)
    def list_evaluations() -> EvaluationRunIndex:
        return EvaluationRunIndex(runs=list_evaluation_runs(_simulations_dir()))

    @app.get("/evaluations/compare", response_model=EvaluationComparison)
    def compare_evaluations() -> EvaluationComparison:
        return compare_evaluation_runs(_simulations_dir())

    @app.get("/evaluations/smoke/compare", response_model=SmokeComparison)
    def compare_smoke_evaluations(
        baseline_run: str,
        candidate_run: str,
    ) -> SmokeComparison:
        try:
            return compare_smoke_runs(
                _simulations_dir(),
                baseline_run=baseline_run,
                candidate_run=candidate_run,
            )
        except KeyError as exc:
            raise _not_found(exc)

    @app.get(
        "/evaluations/{run_name}/summary",
        response_model=EvaluationSummary,
    )
    def get_evaluation_summary(run_name: str) -> EvaluationSummary:
        run_dir = _simulations_dir() / run_name
        if not run_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation run not found: {run_name}",
            )
        try:
            return summarize_run_dir(run_dir)
        except KeyError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Evaluation run not found: {run_name}",
            )

    @app.post(
        "/evaluations/runtime-subset",
        response_model=RuntimeSubsetResponse,
    )
    def run_runtime_subset(request: RuntimeSubsetRequest) -> RuntimeSubsetResponse:
        try:
            results = run_retail_task_subset(
                request.task_ids,
                split=request.split,
                max_steps=request.max_steps,
                planner_type=request.planner_type,
                verify_outcome_execution=request.verify_outcome_execution,
            )
            artifact = None
            artifact_url = None
            if request.save_artifact:
                artifact = save_runtime_task_subset_artifact(
                    results,
                    output_dir=_simulations_dir(),
                    run_name=request.run_name,
                    max_steps=request.max_steps,
                )
                artifact_url = f"/evaluations/runtime-subset/{artifact.run_name}"
            return RuntimeSubsetResponse(
                results=results,
                artifact=artifact,
                artifact_url=artifact_url,
            )
        except KeyError as exc:
            raise _not_found(exc)
        except ModelProviderError as exc:
            if exc.reason == "quota_exhausted":
                detail = (
                    f"模型 {exc.model} 的可用额度已耗尽，"
                    "请切换模型或调整百炼的免费额度限制。"
                )
            else:
                detail = (
                    f"模型 {exc.model} 暂时不可用，请稍后重试或切换模型。"
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=detail,
            ) from exc

    @app.get(
        "/evaluations/runtime-subset/{run_name}",
        response_model=RuntimeSubsetArtifact,
    )
    def get_runtime_subset_artifact(run_name: str) -> RuntimeSubsetArtifact:
        try:
            return load_runtime_task_subset_artifact(_simulations_dir(), run_name)
        except KeyError as exc:
            raise _not_found(exc)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(
            url="/login/" if app.state.auth_required else "/support/"
        )

    @app.post(
        "/sessions",
        status_code=status.HTTP_201_CREATED,
        response_model=CustomerAgentState,
    )
    def create_session(
        request: CreateSessionRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> CustomerAgentState:
        return agent_service.start_session(request.conversation_id)

    @app.get("/sessions", response_model=SessionsIndexResponse)
    def list_sessions(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> SessionsIndexResponse:
        return SessionsIndexResponse(sessions=agent_service.list_sessions())

    @app.post("/admin/reset", response_model=RuntimeResetResult)
    def reset_runtime_state(
        agent_service: AgentSessionService = Depends(get_service),
    ) -> RuntimeResetResult:
        return agent_service.reset_runtime_state()

    @app.get("/sessions/{conversation_id}", response_model=CustomerAgentState)
    def get_session(
        conversation_id: str,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> CustomerAgentState:
        try:
            return agent_service.get_session(conversation_id)
        except KeyError as exc:
            raise _not_found(exc)

    @app.delete("/sessions/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_session(
        conversation_id: str,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> None:
        try:
            agent_service.delete_session(conversation_id)
        except KeyError as exc:
            raise _not_found(exc)

    @app.get("/sessions/{conversation_id}/events", response_model=EventsResponse)
    def list_events(
        conversation_id: str,
        event_type_prefix: str | None = None,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> EventsResponse:
        try:
            return EventsResponse(
                events=agent_service.list_events(
                    conversation_id,
                    event_type_prefix=event_type_prefix,
                )
            )
        except KeyError as exc:
            raise _not_found(exc)

    @app.get("/sessions/{conversation_id}/trace", response_model=SessionTrace)
    def get_trace(
        conversation_id: str,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> SessionTrace:
        try:
            return agent_service.get_trace(conversation_id)
        except KeyError as exc:
            raise _not_found(exc)

    @app.get("/sessions/{conversation_id}/audit", response_model=SessionAudit)
    def get_session_audit(
        conversation_id: str,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> SessionAudit:
        try:
            return agent_service.get_audit(conversation_id)
        except KeyError as exc:
            raise _not_found(exc)

    @app.get(
        "/sessions/{conversation_id}/retail-task-check/{task_id}",
        response_model=SessionTaskCheck,
    )
    def check_session_against_retail_task(
        conversation_id: str,
        task_id: str,
        split: str | None = "base",
        agent_service: AgentSessionService = Depends(get_service),
    ) -> SessionTaskCheck:
        try:
            state = agent_service.get_session(conversation_id)
            task = load_retail_task_summary(task_id, split=split)
            return compare_session_to_task(state, task)
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/messages",
        response_model=CustomerAgentState,
    )
    def add_message(
        conversation_id: str,
        request: UserMessageRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> CustomerAgentState:
        try:
            return agent_service.add_user_message(conversation_id, request.content)
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/turns",
        response_model=AgentTurnResult,
    )
    def run_turn(
        conversation_id: str,
        request: UserMessageRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> AgentTurnResult:
        try:
            return agent_service.run_turn(conversation_id, request.content)
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/auto-run",
        response_model=AgentAutoRunResult,
    )
    def auto_run_turns(
        conversation_id: str,
        request: AutoRunRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> AgentAutoRunResult:
        try:
            return agent_service.auto_run(
                conversation_id,
                request.content,
                max_steps=request.max_steps,
                telemetry_source="sandbox",
            )
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/tool-calls",
        response_model=ToolNodeResult,
    )
    def apply_tool_request(
        conversation_id: str,
        request: ToolCallRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> ToolNodeResult:
        try:
            return agent_service.apply_tool_request(conversation_id, request)
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/tool-proposals",
        response_model=ToolProposalResult,
    )
    def apply_tool_proposal_request(
        conversation_id: str,
        request: ToolProposal,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> ToolProposalResult:
        try:
            return agent_service.apply_tool_proposal(conversation_id, request)
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/confirmations",
        response_model=ConfirmationNodeResult,
    )
    def apply_confirmation(
        conversation_id: str,
        request: ConfirmationRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> ConfirmationNodeResult:
        try:
            return agent_service.apply_confirmation_reply(
                conversation_id,
                confirmed=request.confirmed,
                user_text=request.user_text,
            )
        except KeyError as exc:
            raise _not_found(exc)

    @app.post(
        "/sessions/{conversation_id}/confirm-and-continue",
        response_model=ConfirmAndContinueResult,
    )
    def confirm_and_continue(
        conversation_id: str,
        request: ConfirmAndContinueRequest,
        agent_service: AgentSessionService = Depends(get_service),
    ) -> ConfirmAndContinueResult:
        try:
            return agent_service.confirm_pending_and_continue(
                conversation_id,
                confirmed=request.confirmed,
                user_text=request.user_text,
                objective=request.objective,
                max_steps=request.max_steps,
            )
        except KeyError as exc:
            raise _not_found(exc)

    return app


def _default_service() -> AgentSessionService:
    def build_executor() -> GuardedRetailToolExecutor:
        return GuardedRetailToolExecutor(build_retail_tool_port())

    executor = build_executor()
    store = None
    telemetry = None
    if os.getenv("ECOM_AGENT_STORE", "memory").strip().lower() == "sqlite":
        unit = SqliteUnitOfWork(
            Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
        )
        unit.initialize()
        store = PersistentSessionStore(unit)
        telemetry = RunTelemetryService(unit)
    return AgentSessionService(
        executor,
        executor_factory=build_executor,
        runtime_factory=build_agent_runtime,
        session_store=store,
        telemetry_service=telemetry,
        telemetry_source="support",
    )


def _default_support_service(
    agent_service: AgentSessionService,
    handoff_service: HumanHandoffService | None = None,
) -> SupportService:
    if handoff_service is not None:
        unit = handoff_service._unit
    else:
        unit = SqliteUnitOfWork(
            Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
        )
        unit.initialize()
    return SupportService(agent_service, unit, handoff_service=handoff_service)


def _default_handoff_service() -> HumanHandoffService:
    unit = SqliteUnitOfWork(
        Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
    )
    unit.initialize()
    return HumanHandoffService(unit)


def _default_auth_service() -> AuthService:
    unit = SqliteUnitOfWork(
        Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
    )
    unit.initialize()
    retail_port = build_retail_tool_port()
    return AuthService(
        unit,
        session_hours=int(os.getenv("ECOM_AUTH_SESSION_HOURS", "12")),
        retail_identity_resolver=RetailIdentityResolver(retail_port),
        retail_tool_port=retail_port,
    )


def _default_observability_service() -> ObservabilityService:
    unit = SqliteUnitOfWork(Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db")))
    unit.initialize()
    return ObservabilityService(unit)


def _default_quality_service() -> QualityService:
    unit = SqliteUnitOfWork(Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db")))
    unit.initialize()
    return QualityService(unit)


def _default_regression_service() -> RegressionService:
    unit = SqliteUnitOfWork(
        Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
    )
    unit.initialize()
    return RegressionService(unit)


def _default_system_status_service(agent_service: AgentSessionService) -> SystemStatusService:
    unit = SqliteUnitOfWork(
        Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db"))
    )
    unit.initialize()
    return SystemStatusService(agent_service, unit)


def _default_help_service() -> HelpService:
    unit = SqliteUnitOfWork(Path(os.getenv("ECOM_AGENT_SQLITE_PATH", "data/ecommerce_agent.db")))
    unit.initialize()
    PolicyIngestionService(unit, Path(__file__).resolve().parents[1] / "rag/corpus/taobao_policies.json").ingest()
    return HelpService(unit, PolicyRetrievalService(unit, SentenceTransformerEmbeddingProvider()))


def _exception_source(exc: BaseException) -> str:
    if isinstance(exc, McpTransportError):
        return "mcp"
    if isinstance(exc, sqlite3.Error):
        return "database"
    module = type(exc).__module__
    if module.startswith("app.agent"):
        return "planner"
    return "api"


def _is_public_path(path: str) -> bool:
    return (
        path in {"/health", "/ready"}
        or path.startswith("/api/v1/auth/")
        or path in {"/login", "/login/", "/register", "/register/"}
        or path.startswith("/auth/")
    )


def _is_password_change_path(path: str) -> bool:
    return (
        path in {"/change-password", "/change-password/"}
        or path in {"/api/v1/auth/change-password", "/api/v1/auth/logout", "/api/v1/auth/me"}
        or path.startswith("/auth/")
    )


def _is_engineering_api(path: str) -> bool:
    return not path.startswith(("/api/v1/support/", "/api/v1/auth/", "/api/v1/orders", "/api/v1/help/", "/api/v1/observability/client-errors"))


def _expects_json(path: str) -> bool:
    return path.startswith(("/api/", "/tools", "/policy", "/config", "/retail", "/evaluations", "/sessions", "/admin"))


def _is_engineering_path(path: str) -> bool:
    if path.startswith("/dashboard") or path.startswith("/api/v1/admin/"):
        return True
    if path.startswith("/api/"):
        return _is_engineering_api(path)
    return path.startswith(("/tools", "/policy", "/config", "/retail", "/evaluations", "/sessions", "/admin"))


def build_agent_runtime(executor: GuardedRetailToolExecutor) -> AgentRuntime:
    skill_registry = default_skill_registry()
    proposal_generator = build_proposal_generator(
        executor=executor,
        skill_registry=skill_registry,
    )
    if isinstance(proposal_generator, LLMProposalGenerator):
        return LLMPlannerRuntime(
            executor=executor,
            proposal_generator=proposal_generator,
            skill_registry=skill_registry,
            policy_retriever=_default_help_service().retrieval,
        )
    return BaselineAgentRuntime(
        executor=executor,
        proposal_generator=proposal_generator,
        skill_registry=skill_registry,
        policy_retriever=_default_help_service().retrieval,
    )


def build_proposal_generator(
    executor: GuardedRetailToolExecutor | None = None,
    skill_registry: SkillRegistry | None = None,
) -> ProposalGenerator:
    generator_type = _proposal_generator_type()
    if generator_type == "llm":
        return LLMProposalGenerator(
            model=os.getenv("ECOM_AGENT_PROPOSAL_LLM", "dashscope/qwen3.8-max"),
            client=LiteLLMClient(),
            tool_catalog=None,
            skill_registry=skill_registry.list() if skill_registry is not None else None,
            policy="",
            context_loader=(
                (lambda: (executor.list_tools(), executor.policy))
                if executor is not None
                else None
            ),
        )
    return RuleBasedProposalGenerator()


def _proposal_generator_type() -> str:
    generator_type = os.getenv("ECOM_AGENT_PROPOSAL_GENERATOR", "llm").strip().lower()
    if generator_type not in {"llm", "rule"}:
        raise ValueError("ECOM_AGENT_PROPOSAL_GENERATOR must be 'llm' or 'rule'")
    return generator_type


def _simulations_dir() -> Path:
    return Path(
        os.getenv("ECOM_AGENT_SIMULATIONS_DIR", "benchmarks/data/simulations")
    )


def _frontend_dir() -> Path:
    default = Path(__file__).resolve().parents[3] / "frontend"
    return Path(os.getenv("ECOM_FRONTEND_DIR", str(default))).resolve()


def _dashboard_dir() -> Path:
    return _frontend_dir() / "dashboard"


def _support_dir() -> Path:
    return _frontend_dir() / "support"


def _auth_dir() -> Path:
    return _frontend_dir() / "auth"


def _account_dir() -> Path:
    return _frontend_dir() / "account"

def _orders_dir() -> Path:
    return _frontend_dir() / "orders"

def _help_dir() -> Path:
    return _frontend_dir() / "help"


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=exc.args[0])


app = create_app(auth_required=True)
