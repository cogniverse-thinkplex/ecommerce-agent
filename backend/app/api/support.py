from __future__ import annotations

from collections.abc import Callable
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agent.proposal_generator import ModelProviderError
from app.persistence.models import MessageRecord
from app.support.models import SupportConversation, SupportConversationGroup, SupportTurnResult
from app.support.handoff import HandoffActiveError
from app.support.service import SupportService
from app.support.streaming import stream_support_turn
from app.observability.models import FeedbackCreate, FeedbackPublic, IssueFeedbackCreate
from app.observability.service import ObservabilityService, ObservabilityNotFound


class SupportConversationIndex(BaseModel):
    conversations: list[SupportConversation]


class SupportConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    is_pinned: bool | None = None
    group_id: str | None = None


class SupportGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be blank")
        return value.strip()


class SupportGroupIndex(BaseModel):
    groups: list[SupportConversationGroup]


class SupportMessages(BaseModel):
    messages: list[MessageRecord]


class SupportMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    request_id: str = Field(min_length=1, max_length=128)

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value.strip()


class SupportActionRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=128)


def create_support_router(
    get_support_service: Callable[[], SupportService],
    get_observability_service: Callable[[], ObservabilityService] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/support", tags=["support"])

    @router.post("/conversations", status_code=201, response_model=SupportConversation)
    def create_conversation(
        request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> SupportConversation:
        actor = getattr(request.state, "authenticated_user", None)
        return service.create_conversation(
            owner_user_id=actor.user_id if actor else None,
            retail_user_id=actor.retail_user_id if actor else None,
        )

    @router.get("/conversations", response_model=SupportConversationIndex)
    def list_conversations(
        request: Request,
        active_conversation_id: str | None = Query(default=None),
        service: SupportService = Depends(get_support_service),
    ) -> SupportConversationIndex:
        return SupportConversationIndex(conversations=service.list_conversations(_owner(request), active_conversation_id=active_conversation_id))

    @router.get("/conversations/{conversation_id}", response_model=SupportConversation)
    def get_conversation(
        conversation_id: str, request: Request,
        service: SupportService = Depends(get_support_service)
    ) -> SupportConversation:
        try:
            return service.get_conversation(conversation_id, _owner(request))
        except KeyError:
            raise _not_found("未找到该会话。")

    @router.delete("/conversations/{conversation_id}", status_code=204)
    def archive_conversation(
        conversation_id: str, request: Request,
        service: SupportService = Depends(get_support_service)
    ) -> None:
        try:
            service.archive_conversation(conversation_id, _owner(request))
        except KeyError:
            raise _not_found("未找到该会话。")

    @router.patch("/conversations/{conversation_id}", response_model=SupportConversation)
    def update_conversation(
        conversation_id: str, command: SupportConversationUpdate, request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> SupportConversation:
        try:
            return service.update_conversation(
                conversation_id, _owner(request), title=command.title,
                is_pinned=command.is_pinned, group_id=command.group_id,
                update_group="group_id" in command.model_fields_set,
            )
        except KeyError:
            raise _not_found("未找到该会话或分组。")

    @router.get("/conversation-groups", response_model=SupportGroupIndex)
    def list_groups(request: Request, service: SupportService = Depends(get_support_service)) -> SupportGroupIndex:
        owner = _owner(request)
        return SupportGroupIndex(groups=service.list_groups(owner) if owner else [])

    @router.post("/conversation-groups", status_code=201, response_model=SupportConversationGroup)
    def create_group(command: SupportGroupRequest, request: Request, service: SupportService = Depends(get_support_service)) -> SupportConversationGroup:
        owner = _owner(request)
        if owner is None:
            # Anonymous mode is only used by local tests and development.
            owner = "local-anonymous"
            if service._unit.users.get(owner) is None:
                from app.persistence.models import UserRecord
                with service._unit.transaction():
                    service._unit.users.create(UserRecord(user_id=owner, email="local-anonymous@local.dev", display_name="Local", password_hash="disabled", role="customer"))
        return service.create_group(owner, command.name)

    @router.patch("/conversation-groups/{group_id}", response_model=SupportConversationGroup)
    def rename_group(group_id: str, command: SupportGroupRequest, request: Request, service: SupportService = Depends(get_support_service)) -> SupportConversationGroup:
        try:
            return service.rename_group(group_id, _owner(request) or "local-anonymous", command.name)
        except KeyError:
            raise _not_found("未找到该分组。")

    @router.delete("/conversation-groups/{group_id}", status_code=204)
    def delete_group(group_id: str, request: Request, service: SupportService = Depends(get_support_service)) -> None:
        try:
            service.delete_group(group_id, _owner(request) or "local-anonymous")
        except KeyError:
            raise _not_found("未找到该分组。")

    @router.get(
        "/conversations/{conversation_id}/messages", response_model=SupportMessages
    )
    def list_messages(
        conversation_id: str,
        request: Request,
        limit: int = Query(default=100, ge=1, le=100),
        service: SupportService = Depends(get_support_service),
    ) -> SupportMessages:
        try:
            messages = service.list_messages(conversation_id, _owner(request))
        except KeyError:
            raise _not_found("未找到该会话。")
        return SupportMessages(messages=messages[-limit:])

    @router.post(
        "/conversations/{conversation_id}/messages", response_model=SupportTurnResult
    )
    def submit_message(
        conversation_id: str,
        request: SupportMessageRequest,
        http_request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> SupportTurnResult:
        try:
            return service.submit_message(
                conversation_id, content=request.content, request_id=request.request_id,
                owner_user_id=_owner(http_request),
            )
        except ModelProviderError as exc:
            raise _model_provider_error(exc)
        except KeyError:
            raise _not_found("未找到该会话。")

    @router.post("/conversations/{conversation_id}/messages/stream")
    def stream_message(
        conversation_id: str,
        command: SupportMessageRequest,
        request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> StreamingResponse:
        owner_user_id = _owner(request)
        try:
            service.get_conversation(conversation_id, owner_user_id)
        except KeyError:
            raise _not_found("未找到该会话。")
        return StreamingResponse(
            stream_support_turn(
                service,
                conversation_id=conversation_id,
                content=command.content,
                request_id=command.request_id,
                owner_user_id=owner_user_id,
                error_sink=(
                    lambda exc: get_observability_service().capture_issue(
                        source=(
                            "mcp"
                            if type(exc).__name__ == "McpTransportError"
                            else "database"
                            if isinstance(exc, sqlite3.Error)
                            else "planner"
                        ),
                        severity="error",
                        error_code=f"STREAM_{type(exc).__name__.upper()}",
                        exception=exc,
                        request_id=command.request_id,
                        conversation_id=conversation_id,
                        context={"path": "support_stream", "component": "support"},
                    )
                    if get_observability_service is not None
                    else None
                ),
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post(
        "/conversations/{conversation_id}/actions/{action_id}/confirm",
        response_model=SupportTurnResult,
    )
    def confirm_action(
        conversation_id: str,
        action_id: str,
        request: SupportActionRequest,
        http_request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> SupportTurnResult:
        try:
            return service.confirm_action(
                conversation_id, action_id, request_id=request.request_id,
                owner_user_id=_owner(http_request),
            )
        except HandoffActiveError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "human_handoff_active",
                    "message": str(exc),
                    "recoverable": True,
                },
            )
        except KeyError:
            raise _not_found("未找到该待确认操作。")

    @router.post(
        "/conversations/{conversation_id}/actions/{action_id}/reject",
        response_model=SupportTurnResult,
    )
    def reject_action(
        conversation_id: str,
        action_id: str,
        request: SupportActionRequest,
        http_request: Request,
        service: SupportService = Depends(get_support_service),
    ) -> SupportTurnResult:
        try:
            return service.reject_action(
                conversation_id, action_id, request_id=request.request_id,
                owner_user_id=_owner(http_request),
            )
        except KeyError:
            raise _not_found("未找到该待确认操作。")

    if get_observability_service is not None:
        @router.post("/feedback", status_code=201, response_model=FeedbackPublic)
        def submit_issue_feedback(command: IssueFeedbackCreate, request: Request, service: ObservabilityService = Depends(get_observability_service)):
            try:
                return service.submit_issue_feedback(request.state.authenticated_user, command)
            except ObservabilityNotFound:
                raise _not_found("未找到该会话。")

        @router.post("/conversations/{conversation_id}/feedback", status_code=201, response_model=FeedbackPublic)
        def submit_feedback(conversation_id: str, command: FeedbackCreate, request: Request, service: ObservabilityService = Depends(get_observability_service)):
            try: return service.submit_feedback(request.state.authenticated_user, conversation_id, command)
            except ObservabilityNotFound: raise _not_found("未找到该会话。")

        @router.get("/conversations/{conversation_id}/feedback")
        def list_feedback(conversation_id: str, request: Request, service: ObservabilityService = Depends(get_observability_service)):
            try: return {"feedback": service.list_own_feedback(request.state.authenticated_user, conversation_id)}
            except ObservabilityNotFound: raise _not_found("未找到该会话。")

    return router


def _owner(request: Request) -> str | None:
    user = getattr(request.state, "authenticated_user", None)
    return user.user_id if user is not None else None


def _not_found(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "not_found", "message": message, "recoverable": False},
    )


def _model_provider_error(error: ModelProviderError) -> HTTPException:
    quota_exhausted = error.reason == "quota_exhausted"
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "code": (
                "model_quota_exhausted"
                if quota_exhausted
                else "model_provider_unavailable"
            ),
            "message": (
                "智能客服模型的可用额度已耗尽，请稍后重试或联系管理员切换模型。"
                if quota_exhausted
                else "智能客服模型暂时不可用，请稍后重试。"
            ),
            "recoverable": True,
        },
    )
