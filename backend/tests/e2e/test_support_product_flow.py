from pathlib import Path

from app.agent.proposal_generator import RuleBasedProposalGenerator
from app.agent.session_service import AgentSessionService
from app.agent.session_store import PersistentSessionStore
from app.persistence.sqlite import SqliteUnitOfWork
from app.support.service import SupportService
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.tau_retail_adapter import TauRetailAdapter


def _service(path: Path) -> SupportService:
    unit = SqliteUnitOfWork(path)
    unit.initialize()
    agent = AgentSessionService(
        GuardedRetailToolExecutor(TauRetailAdapter.from_default_data()),
        proposal_generator=RuleBasedProposalGenerator(),
        session_store=PersistentSessionStore(unit),
    )
    return SupportService(agent, unit)


def test_real_retail_authentication_and_order_query_are_projected_and_persisted(
    tmp_path: Path,
):
    database = tmp_path / "product.db"
    first = _service(database)
    conversation = first.create_conversation()

    auth = first.submit_message(
        conversation.conversation_id,
        content="Please find user Yusuf Rossi zip 19122",
        request_id="auth-1",
    )
    order = first.submit_message(
        conversation.conversation_id,
        content="Please check order #W2378156",
        request_id="order-1",
    )

    assert any(block.text == "身份验证成功。" for block in auth.blocks)
    assert first.get_conversation(conversation.conversation_id).authenticated is True
    assert any(block.type == "order_summary" for block in order.blocks)

    restarted = _service(database)
    restored = restarted.get_conversation(conversation.conversation_id)
    history = restarted.list_messages(conversation.conversation_id)
    assert restored.authenticated is True
    assert any(message.kind == "order_summary" for message in history)


def test_real_retail_cancellation_closes_confirmation_execution_and_persistence_loop(
    tmp_path: Path,
):
    database = tmp_path / "cancel-product.db"
    service = _service(database)
    conversation = service.create_conversation()
    service.submit_message(
        conversation.conversation_id,
        content="Please find user Yusuf Rossi zip 19122",
        request_id="auth-cancel",
    )

    proposed = service.submit_message(
        conversation.conversation_id,
        content="Please cancel order #W6247578 because it was ordered by mistake",
        request_id="cancel-proposal",
    )

    assert proposed.pending_action_id is not None
    assert proposed.blocks[-1].type == "confirmation"
    assert proposed.blocks[-1].data["order_id"] == "#W6247578"

    confirmed = service.confirm_action(
        conversation.conversation_id,
        proposed.pending_action_id,
        request_id="cancel-confirm",
    )

    assert confirmed.pending_action_id is None
    assert confirmed.blocks[0].title == "订单已取消"
    assert confirmed.blocks[0].data["order_id"] == "#W6247578"
    assert confirmed.blocks[0].data["order_status"] == "cancelled"
    assert confirmed.blocks[0].data["verification"] == "tool_result"

    restarted = _service(database)
    history = restarted.list_messages(conversation.conversation_id)
    persisted = next(message for message in history if message.kind == "operation_result")
    assert persisted.payload["data"]["status"] == "succeeded"
    assert persisted.payload["data"]["order_status"] == "cancelled"

