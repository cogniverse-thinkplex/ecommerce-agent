from app.agent.proposal_generator import (
    LLMProposalGenerator,
    LiteLLMClient,
    ModelProviderError,
    PlannerDecision,
    RuleBasedProposalGenerator,
    parse_planner_decision_json,
    parse_tool_proposal_json,
    _planner_system_prompt,
    _recent_messages_json,
)
from app.agent.skills import SkillDefinition
from app.agent.state import (
    ConversationMessage,
    CustomerAgentState,
    WriteObjective,
    initialize_objective_ledger,
    record_tool_execution,
)
from app.tools.retail_port import RetailToolDefinition


def test_litellm_client_tracks_tokens_and_qwen_list_price(monkeypatch):
    response = {
        "choices": [{"message": {"content": '{"action":"final_response","message":"ok"}'}}],
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        },
    }
    monkeypatch.setattr("litellm.completion", lambda **_: response)
    client = LiteLLMClient()

    content = client.complete(
        model="dashscope/qwen3.7-flash",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert content == '{"action":"final_response","message":"ok"}'
    assert client.prompt_tokens == 1000
    assert client.completion_tokens == 500
    assert client.total_tokens == 1500
    assert client.estimated_list_cost_cny == 0.0006


def test_litellm_client_bounds_structured_qwen_requests(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": '{"action":"final_response","message":"ok"}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

    monkeypatch.setattr("litellm.completion", fake_completion)
    monkeypatch.setenv("ECOM_AGENT_LLM_TIMEOUT_SECONDS", "75")
    monkeypatch.setenv("ECOM_AGENT_LLM_MAX_TOKENS", "900")
    client = LiteLLMClient()

    client.complete(model="dashscope/qwen3.8-flash", messages=[])

    assert captured["timeout"] == 75.0
    assert captured["max_tokens"] == 900
    assert captured["extra_body"] == {"enable_thinking": False}


def test_litellm_client_normalizes_free_quota_errors(monkeypatch):
    def exhausted_completion(**kwargs):
        raise RuntimeError(
            'DashscopeException - Free quota exhausted. '
            'code="AllocationQuota.FreeTierOnly"'
        )

    monkeypatch.setattr("litellm.completion", exhausted_completion)
    client = LiteLLMClient()

    try:
        client.complete(model="dashscope/qwen3.8-flash", messages=[])
    except ModelProviderError as exc:
        assert exc.reason == "quota_exhausted"
        assert exc.model == "dashscope/qwen3.8-flash"
    else:
        raise AssertionError("Expected a normalized model provider error")


def test_litellm_client_tracks_qwen38_flash_list_price(monkeypatch):
    monkeypatch.setattr(
        "litellm.completion",
        lambda **_: {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        },
    )
    client = LiteLLMClient()

    client.complete(model="dashscope/qwen3.8-flash", messages=[])

    assert client.estimated_list_cost_cny == 0.00215
    assert client.usage_requests[0]["pricing_version"] == "2026-10-22"


def test_parse_planner_decision_preserves_ordered_duplicate_write_objectives():
    decision = parse_planner_decision_json(
        '{"action":"tool_call","tool_name":"modify_pending_order_items",'
        '"arguments":{"order_id":"#W1"},"write_plan":['
        '{"objective_id":"first","tool_name":"modify_pending_order_items",'
        '"order_id":"#W1","intent":"replace the backpack","status":"completed"},'
        '{"objective_id":"second","tool_name":"modify_pending_order_items",'
        '"order_id":"#W1","intent":"replace the lamp"}]}'
    )

    assert decision.action == "tool_call"
    assert [item["objective_id"] for item in decision.write_plan] == [
        "first",
        "second",
    ]
    assert [item["tool_name"] for item in decision.write_plan] == [
        "modify_pending_order_items",
        "modify_pending_order_items",
    ]


def test_litellm_client_keeps_unknown_model_cost_unavailable(monkeypatch):
    response = {
        "choices": [{"message": {"content": "{}"}}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    monkeypatch.setattr("litellm.completion", lambda **_: response)
    client = LiteLLMClient()

    client.complete(model="dashscope/unknown-model", messages=[])

    assert client.total_tokens == 150
    assert client.estimated_list_cost_cny is None


def test_litellm_client_keeps_missing_usage_unavailable(monkeypatch):
    response = {"choices": [{"message": {"content": "{}"}}]}
    monkeypatch.setattr("litellm.completion", lambda **_: response)
    client = LiteLLMClient()

    client.complete(model="dashscope/qwen3.7-flash", messages=[])

    assert client.usage_available is False
    assert client.estimated_list_cost_cny is None
    assert client.usage_requests[0]["usage_available"] is False


def test_rule_based_generator_proposes_user_lookup_from_name_and_zip():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "Please find user Yusuf Rossi zip 19122",
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_name_zip"
    assert proposal.arguments == {
        "first_name": "Yusuf",
        "last_name": "Rossi",
        "zip": "19122",
    }
    assert "name and zip" in proposal.rationale


def test_rule_based_generator_proposes_user_lookup_from_tau_known_info():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "You are Yusuf Rossi in zip code 19122.",
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_name_zip"
    assert proposal.arguments == {
        "first_name": "Yusuf",
        "last_name": "Rossi",
        "zip": "19122",
    }


def test_rule_based_generator_prefers_email_lookup_when_email_is_available():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        (
            "Your name is Daiki Sanchez, and you live in 46236, "
            "your email is daikisanchez1479@example.com. Please cancel the order."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_email"
    assert proposal.arguments == {"email": "daikisanchez1479@example.com"}


def test_rule_based_generator_parses_your_name_and_live_in_zip():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "Your name is Daiki Sanchez, and you live in 46236. Please cancel the order.",
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_name_zip"
    assert proposal.arguments == {
        "first_name": "Daiki",
        "last_name": "Sanchez",
        "zip": "46236",
    }


def test_rule_based_generator_falls_back_to_name_zip_after_email_lookup_failure():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="Error: User not found",
            )
        ],
    )

    proposal = generator.generate(
        state,
        (
            "Your name is Daiki Sanchez, and you live in 46236, "
            "your email is daikisanchez1479@example.com. Please cancel the order."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_name_zip"
    assert proposal.arguments == {
        "first_name": "Daiki",
        "last_name": "Sanchez",
        "zip": "46236",
    }


def test_rule_based_generator_skips_user_lookup_after_user_id_result():
    generator = RuleBasedProposalGenerator()
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

    proposal = generator.generate(
        state,
        "You are Yusuf Rossi in zip code 19122. Please check order #W2378156.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}


def test_rule_based_generator_does_not_treat_email_address_as_shipping_intent():
    generator = RuleBasedProposalGenerator()
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

    proposal = generator.generate(
        state,
        (
            "You received order #W2378156 and wish to exchange the keyboard. "
            "You do not remember your email address."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}


def test_llm_proposal_generator_sends_tool_catalog_policy_and_recent_state():
    client = RecordingLLMClient(
        response=(
            '{"tool_name":"get_order_details",'
            '"arguments":{"order_id":"#W2378156"},'
            '"rationale":"Need order details."}'
        )
    )
    generator = LLMProposalGenerator(
        model="test-model",
        client=client,
        tool_catalog=[
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
        ],
        skill_registry=[
            SkillDefinition(
                id="order_lookup",
                description="Inspect order state.",
                allowed_tools=["get_order_details"],
            )
        ],
        policy="Write actions require confirmation.",
    )

    proposal = generator.generate(
        CustomerAgentState(
            conversation_id="conv-1",
            messages=[
                ConversationMessage(role="user", content="Earlier question"),
                ConversationMessage(
                    role="tool",
                    tool_name="find_user_id_by_name_zip",
                    content='{"user_id":"user-1"}',
                ),
            ],
        ),
        "Please check order #W2378156",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}
    assert len(client.requests) == 1
    request = client.requests[0]
    assert request["model"] == "test-model"
    assert request["messages"][0]["role"] == "system"
    system_prompt = request["messages"][0]["content"]
    assert "Return exactly one JSON object" in system_prompt
    assert "Do not wrap it in Markdown" in system_prompt
    assert "do not return final_response before proposing that write tool" in system_prompt
    assert "A write tool_call is only a staged proposal" in system_prompt
    assert "Do not ask for confirmation in final_response" in system_prompt
    assert "avoid list_all_product_types" in system_prompt
    assert request["messages"][1] == {
        "role": "user",
        "content": (
            'AVAILABLE_TOOLS: [{"name":"get_order_details","tool_type":"read",'
                '"description":"Fetch order details.","parameters":{"order_id":'
                '{"type":"string","required":true}}}]\n'
                'AVAILABLE_SKILLS: [{"id":"order_lookup",'
                '"allowed_tools":["get_order_details"],"actions":{},'
            '"requires_confirmation":false}]\n'
            "POLICY: Write actions require confirmation.\n"
            "POLICY_EVIDENCE: []\n"
            "CONVERSATION_ID: conv-1\n"
                'OBJECTIVE_LEDGER: {"original_objective":"","locked_order_id":null,'
                    '"active_order_id":null,"active_policy_id":null,'
                    '"inspected_order_ids":[],"failed_order_ids":[],"known_order_ids":[],'
                    '"resolved_products":[],"completed_writes":[],"write_plan":[]}\n'
                "NEXT_WRITE_OBJECTIVE: null\n"
                'ORDER_LOOKUP_RECOVERY: {"failed_order_ids":[],'
                '"recommended_order_id":null}\n'
            'RECENT_MESSAGES: [{"role":"user","content":"Earlier question"},'
            '{"role":"tool","content":"{\\"user_id\\":\\"user-1\\"}",'
            '"tool_name":"find_user_id_by_name_zip"}]\n'
            "LATEST_USER_MESSAGE: Please check order #W2378156"
        ),
    }


def test_recent_messages_keeps_latest_assistant_focus_and_compacts_tool_state():
    state = CustomerAgentState(
        conversation_id="conv-compact",
        messages=[
            ConversationMessage(role="user", content="Return my recent order"),
            ConversationMessage(role="assistant", content="I will inspect it."),
            ConversationMessage(role="tool", tool_name="get_user_details", content='{"orders":["#W1"]}'),
            ConversationMessage(role="assistant", content="I will inspect the order."),
            ConversationMessage(role="tool", tool_name="get_order_details", content='{"order_id":"#W1","status":"delivered"}'),
            ConversationMessage(role="assistant", content="I will inspect the order again."),
            ConversationMessage(role="tool", tool_name="get_order_details", content='{"order_id":"#W1","status":"delivered"}'),
        ],
    )

    payload = _recent_messages_json(state)

    assert "Return my recent order" in payload
    assert "get_user_details" in payload
    assert payload.count("get_order_details") == 1
    assert "I will inspect the order again." in payload
    assert "I will inspect it." not in payload


def test_planner_context_exposes_active_order_for_ambiguous_follow_up():
    client = RecordingLLMClient(
        response='{"action":"need_more_info","message":"请选择取消原因"}'
    )
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = record_tool_execution(
        CustomerAgentState(
            conversation_id="conv-focus",
            messages=[
                ConversationMessage(role="user", content="订单 #W8770097 可以退货吗？"),
                ConversationMessage(
                    role="assistant",
                    content="该订单待处理，可以取消订单。",
                ),
            ],
        ),
        tool_name="get_order_details",
        arguments={"order_id": "#W8770097"},
        raw_content='{"order_id":"#W8770097","status":"pending"}',
        tool_type="read",
        error=False,
    )

    generator.decide(state, "取消订单")

    context = client.requests[0]["messages"][1]["content"]
    assert '"active_order_id":"#W8770097"' in context
    assert "该订单待处理，可以取消订单。" in context
    assert "Resolve ambiguous references" in client.requests[0]["messages"][0]["content"]


def test_rule_based_generator_proposes_order_lookup_from_order_id():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156 before we exchange anything.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}
    assert "order details" in proposal.rationale


class RecordingLLMClient:
    def __init__(self, response: str) -> None:
        self._response = response
        self.requests: list[dict] = []

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        self.requests.append({"model": model, "messages": messages})
        return self._response


def test_rule_based_generator_proposes_uninspected_product_from_order_details():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"items":['
                    '{"name":"Mechanical Keyboard","product_id":"1656367028"},'
                    '{"name":"Smart Thermostat","product_id":"4896585277"}'
                    "]}"
                ),
            )
        ],
    )

    proposal = generator.generate(
        state,
        "Please exchange the mechanical keyboard and smart thermostat from order #W2378156.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_product_details"
    assert proposal.arguments == {"product_id": "1656367028"}
    assert "Mechanical Keyboard" in proposal.rationale


def test_rule_based_generator_skips_product_details_already_retrieved():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"items":['
                    '{"name":"Mechanical Keyboard","product_id":"1656367028"},'
                    '{"name":"Smart Thermostat","product_id":"4896585277"}'
                    "]}"
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content='{"product_id":"1656367028","name":"Mechanical Keyboard"}',
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "Please exchange the mechanical keyboard and smart thermostat from order #W2378156.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_product_details"
    assert proposal.arguments == {"product_id": "4896585277"}
    assert "Smart Thermostat" in proposal.rationale


def test_rule_based_generator_proposes_exchange_after_required_product_details():
    generator = RuleBasedProposalGenerator()
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
                    '{"name":"Mechanical Keyboard","product_id":"1656367028","variants":{'
                    '"9025753381":{"item_id":"9025753381","options":{"switch type":"clicky","backlight":"RGB","size":"full size"},"available":false},'
                    '"7706410293":{"item_id":"7706410293","options":{"switch type":"clicky","backlight":"none","size":"full size"},"available":true}'
                    "}}"
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"name":"Smart Thermostat","product_id":"4896585277","variants":{'
                    '"7747408585":{"item_id":"7747408585","options":{"compatibility":"Google Assistant","color":"black"},"available":true},'
                    '"4983901480":{"item_id":"4983901480","options":{"compatibility":"Apple HomeKit","color":"black"},"available":true}'
                    "}}"
                ),
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "Please exchange the mechanical keyboard and smart thermostat from order #W2378156.",
    )

    assert proposal is not None
    assert proposal.tool_name == "exchange_delivered_order_items"
    assert proposal.arguments == {
        "order_id": "#W2378156",
        "item_ids": ["1151293680", "4983901480"],
        "new_item_ids": ["7706410293", "7747408585"],
        "payment_method_id": "credit_card_9513926",
    }
    assert "exchange" in proposal.rationale


def test_rule_based_generator_exchanges_only_thermostat_when_keyboard_exact_match_is_required():
    generator = RuleBasedProposalGenerator()
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
                    '{"name":"Mechanical Keyboard","product_id":"1656367028","variants":{'
                    '"9025753381":{"item_id":"9025753381","options":{"switch type":"clicky","backlight":"RGB","size":"full size"},"available":false},'
                    '"7706410293":{"item_id":"7706410293","options":{"switch type":"clicky","backlight":"none","size":"full size"},"available":true}'
                    "}}"
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content=(
                    '{"name":"Smart Thermostat","product_id":"4896585277","variants":{'
                    '"7747408585":{"item_id":"7747408585","options":{"compatibility":"Google Assistant","color":"black"},"available":true},'
                    '"4983901480":{"item_id":"4983901480","options":{"compatibility":"Apple HomeKit","color":"black"},"available":true}'
                    "}}"
                ),
            ),
        ],
    )

    proposal = generator.generate(
        state,
        (
            "Please exchange the mechanical keyboard and smart thermostat from order #W2378156. "
            "If there is no keyboard that is clicky, RGB backlight, full size, "
            "I'd rather only exchange the thermostat."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "exchange_delivered_order_items"
    assert proposal.arguments == {
        "order_id": "#W2378156",
        "item_ids": ["4983901480"],
        "new_item_ids": ["7747408585"],
        "payment_method_id": "credit_card_9513926",
    }
    assert "exchange" in proposal.rationale


def test_rule_based_generator_proposes_tshirt_details_for_option_count_request():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        (
            "I want to know exactly how many tshirt options are available in the "
            "online store right now."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "get_product_details"
    assert proposal.arguments == {"product_id": "9523456873"}
    assert "T-Shirt" in proposal.rationale


def test_rule_based_generator_retrieves_user_details_after_named_product_lookup():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="yusuf_rossi_9620",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_product_details",
                content='{"name":"T-Shirt","product_id":"9523456873","variants":{}}',
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "I want to count tshirt options and return the cleaner, headphone, and smart watch.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_user_details"
    assert proposal.arguments == {"user_id": "yusuf_rossi_9620"}


def test_rule_based_generator_inspects_next_unchecked_order_for_return():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_user_details",
                content=(
                    '{"user_id":"yusuf_rossi_9620",'
                    '"orders":["#W6247578","#W9711842","#W2378156"]}'
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content='{"order_id":"#W6247578","status":"pending","items":[]}',
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "I want to return the cleaner, headphone, and smart watch.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W9711842"}


def test_rule_based_generator_fetches_user_details_for_pending_order_workflow():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="isabella_lopez_6490",
            )
        ],
    )

    proposal = generator.generate(
        state,
        "Change the payment method on my recent order to visa.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_user_details"
    assert proposal.arguments == {"user_id": "isabella_lopez_6490"}


def test_rule_based_generator_fetches_linked_user_details_for_chinese_order_query():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="ivan_santos_6635",
            )
        ],
    )

    proposal = generator.generate(state, "请查看我的订单")

    assert proposal is not None
    assert proposal.tool_name == "get_user_details"
    assert proposal.arguments == {"user_id": "ivan_santos_6635"}


def test_rule_based_generator_fetches_linked_user_details_for_all_orders_query():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="ivan_santos_6635",
            )
        ],
    )

    proposal = generator.generate(state, "查询所有订单")

    assert proposal is not None
    assert proposal.tool_name == "get_user_details"
    assert proposal.arguments == {"user_id": "ivan_santos_6635"}


def test_rule_based_generator_inspects_explicit_order_before_address_update():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="fatima_johnson_7581",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_user_details",
                content='{"orders":["#W5199551","#W8665881","#W9389413"]}',
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "Change #W8665881 to be delivered to Suite 641 instead.",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W8665881"}


def test_rule_based_generator_proposes_pending_order_address_update():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_name_zip",
                content="fatima_johnson_7581",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W8665881","user_id":"fatima_johnson_7581",'
                    '"status":"pending","address":'
                    '{"address1":"123 Elm Street","address2":"Suite 640",'
                    '"city":"Austin","state":"TX","country":"USA","zip":"78712"}}'
                ),
            )
        ],
    )

    proposal = generator.generate(
        state,
        "Change #W8665881 to be delivered to Suite 641 instead.",
    )

    assert proposal is not None
    assert proposal.tool_name == "modify_pending_order_address"
    assert proposal.arguments == {
        "order_id": "#W8665881",
        "address1": "123 Elm Street",
        "address2": "Suite 641",
        "city": "Austin",
        "state": "TX",
        "country": "USA",
        "zip": "78712",
    }


def test_rule_based_generator_proposes_pending_order_cancellation():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="daiki_sanchez_3253",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W9348897","user_id":"daiki_sanchez_3253",'
                    '"status":"pending","items":[]}'
                ),
            )
        ],
    )

    proposal = generator.generate(
        state,
        "If the alternatives do not work, just cancel the order so I can order again.",
    )

    assert proposal is not None
    assert proposal.tool_name == "cancel_pending_order"
    assert proposal.arguments == {
        "order_id": "#W9348897",
        "reason": "no longer needed",
    }


def test_rule_based_generator_proposes_pending_order_payment_update_by_brand():
    generator = RuleBasedProposalGenerator()
    state = CustomerAgentState(
        conversation_id="conv-1",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="find_user_id_by_email",
                content="isabella_lopez_6490",
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_user_details",
                content=(
                    '{"payment_methods":{'
                    '"credit_card_8897086":{"source":"credit_card","brand":"visa"},'
                    '"credit_card_8554680":{"source":"credit_card","brand":"mastercard"}},'
                    '"orders":["#W4923227"]}'
                ),
            ),
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W4923227","user_id":"isabella_lopez_6490",'
                    '"status":"pending",'
                    '"payment_history":[{"payment_method_id":"credit_card_8554680"}]}'
                ),
            ),
        ],
    )

    proposal = generator.generate(
        state,
        "For my recent order, change my payment method to visa.",
    )

    assert proposal is not None
    assert proposal.tool_name == "modify_pending_order_payment"
    assert proposal.arguments == {
        "order_id": "#W4923227",
        "payment_method_id": "credit_card_8897086",
    }


def test_rule_based_generator_rejects_cross_account_pending_order_writes():
    generator = RuleBasedProposalGenerator()
    base_messages = [
        ConversationMessage(
            role="tool",
            tool_name="find_user_id_by_email",
            content="alice_123",
        ),
        ConversationMessage(
            role="tool",
            tool_name="get_user_details",
            content=(
                '{"user_id":"alice_123","orders":["#W1111111"],'
                '"payment_methods":{"credit_card_alice":'
                '{"source":"credit_card","brand":"visa"}}}'
            ),
        ),
    ]
    order_message = ConversationMessage(
        role="tool",
        tool_name="get_order_details",
        content=(
            '{"order_id":"#W2222222","user_id":"bob_456","status":"pending",'
            '"address":{"address1":"1 Main St","address2":"Suite 1",'
            '"city":"Austin","state":"TX","country":"USA","zip":"78712"}}'
        ),
    )

    for user_message in (
        "Cancel #W2222222 because it is no longer needed.",
        "Change #W2222222 to be delivered to Suite 2.",
        "Change the payment method for #W2222222 to visa.",
    ):
        proposal = generator.generate(
            CustomerAgentState(
                conversation_id="conv-1",
                messages=[*base_messages, order_message],
            ),
            user_message,
        )
        assert proposal is None or proposal.tool_name not in {
            "cancel_pending_order",
            "modify_pending_order_address",
            "modify_pending_order_payment",
        }


def test_rule_based_generator_proposes_return_for_requested_delivered_items():
    generator = RuleBasedProposalGenerator()
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
                    '{"name":"Headphones","item_id":"4202497723"},'
                    '{"name":"Vacuum Cleaner","item_id":"4602305039"},'
                    '{"name":"Mechanical Keyboard","item_id":"1151293680"},'
                    '{"name":"Smart Thermostat","item_id":"4983901480"},'
                    '{"name":"Smart Watch","item_id":"9408160950"}'
                    "]}"
                ),
            )
        ],
    )

    proposal = generator.generate(
        state,
        "I want to return the cleaner, headphone, and smart watch from order #W2378156.",
    )

    assert proposal is not None
    assert proposal.tool_name == "return_delivered_order_items"
    assert proposal.arguments == {
        "order_id": "#W2378156",
        "item_ids": ["4602305039", "4202497723", "9408160950"],
        "payment_method_id": "credit_card_9513926",
    }
    assert "return" in proposal.rationale


def test_rule_based_generator_excludes_information_only_item_from_return():
    state = CustomerAgentState(
        conversation_id="conv-return-intent",
        messages=[
            ConversationMessage(
                role="tool",
                tool_name="get_order_details",
                content=(
                    '{"order_id":"#W9502127","status":"delivered",'
                    '"payment_history":[{"payment_method_id":"paypal_2433177"}],'
                    '"items":['
                    '{"name":"Vacuum Cleaner","item_id":"2872451762"},'
                    '{"name":"Air Purifier","item_id":"9534205511"}'
                    "]}"
                ),
            )
        ],
    )

    proposal = RuleBasedProposalGenerator().generate(
        state,
        (
            "Return the air purifier because it does not work. Also check whether I can "
            "return the vacuum cleaner, but I am not sure yet, so do not process it."
        ),
    )

    assert proposal is not None
    assert proposal.tool_name == "return_delivered_order_items"
    assert proposal.arguments["item_ids"] == ["9534205511"]


def test_planner_prompt_separates_mutation_targets_from_information_only_items():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)

    generator.decide(CustomerAgentState(conversation_id="conv-prompt"), "help")

    prompt = client.requests[0]["messages"][0]["content"]
    assert "information-only items" in prompt


def test_planner_prompt_defines_customer_facing_answer_quality_contract():
    prompt = _planner_system_prompt()

    assert "Simplified Chinese" in prompt
    assert "answer the customer's current question first" in prompt
    assert "Do not expose tool names" in prompt
    assert "customer-visible status labels" in prompt
    assert "one clear next step" in prompt
    assert "Do not list unrelated orders" in prompt
    assert "Never include an information-only item" in prompt


def test_planner_context_includes_runtime_objective_ledger_and_locked_order():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = initialize_objective_ledger(
        CustomerAgentState(conversation_id="conv-ledger"),
        "update address and backpack",
    )
    state = record_tool_execution(
        state,
        tool_name="modify_pending_order_address",
        arguments={"order_id": "#W5270061", "city": "Charlotte"},
        raw_content='{"order_id":"#W5270061"}',
        tool_type="write",
        error=False,
        fingerprint="address:abc",
    )

    generator.decide(state, "continue remaining work")

    system_prompt = client.requests[0]["messages"][0]["content"]
    user_context = client.requests[0]["messages"][1]["content"]
    ledger_line = next(
        line for line in user_context.splitlines() if line.startswith("OBJECTIVE_LEDGER: ")
    )
    ledger = __import__("json").loads(ledger_line.removeprefix("OBJECTIVE_LEDGER: "))
    assert ledger["original_objective"] == "update address and backpack"
    assert ledger["locked_order_id"] == "#W5270061"
    assert ledger["completed_writes"][0]["name"] == "modify_pending_order_address"
    assert "Do not inspect unrelated orders after locked_order_id is set" in system_prompt
    assert "When write_plan is empty" in system_prompt
    assert "work only on NEXT_WRITE_OBJECTIVE" in system_prompt


def test_planner_context_exposes_only_the_next_pending_write_objective():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = CustomerAgentState(conversation_id="conv-plan")
    state = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "write_plan": [
                        WriteObjective(
                            objective_id="done",
                            tool_name="cancel_pending_order",
                            order_id="#W1",
                            status="completed",
                            completed_fingerprint="cancel:1",
                        ),
                        WriteObjective(
                            objective_id="next",
                            tool_name="modify_pending_order_address",
                            order_id="#W2",
                            intent="move the shipment",
                        ),
                    ]
                }
            )
        }
    )

    generator.decide(state, "continue")

    context = client.requests[0]["messages"][1]["content"]
    next_line = next(
        line for line in context.splitlines() if line.startswith("NEXT_WRITE_OBJECTIVE: ")
    )
    assert __import__("json").loads(next_line.split(": ", 1)[1]) == {
        "objective_id": "next",
        "tool_name": "modify_pending_order_address",
        "order_id": "#W2",
        "intent": "move the shipment",
        "status": "pending",
        "completed_fingerprint": None,
    }


def test_planner_recovery_recommends_pending_plan_order_over_known_orders():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = CustomerAgentState(conversation_id="conv-plan-recovery")
    state = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "failed_order_ids": ["#W1111111"],
                    "known_order_ids": ["#W3333333"],
                    "write_plan": [
                        WriteObjective(
                            objective_id="next",
                            tool_name="modify_pending_order_address",
                            order_id="#W2222222",
                        )
                    ],
                }
            )
        }
    )

    generator.decide(state, "continue")

    context = client.requests[0]["messages"][1]["content"]
    recovery = _context_json_line(context, "ORDER_LOOKUP_RECOVERY")
    assert recovery == {
        "failed_order_ids": ["#W1111111"],
        "recommended_order_id": "#W2222222",
    }


def test_planner_recovery_uses_uninspected_nonfailed_known_order():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = CustomerAgentState(conversation_id="conv-known-recovery")
    state = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "failed_order_ids": ["#W1111111"],
                    "known_order_ids": ["#W1111111", "#W2222222", "#W3333333"],
                    "inspected_order_ids": ["#W2222222"],
                    "write_plan": [
                        WriteObjective(
                            objective_id="next",
                            tool_name="cancel_pending_order",
                        )
                    ],
                }
            )
        }
    )

    generator.decide(state, "continue")

    context = client.requests[0]["messages"][1]["content"]
    recovery = _context_json_line(context, "ORDER_LOOKUP_RECOVERY")
    assert recovery["recommended_order_id"] == "#W3333333"
    system_prompt = client.requests[0]["messages"][0]["content"]
    assert "Do not retry failed_order_ids" in system_prompt


def test_planner_recovery_has_no_recommendation_without_trusted_candidate():
    client = RecordingLLMClient('{"action":"final_response","message":"ok"}')
    generator = LLMProposalGenerator(model="test-model", client=client)
    state = CustomerAgentState(conversation_id="conv-no-recovery")
    state = state.model_copy(
        update={
            "objective_ledger": state.objective_ledger.model_copy(
                update={
                    "failed_order_ids": ["#W1111111"],
                    "known_order_ids": ["#W1111111", "#W2222222"],
                    "inspected_order_ids": ["#W2222222"],
                }
            )
        }
    )

    generator.decide(state, "continue")

    context = client.requests[0]["messages"][1]["content"]
    recovery = _context_json_line(context, "ORDER_LOOKUP_RECOVERY")
    assert recovery == {
        "failed_order_ids": ["#W1111111"],
        "recommended_order_id": None,
    }
    assert "expected_actions" not in context


def _context_json_line(context: str, label: str):
    line = next(
        item for item in context.splitlines() if item.startswith(f"{label}: ")
    )
    return __import__("json").loads(line.split(": ", 1)[1])


def test_rule_based_generator_returns_none_for_unrecognized_message():
    generator = RuleBasedProposalGenerator()

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "hello there",
    )

    assert proposal is None


def test_parse_tool_proposal_json_accepts_plain_json():
    proposal = parse_tool_proposal_json(
        '{"tool_name":"get_order_details","arguments":{"order_id":"#W2378156"},"rationale":"Need order details."}'
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}
    assert proposal.rationale == "Need order details."


def test_parse_planner_decision_json_accepts_tool_call_action():
    decision = parse_planner_decision_json(
        (
            '{"action":"tool_call","tool_name":"get_order_details",'
            '"arguments":{"order_id":"#W2378156"},'
            '"skill_id":"order_lookup","skill_action":"inspect_order",'
            '"rationale":"Need order details."}'
        )
    )

    assert decision == PlannerDecision(
        action="tool_call",
        skill_id="order_lookup",
        skill_action="inspect_order",
        tool_name="get_order_details",
        arguments={"order_id": "#W2378156"},
        rationale="Need order details.",
    )


def test_parse_planner_decision_json_accepts_final_response_action():
    decision = parse_planner_decision_json(
        '{"action":"final_response","message":"Your order has shipped.","rationale":"Enough context."}'
    )

    assert decision == PlannerDecision(
        action="final_response",
        message="Your order has shipped.",
        rationale="Enough context.",
    )


def test_parse_planner_decision_json_accepts_need_more_info_action():
    decision = parse_planner_decision_json(
        '{"action":"need_more_info","message":"Please provide your order id.","rationale":"Missing order id."}'
    )

    assert decision == PlannerDecision(
        action="need_more_info",
        message="Please provide your order id.",
        rationale="Missing order id.",
    )


def test_parse_planner_decision_json_returns_schema_error_for_invalid_action():
    decision = parse_planner_decision_json('{"action":"dance","message":"Nope."}')

    assert decision == PlannerDecision(
        action="invalid",
        error="Invalid planner action: dance",
    )


def test_parse_tool_proposal_json_accepts_fenced_json():
    proposal = parse_tool_proposal_json(
        '```json\n{"tool_name":"find_user_id_by_email","arguments":{"email":"a@example.com"},"rationale":"Lookup by email."}\n```'
    )

    assert proposal is not None
    assert proposal.tool_name == "find_user_id_by_email"


def test_parse_tool_proposal_json_returns_none_for_no_tool():
    proposal = parse_tool_proposal_json('{"tool_name":"","arguments":{},"rationale":"No action."}')

    assert proposal is None


def test_llm_proposal_generator_uses_client_response():
    client = FakeLLMClient(
        '{"tool_name":"get_order_details","arguments":{"order_id":"#W2378156"},"rationale":"Need order details."}'
    )
    generator = LLMProposalGenerator(model="fake-model", client=client)

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}
    assert client.calls[0]["model"] == "fake-model"
    assert "Please check order #W2378156" in client.calls[0]["messages"][-1]["content"]


def test_llm_proposal_generator_repairs_missing_write_plan_once():
    client = FakeLLMClient(
        [
            '{"action":"tool_call","tool_name":"get_order_details",'
            '"arguments":{"order_id":"#W1"}}',
            '{"action":"tool_call","tool_name":"cancel_pending_order",'
            '"arguments":{"order_id":"#W2","reason":"other"},"write_plan":['
            '{"objective_id":"cancel","tool_name":"cancel_pending_order",'
            '"order_id":"#W2","intent":"cancel the older order"},'
            '{"objective_id":"move","tool_name":"modify_pending_order_address",'
            '"order_id":"#W1","intent":"move the newer order"}]}',
        ]
    )
    generator = LLMProposalGenerator(
        model="fake-model",
        client=client,
        tool_catalog=[
            RetailToolDefinition(
                name="get_order_details",
                tool_type="read",
                description="",
                parameters_schema={},
            ),
            RetailToolDefinition(
                name="cancel_pending_order",
                tool_type="write",
                description="",
                parameters_schema={},
            ),
            RetailToolDefinition(
                name="modify_pending_order_address",
                tool_type="write",
                description="",
                parameters_schema={},
            ),
        ],
    )

    decision = generator.decide(
        CustomerAgentState(conversation_id="conv-plan-repair"),
        "Cancel #W2 and move #W1.",
    )

    assert len(client.calls) == 2
    assert decision.tool_name == "get_order_details"
    assert decision.arguments == {"order_id": "#W1"}
    assert decision.write_plan_provided is True
    assert [item["tool_name"] for item in decision.write_plan] == [
        "cancel_pending_order",
        "modify_pending_order_address",
    ]
    assert "omitted the required write_plan field" in client.calls[1]["messages"][1][
        "content"
    ]


def test_llm_proposal_generator_decide_returns_final_response_decision():
    generator = LLMProposalGenerator(
        model="fake-model",
        client=FakeLLMClient(
            '{"action":"final_response","message":"I can help with that.","rationale":"No tool needed."}'
        ),
    )

    decision = generator.decide(
        CustomerAgentState(conversation_id="conv-1"),
        "hello",
    )

    assert decision == PlannerDecision(
        action="final_response",
        message="I can help with that.",
        rationale="No tool needed.",
    )


def test_llm_proposal_generator_repairs_invalid_json_once():
    client = FakeLLMClient(
        [
            "I should check the order next.",
            '{"action":"tool_call","tool_name":"get_order_details",'
            '"arguments":{"order_id":"#W2378156"},"rationale":"Repair to valid JSON."}',
        ]
    )
    generator = LLMProposalGenerator(model="fake-model", client=client)

    proposal = generator.generate(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156",
    )

    assert proposal is not None
    assert proposal.tool_name == "get_order_details"
    assert proposal.arguments == {"order_id": "#W2378156"}
    assert len(client.calls) == 2
    assert client.calls[1]["messages"][0]["content"].startswith(
        "Repair the ecommerce planner decision JSON."
    )
    assert "I should check the order next." in client.calls[1]["messages"][1]["content"]


def test_llm_proposal_generator_decide_returns_error_after_failed_json_repair():
    generator = LLMProposalGenerator(model="fake-model", client=FakeLLMClient(["not json", "still not json"]))

    decision = generator.decide(
        CustomerAgentState(conversation_id="conv-1"),
        "Please check order #W2378156",
    )

    assert decision.action == "invalid"
    assert decision.error == "Planner output was not valid JSON"


class FakeLLMClient:
    def __init__(self, content: str | list[str]) -> None:
        self.contents = content if isinstance(content, list) else [content]
        self.calls = []

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        self.calls.append({"model": model, "messages": messages})
        index = min(len(self.calls) - 1, len(self.contents) - 1)
        return self.contents[index]
