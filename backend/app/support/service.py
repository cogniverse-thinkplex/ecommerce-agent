from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from threading import RLock
from uuid import uuid4

from app.agent.session_service import AgentSessionService
from app.agent.progress import ProgressSink
from app.persistence.models import (
    AuditEventRecord,
    ConversationRecord,
    ConversationGroupRecord,
    MessageRecord,
    PendingActionRecord,
)
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.models import (
    SupportConversation,
    SupportConversationGroup,
    SupportMessageBlock,
    SupportTurnResult,
)
from app.support.projector import project_state
from app.support.handoff import HandoffActiveError, HumanHandoffService


class SupportService:
    def __init__(
        self,
        agent_service: AgentSessionService,
        unit_of_work: SqliteUnitOfWork,
        handoff_service: HumanHandoffService | None = None,
    ) -> None:
        self._agent = agent_service
        self._unit = unit_of_work
        self._handoffs = handoff_service
        self._conversation_locks: defaultdict[str, RLock] = defaultdict(RLock)

    def create_conversation(
        self,
        owner_user_id: str | None = None,
        retail_user_id: str | None = None,
    ) -> SupportConversation:
        conversation_id = str(uuid4())
        state = self._agent.start_session(
            conversation_id, authenticated_user_id=retail_user_id
        )
        record = ConversationRecord(
            conversation_id=conversation_id,
            state=state,
            owner_user_id=owner_user_id,
            authenticated_user_id=retail_user_id,
            authentication_method="email" if retail_user_id else None,
        )
        greeting = MessageRecord(
            message_id=str(uuid4()),
            conversation_id=conversation_id,
            sequence=1,
            role="assistant",
            kind="text",
            text=(
                "您好，我是在线客服。您的购买账户已关联，可以直接查询订单或办理售后。"
                if retail_user_id
                else "您好，我是在线客服。请提供邮箱，或姓名和邮编以验证身份。"
            ),
        )
        with self._unit.transaction():
            self._unit.conversations.archive_empty_for_owner(owner_user_id)
            self._unit.conversations.save(record)
            self._unit.messages.append(greeting)
        return self.get_conversation(conversation_id, owner_user_id=owner_user_id)

    def list_conversations(self, owner_user_id: str | None = None, active_conversation_id: str | None = None) -> list[SupportConversation]:
        if active_conversation_id is not None:
            active = self._unit.conversations.get_for_owner(active_conversation_id, owner_user_id) if owner_user_id is not None else self._unit.conversations.get(active_conversation_id)
            if active is None:
                active_conversation_id = None
        with self._unit.transaction():
            self._unit.conversations.archive_empty_for_owner(owner_user_id, exclude_conversation_id=active_conversation_id)
        records = (
            self._unit.conversations.list_active_for_owner(owner_user_id)
            if owner_user_id is not None
            else self._unit.conversations.list_active()
        )
        return [self._summary(item) for item in records]

    def get_conversation(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> SupportConversation:
        record = self._require_conversation(conversation_id, owner_user_id)
        return self._summary(record)

    def set_order_context(self, conversation_id: str, owner_user_id: str, order_id: str) -> None:
        self._require_conversation(conversation_id, owner_user_id)
        self._agent.set_active_order_context(conversation_id, order_id)

    def set_policy_context(self, conversation_id: str, owner_user_id: str, policy_id: str) -> None:
        self._require_conversation(conversation_id, owner_user_id)
        self._agent.set_active_policy_context(conversation_id, policy_id)

    def list_messages(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> list[MessageRecord]:
        self._require_conversation(conversation_id, owner_user_id)
        return self._unit.messages.list_for_conversation(conversation_id)

    def archive_conversation(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> None:
        self._require_conversation(conversation_id, owner_user_id)
        with self._unit.transaction():
            if owner_user_id is None:
                self._unit.conversations.archive(conversation_id)
            else:
                self._unit.conversations.archive_for_owner(conversation_id, owner_user_id)

    def update_conversation(
        self, conversation_id: str, owner_user_id: str | None, *,
        title: str | None = None, is_pinned: bool | None = None,
        group_id: str | None = None, update_group: bool = False,
    ) -> SupportConversation:
        self._require_conversation(conversation_id, owner_user_id)
        if update_group and group_id is not None:
            group_owner = owner_user_id or "local-anonymous"
            if self._unit.conversation_groups.get_for_owner(group_id, group_owner) is None:
                raise KeyError(f"Unknown group_id: {group_id}")
        with self._unit.transaction():
            if owner_user_id is None:
                record = self._unit.conversations.get(conversation_id)
                if record is None:
                    raise KeyError(conversation_id)
                self._unit.conversations.save(record.model_copy(update={
                    **({"title": title, "title_source": "custom"} if title is not None else {}),
                    **({"is_pinned": is_pinned} if is_pinned is not None else {}),
                    **({"group_id": group_id} if update_group else {}),
                }))
            elif not self._unit.conversations.update_management(
                conversation_id, owner_user_id, title=title, is_pinned=is_pinned,
                group_id=group_id, update_group=update_group,
            ):
                raise KeyError(conversation_id)
        return self.get_conversation(conversation_id, owner_user_id)

    def list_groups(self, owner_user_id: str) -> list[SupportConversationGroup]:
        return [SupportConversationGroup.model_validate(item.model_dump()) for item in self._unit.conversation_groups.list_for_owner(owner_user_id)]

    def create_group(self, owner_user_id: str, name: str) -> SupportConversationGroup:
        record = ConversationGroupRecord(group_id=str(uuid4()), owner_user_id=owner_user_id, name=name.strip())
        with self._unit.transaction():
            self._unit.conversation_groups.create(record)
        return SupportConversationGroup.model_validate(record.model_dump())

    def rename_group(self, group_id: str, owner_user_id: str, name: str) -> SupportConversationGroup:
        with self._unit.transaction():
            if not self._unit.conversation_groups.rename_for_owner(group_id, owner_user_id, name.strip()):
                raise KeyError(group_id)
        record = self._unit.conversation_groups.get_for_owner(group_id, owner_user_id)
        if record is None:
            raise KeyError(group_id)
        return SupportConversationGroup.model_validate(record.model_dump())

    def delete_group(self, group_id: str, owner_user_id: str) -> None:
        with self._unit.transaction():
            if not self._unit.conversation_groups.delete_for_owner(group_id, owner_user_id):
                raise KeyError(group_id)

    def submit_message(
        self, conversation_id: str, *, content: str, request_id: str,
        owner_user_id: str | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> SupportTurnResult:
        with self._conversation_locks[conversation_id]:
            return self._submit_message_locked(
                conversation_id,
                content=content,
                request_id=request_id,
                owner_user_id=owner_user_id,
                progress_sink=progress_sink,
            )

    def _submit_message_locked(
        self, conversation_id: str, *, content: str, request_id: str,
        owner_user_id: str | None = None,
        progress_sink: ProgressSink | None = None,
    ) -> SupportTurnResult:
        self._require_conversation(conversation_id, owner_user_id)
        duplicate = self._unit.messages.find_by_request_id(conversation_id, request_id)
        if duplicate is not None:
            return self._result_after_sequence(conversation_id, duplicate.sequence)

        before = self._agent.get_session(conversation_id)
        runtime_result = (
            self._agent.auto_run(
                conversation_id,
                content,
                max_steps=6,
                progress_sink=progress_sink,
            )
            if progress_sink is not None
            else self._agent.auto_run(conversation_id, content, max_steps=6)
        )
        state = runtime_result.state
        blocks = project_state(state, message_start=len(before.messages))
        pending = state.confirmation.pending
        action_id = str(uuid4()) if pending is not None else None
        if action_id is not None:
            blocks = [
                block.model_copy(update={"data": {**block.data, "action_id": action_id}})
                if block.type == "confirmation"
                else block
                for block in blocks
            ]

        with self._unit.transaction():
            sequence = self._unit.messages.next_sequence(conversation_id)
            user_message = MessageRecord(
                message_id=str(uuid4()),
                conversation_id=conversation_id,
                sequence=sequence,
                role="user",
                kind="text",
                text=content,
                request_id=request_id,
            )
            self._unit.messages.append(user_message)
            for block in blocks:
                sequence += 1
                self._unit.messages.append(
                    MessageRecord(
                        message_id=str(uuid4()),
                        conversation_id=conversation_id,
                        sequence=sequence,
                        role="action" if block.type == "confirmation" else "assistant",
                        kind=block.type,
                        text=block.text,
                        payload=block.model_dump(mode="json"),
                    )
                )
            record = self._require_conversation(conversation_id)
            first_question = self._unit.messages.first_user_message(conversation_id)
            authenticated_user_id, authentication_method = _authentication_from_state(
                state
            )
            self._unit.conversations.save(
                record.model_copy(
                    update={
                        "title": (
                            summarize_question(first_question.text or content)
                            if record.title_source == "auto"
                            else record.title
                        ),
                        "updated_at": user_message.created_at,
                        "state": state,
                        "authenticated_user_id": (
                            authenticated_user_id or record.authenticated_user_id
                        ),
                        "authentication_method": (
                            authentication_method or record.authentication_method
                        ),
                    }
                )
            )

            if pending is not None:
                self._unit.pending_actions.create(
                    PendingActionRecord(
                        action_id=action_id,
                        conversation_id=conversation_id,
                        tool_name=pending.name,
                        arguments=pending.arguments,
                        fingerprint=pending.fingerprint,
                        idempotency_key=_idempotency_key(conversation_id, pending.fingerprint),
                        confirmation_summary=next(
                            (block.title for block in blocks if block.type == "confirmation"),
                            "确认执行操作",
                        ),
                    )
                )
        handoff = None
        if (
            owner_user_id is not None
            and self._handoffs is not None
            and any(
                message.role == "tool"
                and message.tool_name == "transfer_to_human_agents"
                for message in state.messages[len(before.messages):]
            )
        ):
            handoff = self._handoffs.create_or_get_active(
                conversation_id,
                owner_user_id,
                reason="agent_requested",
                customer_message="智能客服已申请人工协助。",
                context_summary="Agent 判断当前请求需要人工处理。",
            )
        return SupportTurnResult(
            conversation_id=conversation_id,
            blocks=blocks,
            pending_action_id=action_id,
            handoff_ticket_id=handoff.ticket_id if handoff else None,
            handoff_status=handoff.status if handoff else None,
        )

    def confirm_action(
        self, conversation_id: str, action_id: str, *, request_id: str,
        owner_user_id: str | None = None,
    ) -> SupportTurnResult:
        self._require_conversation(conversation_id, owner_user_id)
        if self._unit.human_handoffs.get_active_for_conversation(
            conversation_id
        ) is not None:
            raise HandoffActiveError("人工服务处理中，暂时不能执行账户变更操作。")
        action = self._require_action(conversation_id, action_id)
        with self._unit.transaction():
            claimed = self._unit.pending_actions.claim_if_no_active_handoff(
                action_id, conversation_id
            )
        if not claimed:
            if self._unit.human_handoffs.get_active_for_conversation(
                conversation_id
            ) is not None:
                raise HandoffActiveError("人工服务处理中，暂时不能执行账户变更操作。")
            return self._resolved_result(conversation_id, action_id)

        before = self._agent.get_session(conversation_id)
        result = self._agent.confirm_pending_and_continue(
            conversation_id,
            confirmed=True,
            user_text="yes",
            objective=self._agent.get_session(
                conversation_id
            ).objective_ledger.original_objective
            or action.confirmation_summary,
            max_steps=6,
        )
        succeeded = bool(
            result.confirmation.confirmed
            and result.executed is not None
            and result.executed.executed
            and not result.executed.error
        )
        status = "succeeded" if succeeded else "failed"
        block = _operation_result_block(action, result.state, succeeded=succeeded)
        self._finish_action(action_id, conversation_id, block, status)

        blocks = [block]
        next_action_id = None
        if succeeded:
            continuation = project_state(
                result.state,
                message_start=len(before.messages),
                include_pending=True,
            )
            pending = result.state.confirmation.pending
            if pending is not None:
                next_action_id = str(uuid4())
                continuation = [
                    item.model_copy(
                        update={"data": {**item.data, "action_id": next_action_id}}
                    )
                    if item.type == "confirmation"
                    else item
                    for item in continuation
                ]
                summary = next(
                    (item.title for item in continuation if item.type == "confirmation"),
                    "确认执行操作",
                )
                with self._unit.transaction():
                    self._unit.pending_actions.create(
                        PendingActionRecord(
                            action_id=next_action_id,
                            conversation_id=conversation_id,
                            tool_name=pending.name,
                            arguments=pending.arguments,
                            fingerprint=pending.fingerprint,
                            idempotency_key=_idempotency_key(
                                conversation_id, pending.fingerprint
                            ),
                            confirmation_summary=summary,
                        )
                    )
            for continuation_block in continuation:
                self._append_block(conversation_id, continuation_block)
            blocks.extend(continuation)
        return SupportTurnResult(
            conversation_id=conversation_id,
            blocks=blocks,
            pending_action_id=next_action_id,
        )

    def reject_action(
        self, conversation_id: str, action_id: str, *, request_id: str,
        owner_user_id: str | None = None,
    ) -> SupportTurnResult:
        self._require_conversation(conversation_id, owner_user_id)
        self._require_action(conversation_id, action_id)
        with self._unit.transaction():
            changed = self._unit.pending_actions.transition(
                action_id, expected="pending", target="rejected"
            )
        if not changed:
            return self._resolved_result(conversation_id, action_id)
        block = SupportMessageBlock(
            type="operation_result",
            title="已取消操作",
            text="本次操作未执行。",
            data={"status": "rejected"},
        )
        self._append_block(conversation_id, block, request_id=request_id)
        return SupportTurnResult(conversation_id=conversation_id, blocks=[block])

    def _finish_action(
        self, action_id: str, conversation_id: str, block: SupportMessageBlock, status: str
    ) -> None:
        with self._unit.transaction():
            self._unit.pending_actions.set_outcome(
                action_id, status=status, result=block.data
            )
            self._unit.audit_events.append(
                AuditEventRecord(
                    event_id=str(uuid4()),
                    conversation_id=conversation_id,
                    action_id=action_id,
                    event_type=f"operation.{status}",
                    payload=block.data,
                )
            )
        self._append_block(conversation_id, block)

    def _append_block(
        self,
        conversation_id: str,
        block: SupportMessageBlock,
        request_id: str | None = None,
    ) -> None:
        with self._unit.transaction():
            message = MessageRecord(
                    message_id=str(uuid4()),
                    conversation_id=conversation_id,
                    sequence=self._unit.messages.next_sequence(conversation_id),
                    role="assistant",
                    kind=block.type,
                    text=block.text,
                    payload=block.model_dump(mode="json"),
                    request_id=request_id,
                )
            self._unit.messages.append(message)
            conversation = self._require_conversation(conversation_id)
            self._unit.conversations.save(
                conversation.model_copy(update={"updated_at": message.created_at})
            )

    def _resolved_result(
        self, conversation_id: str, action_id: str
    ) -> SupportTurnResult:
        action = self._require_action(conversation_id, action_id)
        block = SupportMessageBlock(
            type="operation_result",
            title="操作已处理",
            text="该操作已经处理，无需重复提交。",
            data={"status": action.status, "already_resolved": True},
        )
        return SupportTurnResult(conversation_id=conversation_id, blocks=[block])

    def _result_after_sequence(
        self, conversation_id: str, sequence: int
    ) -> SupportTurnResult:
        messages = self._unit.messages.list_for_conversation(conversation_id)
        blocks = [
            SupportMessageBlock.model_validate(message.payload)
            for message in messages
            if message.sequence > sequence and message.payload.get("type")
        ]
        pending = self._unit.pending_actions.list_for_conversation(conversation_id)
        action_id = next(
            (item.action_id for item in reversed(pending) if item.status == "pending"), None
        )
        return SupportTurnResult(
            conversation_id=conversation_id,
            blocks=blocks,
            pending_action_id=action_id,
        )

    def _summary(self, record: ConversationRecord) -> SupportConversation:
        first_question = self._unit.messages.first_user_message(record.conversation_id)
        last_question = self._unit.messages.last_user_message(record.conversation_id)
        return SupportConversation(
            conversation_id=record.conversation_id,
            title=(
                summarize_question(first_question.text or "")
                if record.title_source == "auto" and first_question is not None
                else record.title
            ),
            status=record.status,
            authenticated=record.authenticated_user_id is not None,
            group_id=record.group_id,
            is_pinned=record.is_pinned,
            title_source=record.title_source,
            message_count=self._unit.messages.count_user_messages(
                record.conversation_id
            ),
            last_question_at=(
                last_question.created_at if last_question is not None else None
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _require_conversation(
        self, conversation_id: str, owner_user_id: str | None = None
    ) -> ConversationRecord:
        record = (
            self._unit.conversations.get_for_owner(conversation_id, owner_user_id)
            if owner_user_id is not None
            else self._unit.conversations.get(conversation_id)
        )
        if record is None or record.status != "active":
            raise KeyError(f"Unknown conversation_id: {conversation_id}")
        return record

    def _require_action(
        self, conversation_id: str, action_id: str
    ) -> PendingActionRecord:
        action = self._unit.pending_actions.get(action_id)
        if action is None or action.conversation_id != conversation_id:
            raise KeyError(f"Unknown action_id: {action_id}")
        return action


def _idempotency_key(conversation_id: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{conversation_id}:{fingerprint}".encode()).hexdigest()


def _operation_result_block(
    action: PendingActionRecord,
    state: CustomerAgentState,
    *,
    succeeded: bool,
) -> SupportMessageBlock:
    labels = {
        "cancel_pending_order": ("取消订单", "订单已取消"),
        "return_delivered_order_items": ("申请退货", "退货申请已提交"),
        "exchange_delivered_order_items": ("申请换货", "换货申请已提交"),
        "modify_pending_order_address": ("修改配送地址", "配送地址已修改"),
        "modify_pending_order_items": ("修改订单商品", "订单商品已修改"),
        "modify_pending_order_payment": ("修改支付方式", "支付方式已修改"),
        "modify_user_address": ("修改默认地址", "默认地址已修改"),
    }
    action_label, success_title = labels.get(
        action.tool_name, ("执行操作", "操作已完成")
    )
    order_id = action.arguments.get("order_id")
    tool_payload = _latest_tool_payload(state, action.tool_name)
    data = {
        "status": "succeeded" if succeeded else "failed",
        "action": action_label,
        **({"order_id": order_id} if order_id else {}),
    }
    if succeeded:
        if tool_payload.get("status") is not None:
            data["order_status"] = tool_payload["status"]
        data["verification"] = "tool_result"
        text = (
            f"{action_label}已成功执行。"
            if order_id is None
            else f"订单 {order_id} 的{action_label}已成功执行。"
        )
        return SupportMessageBlock(
            type="operation_result",
            title=success_title,
            text=text,
            data=data,
        )
    return SupportMessageBlock(
        type="operation_result",
        title="操作未完成",
        text="本次操作未能完成，请稍后重试；如果问题持续，可以转接人工客服。",
        data=data,
    )


def _latest_tool_payload(state: CustomerAgentState, tool_name: str) -> dict:
    import json

    for message in reversed(state.messages):
        if message.role != "tool" or message.tool_name != tool_name or not message.content:
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def summarize_question(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).strip()
    if len(normalized) <= 32:
        return normalized or "新会话"
    return f"{normalized[:31]}…"


def _authentication_from_state(state):
    for message in reversed(state.messages):
        if message.role != "tool" or not message.content:
            continue
        if message.tool_name == "find_user_id_by_name_zip":
            return message.content.strip('"'), "name_zip"
        if message.tool_name == "find_user_id_by_email":
            return message.content.strip('"'), "email"
    return None, None

