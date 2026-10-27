from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
import hashlib
from typing import Literal

from app.auth.models import AuthenticatedUser
from app.persistence.models import DemoOrderMetadataRecord
from app.persistence.sqlite import SqliteUnitOfWork
from app.tools.retail_port import RetailToolPort

Period = Literal["week", "month", "year"]
DEMO_ANCHOR = date(2026, 10, 23)

CATEGORIES = {
    "Headphones":"数码","Mechanical Keyboard":"数码","Smart Watch":"数码","Digital Camera":"数码","Action Camera":"数码","Bluetooth Speaker":"数码","Smart Thermostat":"家居","Office Chair":"家居","LED Light Bulb":"家居","Vacuum Cleaner":"家居","Desk Lamp":"家居","Patio Umbrella":"家居","T-Shirt":"服饰","Sunglasses":"服饰","Backpack":"服饰","Skateboard":"运动户外","Dumbbell Set":"运动户外","Water Bottle":"运动户外","Espresso Machine":"食品饮料",
}


def demo_purchase_date(order_id: str, *, anchor: date = DEMO_ANCHOR) -> date:
    offset = int(hashlib.sha256(order_id.encode()).hexdigest()[:8], 16) % 730
    return anchor - timedelta(days=offset)


class SpendingService:
    def __init__(self, unit: SqliteUnitOfWork, retail_port: RetailToolPort, *, today: date | None = None) -> None:
        self._unit, self._retail_port, self._today = unit, retail_port, today or DEMO_ANCHOR

    def summary(self, actor: AuthenticatedUser, period: Period) -> dict:
        if period not in {"week", "month", "year"}: raise ValueError("不支持的统计周期。")
        orders = self._orders(actor)
        buckets = _buckets(period, self._today)
        start = buckets[0][0]
        series = [{"label": label, "amount": 0.0, "orders": 0} for _, _, label in buckets]
        categories: dict[str, dict] = defaultdict(lambda: {"amount": 0.0, "purchases": 0})
        recent, net_total, refunds, count = [], 0.0, 0.0, 0
        for order, purchased in orders:
            if purchased < start or purchased > self._today: continue
            payments = sum(float(x.get("amount", 0)) for x in order.get("payment_history", []) if x.get("transaction_type") == "payment")
            order_refunds = sum(float(x.get("amount", 0)) for x in order.get("payment_history", []) if x.get("transaction_type") == "refund")
            net = 0.0 if order.get("status") == "cancelled" else max(0.0, payments - order_refunds)
            refunds += order_refunds
            if net > 0: count += 1
            net_total += net
            for index, (bucket_start, bucket_end, _) in enumerate(buckets):
                if bucket_start <= purchased <= bucket_end:
                    series[index]["amount"] = round(series[index]["amount"] + net, 2)
                    if net > 0: series[index]["orders"] += 1
                    break
            items = order.get("items") or []
            item_total = sum(max(0.0, float(item.get("price", 0))) for item in items)
            allocated = 0.0
            for index, item in enumerate(items):
                amount = round(net - allocated, 2) if index == len(items)-1 else round(net * float(item.get("price",0)) / item_total, 2) if item_total else 0.0
                allocated += amount
                category = CATEGORIES.get(str(item.get("name", "")), "其他")
                categories[category]["amount"] = round(categories[category]["amount"] + amount, 2)
                if amount > 0: categories[category]["purchases"] += 1
            recent.append({"order_id":order.get("order_id"),"date":purchased.isoformat(),"status":order.get("status"),"amount":round(net,2)})
        return {
            "period": period, "demo_data": True,
            "summary": {"net_spend":round(net_total,2),"refund_amount":round(refunds,2),"order_count":count,"average_order_value":round(net_total/count,2) if count else 0.0},
            "series": series,
            "categories": sorted(({"category":key,**value} for key,value in categories.items() if value["amount"] > 0), key=lambda row: row["amount"], reverse=True),
            "recent_orders": sorted(recent, key=lambda row: row["date"], reverse=True)[:8],
        }

    def _orders(self, actor: AuthenticatedUser) -> list[tuple[dict, date]]:
        if actor.role != "customer" or not actor.retail_user_id: return []
        result = self._retail_port.call_tool("get_user_details", {"user_id":actor.retail_user_id}, call_id="spending-user-orders")
        if result.error or not isinstance(result.content, dict): return []
        rows = []
        for order_id in result.content.get("orders", []):
            metadata = self._unit.demo_order_metadata.get(str(order_id))
            if metadata is None:
                purchased = demo_purchase_date(str(order_id), anchor=self._today)
                metadata = DemoOrderMetadataRecord(order_id=str(order_id), purchased_at=datetime.combine(purchased,time(12),tzinfo=timezone.utc))
                with self._unit.transaction(): self._unit.demo_order_metadata.save(metadata)
            detail = self._retail_port.call_tool("get_order_details", {"order_id":str(order_id)}, call_id=f"spending-{order_id}")
            if not detail.error and isinstance(detail.content, dict): rows.append((detail.content, metadata.purchased_at.date()))
        return rows


def _buckets(period: Period, today: date) -> list[tuple[date,date,str]]:
    if period == "week":
        current = today - timedelta(days=today.weekday())
        starts = [current - timedelta(weeks=i) for i in reversed(range(12))]
        return [(start, start+timedelta(days=6), f"{start.month}/{start.day}") for start in starts]
    if period == "month":
        starts=[]
        for offset in reversed(range(12)):
            value=today.year*12+today.month-1-offset; starts.append(date(value//12,value%12+1,1))
        return [(start, (date(start.year+(start.month==12), start.month%12+1, 1)-timedelta(days=1)), f"{start.year}/{start.month:02d}") for start in starts]
    starts=[date(today.year-offset,1,1) for offset in reversed(range(5))]
    return [(start,date(start.year,12,31),str(start.year)) for start in starts]
