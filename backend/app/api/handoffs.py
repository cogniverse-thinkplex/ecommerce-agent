from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.persistence.models import HumanHandoffRecord
from app.support.handoff import HandoffConflictError, HumanHandoffService


class CreateHandoffRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=100)
    message: str | None = Field(default=None, max_length=2000)


class HandoffIndex(BaseModel):
    handoffs: list[HumanHandoffRecord]


class HandoffDetail(BaseModel):
    handoff: HumanHandoffRecord
    messages: list[dict]


def create_handoff_router(
    get_handoff_service: Callable[[], HumanHandoffService],
) -> APIRouter:
    router = APIRouter(tags=["handoffs"])

    @router.post(
        "/api/v1/support/conversations/{conversation_id}/handoff",
        status_code=201,
        response_model=HumanHandoffRecord,
    )
    def create_handoff(
        conversation_id: str,
        command: CreateHandoffRequest,
        request: Request,
        service: HumanHandoffService = Depends(get_handoff_service),
    ) -> HumanHandoffRecord:
        actor = request.state.authenticated_user
        try:
            return service.create_or_get_active(
                conversation_id,
                actor.user_id,
                reason=command.reason,
                customer_message=command.message,
                context_summary="客户申请人工服务。",
            )
        except KeyError:
            raise _error(404, "not_found", "未找到该会话。")
        except HandoffConflictError as exc:
            raise _error(409, "handoff_conflict", str(exc))

    @router.get(
        "/api/v1/support/conversations/{conversation_id}/handoff",
        response_model=HumanHandoffRecord,
    )
    def get_handoff(
        conversation_id: str,
        request: Request,
        service: HumanHandoffService = Depends(get_handoff_service),
    ) -> HumanHandoffRecord:
        try:
            return service.get_for_owner(
                conversation_id, request.state.authenticated_user.user_id
            )
        except KeyError:
            raise _error(404, "not_found", "当前会话没有进行中的人工工单。")

    @router.get("/api/v1/admin/handoffs", response_model=HandoffIndex)
    def list_handoffs(
        service: HumanHandoffService = Depends(get_handoff_service),
    ) -> HandoffIndex:
        return HandoffIndex(handoffs=service.list_for_developer())

    @router.get(
        "/api/v1/admin/handoffs/{ticket_id}", response_model=HandoffDetail
    )
    def get_handoff_detail(
        ticket_id: str,
        service: HumanHandoffService = Depends(get_handoff_service),
    ) -> HandoffDetail:
        try:
            ticket = service.get_for_developer(ticket_id)
            messages = [
                {
                    "role": message.role,
                    "kind": message.kind,
                    "text": message.text,
                    "created_at": message.created_at.isoformat(),
                }
                for message in service.conversation_messages(ticket_id)
                if message.role in {"user", "assistant", "action"}
            ]
            return HandoffDetail(handoff=ticket, messages=messages)
        except KeyError:
            raise _error(404, "not_found", "未找到人工工单。")

    def transition(ticket_id: str, request: Request, target: str):
        service = get_handoff_service()
        actor_id = request.state.authenticated_user.user_id
        try:
            if target == "claim":
                return service.claim(ticket_id, actor_id)
            if target == "resolve":
                return service.resolve(ticket_id, actor_id)
            return service.cancel(ticket_id, actor_id)
        except KeyError:
            raise _error(404, "not_found", "未找到人工工单。")
        except HandoffConflictError as exc:
            raise _error(409, "handoff_conflict", str(exc))

    @router.post(
        "/api/v1/admin/handoffs/{ticket_id}/claim",
        response_model=HumanHandoffRecord,
    )
    def claim_handoff(ticket_id: str, request: Request):
        return transition(ticket_id, request, "claim")

    @router.post(
        "/api/v1/admin/handoffs/{ticket_id}/resolve",
        response_model=HumanHandoffRecord,
    )
    def resolve_handoff(ticket_id: str, request: Request):
        return transition(ticket_id, request, "resolve")

    @router.post(
        "/api/v1/admin/handoffs/{ticket_id}/cancel",
        response_model=HumanHandoffRecord,
    )
    def cancel_handoff(ticket_id: str, request: Request):
        return transition(ticket_id, request, "cancel")

    return router


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "recoverable": True},
    )
