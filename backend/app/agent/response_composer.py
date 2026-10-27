from __future__ import annotations

import json
from typing import Any

from app.agent.state import ConversationMessage


_STATUS_LABELS = {
    "pending": "待处理",
    "processed": "处理中",
    "shipped": "已发货",
    "delivered": "已送达",
    "cancelled": "已取消",
    "canceled": "已取消",
    "returned": "已退货",
    "exchanged": "已换货",
}

_WRITE_ACTIONS = {
    "cancel_pending_order": "取消",
    "return_delivered_order_items": "退货",
    "exchange_delivered_order_items": "换货",
    "modify_pending_order_address": "修改收货地址",
    "modify_pending_order_items": "修改商品",
    "modify_pending_order_payment": "修改支付方式",
}


def compose_tool_response(message: ConversationMessage) -> str | None:
    if message.role != "tool" or not message.tool_name:
        return None

    payload = _parse_json(message.content)
    if message.tool_name == "find_user_id_by_name_zip" and payload is None:
        if message.content:
            return "身份信息已确认。您可以继续查询订单或办理售后。"

    if payload is None:
        if message.content and message.content.startswith("Error:"):
            return _safe_error_response(message.tool_name)
        return None

    if message.tool_name == "find_user_id_by_name_zip":
        user_id = _payload_scalar(payload, "user_id")
        if user_id:
            return "身份信息已确认。您可以继续查询订单或办理售后。"

    if message.tool_name == "get_order_details":
        order_id = _payload_scalar(payload, "order_id")
        status = _payload_scalar(payload, "status")
        items = payload.get("items") or [] if isinstance(payload, dict) else []
        item_count = len(items)
        if order_id and status:
            item_summary = _format_items(items)
            amount = _order_amount(payload)
            amount_text = f"订单金额 {_format_money(amount)}。" if amount is not None else ""
            next_step = _order_next_step(status)
            return (
                f"订单 {order_id} 当前为{_status_label(status)}，共 {item_count} 件商品"
                f"{f'：{item_summary}' if item_summary else ''}。{amount_text}{next_step}"
            )

    if message.tool_name == "get_user_details" and isinstance(payload, dict):
        orders = payload.get("orders")
        if isinstance(orders, list):
            name = _person_name(payload.get("name")) or "当前账户"
            if not orders:
                return f"{name} 名下暂时没有订单。您还需要查询其他账户信息吗？"
            order_ids = "、".join(str(order_id) for order_id in orders)
            return f"{name} 名下共有 {len(orders)} 个订单：{order_ids}。您想查看哪个订单？"

    if message.tool_name == "get_product_details":
        name = _payload_scalar(payload, "name")
        variants = payload.get("variants") if isinstance(payload, dict) else None
        if name and isinstance(variants, dict):
            available = [
                variant for variant in variants.values()
                if isinstance(variant, dict) and variant.get("available") is True
            ]
            option_text = "；".join(
                _format_options(variant.get("options")) for variant in available
                if _format_options(variant.get("options"))
            )
            return (
                f"{name} 当前有 {len(available)} 个可选规格"
                f"{f'：{option_text}' if option_text else ''}。"
                "如需，我可以继续帮您确认该商品是否在您的订单中。"
            )

    if message.tool_name in _WRITE_ACTIONS:
        order_id = _payload_scalar(payload, "order_id")
        status = _payload_scalar(payload, "status")
        if order_id and status:
            action = _WRITE_ACTIONS[message.tool_name]
            suffix = "退款进度请以原支付渠道为准。" if action in {"取消", "退货"} else "您可以继续查看订单详情。"
            return f"订单 {order_id} 已成功{action}，当前状态为{_status_label(status)}。{suffix}"

    return None


def _parse_json(content: str | None) -> Any | None:
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _payload_scalar(payload: Any, key: str) -> str | None:
    if isinstance(payload, dict):
        value = payload.get(key)
        if value is not None:
            return str(value)
    if key == "user_id" and isinstance(payload, str):
        return payload
    return None


def _status_label(status: str) -> str:
    return _STATUS_LABELS.get(status.lower(), "状态待确认")


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def _format_items(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    summaries = []
    for item in items[:5]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "商品")
        price = item.get("price")
        summaries.append(f"{name}（{_format_money(price)}）" if price is not None else name)
    if len(items) > 5:
        summaries.append(f"等 {len(items)} 件")
    return "、".join(summaries)


def _order_amount(payload: dict[str, Any]) -> Any | None:
    history = payload.get("payment_history")
    if not isinstance(history, list):
        return None
    payments = [
        item.get("amount") for item in history
        if isinstance(item, dict) and item.get("transaction_type") == "payment"
    ]
    return payments[-1] if payments else None


def _order_next_step(status: str) -> str:
    normalized = status.lower()
    if normalized == "pending":
        return "您可以继续查询物流、修改或取消该订单。"
    if normalized == "delivered":
        return "您可以继续申请退货、换货或查询商品信息。"
    return "您可以继续查看订单详情。"


def _person_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return " ".join(
        str(value.get(key) or "").strip() for key in ("first_name", "last_name")
    ).strip()


def _format_options(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return "，".join(f"{key}：{item}" for key, item in value.items())


def _safe_error_response(tool_name: str) -> str:
    if tool_name in {"get_order_details", "get_user_details"}:
        return "暂时无法读取订单信息，请稍后重试；如果问题持续，可以转接人工客服。"
    if tool_name == "get_product_details":
        return "暂时无法读取商品信息，请稍后重试；如果问题持续，可以转接人工客服。"
    return "当前操作暂时没有完成，请稍后重试；如果问题持续，可以转接人工客服。"
