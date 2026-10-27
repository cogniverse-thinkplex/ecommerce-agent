import json
from typing import Any

import pytest

from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.proposal_generator import LLMProposalGenerator
from app.agent.runtime import AgentTurnResult, BaselineAgentRuntime, LLMPlannerRuntime
from app.agent.skills import SkillDefinition, default_skill_registry
from app.agent.state import (
    AgentEvent,
    ConversationMessage,
    CustomerAgentState,
    initialize_objective_ledger,
    record_tool_execution,
)
from app.tools.guarded_executor import GuardedRetailToolExecutor
from app.tools.retail_port import RetailToolDefinition, RetailToolResult


def test_baseline_runtime_appends_user_message_and_executes_generated_proposal():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="find_user_id_by_name_zip",
                        tool_type="read",
                        description="",
                        parameters_schema={},
                    )
                ]
            )
        ),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                tool_name="find_user_id_by_name_zip",
                arguments={"first_name": "Yusuf", "last_name": "Rossi", "zip": "19122"},
                rationale="Look up the user before account-specific work.",
            )
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please find user Yusuf Rossi zip 19122",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "find_user_id_by_name_zip"
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert [message.role for message in result.state.messages] == [
        "user",
        "tool",
        "assistant",
    ]
    assert result.state.messages[0].content == "Please find user Yusuf Rossi zip 19122"
    assert result.state.messages[-1].content == "身份信息已确认。您可以继续查询订单或办理售后。"


def test_baseline_runtime_run_until_blocked_stops_at_pending_confirmation():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="cancel_pending_order",
                        tool_type="write",
                        description="",
                        parameters_schema={},
                    )
                ]
            )
        ),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
                rationale="Cancel pending order after user confirmation.",
            )
        ),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="conv-1"),
        "Please cancel order #W0000000",
        max_steps=3,
    )

    assert result.stopped_reason == "pending_confirmation"
    assert len(result.turns) == 1
    assert result.state.confirmation.pending is not None
    assert result.state.confirmation.pending.name == "cancel_pending_order"
    assert result.state.objective_ledger.original_objective == (
        "Please cancel order #W0000000"
    )


def test_baseline_runtime_run_until_blocked_replies_when_no_tool_is_selected():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=FixedProposalGenerator(None),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="conv-1"),
        "这个订单现在怎么样？",
        max_steps=3,
    )

    assert result.stopped_reason == "no_proposal"
    assert result.state.messages[-1].role == "assistant"
    assert "订单号" in result.state.messages[-1].content


def test_baseline_runtime_stops_after_cross_account_denial():
    port = CrossAccountOrderPort()
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(port),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                tool_name="get_order_details",
                arguments={"order_id": "#W6893533"},
                rationale="Fetch the requested order.",
            )
        ),
    )
    state = CustomerAgentState(
        conversation_id="conv-linked",
        events=[
            AgentEvent(
                event_type="identity.platform_account_linked",
                payload={"user_id": "noah_brown_6181"},
            )
        ],
    )

    result = runtime.run_until_blocked(
        state,
        "请查询订单 #W6893533",
        max_steps=6,
    )

    assert result.stopped_reason == "no_proposal"
    assert len(port.calls) == 1
    assert result.state.messages[-1].content == "无法访问不属于当前账户的数据。"


def test_baseline_runtime_runs_fake_llm_proposal_through_guarded_confirmation():
    tools = [
        RetailToolDefinition(
            name="cancel_pending_order",
            tool_type="write",
            description="Cancel a pending order.",
            parameters_schema={
                "type": "object",
                "required": ["order_id", "reason"],
                "properties": {
                    "order_id": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        )
    ]
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                (
                    '{"tool_name":"cancel_pending_order",'
                    '"arguments":{"order_id":"#W0000000","reason":"ordered by mistake"},'
                    '"rationale":"Cancel after explicit user request."}'
                )
            ),
            tool_catalog=tools,
            policy="Write actions require confirmation.",
        ),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="conv-1"),
        "Cancel order #W0000000 because I ordered by mistake.",
        max_steps=3,
    )

    assert result.stopped_reason == "pending_confirmation"
    assert len(result.turns) == 1
    assert result.turns[0].proposal is not None
    assert result.turns[0].proposal.tool_name == "cancel_pending_order"
    assert result.state.confirmation.pending is not None
    assert result.state.confirmation.pending.arguments == {
        "order_id": "#W0000000",
        "reason": "ordered by mistake",
    }
    assert [event.event_type for event in result.state.events] == [
        "tool_proposal.accepted",
        "policy_guard.requires_confirmation",
    ]


def test_baseline_runtime_appends_final_response_planner_decision():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"final_response","message":"Your order is already delivered.","rationale":"Enough context."}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "What is the status?",
    )

    assert result.proposal is None
    assert result.proposal_result is None
    assert [message.role for message in result.state.messages] == ["user", "assistant"]
    assert result.state.messages[-1].content == "Your order is already delivered."
    assert result.state.events[-1].event_type == "planner.final_response"
    assert result.state.events[-1].payload == {"rationale": "Enough context."}


def test_baseline_runtime_appends_need_more_info_planner_decision():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"need_more_info","message":"Please provide your order id.","rationale":"Need order id."}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Can you check it?",
    )

    assert result.proposal is None
    assert result.proposal_result is None
    assert result.state.messages[-1].role == "assistant"
    assert result.state.messages[-1].content == "Please provide your order id."
    assert result.state.events[-1].event_type == "planner.need_more_info"
    assert result.state.events[-1].payload == {"rationale": "Need order id."}


def test_baseline_runtime_records_invalid_planner_output():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient("not json"),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156",
    )

    assert result.proposal is None
    assert result.proposal_result is None
    assert [message.role for message in result.state.messages] == ["user"]
    assert result.state.events[-1].event_type == "planner.invalid_output"
    assert result.state.events[-1].payload == {
        "error": "Planner output was not valid JSON"
    }


def test_baseline_runtime_rejects_unknown_tool_before_executor_call():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="get_order_details",
                        tool_type="read",
                        description="",
                        parameters_schema={},
                    )
                ]
            )
        ),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                tool_name="delete_everything",
                arguments={},
                rationale="Bad model output.",
            )
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check my account",
    )

    assert result.proposal_result is not None
    assert result.proposal_result.accepted is False
    assert result.proposal_result.error == "Unknown tool proposal: delete_everything"
    assert result.state.events[-1].event_type == "tool_proposal.rejected"
    assert result.state.events[-1].payload == {
        "reason": "unknown_tool",
        "tool": "delete_everything",
    }
    assert [message.role for message in result.state.messages] == ["user"]


def test_baseline_runtime_rejects_tool_outside_declared_skill_boundary():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="cancel_pending_order",
                        tool_type="write",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": ["order_id", "reason"],
                            "properties": {
                                "order_id": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                        },
                    )
                ]
            )
        ),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                skill_id="order_lookup",
                skill_action="inspect_order",
                tool_name="cancel_pending_order",
                arguments={"order_id": "#W0000000", "reason": "ordered by mistake"},
                rationale="Bad skill/tool pairing.",
            )
        ),
        skill_registry=[
            SkillDefinition(
                id="order_lookup",
                description="Inspect order state.",
                allowed_tools=["get_order_details"],
            )
        ],
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please cancel order #W0000000",
    )

    assert result.proposal_result is not None
    assert result.proposal_result.accepted is False
    assert result.proposal_result.error == (
        "Tool cancel_pending_order is not allowed for skill order_lookup"
    )
    assert result.state.events[-1].event_type == "skill_policy.rejected"
    assert result.state.events[-1].payload == {
        "reason": "tool_not_allowed",
        "skill_id": "order_lookup",
        "tool": "cancel_pending_order",
    }


def test_baseline_runtime_routes_skill_action_to_tool_before_execution():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="find_user_id_by_name_zip",
                        tool_type="read",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": ["first_name", "last_name", "zip"],
                            "properties": {
                                "first_name": {"type": "string"},
                                "last_name": {"type": "string"},
                                "zip": {"type": "string"},
                            },
                        },
                    )
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                (
                    '{"action":"tool_call","skill_id":"authentication",'
                    '"skill_action":"lookup_by_name_zip",'
                    '"arguments":{"first_name":"Yusuf","last_name":"Rossi","zip":"19122"},'
                    '"rationale":"Authenticate user."}'
                )
            ),
        ),
        skill_registry=default_skill_registry(),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please find user Yusuf Rossi zip 19122",
    )

    assert result.proposal is not None
    assert result.proposal.skill_id == "authentication"
    assert result.proposal.skill_action == "lookup_by_name_zip"
    assert result.proposal.tool_name == "find_user_id_by_name_zip"
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert result.state.events[0].event_type == "skill_node.routed"
    assert result.state.events[0].payload == {
        "skill_id": "authentication",
        "skill_action": "lookup_by_name_zip",
        "tool": "find_user_id_by_name_zip",
    }
    assert result.state.messages[-2].role == "tool"
    assert result.state.messages[-1].role == "assistant"


def test_baseline_runtime_rejects_unknown_skill_action_before_tool_validation():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort([])),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                (
                    '{"action":"tool_call","skill_id":"order_lookup",'
                    '"skill_action":"cancel_pending_order",'
                    '"arguments":{"order_id":"#W0000000"},'
                    '"rationale":"Wrong action for skill."}'
                )
            ),
        ),
        skill_registry=default_skill_registry(),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please cancel order #W0000000",
    )

    assert result.proposal_result is not None
    assert result.proposal_result.accepted is False
    assert result.proposal_result.error == (
        "Skill action cancel_pending_order is not available for skill order_lookup"
    )
    assert result.state.events[-1].event_type == "skill_node.rejected"
    assert result.state.events[-1].payload == {
        "reason": "unknown_skill_action",
        "skill_id": "order_lookup",
        "skill_action": "cancel_pending_order",
    }


def test_baseline_runtime_routes_write_skill_action_to_pending_confirmation():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="cancel_pending_order",
                        tool_type="write",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": ["order_id", "reason"],
                            "properties": {
                                "order_id": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                        },
                    )
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                (
                    '{"action":"tool_call","skill_id":"cancel_order",'
                    '"skill_action":"cancel_pending_order",'
                    '"arguments":{"order_id":"#W0000000","reason":"ordered by mistake"},'
                    '"rationale":"Cancel pending order."}'
                )
            ),
        ),
        skill_registry=default_skill_registry(),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="conv-1"),
        "Please cancel order #W0000000",
        max_steps=3,
    )

    assert result.stopped_reason == "pending_confirmation"
    assert len(result.turns) == 1
    assert result.turns[0].proposal is not None
    assert result.turns[0].proposal.skill_id == "cancel_order"
    assert result.turns[0].proposal.tool_name == "cancel_pending_order"
    assert result.state.confirmation.pending is not None
    assert result.state.events[0].event_type == "skill_node.routed"
    assert result.state.events[1].event_type == "tool_proposal.accepted"
    assert result.state.events[2].event_type == "policy_guard.requires_confirmation"


def test_llm_runtime_falls_back_to_write_tool_when_planner_final_response_is_premature():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="exchange_delivered_order_items",
                        tool_type="write",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": [
                                "order_id",
                                "item_ids",
                                "new_item_ids",
                                "payment_method_id",
                            ],
                            "properties": {
                                "order_id": {"type": "string"},
                                "item_ids": {"type": "array"},
                                "new_item_ids": {"type": "array"},
                                "payment_method_id": {"type": "string"},
                            },
                        },
                    )
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"final_response","message":"I can exchange those for you.","rationale":"Enough context."}'
            ),
        ),
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W2378156","status":"delivered",'
                    '"payment_history":[{"payment_method_id":"credit_card_9513926"}],'
                    '"items":['
                    '{"name":"Mechanical Keyboard","product_id":"1656367028","item_id":"1151293680"},'
                    '{"name":"Smart Thermostat","product_id":"4896585277","item_id":"4983901480"}'
                    "]}"
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"product_id":"1656367028","name":"Mechanical Keyboard",'
                    '"variants":{"7706410293":{"item_id":"7706410293","available":true,'
                    '"options":{"switch type":"clicky","backlight":"none","size":"full size"}}}}'
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"product_id":"4896585277","name":"Smart Thermostat",'
                    '"variants":{"7747408585":{"item_id":"7747408585","available":true,'
                    '"options":{"compatibility":"Google Assistant","color":"black"}}}}'
                ),
            ),
        ],
    )

    result = runtime.run_until_blocked(
        state,
        "Please exchange the mechanical keyboard and smart thermostat from order #W2378156.",
        max_steps=2,
    )

    assert result.stopped_reason == "pending_confirmation"
    assert result.turns[0].proposal is not None
    assert result.turns[0].proposal.tool_name == "exchange_delivered_order_items"
    assert result.state.confirmation.pending is not None
    assert result.state.events[0].event_type == "planner.terminal_fallback"
    assert result.state.events[0].payload == {
        "terminal_action": "final_response",
        "fallback_tool": "exchange_delivered_order_items",
    }
    assert result.state.events[-1].event_type == "policy_guard.requires_confirmation"


def test_llm_runtime_falls_back_to_rule_tool_after_invalid_json_repair_fails():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="get_order_details",
                        tool_type="read",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": ["order_id"],
                            "properties": {"order_id": {"type": "string"}},
                        },
                    )
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient("not json"),
        ),
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="yusuf_rossi_9620",
            )
        ],
    )

    result = runtime.run_step(
        state,
        "You are Yusuf Rossi in zip code 19122. Please check order #W2378156.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_order_details"
    assert result.proposal.arguments == {"order_id": "#W2378156"}
    assert result.state.events[0].event_type == "planner.terminal_fallback"
    assert result.state.events[0].payload == {
        "terminal_action": "invalid",
        "fallback_tool": "get_order_details",
    }


def test_llm_runtime_replaces_repeated_read_with_exchange_fallback():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="find_user_id_by_name_zip",
                        tool_type="read",
                        description="",
                        parameters_schema={},
                    ),
                    RetailToolDefinition(
                        name="exchange_delivered_order_items",
                        tool_type="write",
                        description="",
                        parameters_schema={},
                    ),
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"find_user_id_by_name_zip",'
                '"arguments":{"first_name":"Yusuf","last_name":"Rossi","zip":"19122"},'
                '"rationale":"Restart lookup."}'
            ),
        ),
    )
    state = _exchange_ready_state()

    result = runtime.run_until_blocked(
        state,
        "Please exchange the mechanical keyboard and smart thermostat from order #W2378156.",
        max_steps=2,
    )

    assert result.stopped_reason == "pending_confirmation"
    assert result.turns[0].proposal is not None
    assert result.turns[0].proposal.tool_name == "exchange_delivered_order_items"
    assert result.state.events[0].event_type == "planner.repeated_read_fallback"
    assert result.state.events[0].payload == {
        "repeated_tool": "find_user_id_by_name_zip",
        "fallback_tool": "exchange_delivered_order_items",
    }


def test_llm_runtime_does_not_replace_read_for_uninspected_order():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("get_order_details", "read")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":"#W2"},"write_plan":[]}'
            ),
        ),
    )
    state = record_tool_execution(
        CustomerAgentState(
            conversation_id="conv-two-orders",
            messages=[
                ConversationMessage(
                    role="tool",
                    tool_name="find_user_id_by_name_zip",
                    content='{"user_id":"user-1"}',
                ),
                ConversationMessage(
                    role="tool",
                    tool_name="get_order_details",
                    content=(
                        '{"order_id":"#W1","user_id":"user-1","status":"pending",'
                        '"address":{"address1":"Old","city":"Austin","state":"TX",'
                        '"country":"USA","zip":"73301"}}'
                    ),
                )
            ],
        ),
        tool_name="get_order_details",
        arguments={"order_id": "#W1"},
        raw_content='{"order_id":"#W1"}',
        tool_type="read",
        error=False,
    )

    result = runtime.run_step(
        state,
        "Change the address for order #W1 to Suite 4 and cancel order #W2.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments == {"order_id": "#W2"}
    assert all(
        event.event_type != "planner.repeated_read_fallback"
        for event in result.state.events
    )


@pytest.mark.parametrize("proposed_tool", ["get_user_details", "list_all_product_types"])
def test_llm_runtime_replaces_broad_return_discovery_with_known_product_lookup(
    proposed_tool: str,
):
    tools = [
        RetailToolDefinition(
            name="get_user_details",
            tool_type="read",
            description="Fetch customer details.",
            parameters_schema={
                "type": "object",
                "required": ["user_id"],
                "properties": {"user_id": {"type": "string"}},
            },
        ),
        RetailToolDefinition(
            name="list_all_product_types",
            tool_type="read",
            description="List product types.",
            parameters_schema={"type": "object", "properties": {}},
        ),
        RetailToolDefinition(
            name="get_product_details",
            tool_type="read",
            description="Fetch product details.",
            parameters_schema={
                "type": "object",
                "required": ["product_id"],
                "properties": {"product_id": {"type": "string"}},
            },
        ),
    ]
    arguments = (
        {"user_id": "yusuf_rossi_9620"}
        if proposed_tool == "get_user_details"
        else {}
    )
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                "{"
                '"action":"tool_call",'
                f'"tool_name":"{proposed_tool}",'
                f'"arguments":{json.dumps(arguments)},'
                '"rationale":"Explore broadly before processing the return."'
                "}"
            ),
        ),
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content='{"user_id":"yusuf_rossi_9620"}',
            )
        ],
    )

    result = runtime.run_step(
        state,
        (
            "You are Yusuf Rossi in zip code 19122. You want to know exactly how many "
            "tshirt options are available and return the cleaner, headphone, and smart watch."
        ),
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_product_details"
    assert result.proposal.arguments == {"product_id": "9523456873"}
    assert result.state.events[0].event_type == "planner.known_product_fallback"
    assert result.state.events[0].payload == {
        "replaced_tool": proposed_tool,
        "fallback_tool": "get_product_details",
        "product_id": "9523456873",
    }


def test_llm_runtime_keeps_explicit_generic_catalog_lookup():
    tools = [
        RetailToolDefinition(
            name="list_all_product_types",
            tool_type="read",
            description="List product types.",
            parameters_schema={"type": "object", "properties": {}},
        )
    ]
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"list_all_product_types",'
                '"arguments":{},"rationale":"The customer asked to browse the catalog."}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please list all product types in the store.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "list_all_product_types"
    assert all(
        event.event_type != "planner.known_product_fallback"
        for event in result.state.events
    )


def test_llm_runtime_repairs_unknown_tool_once_before_rejecting():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="get_order_details",
                        tool_type="read",
                        description="Fetch order details.",
                        parameters_schema={
                            "type": "object",
                            "required": ["order_id"],
                            "properties": {"order_id": {"type": "string"}},
                        },
                    )
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=SequencedLLMClient(
                [
                    '{"action":"tool_call","tool_name":"lookup_order",'
                    '"arguments":{"order_id":"#W2378156"},"rationale":"Wrong tool name."}',
                    '{"action":"tool_call","tool_name":"get_order_details",'
                    '"arguments":{"order_id":"#W2378156"},"rationale":"Repair to valid tool."}',
                ]
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check my recent order.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_order_details"
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert result.state.events[0].event_type == "planner.rejected_tool_repair"
    assert result.state.events[0].payload == {
        "reason": "unknown_tool",
        "rejected_tool": "lookup_order",
        "repaired_tool": "get_order_details",
    }


def test_llm_runtime_prefers_deterministic_fallback_over_unknown_tool_repair():
    client = SequencedLLMClient(
        [
            '{"action":"tool_call","tool_name":"ecommerce_backend",'
            '"arguments":{},"rationale":"Use a nonexistent generic backend."}',
            '{"action":"tool_call","tool_name":"get_user_details",'
            '"arguments":{"user_id":"yusuf_rossi_9620"},'
            '"rationale":"This repair should not be needed."}',
        ]
    )
    tools = [
        RetailToolDefinition(
            name="get_product_details",
            tool_type="read",
            description="Fetch product details.",
            parameters_schema={
                "type": "object",
                "required": ["product_id"],
                "properties": {"product_id": {"type": "string"}},
            },
        )
    ]
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=client,
        ),
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="yusuf_rossi_9620",
            )
        ],
    )

    result = runtime.run_step(
        state,
        "I want to count tshirt options and return the cleaner, headphone, and smart watch.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_product_details"
    assert result.proposal.arguments == {"product_id": "9523456873"}
    assert len(client.calls) == 1
    assert result.state.events[0].event_type == "planner.rejected_tool_fallback"
    assert result.state.events[0].payload == {
        "reason": "unknown_tool",
        "rejected_tool": "ecommerce_backend",
        "fallback_tool": "get_product_details",
    }


def test_llm_runtime_falls_back_when_skill_action_is_unknown():
    tools = [
        RetailToolDefinition(
            name="get_product_details",
            tool_type="read",
            description="Fetch product details.",
            parameters_schema={
                "type": "object",
                "required": ["product_id"],
                "properties": {"product_id": {"type": "string"}},
            },
        )
    ]
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","skill_id":"order_lookup",'
                '"skill_action":"inspect_user_profile","arguments":{},'
                '"rationale":"Use an unavailable skill action."}'
            ),
        ),
        skill_registry=default_skill_registry(),
    )
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="yusuf_rossi_9620",
            )
        ],
    )

    result = runtime.run_step(
        state,
        "I want to count tshirt options and return the cleaner, headphone, and smart watch.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_product_details"
    assert result.state.events[0].event_type == "planner.rejected_skill_fallback"
    assert result.state.events[0].payload == {
        "reason": "unknown_skill_action",
        "skill_id": "order_lookup",
        "skill_action": "inspect_user_profile",
        "fallback_tool": "get_product_details",
    }


def test_llm_runtime_removes_unknown_skill_metadata_from_valid_tool():
    tools = [
        RetailToolDefinition(
            name="get_order_details",
            tool_type="read",
            description="Fetch order details.",
            parameters_schema={
                "type": "object",
                "required": ["order_id"],
                "properties": {"order_id": {"type": "string"}},
            },
        )
    ]
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(RecordingPort(tools)),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","skill_id":"ecommerce_order_mgmt",'
                '"tool_name":"get_order_details",'
                '"arguments":{"order_id":"#W9711842"},'
                '"rationale":"Inspect the next order."}'
            ),
        ),
        skill_registry=default_skill_registry(),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Inspect the next order for a return.",
    )

    assert result.proposal is not None
    assert result.proposal.tool_name == "get_order_details"
    assert result.proposal.skill_id == ""
    assert result.proposal_result is not None
    assert result.proposal_result.accepted is True
    assert result.state.events[0].event_type == "planner.invalid_skill_metadata_removed"
    assert result.state.events[0].payload == {
        "reason": "unknown_skill",
        "skill_id": "ecommerce_order_mgmt",
        "tool": "get_order_details",
    }


def test_baseline_runtime_rejects_missing_required_arguments_before_executor_call():
    runtime = BaselineAgentRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    RetailToolDefinition(
                        name="get_order_details",
                        tool_type="read",
                        description="",
                        parameters_schema={
                            "type": "object",
                            "required": ["order_id"],
                            "properties": {"order_id": {"type": "string"}},
                        },
                    )
                ]
            )
        ),
        proposal_generator=FixedProposalGenerator(
            ToolProposal(
                tool_name="get_order_details",
                arguments={},
                rationale="Missing required argument.",
            )
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156",
    )

    assert result.proposal_result is not None
    assert result.proposal_result.accepted is False
    assert result.proposal_result.error == "Missing required tool arguments: order_id"
    assert result.state.events[-1].event_type == "tool_proposal.rejected"
    assert result.state.events[-1].payload == {
        "reason": "missing_required_arguments",
        "tool": "get_order_details",
        "missing": ["order_id"],
    }


def test_llm_runtime_redirects_unrelated_order_read_to_locked_order():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("get_order_details", "read")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":"#WOTHER"},'
                '"rationale":"Inspect another order."}'
            ),
        ),
    )

    result = runtime.run_step(
        _state_with_locked_order("#WLOCKED"),
        "Update the remaining item in my order.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments == {"order_id": "#WLOCKED"}
    redirect = next(
        event
        for event in result.state.events
        if event.event_type == "planner.locked_order_redirect"
    )
    assert redirect.payload == {
        "proposed_order_id": "#WOTHER",
        "locked_order_id": "#WLOCKED",
    }


def test_llm_runtime_preserves_locked_order_read():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("get_order_details", "read")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":"#WLOCKED"},'
                '"rationale":"Refresh the active order."}'
            ),
        ),
    )

    result = runtime.run_step(
        _state_with_locked_order("#WLOCKED"),
        "Update the remaining item in my order.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments == {"order_id": "#WLOCKED"}
    assert all(
        event.event_type != "planner.locked_order_redirect"
        for event in result.state.events
    )


def test_llm_runtime_does_not_rewrite_write_for_different_order():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("modify_pending_order_address", "write")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"modify_pending_order_address",'
                '"arguments":{"order_id":"#WOTHER","city":"Boston"},'
                '"rationale":"Apply the requested address update."}'
            ),
        ),
    )

    result = runtime.run_step(
        _state_with_locked_order("#WLOCKED"),
        "Update the remaining item in my order.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments["order_id"] == "#WOTHER"
    assert result.state.confirmation.pending is not None
    assert result.state.confirmation.pending.arguments["order_id"] == "#WOTHER"
    assert all(
        event.event_type != "planner.locked_order_redirect"
        for event in result.state.events
    )


def test_llm_runtime_order_id_normalization_canonicalizes_read_and_audits():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("get_order_details", "read")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":" W8268610 "},"rationale":"Inspect it."}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-normalize-read"),
        "Inspect my order.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments == {"order_id": "#W8268610"}
    events = [
        event
        for event in result.state.events
        if event.event_type == "planner.order_id_normalized"
    ]
    assert [event.payload for event in events] == [
        {
            "tool_name": "get_order_details",
            "original": " W8268610 ",
            "normalized": "#W8268610",
        }
    ]


@pytest.mark.parametrize("order_id", ["#W8268610", "W82-68610"])
def test_llm_runtime_order_id_normalization_leaves_canonical_or_malformed_read(
    order_id,
):
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("get_order_details", "read")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                json.dumps(
                    {
                        "action": "tool_call",
                        "tool_name": "get_order_details",
                        "arguments": {"order_id": order_id},
                    }
                )
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-unchanged-read"),
        "Inspect my order.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments == {"order_id": order_id}
    assert all(
        event.event_type != "planner.order_id_normalized"
        for event in result.state.events
    )


def test_llm_runtime_order_id_normalization_never_rewrites_write_arguments():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort([_order_tool("modify_pending_order_address", "write")])
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"modify_pending_order_address",'
                '"arguments":{"order_id":"W8268610","city":"Boston"}}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-write-verbatim"),
        "Update the address.",
    )

    assert result.proposal is not None
    assert result.proposal.arguments["order_id"] == "W8268610"
    assert result.state.confirmation.pending is not None
    assert result.state.confirmation.pending.arguments["order_id"] == "W8268610"
    assert all(
        event.event_type != "planner.order_id_normalized"
        for event in result.state.events
    )


def test_llm_runtime_write_plan_canonicalizes_only_trusted_order_ids():
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    _order_tool("get_order_details", "read"),
                    _order_tool("modify_pending_order_address", "write"),
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":"W8268610"},"write_plan":['
                '{"objective_id":"first","tool_name":"modify_pending_order_address",'
                '"order_id":"#w8268610"},'
                '{"objective_id":"second","tool_name":"modify_pending_order_address",'
                '"order_id":"W82-68610"}]}'
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-plan-canonical"),
        "Update two orders.",
    )

    assert [
        objective.order_id for objective in result.state.objective_ledger.write_plan
    ] == ["#W8268610", None]


def test_llm_runtime_failed_order_reaches_next_planner_recovery_context():
    client = SequencedLLMClient(
        [
            '{"action":"tool_call","tool_name":"get_order_details",'
            '"arguments":{"order_id":"w8268610"}}',
            '{"action":"final_response","message":"I could not find that order."}',
        ]
    )
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(FailingOrderPort()),
        proposal_generator=LLMProposalGenerator(model="test-model", client=client),
    )

    result = runtime.run_until_blocked(
        CustomerAgentState(conversation_id="conv-failed-recovery"),
        "Inspect my order.",
        max_steps=2,
    )

    assert result.state.objective_ledger.failed_order_ids == ["#W8268610"]
    assert result.state.objective_ledger.inspected_order_ids == []
    assert len(client.calls) == 2
    second_context = client.calls[1]["messages"][1]["content"]
    assert (
        'ORDER_LOOKUP_RECOVERY: {"failed_order_ids":["#W8268610"],'
        '"recommended_order_id":null}'
    ) in second_context


def test_llm_runtime_validates_and_normalizes_first_write_plan():
    planned = [
        {
            "objective_id": "step",
            "tool_name": "modify_pending_order_address",
            "order_id": f"#W{index}",
            "intent": f"move shipment {index}",
            "status": "completed",
        }
        for index in range(10)
    ]
    planned.insert(
        1,
        {"objective_id": "read", "tool_name": "get_order_details"},
    )
    planned.insert(
        2,
        {"objective_id": "unknown", "tool_name": "delete_everything"},
    )
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    _order_tool("get_order_details", "read"),
                    _order_tool("modify_pending_order_address", "write"),
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                json.dumps(
                    {
                        "action": "tool_call",
                        "tool_name": "get_order_details",
                        "arguments": {"order_id": "#W0"},
                        "write_plan": planned,
                    }
                )
            ),
        ),
    )

    result = runtime.run_step(
        CustomerAgentState(conversation_id="conv-plan"),
        "Make several order changes.",
    )

    plan = result.state.objective_ledger.write_plan
    assert len(plan) == 8
    assert [item.objective_id for item in plan[:3]] == ["step", "step-2", "step-3"]
    assert all(item.tool_name == "modify_pending_order_address" for item in plan)
    assert all(item.status == "pending" for item in plan)
    assert all(item.completed_fingerprint is None for item in plan)
    created = next(
        event for event in result.state.events if event.event_type == "objective_plan.created"
    )
    assert created.payload == {"objective_count": 8}


def test_llm_runtime_keeps_existing_write_plan_immutable():
    state = _state_with_write_plan()
    runtime = LLMPlannerRuntime(
        executor=GuardedRetailToolExecutor(
            RecordingPort(
                [
                    _order_tool("get_order_details", "read"),
                    _order_tool("modify_pending_order_address", "write"),
                ]
            )
        ),
        proposal_generator=LLMProposalGenerator(
            model="test-model",
            client=FixedLLMClient(
                '{"action":"tool_call","tool_name":"get_order_details",'
                '"arguments":{"order_id":"#W1"},"write_plan":['
                '{"objective_id":"replacement","tool_name":"modify_pending_order_address"}]}'
            ),
        ),
    )

    result = runtime.run_step(state, "continue")

    assert [item.objective_id for item in result.state.objective_ledger.write_plan] == [
        "original"
    ]
    assert all(
        event.event_type != "objective_plan.created" for event in result.state.events
    )


def _state_with_locked_order(order_id: str) -> CustomerAgentState:
    state = initialize_objective_ledger(
        CustomerAgentState(conversation_id="conv-lock"),
        "Update two fields on my pending order.",
    )
    return record_tool_execution(
        state,
        tool_name="modify_pending_order_address",
        arguments={"order_id": order_id, "city": "Charlotte"},
        raw_content=f'{{"order_id":"{order_id}"}}',
        tool_type="write",
        error=False,
        fingerprint="address:locked",
    )


def _state_with_write_plan() -> CustomerAgentState:
    from app.agent.state import WriteObjective

    state = CustomerAgentState(conversation_id="conv-existing-plan")
    return state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "write_plan": [
                        WriteObjective(
                            objective_id="original",
                            tool_name="modify_pending_order_address",
                        )
                    ]
                }
            )
        }
    )


def _order_tool(name: str, tool_type: str) -> RetailToolDefinition:
    return RetailToolDefinition(
        name=name,
        tool_type=tool_type,
        description="Order operation.",
        parameters_schema={
            "type": "object",
            "required": ["order_id"],
            "properties": {
                "order_id": {"type": "string"},
                "city": {"type": "string"},
            },
        },
    )


class FixedProposalGenerator:
    def __init__(self, proposal: ToolProposal | None) -> None:
        self._proposal = proposal

    def generate(
        self,
        state: CustomerAgentState,
        user_message: str,
    ) -> ToolProposal | None:
        return self._proposal


class FixedLLMClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        return self._response


class SequencedLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[dict] = []

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        self.calls.append({"model": model, "messages": messages})
        index = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[index]


def _exchange_ready_state() -> CustomerAgentState:
    return CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="yusuf_rossi_9620",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W2378156","status":"delivered",'
                    '"payment_history":[{"payment_method_id":"credit_card_9513926"}],'
                    '"items":['
                    '{"name":"Mechanical Keyboard","product_id":"1656367028","item_id":"1151293680"},'
                    '{"name":"Smart Thermostat","product_id":"4896585277","item_id":"4983901480"}'
                    "]}"
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"product_id":"1656367028","name":"Mechanical Keyboard",'
                    '"variants":{"7706410293":{"item_id":"7706410293","available":true,'
                    '"options":{"switch type":"clicky","backlight":"none","size":"full size"}}}}'
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"product_id":"4896585277","name":"Smart Thermostat",'
                    '"variants":{"7747408585":{"item_id":"7747408585","available":true,'
                    '"options":{"compatibility":"Google Assistant","color":"black"}}}}'
                ),
            ),
        ],
    )


class RecordingPort:
    def __init__(self, tools: list[RetailToolDefinition]) -> None:
        self._tools = tools

    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list[RetailToolDefinition]:
        return self._tools

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "generated-call-id",
            name=name,
            content={"user_id": "yusuf_rossi_9620"},
            raw_content='{"user_id": "yusuf_rossi_9620"}',
            error=False,
        )


class FailingOrderPort:
    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list[RetailToolDefinition]:
        return [_order_tool("get_order_details", "read")]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        return RetailToolResult(
            call_id=call_id or "failed-order-call",
            name=name,
            content="Order not found",
            raw_content="Order not found",
            error=True,
        )


class CrossAccountOrderPort:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def policy(self) -> str:
        return ""

    def list_tools(self) -> list[RetailToolDefinition]:
        return [_order_tool("get_order_details", "read")]

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        call_id: str | None = None,
    ) -> RetailToolResult:
        self.calls.append(arguments)
        return RetailToolResult(
            call_id=call_id or "cross-account-call",
            name=name,
            content={"order_id": "#W6893533", "user_id": "ivan_santos_6635"},
            raw_content=(
                '{"order_id":"#W6893533",'
                '"user_id":"ivan_santos_6635"}'
            ),
            error=False,
        )
