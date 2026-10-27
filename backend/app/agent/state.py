from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.order_identity import canonicalize_retail_order_id


MessageRole = Literal["system", "user", "assistant", "tool"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConversationMessage(BaseModel):
    role: MessageRole
    content: str | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)


class PendingAction(BaseModel):
    name: str
    arguments: dict[str, Any]
    fingerprint: str


class ConfirmationState(BaseModel):
    pending: PendingAction | None = None
    confirmed_fingerprints: list[str] = Field(default_factory=list)


class CompletedWrite(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str


class ResolvedProduct(BaseModel):
    product_id: str
    name: str = ""
    available_variants: list[dict[str, Any]] = Field(default_factory=list)


class WriteObjective(BaseModel):
    objective_id: str
    tool_name: str
    order_id: str | None = None
    intent: str = ""
    status: Literal["pending", "completed"] = "pending"
    completed_fingerprint: str | None = None


class ObjectiveLedger(BaseModel):
    original_objective: str = ""
    locked_order_id: str | None = None
    active_order_id: str | None = None
    active_policy_id: str | None = None
    inspected_order_ids: list[str] = Field(default_factory=list)
    failed_order_ids: list[str] = Field(default_factory=list)
    known_order_ids: list[str] = Field(default_factory=list)
    resolved_products: list[ResolvedProduct] = Field(default_factory=list)
    completed_writes: list[CompletedWrite] = Field(default_factory=list)
    write_plan: list[WriteObjective] = Field(default_factory=list)


class AgentEvent(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)


class CustomerAgentState(BaseModel):
    conversation_id: str
    messages: list[ConversationMessage] = Field(default_factory=list)
    confirmation: ConfirmationState = Field(default_factory=ConfirmationState)
    objective_ledger: ObjectiveLedger = Field(default_factory=ObjectiveLedger)
    events: list[AgentEvent] = Field(default_factory=list)


def append_event(
    state: CustomerAgentState,
    event_type: str,
    payload: dict[str, Any] | None = None,
) -> CustomerAgentState:
    events = [
        *state.events,
        AgentEvent(event_type=event_type, payload=payload or {}),
    ]
    return state.model_copy(update={"events": events})


def initialize_objective_ledger(
    state: CustomerAgentState,
    objective: str,
) -> CustomerAgentState:
    if state.objective_ledger.original_objective:
        return state
    return state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={"original_objective": objective}
            )
        }
    )


def record_tool_execution(
    state: CustomerAgentState,
    *,
    tool_name: str,
    arguments: dict[str, Any],
    raw_content: str | None,
    tool_type: str,
    error: bool,
    fingerprint: str | None = None,
) -> CustomerAgentState:
    if error:
        if tool_name == "get_order_details":
            order_id = canonicalize_retail_order_id(arguments.get("order_id"))
            if order_id and order_id not in state.objective_ledger.failed_order_ids:
                ledger = state.objective_ledger.model_copy(
                    update={
                        "failed_order_ids": [
                            *state.objective_ledger.failed_order_ids,
                            order_id,
                        ]
                    }
                )
                return state.model_copy(update={"objective_ledger": ledger})
        return state
    ledger = state.objective_ledger
    payload = _json_object(raw_content)

    if tool_name == "get_order_details":
        order_id = canonicalize_retail_order_id(
            (payload or {}).get("order_id") or arguments.get("order_id")
        )
        if order_id and order_id not in ledger.inspected_order_ids:
            ledger = ledger.model_copy(
                update={
                    "active_order_id": order_id,
                    "inspected_order_ids": [*ledger.inspected_order_ids, order_id],
                    "failed_order_ids": [
                        failed
                        for failed in ledger.failed_order_ids
                        if failed != order_id
                    ],
                }
            )

    if tool_name == "get_user_details" and payload is not None:
        known_order_ids = [*ledger.known_order_ids]
        for order_id in _order_ids_from_user_details(payload):
            if order_id not in known_order_ids:
                known_order_ids.append(order_id)
        ledger = ledger.model_copy(update={"known_order_ids": known_order_ids})

    if tool_name == "get_product_details" and payload is not None:
        product_id = str(payload.get("product_id") or arguments.get("product_id") or "")
        variants = payload.get("variants")
        available_variants = []
        if isinstance(variants, dict):
            for fallback_id, variant in variants.items():
                if not isinstance(variant, dict) or not variant.get("available"):
                    continue
                available_variants.append(
                    {
                        "item_id": str(variant.get("item_id") or fallback_id),
                        "options": variant.get("options") or {},
                    }
                )
        product = ResolvedProduct(
            product_id=product_id,
            name=str(payload.get("name") or ""),
            available_variants=available_variants,
        )
        products = [
            existing
            for existing in ledger.resolved_products
            if existing.product_id != product_id
        ]
        ledger = ledger.model_copy(update={"resolved_products": [*products, product]})

    if tool_type == "write" and fingerprint:
        if fingerprint not in {item.fingerprint for item in ledger.completed_writes}:
            completed = CompletedWrite(
                name=tool_name,
                arguments=arguments,
                fingerprint=fingerprint,
            )
            order_id = arguments.get("order_id")
            write_plan = ledger.write_plan
            locked_order_id = ledger.locked_order_id
            matched_index = _matching_pending_objective_index(
                write_plan,
                tool_name=tool_name,
                order_id=str(order_id) if order_id is not None else None,
            )
            if matched_index is not None:
                write_plan = [*write_plan]
                write_plan[matched_index] = write_plan[matched_index].model_copy(
                    update={
                        "status": "completed",
                        "completed_fingerprint": fingerprint,
                    }
                )
                next_pending = next(
                    (item for item in write_plan if item.status == "pending"),
                    None,
                )
                locked_order_id = (
                    next_pending.order_id if next_pending is not None else None
                )
            elif not write_plan and order_id is not None:
                locked_order_id = str(order_id)
            ledger = ledger.model_copy(
                update={
                    "completed_writes": [*ledger.completed_writes, completed],
                    "write_plan": write_plan,
                    "locked_order_id": locked_order_id,
                }
            )

    return state.model_copy(update={"objective_ledger": ledger})


def _matching_pending_objective_index(
    write_plan: list[WriteObjective],
    *,
    tool_name: str,
    order_id: str | None,
) -> int | None:
    for index, objective in enumerate(write_plan):
        if objective.status != "pending" or objective.tool_name != tool_name:
            continue
        if objective.order_id and order_id and objective.order_id != order_id:
            continue
        return index
    return None


def _json_object(content: str | None) -> dict[str, Any] | None:
    if not content:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _order_ids_from_user_details(payload: dict[str, Any]) -> list[str]:
    orders = payload.get("orders")
    if isinstance(orders, dict):
        candidates: list[object] = list(orders)
    elif isinstance(orders, list):
        candidates = [
            item.get("order_id") if isinstance(item, dict) else item
            for item in orders
        ]
    else:
        return []

    order_ids: list[str] = []
    for candidate in candidates:
        order_id = canonicalize_retail_order_id(candidate)
        if order_id and order_id not in order_ids:
            order_ids.append(order_id)
    return order_ids
