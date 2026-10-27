from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Callable
from typing import Any

from pydantic import BaseModel

from app.agent.progress import AgentProgressEvent
from app.agent.proposal_generator import ModelProviderError
from app.tools.mcp_retail_adapter import McpTransportError
from app.support.service import SupportService


class SupportStreamEvent(BaseModel):
    event: str
    event_id: int
    data: dict[str, Any]


def encode_sse(event: SupportStreamEvent) -> bytes:
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return (
        f"id: {event.event_id}\nevent: {event.event}\ndata: {data}\n\n"
    ).encode("utf-8")


async def stream_support_turn(
    service: SupportService,
    *,
    conversation_id: str,
    content: str,
    request_id: str,
    owner_user_id: str | None,
    heartbeat_seconds: float = 10.0,
    error_sink: Callable[[Exception], None] | None = None,
) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    next_event_id = 1

    def progress_sink(progress: AgentProgressEvent) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, ("progress", progress))

    def run_turn() -> None:
        try:
            result = service.submit_message(
                conversation_id,
                content=content,
                request_id=request_id,
                owner_user_id=owner_user_id,
                progress_sink=progress_sink,
            )
        except Exception as exc:
            if error_sink is not None:
                error_sink(exc)
            loop.call_soon_threadsafe(queue.put_nowait, ("error", exc))
        else:
            loop.call_soon_threadsafe(queue.put_nowait, ("result", result))

    yield encode_sse(
        SupportStreamEvent(
            event="accepted",
            event_id=next_event_id,
            data={"conversation_id": conversation_id, "request_id": request_id},
        )
    )
    next_event_id += 1
    worker = asyncio.create_task(asyncio.to_thread(run_turn))
    try:
        while True:
            try:
                kind, value = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_seconds
                )
            except TimeoutError:
                yield b": heartbeat\n\n"
                continue
            if kind == "progress":
                yield encode_sse(
                    SupportStreamEvent(
                        event="progress",
                        event_id=next_event_id,
                        data=value.model_dump(mode="json", exclude_none=True),
                    )
                )
                next_event_id += 1
                continue
            if kind == "error":
                yield encode_sse(
                    SupportStreamEvent(
                        event="error",
                        event_id=next_event_id,
                        data=_safe_error(value),
                    )
                )
                break
            for index, block in enumerate(value.blocks):
                event_name = (
                    "confirmation_required"
                    if block.type == "confirmation"
                    else "block"
                )
                yield encode_sse(
                    SupportStreamEvent(
                        event=event_name,
                        event_id=next_event_id,
                        data={
                            "index": index,
                            "block": block.model_dump(mode="json"),
                            **(
                                {"action_id": value.pending_action_id}
                                if value.pending_action_id
                                else {}
                            ),
                        },
                    )
                )
                next_event_id += 1
            if value.handoff_ticket_id:
                yield encode_sse(
                    SupportStreamEvent(
                        event="handoff",
                        event_id=next_event_id,
                        data={
                            "ticket_id": value.handoff_ticket_id,
                            "status": value.handoff_status,
                            "message": "已为您申请人工服务。",
                        },
                    )
                )
                break
            yield encode_sse(
                SupportStreamEvent(
                    event="completed",
                    event_id=next_event_id,
                    data={
                        "pending_action_id": value.pending_action_id,
                        "block_count": len(value.blocks),
                    },
                )
            )
            break
    finally:
        await worker


def _safe_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, ModelProviderError):
        quota = error.reason == "quota_exhausted"
        return {
            "code": "model_quota_exhausted" if quota else "model_provider_unavailable",
            "message": (
                "智能客服模型的可用额度已耗尽，请稍后重试或联系管理员。"
                if quota
                else "智能客服模型暂时不可用，请稍后重试。"
            ),
            "recoverable": True,
        }
    if isinstance(error, McpTransportError):
        return {
            "code": "retail_tools_unavailable",
            "message": "订单系统暂时不可用，请稍后重试或申请人工服务。",
            "recoverable": True,
        }
    if isinstance(error, sqlite3.Error):
        return {
            "code": "support_storage_unavailable",
            "message": "会话暂时无法保存，请稍后重试。",
            "recoverable": True,
        }
    return {
        "code": "support_turn_failed",
        "message": "本次请求未能完成，请稍后重试或申请人工服务。",
        "recoverable": True,
    }
