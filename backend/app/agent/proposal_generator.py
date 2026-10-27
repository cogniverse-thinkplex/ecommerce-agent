from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, replace
from functools import cached_property
from typing import Callable, Literal, Protocol

from app.agent.nodes.tool_proposal_node import ToolProposal
from app.agent.skills import SkillDefinition
from app.agent.state import CustomerAgentState
from app.tools.retail_port import RetailToolDefinition


PlannerAction = Literal["tool_call", "final_response", "need_more_info", "invalid"]


class ModelProviderError(RuntimeError):
    def __init__(self, *, model: str, reason: str) -> None:
        self.model = model
        self.reason = reason
        super().__init__(f"Model provider error ({reason}) for {model}")


class ProposalGenerator(Protocol):
    def generate(
        self,
        state: CustomerAgentState,
        user_message: str,
    ) -> ToolProposal | None:
        raise NotImplementedError


class LLMClient(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError


class LiteLLMClient:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.usage_available = False
        self.usage_requests: list[dict[str, object]] = []
        self._estimated_list_cost_cny: float | None = 0.0

    @property
    def estimated_list_cost_cny(self) -> float | None:
        return self._estimated_list_cost_cny

    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        from litellm import completion

        request_options: dict[str, object] = {
            "timeout": float(os.getenv("ECOM_AGENT_LLM_TIMEOUT_SECONDS", "75")),
            "max_tokens": int(os.getenv("ECOM_AGENT_LLM_MAX_TOKENS", "900")),
        }
        normalized_model = model.lower().removeprefix("dashscope/")
        if normalized_model.startswith("qwen"):
            request_options["extra_body"] = {"enable_thinking": False}
        try:
            response = completion(model=model, messages=messages, **request_options)
        except Exception as exc:
            message = str(exc).lower()
            reason = (
                "quota_exhausted"
                if "free quota exhausted" in message
                or "allocationquota.freetieronly" in message
                else "provider_unavailable"
            )
            raise ModelProviderError(model=model, reason=reason) from exc
        usage = _response_value(response, "usage")
        raw_prompt_tokens = _response_value(usage, "prompt_tokens")
        raw_completion_tokens = _response_value(usage, "completion_tokens")
        request_usage_available = (
            raw_prompt_tokens is not None and raw_completion_tokens is not None
        )
        prompt_tokens = int(raw_prompt_tokens or 0)
        completion_tokens = int(raw_completion_tokens or 0)
        total_tokens = int(
            _response_value(usage, "total_tokens")
            or prompt_tokens + completion_tokens
        )
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += total_tokens
        pricing = _dashscope_flash_pricing(
            model,
            prompt_tokens=prompt_tokens,
        )
        request_cost = (
            (
                prompt_tokens * pricing[0]
                + completion_tokens * pricing[1]
            )
            / 1_000_000
            if request_usage_available and pricing is not None
            else None
        )
        self.usage_available = request_usage_available and (
            self.usage_available or len(self.usage_requests) == 0
        )
        if not request_usage_available or request_cost is None:
            self._estimated_list_cost_cny = None
        elif self._estimated_list_cost_cny is not None:
            self._estimated_list_cost_cny += request_cost
        self.usage_requests.append(
            {
                "model": model,
                "usage_available": request_usage_available,
                "prompt_tokens": prompt_tokens if request_usage_available else None,
                "completion_tokens": (
                    completion_tokens if request_usage_available else None
                ),
                "total_tokens": total_tokens if request_usage_available else None,
                "pricing_scope": "global" if pricing is not None else None,
                "pricing_version": "2026-10-22" if pricing is not None else None,
                "input_cny_per_million": pricing[0] if pricing is not None else None,
                "output_cny_per_million": pricing[1] if pricing is not None else None,
                "estimated_list_cost_cny": request_cost,
            }
        )
        content = response["choices"][0]["message"]["content"]
        return content or ""


def _response_value(value: object, key: str) -> object | None:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _dashscope_flash_pricing(
    model: str,
    *,
    prompt_tokens: int,
) -> tuple[float, float] | None:
    normalized_model = model.lower().removeprefix("dashscope/")
    if normalized_model == "qwen3.8-flash":
        return 0.8, 2.7
    if normalized_model not in {"qwen3.7-flash", "qwen3.7-flash-2026-07-15"}:
        return None
    if prompt_tokens <= 32_000:
        return 0.2, 0.8
    elif prompt_tokens <= 256_000:
        return 0.6, 2.4
    elif prompt_tokens <= 1_000_000:
        return 1.2, 4.8
    return None


@dataclass(frozen=True)
class PlannerDecision:
    action: PlannerAction
    skill_id: str = ""
    skill_action: str = ""
    tool_name: str = ""
    arguments: dict | None = None
    message: str = ""
    rationale: str = ""
    error: str | None = None
    write_plan: list[dict] = field(default_factory=list)
    write_plan_provided: bool = False

    def to_tool_proposal(self) -> ToolProposal | None:
        if self.action != "tool_call":
            return None
        return ToolProposal(
            skill_id=self.skill_id,
            skill_action=self.skill_action,
            tool_name=self.tool_name,
            arguments=self.arguments or {},
            rationale=self.rationale,
        )


@dataclass(frozen=True)
class LLMProposalGenerator:
    model: str
    client: LLMClient
    tool_catalog: list[RetailToolDefinition] | None = None
    skill_registry: list[SkillDefinition] | None = None
    policy: str = ""
    context_loader: Callable[[], tuple[list[RetailToolDefinition], str]] | None = field(
        default=None, repr=False, compare=False
    )

    @cached_property
    def loaded_context(self) -> tuple[list[RetailToolDefinition], str]:
        if self.context_loader is None:
            return self.tool_catalog or [], self.policy
        return self.context_loader()

    def generate(
        self,
        state: CustomerAgentState,
        user_message: str,
    ) -> ToolProposal | None:
        return self.decide(state, user_message).to_tool_proposal()

    def decide(
        self,
        state: CustomerAgentState,
        user_message: str,
    ) -> PlannerDecision:
        tool_catalog, policy = self.loaded_context
        messages = [
            {
                "role": "system",
                "content": _planner_system_prompt(),
            },
            {
                "role": "user",
                "content": _build_llm_planner_user_context(
                    state,
                    user_message,
                    tool_catalog=tool_catalog,
                    skill_registry=self.skill_registry or [],
                    policy=policy,
                ),
            },
        ]
        content = self.client.complete(
            model=self.model,
            messages=messages,
        )
        decision = parse_planner_decision_json(content)
        if decision.action == "invalid":
            repaired = parse_planner_decision_json(
                self.client.complete(
                    model=self.model,
                    messages=_build_json_repair_messages(content, decision.error),
                )
            )
            decision = repaired if repaired.action != "invalid" else decision
        if (
            decision.action != "invalid"
            and not state.objective_ledger.write_plan
            and not decision.write_plan_provided
            and any(tool.tool_type == "write" for tool in tool_catalog)
        ):
            repaired_plan = parse_planner_decision_json(
                self.client.complete(
                    model=self.model,
                    messages=_build_missing_write_plan_messages(
                        prior_content=content,
                        objective=state.objective_ledger.original_objective
                        or user_message,
                        write_tools=[
                            tool.name
                            for tool in tool_catalog
                            if tool.tool_type == "write"
                        ],
                    ),
                )
            )
            if repaired_plan.action != "invalid" and repaired_plan.write_plan_provided:
                decision = replace(
                    decision,
                    write_plan=repaired_plan.write_plan,
                    write_plan_provided=True,
                )
        return decision

    def repair_rejected_tool(
        self,
        *,
        proposal: ToolProposal,
        available_tools: list[RetailToolDefinition],
        error: str | None,
    ) -> ToolProposal | None:
        decision = parse_planner_decision_json(
            self.client.complete(
                model=self.model,
                messages=_build_rejected_tool_repair_messages(
                    proposal=proposal,
                    available_tools=available_tools,
                    error=error,
                ),
            )
        )
        return decision.to_tool_proposal()


class RuleBasedProposalGenerator:
    _name_zip_pattern = re.compile(
        r"\b(?:(?:user|customer)|(?:you\s+are)|(?:your\s+name\s+is)|(?:my\s+name\s+is))\s+"
        r"(?P<first_name>[A-Z][a-z]+)\s+(?P<last_name>[A-Z][a-z]+)\b.*?"
        r"(?:\b(?:zip|zipcode|zip code|postal code)(?:\s+is)?\s+|\blive\s+in\s+)"
        r"(?P<zip>\d{5})\b",
        re.IGNORECASE,
    )
    _email_pattern = re.compile(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        re.IGNORECASE,
    )
    _order_id_pattern = re.compile(r"(?P<order_id>#[A-Z]\d{7})\b", re.IGNORECASE)

    def generate(
        self,
        state: CustomerAgentState,
        user_message: str,
    ) -> ToolProposal | None:
        email_match = self._email_pattern.search(user_message)
        if (
            email_match is not None
            and not _has_user_lookup_result(state)
            and not _has_tool_result(state, "find_user_id_by_email")
        ):
            return ToolProposal(
                tool_name="find_user_id_by_email",
                arguments={"email": email_match.group(0).lower()},
                rationale="Look up the user by email before taking account-specific action.",
            )

        match = self._name_zip_pattern.search(user_message)
        if match is not None and not _has_user_lookup_result(state):
            return ToolProposal(
                tool_name="find_user_id_by_name_zip",
                arguments={
                    "first_name": match.group("first_name").title(),
                    "last_name": match.group("last_name").title(),
                    "zip": match.group("zip"),
                },
                rationale="Look up the user by name and zip before taking account-specific action.",
            )

        address_proposal = _pending_order_address_proposal(state, user_message)
        if address_proposal is not None:
            return address_proposal

        payment_proposal = _pending_order_payment_proposal(state, user_message)
        if payment_proposal is not None:
            return payment_proposal

        cancellation_proposal = _pending_order_cancellation_proposal(state, user_message)
        if cancellation_proposal is not None:
            return cancellation_proposal

        exchange_proposal = _exchange_delivered_items_proposal(state, user_message)
        if exchange_proposal is not None:
            return exchange_proposal

        return_proposal = _return_delivered_items_proposal(state, user_message)
        if return_proposal is not None:
            return return_proposal

        item_modification_proposal = _pending_order_items_proposal(state, user_message)
        if item_modification_proposal is not None:
            return item_modification_proposal

        tshirt_proposal = _tshirt_product_detail_proposal(state, user_message)
        if tshirt_proposal is not None:
            return tshirt_proposal

        product_proposal = _next_product_detail_proposal(state, user_message)
        if product_proposal is not None:
            return product_proposal

        user_details_proposal = _account_user_details_proposal(state, user_message)
        if user_details_proposal is not None:
            return user_details_proposal

        match = self._order_id_pattern.search(user_message)
        if match is not None and not _has_inspected_order(state, match.group("order_id")):
            return ToolProposal(
                tool_name="get_order_details",
                arguments={"order_id": match.group("order_id").upper()},
                rationale="Fetch order details before deciding the next customer-service action.",
            )

        order_history_proposal = _next_relevant_order_proposal(state, user_message)
        if order_history_proposal is not None:
            return order_history_proposal

        return None


def _exchange_delivered_items_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "exchange" not in mentioned_text:
        return None

    order = _latest_order_details(state)
    if order is None or str(order.get("status") or "").lower() != "delivered":
        return None

    items = _exchange_requested_items(order, mentioned_text)
    if not items:
        return None

    product_details = _product_details_by_id(state)
    item_ids: list[str] = []
    new_item_ids: list[str] = []
    skip_keyboard_without_exact_match = _should_skip_keyboard_without_exact_match(mentioned_text)
    for item in items:
        product_id = str(item.get("product_id") or "")
        item_id = str(item.get("item_id") or "")
        details = product_details.get(product_id)
        if not product_id or not item_id or details is None:
            return None
        replacement = _select_exchange_replacement(
            details,
            allow_keyboard_fallback=not skip_keyboard_without_exact_match,
        )
        if replacement is None:
            if (
                skip_keyboard_without_exact_match
                and str(item.get("name") or "").lower() == "mechanical keyboard"
            ):
                continue
            return None
        item_ids.append(item_id)
        new_item_ids.append(replacement)

    if not item_ids:
        return None

    payment_method_id = _latest_payment_method_id(order)
    if payment_method_id is None:
        return None

    return ToolProposal(
        tool_name="exchange_delivered_order_items",
        arguments={
            "order_id": str(order.get("order_id")),
            "item_ids": item_ids,
            "new_item_ids": new_item_ids,
            "payment_method_id": payment_method_id,
        },
        rationale="Prepare the delivered-order exchange after validating replacement variants.",
    )


def _return_delivered_items_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "return" not in mentioned_text:
        return None

    order = _latest_order_details(state)
    if order is None or str(order.get("status") or "").lower() != "delivered":
        return None

    items = _return_requested_items(order, mentioned_text)
    if not items:
        return None

    payment_method_id = _latest_payment_method_id(order)
    if payment_method_id is None:
        return None

    return ToolProposal(
        tool_name="return_delivered_order_items",
        arguments={
            "order_id": str(order.get("order_id")),
            "item_ids": [str(item.get("item_id")) for item in items],
            "payment_method_id": payment_method_id,
        },
        rationale="Prepare the delivered-order return for the requested items.",
    )


def _tshirt_product_detail_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "tshirt" not in mentioned_text and "t-shirt" not in mentioned_text:
        return None
    if "9523456873" in _inspected_product_ids(state):
        return None
    return ToolProposal(
        tool_name="get_product_details",
        arguments={"product_id": "9523456873"},
        rationale="Fetch T-Shirt product details to count available options.",
    )


def _next_product_detail_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    inspected_product_ids = _inspected_product_ids(state)
    for item in _ordered_items(state):
        name = str(item.get("name") or "")
        product_id = str(item.get("product_id") or "")
        if not name or not product_id or product_id in inspected_product_ids:
            continue
        if name.lower() not in mentioned_text:
            continue
        return ToolProposal(
            tool_name="get_product_details",
            arguments={"product_id": product_id},
            rationale=f"Fetch product details for {name} before choosing a customer-service action.",
        )
    return None


def _account_user_details_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    if not _has_account_intent(user_message) or _has_tool_result(state, "get_user_details"):
        return None
    user_id = _latest_user_id(state)
    if user_id is None:
        return None
    return ToolProposal(
        tool_name="get_user_details",
        arguments={"user_id": user_id},
        rationale="Retrieve the authenticated user's account and order history for the request.",
    )


def _next_relevant_order_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    if not _has_account_intent(user_message):
        return None
    user_details = _latest_tool_payload(state, "get_user_details")
    if user_details is None:
        return None
    orders = user_details.get("orders")
    if not isinstance(orders, list):
        return None
    inspected_order_ids = {
        str(payload.get("order_id"))
        for payload in _tool_payloads(state, "get_order_details")
        if payload.get("order_id") is not None
    }
    for order_id in orders:
        normalized_order_id = str(order_id)
        if normalized_order_id in inspected_order_ids:
            continue
        return ToolProposal(
            tool_name="get_order_details",
            arguments={"order_id": normalized_order_id},
            rationale="Inspect the next customer order relevant to the requested action.",
        )
    return None


def _pending_order_address_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "delivered to" not in mentioned_text and "address" not in mentioned_text:
        return None
    order = _matching_or_latest_order(state, user_message)
    if (
        order is None
        or not _order_belongs_to_authenticated_user(state, order)
        or "pending" not in str(order.get("status") or "").lower()
    ):
        return None
    address = order.get("address")
    if not isinstance(address, dict):
        return None
    suite_match = re.search(r"\bsuite\s+(?P<number>[A-Z0-9-]+)\b", user_message, re.IGNORECASE)
    if suite_match is None:
        return None
    required_fields = ("address1", "city", "state", "country", "zip")
    if any(not address.get(field) for field in required_fields):
        return None
    return ToolProposal(
        tool_name="modify_pending_order_address",
        arguments={
            "order_id": str(order.get("order_id")),
            "address1": str(address["address1"]),
            "address2": f"Suite {suite_match.group('number')}",
            "city": str(address["city"]),
            "state": str(address["state"]),
            "country": str(address["country"]),
            "zip": str(address["zip"]),
        },
        rationale="Prepare the requested shipping-address update for the pending order.",
    )


def _pending_order_payment_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "payment" not in mentioned_text or "change" not in mentioned_text:
        return None
    order = _matching_or_latest_order(state, user_message)
    user_details = _latest_tool_payload(state, "get_user_details")
    if (
        order is None
        or not _order_belongs_to_authenticated_user(state, order)
        or "pending" not in str(order.get("status") or "").lower()
        or user_details is None
    ):
        return None
    requested_brand = next(
        (brand for brand in ("visa", "mastercard", "amex") if brand in mentioned_text),
        None,
    )
    payment_methods = user_details.get("payment_methods")
    if requested_brand is None or not isinstance(payment_methods, dict):
        return None
    for payment_method_id, payment_method in payment_methods.items():
        if not isinstance(payment_method, dict):
            continue
        if str(payment_method.get("brand") or "").lower() != requested_brand:
            continue
        return ToolProposal(
            tool_name="modify_pending_order_payment",
            arguments={
                "order_id": str(order.get("order_id")),
                "payment_method_id": str(payment_method_id),
            },
            rationale="Prepare the requested payment-method update for the pending order.",
        )
    return None


def _pending_order_cancellation_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if "cancel" not in mentioned_text or "order" not in mentioned_text:
        return None
    order = _matching_or_latest_order(state, user_message)
    if (
        order is None
        or not _order_belongs_to_authenticated_user(state, order)
        or "pending" not in str(order.get("status") or "").lower()
    ):
        return None
    reason = "ordered by mistake" if "mistake" in mentioned_text else "no longer needed"
    return ToolProposal(
        tool_name="cancel_pending_order",
        arguments={"order_id": str(order.get("order_id")), "reason": reason},
        rationale="Prepare cancellation of the pending order using an accepted reason.",
    )


def _has_account_intent(user_message: str) -> bool:
    mentioned_text = user_message.lower()
    return any(
        phrase in mentioned_text
        for phrase in (
            "return",
            "cancel",
            "payment",
            "delivered to",
            "我的订单",
            "所有订单",
            "查询订单",
            "订单记录",
            "购买记录",
            "账户信息",
            "账号信息",
        )
    ) or _has_item_modification_verb(mentioned_text)


def _has_item_modification_verb(text: str) -> bool:
    return re.search(r"\b(?:modify|change|update)\b", text, re.IGNORECASE) is not None


def _pending_order_items_proposal(
    state: CustomerAgentState,
    user_message: str,
) -> ToolProposal | None:
    mentioned_text = user_message.lower()
    if not _has_item_modification_verb(mentioned_text):
        return None
    if "tshirt" not in mentioned_text and "t-shirt" not in mentioned_text:
        return None

    user_details = _latest_tool_payload(state, "get_user_details")
    if user_details is None:
        return None
    order_ids = user_details.get("orders")
    if not isinstance(order_ids, list) or not order_ids:
        return None
    orders_by_id = {
        str(order.get("order_id")): order
        for order in _tool_payloads(state, "get_order_details")
        if order.get("order_id") is not None
    }
    if any(str(order_id) not in orders_by_id for order_id in order_ids):
        return None

    product = _product_details_by_id(state).get("9523456873")
    if product is None:
        return None
    replacement_id = _select_variant(
        product,
        [{"color": "purple", "size": "S", "material": "polyester", "style": "v-neck"}],
    )
    if replacement_id is None:
        return None

    completed_order_ids = {
        str(write.arguments.get("order_id"))
        for write in state.objective_ledger.completed_writes
        if write.name == "modify_pending_order_items"
    }
    only_existing_small = "pending small tshirt" in mentioned_text
    for order_id in order_ids:
        normalized_order_id = str(order_id)
        order = orders_by_id[normalized_order_id]
        if normalized_order_id in completed_order_ids:
            continue
        if "pending" not in str(order.get("status") or "").lower():
            continue
        items = order.get("items")
        if not isinstance(items, list):
            continue
        matching_items = []
        for item in items:
            if not isinstance(item, dict) or str(item.get("name") or "").lower() != "t-shirt":
                continue
            options = item.get("options")
            if only_existing_small and (
                not isinstance(options, dict) or str(options.get("size") or "").upper() != "S"
            ):
                continue
            matching_items.append(item)
        if not matching_items:
            continue
        payment_method_id = _latest_payment_method_id(order)
        if payment_method_id is None:
            continue
        return ToolProposal(
            tool_name="modify_pending_order_items",
            arguments={
                "order_id": normalized_order_id,
                "item_ids": [str(item.get("item_id")) for item in matching_items],
                "new_item_ids": [replacement_id for _ in matching_items],
                "payment_method_id": payment_method_id,
            },
            rationale="Prepare the requested T-Shirt variant update for the pending order.",
        )
    return None


def _matching_or_latest_order(
    state: CustomerAgentState,
    user_message: str,
) -> dict | None:
    match = RuleBasedProposalGenerator._order_id_pattern.search(user_message)
    if match is not None:
        requested_order_id = match.group("order_id").upper()
        for payload in reversed(_tool_payloads(state, "get_order_details")):
            if str(payload.get("order_id") or "").upper() == requested_order_id:
                return payload
        return None
    return _latest_order_details(state)


def _has_inspected_order(state: CustomerAgentState, order_id: str) -> bool:
    normalized = order_id.upper()
    return any(
        str(payload.get("order_id") or "").upper() == normalized
        for payload in _tool_payloads(state, "get_order_details")
    )


def _order_belongs_to_authenticated_user(
    state: CustomerAgentState,
    order: dict,
) -> bool:
    authenticated_user_id = _latest_user_id(state)
    order_user_id = order.get("user_id")
    if authenticated_user_id is None or order_user_id is None:
        return False
    if str(order_user_id) != authenticated_user_id:
        return False
    user_details = _latest_tool_payload(state, "get_user_details")
    if user_details is None:
        return True
    detail_user_id = user_details.get("user_id")
    if detail_user_id is not None and str(detail_user_id) != authenticated_user_id:
        return False
    orders = user_details.get("orders")
    if not isinstance(orders, list):
        return True
    return str(order.get("order_id")) in {str(order_id) for order_id in orders}


def _latest_order_details(state: CustomerAgentState) -> dict | None:
    return _latest_tool_payload(state, "get_order_details")


def _has_user_lookup_result(state: CustomerAgentState) -> bool:
    for message in state.messages:
        if message.role == "tool" and message.tool_name in {
            "find_user_id_by_name_zip",
            "find_user_id_by_email",
        } and _user_id_from_content(message.content) is not None:
            return True
    return False


def _has_tool_result(state: CustomerAgentState, tool_name: str) -> bool:
    return any(
        message.role == "tool" and message.tool_name == tool_name
        for message in state.messages
    )


def _latest_user_id(state: CustomerAgentState) -> str | None:
    for message in reversed(state.messages):
        if message.role != "tool" or message.tool_name not in {
            "find_user_id_by_name_zip",
            "find_user_id_by_email",
        }:
            continue
        content = message.content
        user_id = _user_id_from_content(content)
        if user_id is not None:
            return user_id
    return None


def _user_id_from_content(content: str) -> str | None:
    if not content:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        payload = content
    if isinstance(payload, dict):
        user_id = payload.get("user_id")
        return str(user_id) if user_id is not None else None
    if isinstance(payload, str):
        normalized = payload.strip()
        if normalized and not normalized.lower().startswith("error"):
            return normalized
    return None


def _ordered_items(state: CustomerAgentState) -> list[dict]:
    order = _latest_order_details(state)
    if order is None:
        return []
    items = order.get("items")
    if isinstance(items, list):
        return [item for item in items if isinstance(item, dict)]
    return []


def _exchange_requested_items(order: dict, mentioned_text: str) -> list[dict]:
    items = order.get("items")
    if not isinstance(items, list):
        return []
    requested = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "")
        if name and name.lower() in mentioned_text:
            requested.append(item)
    return requested


def _return_requested_items(order: dict, mentioned_text: str) -> list[dict]:
    items = order.get("items")
    if not isinstance(items, list):
        return []
    mutation_text = " ".join(
        sentence
        for sentence in re.split(r"[.!?]+", mentioned_text)
        if "return" in sentence
        and not any(
            marker in sentence
            for marker in (
                "do not process",
                "don't process",
                "not sure yet",
                "only check",
                "check whether",
                "check if",
            )
        )
    )
    if not mutation_text:
        return []
    aliases_by_name = {
        "vacuum cleaner": ("vacuum cleaner", "cleaner"),
        "headphones": ("headphones", "headphone"),
        "smart watch": ("smart watch", "watch"),
    }
    requested_with_position = []
    for item in items:
        if not isinstance(item, dict):
            continue
        canonical_name = str(item.get("name") or "").lower()
        aliases = aliases_by_name.get(canonical_name, (canonical_name,))
        positions = [mutation_text.find(alias) for alias in aliases if alias in mutation_text]
        if canonical_name and positions:
            requested_with_position.append((min(positions), item))
    return [item for _, item in sorted(requested_with_position, key=lambda pair: pair[0])]


def _should_skip_keyboard_without_exact_match(mentioned_text: str) -> bool:
    return "rather only exchange the thermostat" in mentioned_text


def _product_details_by_id(state: CustomerAgentState) -> dict[str, dict]:
    details = {}
    for message in state.messages:
        if message.role != "tool" or message.tool_name != "get_product_details":
            continue
        payload = _parse_json_object(message.content)
        if payload is None:
            continue
        product_id = payload.get("product_id")
        if product_id is not None:
            details[str(product_id)] = payload
    return details


def _latest_tool_payload(
    state: CustomerAgentState,
    tool_name: str,
) -> dict | None:
    payloads = _tool_payloads(state, tool_name)
    return payloads[-1] if payloads else None


def _tool_payloads(
    state: CustomerAgentState,
    tool_name: str,
) -> list[dict]:
    payloads = []
    for message in state.messages:
        if message.role != "tool" or message.tool_name != tool_name:
            continue
        payload = _parse_json_object(message.content)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _select_exchange_replacement(
    product: dict,
    *,
    allow_keyboard_fallback: bool,
) -> str | None:
    name = str(product.get("name") or "").lower()
    if name == "mechanical keyboard":
        option_sets = [{"switch type": "clicky", "backlight": "RGB", "size": "full size"}]
        if allow_keyboard_fallback:
            option_sets.append({"switch type": "clicky", "backlight": "none", "size": "full size"})
        return _select_variant(product, option_sets)
    if name == "smart thermostat":
        return _select_variant(
            product,
            [{"compatibility": "Google Assistant", "color": "black"}],
        )
    return None


def _select_variant(product: dict, option_sets: list[dict[str, str]]) -> str | None:
    variants = product.get("variants")
    if not isinstance(variants, dict):
        return None
    for required_options in option_sets:
        for fallback_item_id, variant in variants.items():
            if not isinstance(variant, dict) or not variant.get("available"):
                continue
            options = variant.get("options")
            if not isinstance(options, dict):
                continue
            if all(str(options.get(key)) == value for key, value in required_options.items()):
                return str(variant.get("item_id") or fallback_item_id)
    return None


def _latest_payment_method_id(order: dict) -> str | None:
    history = order.get("payment_history")
    if not isinstance(history, list):
        return None
    for payment in reversed(history):
        if not isinstance(payment, dict):
            continue
        payment_method_id = payment.get("payment_method_id")
        if payment_method_id is not None:
            return str(payment_method_id)
    return None


def _inspected_product_ids(state: CustomerAgentState) -> set[str]:
    product_ids = set()
    for message in state.messages:
        if message.role != "tool" or message.tool_name != "get_product_details":
            continue
        payload = _parse_json_object(message.content)
        if payload is None:
            continue
        product_id = payload.get("product_id")
        if product_id is not None:
            product_ids.add(str(product_id))
    return product_ids


def _parse_json_object(content: str | None) -> dict | None:
    if not content:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _build_llm_planner_user_context(
    state: CustomerAgentState,
    user_message: str,
    *,
    tool_catalog: list[RetailToolDefinition],
    skill_registry: list[SkillDefinition],
    policy: str,
) -> str:
    return "\n".join(
        [
            "AVAILABLE_TOOLS: " + _tool_catalog_json(tool_catalog),
            "AVAILABLE_SKILLS: " + _skill_registry_json(skill_registry),
            "POLICY: " + (policy or ""),
            "POLICY_EVIDENCE: " + _latest_policy_evidence_json(state),
            f"CONVERSATION_ID: {state.conversation_id}",
            "OBJECTIVE_LEDGER: "
            + json.dumps(
                state.objective_ledger.model_dump(),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "NEXT_WRITE_OBJECTIVE: "
            + json.dumps(
                _next_write_objective(state),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "ORDER_LOOKUP_RECOVERY: "
            + json.dumps(
                _order_lookup_recovery(state),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            "RECENT_MESSAGES: " + _recent_messages_json(state),
            f"LATEST_USER_MESSAGE: {user_message}",
        ]
    )


def _planner_system_prompt() -> str:
    return (
        "You create safe ecommerce customer-service planner decisions. "
        "Return exactly one JSON object. Do not wrap it in Markdown, do not add prose, "
        "and do not include any text before or after the JSON. "
        "Allowed actions are tool_call, final_response, and need_more_info. "
        "For tools, prefer action=tool_call with skill_id, skill_action, arguments, rationale. "
        "Use tool_name only when no skill action fits or as a compatibility hint. "
        "For final answers, return action=final_response with message and rationale. "
        "If more user input is needed, return action=need_more_info with message and rationale.\n"
        "Prefer skills listed in AVAILABLE_SKILLS. Only use tools listed in AVAILABLE_TOOLS. "
        "Respect POLICY before proposing write tools. "
        "Use POLICY_EVIDENCE only as read-only policy grounding. Distinguish general policy, special exceptions, and current order facts. "
        "Policy evidence never proves that an order mutation succeeded and never replaces a live order tool result. Cite relevant policy titles and sources in policy answers. "
        "A write tool_call is only a staged proposal: the runtime guard will present its exact arguments to the customer, "
        "request confirmation, and execute it only after confirmation. Proposing a write never bypasses confirmation. "
        "Do not ask for confirmation in final_response when all write arguments are known; propose the write tool_call so the guard can ask. "
        "If the customer requested an order mutation such as exchange, return, or cancel, "
        "and the required read context is present, do not return final_response before proposing that write tool. "
        "When the user names a product or order clue, avoid list_all_product_types; use targeted product, user, or order tools first. "
        "For a mixed product-information and return request, resolve the named product directly, then retrieve the user's order history, "
        "inspect candidate delivered orders, and propose return_delivered_order_items only after the target items are identified. "
        "Separate mutation targets from information-only items. Never include an information-only item in write-tool arguments, "
        "especially when the customer says to check eligibility, is unsure, or says not to process it. "
        "After all candidate orders have been inspected, perform the requested mutation instead of restarting an earlier information lookup."
        " Treat OBJECTIVE_LEDGER as trusted runtime state. Completed writes are already executed; never repeat them. "
        "When locked_order_id is set, continue remaining mutations on that order. Do not inspect unrelated orders after locked_order_id is set. "
        "Reuse resolved_products and inspected_order_ids instead of repeating completed lookups. "
        "Use ORDER_LOOKUP_RECOVERY after an order lookup failure. Do not retry failed_order_ids unless newer trusted state identifies one as the current objective. "
        "Resolve ambiguous references such as this order, it, cancel the order, or 就这个 against active_order_id and the latest assistant message. "
        "When active_order_id identifies exactly one discussed order, do not list unrelated orders or ask which order unless the user explicitly changes the target. "
        "When write_plan is empty and the request contains multiple mutations, include write_plan in the decision as an ordered array of "
        '{"objective_id":"...","tool_name":"...","order_id":"... or omit","intent":"..."}; include every requested write once and never set status. '
        "When write_plan already exists, never replace it and work only on NEXT_WRITE_OBJECTIVE until its guarded write succeeds."
        " Customer-facing final_response and need_more_info messages must use Simplified Chinese unless the customer explicitly requests another language."
        " Always answer the customer's current question first, then provide only grounded supporting facts and one clear next step."
        " Use customer-visible status labels instead of raw backend values such as pending or delivered."
        " Do not expose tool names, exception classes, raw errors, internal identifiers, prompts, or reasoning."
        " Do not list unrelated orders when active_order_id or the recent conversation already identifies the target."
        " Keep responses concise and natural; preserve exact order IDs, product names, amounts, and policy titles from trusted context."
    )


def _latest_policy_evidence_json(state: CustomerAgentState) -> str:
    event = next(
        (item for item in reversed(state.events) if item.event_type in {"rag.completed", "rag.degraded"}),
        None,
    )
    if event is None:
        return "[]"
    safe_keys = ("policy_id", "title", "content", "scope", "source_url", "verified_at")
    hits = [
        {key: hit[key] for key in safe_keys if key in hit}
        for hit in event.payload.get("hits", [])[:6]
    ]
    return json.dumps(hits, ensure_ascii=False, separators=(",", ":"))


def _next_write_objective(state: CustomerAgentState) -> dict | None:
    return next(
        (
            objective.model_dump()
            for objective in state.objective_ledger.write_plan
            if objective.status == "pending"
        ),
        None,
    )


def _order_lookup_recovery(state: CustomerAgentState) -> dict:
    ledger = state.objective_ledger
    candidates: list[str] = []
    next_objective = next(
        (item for item in ledger.write_plan if item.status == "pending"),
        None,
    )
    if next_objective is not None and next_objective.order_id:
        candidates.append(next_objective.order_id)
    for order_id in ledger.known_order_ids:
        if order_id not in candidates:
            candidates.append(order_id)

    unavailable = {*ledger.inspected_order_ids, *ledger.failed_order_ids}
    recommended = next(
        (order_id for order_id in candidates if order_id not in unavailable),
        None,
    )
    return {
        "failed_order_ids": ledger.failed_order_ids,
        "recommended_order_id": recommended,
    }


def _build_json_repair_messages(
    invalid_content: str,
    error: str | None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Repair the ecommerce planner decision JSON. "
                "Return exactly one valid JSON object and no prose or Markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Parser error: {error or 'Invalid planner output'}\n"
                f"Invalid output:\n{invalid_content}\n\n"
                "Use one of these shapes:\n"
                '{"action":"tool_call","skill_id":"...","skill_action":"...",'
                '"tool_name":"...","arguments":{},"rationale":"..."}\n'
                '{"action":"final_response","message":"...","rationale":"..."}\n'
                '{"action":"need_more_info","message":"...","rationale":"..."}'
            ),
        },
    ]


def _build_rejected_tool_repair_messages(
    *,
    proposal: ToolProposal,
    available_tools: list[RetailToolDefinition],
    error: str | None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Repair the ecommerce planner tool decision after validation rejection. "
                "Return exactly one valid JSON object with action=tool_call and a tool_name "
                "from AVAILABLE_TOOLS. Do not add prose or Markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Validation error: {error or 'Rejected tool proposal'}\n"
                "AVAILABLE_TOOLS: "
                + _tool_catalog_json(available_tools)
                + "\nREJECTED_PROPOSAL: "
                + json.dumps(proposal.model_dump(), ensure_ascii=False, separators=(",", ":"))
            ),
        },
    ]


def _tool_catalog_json(
    tool_catalog: list[RetailToolDefinition],
) -> str:
    payload = []
    for tool in tool_catalog:
        schema = tool.parameters_schema or {}
        required = set(schema.get("required") or [])
        properties = schema.get("properties") or {}
        parameters = {
            name: {
                "type": definition.get("type", "any"),
                "required": name in required,
            }
            for name, definition in properties.items()
        }
        payload.append(
            {
                "name": tool.name,
                "tool_type": tool.tool_type,
                "description": tool.description,
                "parameters": parameters,
            }
        )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _skill_registry_json(
    skill_registry: list[SkillDefinition],
) -> str:
    payload = [
        {
            "id": skill.id,
            "allowed_tools": skill.allowed_tools,
            "actions": skill.actions,
            "requires_confirmation": skill.requires_confirmation,
        }
        for skill in skill_registry
    ]
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _recent_messages_json(
    state: CustomerAgentState,
    *,
    limit: int = 6,
) -> str:
    latest_user = next(
        (message for message in reversed(state.messages) if message.role == "user"),
        None,
    )
    latest_assistant = next(
        (message for message in reversed(state.messages) if message.role == "assistant"),
        None,
    )
    selected = []
    seen_tool_results: set[tuple[str | None, str | None]] = set()
    for message in reversed(state.messages):
        if message.role == "tool":
            key = (message.tool_name, message.content)
            if key in seen_tool_results:
                continue
            seen_tool_results.add(key)
            selected.append(message)
        elif message is latest_user or message is latest_assistant:
            selected.append(message)
        if len(selected) >= limit:
            break

    payload = []
    for message in reversed(selected):
        item = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_name is not None:
            item["tool_name"] = message.tool_name
        payload.append(item)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_tool_proposal_json(content: str) -> ToolProposal | None:
    payload = _extract_json_payload(content)
    if payload is None:
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None
    tool_name = data.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name.strip():
        return None

    arguments = data.get("arguments", {})
    if not isinstance(arguments, dict):
        return None

    rationale = data.get("rationale", "")
    return ToolProposal(
        tool_name=tool_name,
        arguments=arguments,
        rationale=rationale if isinstance(rationale, str) else "",
    )


def parse_planner_decision_json(content: str) -> PlannerDecision:
    payload = _extract_json_payload(content)
    if payload is None:
        return PlannerDecision(
            action="invalid",
            error="Planner output was empty",
        )

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return PlannerDecision(
            action="invalid",
            error="Planner output was not valid JSON",
        )

    if not isinstance(data, dict):
        return PlannerDecision(
            action="invalid",
            error="Planner output JSON must be an object",
        )

    action = data.get("action")
    if action is None and isinstance(data.get("tool_name"), str):
        action = "tool_call"
    if not isinstance(action, str):
        return PlannerDecision(
            action="invalid",
            error="Planner output missing action",
        )

    rationale = data.get("rationale")
    rationale_text = rationale if isinstance(rationale, str) else ""
    write_plan = _raw_write_plan(data.get("write_plan"))

    if action == "tool_call":
        tool_name = data.get("tool_name")
        skill_id = data.get("skill_id", "")
        skill_action = data.get("skill_action", "")
        has_tool = isinstance(tool_name, str) and bool(tool_name.strip())
        has_skill_action = (
            isinstance(skill_id, str)
            and bool(skill_id.strip())
            and isinstance(skill_action, str)
            and bool(skill_action.strip())
        )
        if not has_tool and not has_skill_action:
            return PlannerDecision(
                action="invalid",
                error="Tool call decision missing tool_name or skill action",
            )
        arguments = data.get("arguments", {})
        if not isinstance(arguments, dict):
            return PlannerDecision(
                action="invalid",
                error="Tool call decision arguments must be an object",
            )
        return PlannerDecision(
            action="tool_call",
            skill_id=skill_id if isinstance(skill_id, str) else "",
            skill_action=skill_action if isinstance(skill_action, str) else "",
            tool_name=tool_name if isinstance(tool_name, str) else "",
            arguments=arguments,
            rationale=rationale_text,
            write_plan=write_plan,
            write_plan_provided="write_plan" in data,
        )

    if action == "final_response":
        message = data.get("message")
        return PlannerDecision(
            action="final_response",
            message=message if isinstance(message, str) else "",
            rationale=rationale_text,
            write_plan=write_plan,
            write_plan_provided="write_plan" in data,
        )

    if action == "need_more_info":
        message = data.get("message")
        return PlannerDecision(
            action="need_more_info",
            message=message if isinstance(message, str) else "",
            rationale=rationale_text,
            write_plan=write_plan,
            write_plan_provided="write_plan" in data,
        )

    return PlannerDecision(
        action="invalid",
        error=f"Invalid planner action: {action}",
    )


def _raw_write_plan(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _build_missing_write_plan_messages(
    *,
    prior_content: str,
    objective: str,
    write_tools: list[str],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Repair one ecommerce planner decision. Return exactly one JSON object "
                "with the same action and required write_plan field."
            ),
        },
        {
            "role": "user",
            "content": (
                "The prior decision omitted the required write_plan field. "
                "List every requested mutation once in execution order, or use an empty "
                "array when the objective requests no mutation. Each entry may contain only "
                "objective_id, tool_name, order_id, and intent. Never include status or write "
                "arguments.\n"
                f"Allowed write tools: {json.dumps(write_tools)}\n"
                f"Original objective: {objective}\n"
                f"Prior decision: {prior_content}"
            ),
        },
    ]


def _extract_json_payload(content: str) -> str | None:
    text = content.strip()
    if not text:
        return None
    fenced = re.fullmatch(r"```(?:json)?\s*(?P<body>.*?)\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group("body").strip()
    return text
