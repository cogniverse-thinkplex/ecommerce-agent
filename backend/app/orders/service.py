from __future__ import annotations

from datetime import datetime, time, timezone

from app.account.spending import demo_purchase_date
from app.auth.models import AuthenticatedUser
from app.orders.models import OrderDetail, OrderIndex, OrderItem, OrderSummary
from app.persistence.models import DemoOrderMetadataRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolPort


class OrderNotFoundError(KeyError):
    pass


class OrderCenterService:
    def __init__(self, unit: SqliteUnitOfWork, retail_port: RetailToolPort) -> None:
        self._unit = unit
        self._retail_port = retail_port

    def list_orders(self, actor: AuthenticatedUser, status: str | None = None) -> OrderIndex:
        order_ids = self._owned_order_ids(actor)
        rows: list[OrderSummary] = []
        for order_id in order_ids:
            result = self._retail_port.call_tool("get_order_details", {"order_id": order_id}, call_id=f"orders-{order_id}")
            if result.error or not isinstance(result.content, dict):
                rows.append(OrderSummary(order_id=order_id, status="unavailable", purchased_at=self._date(order_id), available=False))
                continue
            rows.append(self._summary(result.content))
        rows.sort(key=lambda row: row.purchased_at or "", reverse=True)
        counts = {"all": len(rows)}
        for row in rows: counts[row.status] = counts.get(row.status, 0) + 1
        filtered = rows if not status or status == "all" else [row for row in rows if row.status == status]
        return OrderIndex(orders=filtered, counts=counts)

    def get_order(self, actor: AuthenticatedUser, order_id: str) -> OrderDetail:
        owned = self._owned_order_ids(actor)
        if order_id not in owned:
            raise OrderNotFoundError(order_id)
        result = self._retail_port.call_tool("get_order_details", {"order_id": order_id}, call_id=f"order-detail-{order_id}")
        if result.error or not isinstance(result.content, dict):
            raise OrderNotFoundError(order_id)
        data = result.content
        summary = self._summary(data)
        payments, refunds = _amounts(data.get("payment_history") or [])
        return OrderDetail(
            **summary.model_dump(),
            items=[OrderItem.model_validate(item) for item in data.get("items") or []],
            payment_amount=payments, refund_amount=refunds,
            payment_method=_mask_payment(str(data.get("payment_method") or "")),
            address={str(k): str(v) for k, v in (data.get("address") or {}).items() if v is not None},
            payment_history=[_safe_payment(item) for item in data.get("payment_history") or [] if isinstance(item, dict)],
        )

    def owns(self, actor: AuthenticatedUser, order_id: str) -> bool:
        return order_id in self._owned_order_ids(actor)

    def _owned_order_ids(self, actor: AuthenticatedUser) -> list[str]:
        if actor.role != "customer" or not actor.retail_user_id:
            raise OrderNotFoundError("retail account unavailable")
        result = self._retail_port.call_tool("get_user_details", {"user_id": actor.retail_user_id}, call_id="orders-user")
        if result.error or not isinstance(result.content, dict):
            return []
        orders = result.content.get("orders") or []
        return [str(item.get("order_id") if isinstance(item, dict) else item) for item in orders]

    def _summary(self, data: dict) -> OrderSummary:
        order_id = str(data.get("order_id") or "")
        items = data.get("items") or []
        payments, refunds = _amounts(data.get("payment_history") or [])
        net = 0.0 if data.get("status") == "cancelled" else max(0.0, payments - refunds)
        return OrderSummary(order_id=order_id, status=str(data.get("status") or "unknown"), purchased_at=self._date(order_id), item_count=len(items), item_names=[str(item.get("name") or "商品") for item in items if isinstance(item, dict)], net_amount=round(net, 2))

    def _date(self, order_id: str) -> str:
        metadata = self._unit.demo_order_metadata.get(order_id)
        if metadata is None:
            purchased = demo_purchase_date(order_id)
            metadata = DemoOrderMetadataRecord(order_id=order_id, purchased_at=datetime.combine(purchased, time(12), tzinfo=timezone.utc))
            with self._unit.transaction(): self._unit.demo_order_metadata.save(metadata)
        return metadata.purchased_at.date().isoformat()


def _amounts(history: list[dict]) -> tuple[float, float]:
    paid = sum(float(row.get("amount", 0)) for row in history if row.get("transaction_type") == "payment")
    refunded = sum(float(row.get("amount", 0)) for row in history if row.get("transaction_type") == "refund")
    return round(paid, 2), round(refunded, 2)


def _mask_payment(value: str) -> str:
    suffix = "".join(char for char in value if char.isalnum())[-4:]
    return f"•••• {suffix}" if suffix else "-"


def _safe_payment(row: dict) -> dict:
    return {key: row[key] for key in ("transaction_type", "amount", "timestamp") if key in row}
