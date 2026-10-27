from __future__ import annotations

from pydantic import BaseModel, Field


class OrderItem(BaseModel):
    item_id: str
    name: str = "商品"
    price: float = 0.0
    options: dict[str, str] = Field(default_factory=dict)


class OrderSummary(BaseModel):
    order_id: str
    status: str
    purchased_at: str | None = None
    item_count: int = 0
    item_names: list[str] = Field(default_factory=list)
    net_amount: float = 0.0
    available: bool = True


class OrderIndex(BaseModel):
    orders: list[OrderSummary]
    counts: dict[str, int]


class OrderDetail(OrderSummary):
    items: list[OrderItem] = Field(default_factory=list)
    payment_amount: float = 0.0
    refund_amount: float = 0.0
    payment_method: str = "-"
    address: dict[str, str] = Field(default_factory=dict)
    payment_history: list[dict] = Field(default_factory=list)
