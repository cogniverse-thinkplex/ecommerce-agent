from __future__ import annotations

import json
from typing import Any

from app.agent.state import ConversationMessage, CustomerAgentState, PendingAction
from app.support.models import SupportMessageBlock


def project_state(
    state: CustomerAgentState, *, message_start: int = 0, include_pending: bool = True
) -> list[SupportMessageBlock]:
    blocks: list[SupportMessageBlock] = []
    for message in state.messages[message_start:]:
        block = _project_message(message)
        if block is not None and (not blocks or block != blocks[-1]):
            blocks.append(block)
    citation_block = _project_policy_citations(state)
    if citation_block is not None:
        blocks.append(citation_block)
    if include_pending and state.confirmation.pending is not None:
        blocks.append(_project_confirmation(state.confirmation.pending))
    return blocks


def _project_policy_citations(state: CustomerAgentState) -> SupportMessageBlock | None:
    event = next(
        (item for item in reversed(state.events) if item.event_type in {"rag.completed", "rag.degraded"}),
        None,
    )
    if event is None or not event.payload.get("hits"):
        return None
    allowed = ("policy_id", "title", "content", "scope", "source_url", "verified_at")
    citations = [
        {key: hit[key] for key in allowed if key in hit}
        for hit in event.payload["hits"][:3]
    ]
    return SupportMessageBlock(
        type="policy_citations",
        title="相关政策依据",
        text="以下为政策摘要；订单当前状态与可执行操作以实时查询结果为准。",
        data={"citations": citations},
    )


def _project_message(message: ConversationMessage) -> SupportMessageBlock | None:
    if message.role == "assistant" and message.content:
        if message.content.startswith("请确认是否执行这个写操作："):
            return None
        if message.content.startswith("找到用户 ID："):
            return SupportMessageBlock(type="text", text="身份验证成功。")
        return SupportMessageBlock(type="text", text=message.content)
    if message.role != "tool" or not message.tool_name:
        return None
    if message.tool_name in {"find_user_id_by_name_zip", "find_user_id_by_email"}:
        return SupportMessageBlock(type="text", text="身份验证成功。")
    payload = _object_payload(message.content)
    if payload is None:
        return None
    if message.tool_name == "get_order_details":
        return SupportMessageBlock(
            type="order_summary",
            title=f"订单 {payload.get('order_id', '')}".strip(),
            data=_allow(payload, "order_id", "status", "items", "address", "payment_method"),
        )
    if message.tool_name == "get_product_details":
        return SupportMessageBlock(
            type="product_summary",
            title=str(payload.get("name") or "商品信息"),
            data=_allow(payload, "product_id", "name", "variants"),
        )
    if message.tool_name == "get_user_details":
        return SupportMessageBlock(
            type="profile_summary",
            title="账户信息",
            data=_allow(payload, "name", "email", "address", "orders"),
        )
    return None


def _project_confirmation(pending: PendingAction) -> SupportMessageBlock:
    labels = {
        "cancel_pending_order": "确认取消订单",
        "modify_pending_order_address": "确认修改配送地址",
        "modify_pending_order_items": "确认修改订单商品",
        "return_delivered_order_items": "确认退货",
        "exchange_delivered_order_items": "确认换货",
        "modify_user_address": "确认修改默认地址",
    }
    allowed = {
        key: value
        for key, value in pending.arguments.items()
        if key
        in {
            "order_id",
            "reason",
            "item_ids",
            "new_item_ids",
            "address1",
            "address2",
            "city",
            "state",
            "country",
            "zip",
        }
    }
    return SupportMessageBlock(
        type="confirmation",
        title=labels.get(pending.name, "确认执行操作"),
        text="请核对以下信息。确认仅授权本次操作一次，参数发生变化时需要重新确认。",
        data=allowed,
    )


def _object_payload(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _allow(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}

