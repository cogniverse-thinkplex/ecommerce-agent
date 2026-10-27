from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.agent.state import (
    ConfirmationState,
    CustomerAgentState,
    PendingAction,
    append_event,
)
from app.tools.retail_port import RetailToolDefinition


class GuardDecisionType(StrEnum):
    ALLOW = "allow"
    REQUIRE_CONFIRMATION = "require_confirmation"


class GuardDecision(BaseModel):
    decision: GuardDecisionType
    state: CustomerAgentState
    reason: str
    fingerprint: str | None = None


def fingerprint_action(name: str, arguments: dict[str, Any]) -> str:
    payload = {
        "name": name,
        "arguments": arguments,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{name}:{digest[:16]}"


def check_tool_call(
    state: CustomerAgentState,
    tool: RetailToolDefinition,
    arguments: dict[str, Any],
) -> GuardDecision:
    if tool.tool_type != "write":
        return GuardDecision(
            decision=GuardDecisionType.ALLOW,
            state=append_event(
                state,
                "policy_guard.allowed",
                {"tool": tool.name, "tool_type": tool.tool_type},
            ),
            reason="read_or_non_mutating_tool",
        )

    fingerprint = fingerprint_action(tool.name, arguments)
    if fingerprint in state.confirmation.confirmed_fingerprints:
        return GuardDecision(
            decision=GuardDecisionType.ALLOW,
            state=append_event(
                state,
                "policy_guard.allowed",
                {
                    "tool": tool.name,
                    "tool_type": tool.tool_type,
                    "fingerprint": fingerprint,
                },
            ),
            reason="confirmed_write_action",
            fingerprint=fingerprint,
        )

    pending = PendingAction(
        name=tool.name,
        arguments=arguments,
        fingerprint=fingerprint,
    )
    next_state = state.model_copy(
        update={
            "confirmation": state.confirmation.model_copy(update={"pending": pending})
        }
    )
    next_state = append_event(
        next_state,
        "policy_guard.requires_confirmation",
        {
            "tool": tool.name,
            "tool_type": tool.tool_type,
            "fingerprint": fingerprint,
            "arguments": arguments,
        },
    )
    return GuardDecision(
        decision=GuardDecisionType.REQUIRE_CONFIRMATION,
        state=next_state,
        reason="write_tool_requires_explicit_confirmation",
        fingerprint=fingerprint,
    )


def confirm_pending_action(state: CustomerAgentState) -> CustomerAgentState:
    pending = state.confirmation.pending
    if pending is None:
        return state

    fingerprints = [
        *state.confirmation.confirmed_fingerprints,
        pending.fingerprint,
    ]
    confirmation = ConfirmationState(
        pending=None,
        confirmed_fingerprints=fingerprints,
    )
    next_state = state.model_copy(update={"confirmation": confirmation})
    return append_event(
        next_state,
        "policy_guard.confirmed",
        {
            "tool": pending.name,
            "fingerprint": pending.fingerprint,
            "arguments": pending.arguments,
        },
    )


def reject_pending_action(state: CustomerAgentState) -> CustomerAgentState:
    pending = state.confirmation.pending
    if pending is None:
        return state

    next_state = state.model_copy(
        update={
            "confirmation": state.confirmation.model_copy(update={"pending": None})
        }
    )
    return append_event(
        next_state,
        "policy_guard.rejected",
        {
            "tool": pending.name,
            "fingerprint": pending.fingerprint,
            "arguments": pending.arguments,
        },
    )
