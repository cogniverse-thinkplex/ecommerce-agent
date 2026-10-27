from __future__ import annotations

from pydantic import BaseModel

from app.agent.state import ConversationMessage, CustomerAgentState
from app.policy.guard import confirm_pending_action, reject_pending_action


class ConfirmationReply(BaseModel):
    confirmed: bool
    user_text: str


class ConfirmationNodeResult(BaseModel):
    state: CustomerAgentState
    confirmed: bool
    error: str | None = None


def apply_confirmation_reply(
    state: CustomerAgentState,
    reply: ConfirmationReply,
) -> ConfirmationNodeResult:
    state_with_message = state.model_copy(
        update={
            "messages": [
                *state.messages,
                ConversationMessage(role="user", content=reply.user_text),
            ]
        }
    )

    if state.confirmation.pending is None:
        return ConfirmationNodeResult(
            state=state_with_message,
            confirmed=False,
            error="No pending action to confirm",
        )

    if reply.confirmed:
        return ConfirmationNodeResult(
            state=confirm_pending_action(state_with_message),
            confirmed=True,
        )

    return ConfirmationNodeResult(
        state=reject_pending_action(state_with_message),
        confirmed=False,
    )
