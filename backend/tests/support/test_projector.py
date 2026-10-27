from app.agent.state import AgentEvent, ConversationMessage, CustomerAgentState, PendingAction
from app.support.projector import project_state


def test_projector_emits_order_card_without_internal_tool_metadata():
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                tool_call_id="secret-call",
                content=(
                    '{"order_id":"#W2378156","status":"pending",'
                    '"items":[{"name":"Keyboard","quantity":1}]}'
                ),
            )
        ],
    )

    blocks = project_state(state)
    serialized = "".join(block.model_dump_json() for block in blocks)

    assert blocks[0].type == "order_summary"
    assert blocks[0].data["order_id"] == "#W2378156"
    assert "get_order_details" not in serialized
    assert "secret-call" not in serialized


def test_projector_emits_confirmation_with_localized_material_details():
    state = CustomerAgentState(conversation_id="conv-1")
    state.confirmation.pending = PendingAction(
        name="cancel_pending_order",
        arguments={"order_id": "#W2378156", "reason": "ordered by mistake"},
        fingerprint="private-fingerprint",
    )

    block = project_state(state)[0]

    assert block.type == "confirmation"
    assert block.title == "确认取消订单"
    assert "仅授权本次操作一次" in block.text
    assert block.data == {
        "order_id": "#W2378156",
        "reason": "ordered by mistake",
    }
    assert "private-fingerprint" not in block.model_dump_json()


def test_projector_never_returns_policy_trace_cost_or_raw_unknown_tool_payload():
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="unknown_internal_tool",
                content='{"policy":"secret","cost":9,"trace":"raw"}',
            )
        ],
    )

    assert project_state(state) == []


def test_projector_emits_customer_safe_policy_citations():
    state = CustomerAgentState(
        conversation_id="conv-1",
        events=[AgentEvent(event_type="rag.completed", payload={"hits": [{
            "policy_id": "seven-day-return", "title": "七天无理由退货",
            "content": "符合条件的商品可在签收后七日内申请退货。",
            "scope": "普通实物商品，特殊品类除外",
            "source_url": "https://terms.alicdn.com/example", "verified_at": "2026-10-24",
            "dense_rank": 1, "bm25_rank": 2, "rrf_score": 0.03,
        }]})],
    )
    blocks = project_state(state)
    assert blocks[-1].type == "policy_citations"
    serialized = blocks[-1].model_dump_json()
    assert "七天无理由退货" in serialized and "rrf_score" not in serialized

