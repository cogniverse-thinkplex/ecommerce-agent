from __future__ import annotations

import json
from pydantic import BaseModel

from app.agent.state import CustomerAgentState, append_event
from app.policy.guard import GuardDecisionType, check_tool_call
from app.tools.retail_port import (
    RetailToolDefinition,
    RetailToolPort,
    RetailToolResult,
    ToolBackendInfo,
)


class GuardedToolCallResult(BaseModel):
    state: CustomerAgentState
    executed: bool
    confirmation_required: bool = False
    tool_result: RetailToolResult | None = None
    error: str | None = None


class GuardedRetailToolExecutor:
    def __init__(self, port: RetailToolPort) -> None:
        self._port = port

    @property
    def backend(self) -> ToolBackendInfo:
        return self._port.backend

    @property
    def policy(self) -> str:
        return self._port.policy

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._port.list_tools()

    def db_hash(self) -> str | None:
        getter = getattr(self._port, "db_hash", None)
        return getter() if callable(getter) else None

    def call(
        self,
        state: CustomerAgentState,
        name: str,
        arguments: dict,
        call_id: str | None = None,
    ) -> GuardedToolCallResult:
        tool = self._find_tool(name)
        if tool is None:
            return GuardedToolCallResult(
                state=append_event(
                    state,
                    "tool_executor.unknown_tool",
                    {"tool": name},
                ),
                executed=False,
                error=f"Unknown tool: {name}",
            )

        identity_error = _identity_error_before_call(state, name, arguments)
        if identity_error is not None:
            return _identity_denied(state, name, identity_error)

        decision = check_tool_call(state, tool, arguments)
        if decision.decision == GuardDecisionType.REQUIRE_CONFIRMATION:
            return GuardedToolCallResult(
                state=decision.state,
                executed=False,
                confirmation_required=True,
            )

        state_before_hash = self.db_hash() if tool.tool_type == "write" else None
        tool_result = self._port.call_tool(name, arguments, call_id=call_id)
        identity_error = _identity_error_after_call(state, name, tool_result)
        if identity_error is not None:
            return _identity_denied(decision.state, name, identity_error)
        state_after_hash = self.db_hash() if tool.tool_type == "write" else None
        state_verification_available = (
            state_before_hash is not None and state_after_hash is not None
        )
        return GuardedToolCallResult(
            state=append_event(
                decision.state,
                "tool_executor.executed",
                {
                    "tool": name,
                    "tool_type": tool.tool_type,
                    "error": tool_result.error,
                    "fingerprint": decision.fingerprint,
                    "state_verification_available": state_verification_available,
                    "state_changed": (
                        state_before_hash != state_after_hash
                        if state_verification_available
                        else None
                    ),
                },
            ),
            executed=True,
            tool_result=tool_result,
        )

    def _find_tool(self, name: str) -> RetailToolDefinition | None:
        for tool in self._port.list_tools():
            if tool.name == name:
                return tool
        return None


def _linked_user_id(state: CustomerAgentState) -> str | None:
    for event in reversed(state.events):
        if event.event_type == "identity.platform_account_linked":
            value = event.payload.get("user_id")
            return str(value) if value is not None else None
    return None


def _identity_error_before_call(
    state: CustomerAgentState,
    name: str,
    arguments: dict,
) -> str | None:
    linked_user_id = _linked_user_id(state)
    if linked_user_id is None:
        return None
    if name in {"find_user_id_by_email", "find_user_id_by_name_zip"}:
        return "linked_identity_cannot_be_replaced"
    if name in {"get_user_details", "modify_user_address"}:
        if str(arguments.get("user_id") or "") != linked_user_id:
            return "user_id_mismatch"
    order_id = arguments.get("order_id")
    if order_id is not None and name != "get_order_details":
        owner = _known_order_owner(state, str(order_id))
        if owner != linked_user_id:
            return "order_owner_mismatch"
    return None


def _identity_error_after_call(
    state: CustomerAgentState,
    name: str,
    result: RetailToolResult,
) -> str | None:
    linked_user_id = _linked_user_id(state)
    if linked_user_id is None or name != "get_order_details" or result.error:
        return None
    if not isinstance(result.content, dict):
        return "order_owner_unavailable"
    owner = result.content.get("user_id")
    if owner is None or str(owner) != linked_user_id:
        return "order_owner_mismatch"
    return None


def _known_order_owner(state: CustomerAgentState, order_id: str) -> str | None:
    for message in reversed(state.messages):
        if message.role != "tool" or message.tool_name != "get_order_details":
            continue
        try:
            payload = json.loads(message.content or "")
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or str(payload.get("order_id")) != order_id:
            continue
        owner = payload.get("user_id")
        return str(owner) if owner is not None else None
    return None


def _identity_denied(
    state: CustomerAgentState,
    tool_name: str,
    reason: str,
) -> GuardedToolCallResult:
    return GuardedToolCallResult(
        state=append_event(
            state,
            "policy_guard.identity_denied",
            {"tool": tool_name, "reason": reason},
        ),
        executed=False,
        error="Retail identity access denied",
    )
