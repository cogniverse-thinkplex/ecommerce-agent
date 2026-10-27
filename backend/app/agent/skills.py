from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    description: str
    allowed_tools: list[str]
    actions: dict[str, str] = field(default_factory=dict)
    required_state: list[str] = field(default_factory=list)
    requires_confirmation: bool = False


class SkillRegistry:
    def __init__(self, skills: list[SkillDefinition]) -> None:
        self._skills = {skill.id: skill for skill in skills}

    def get(self, skill_id: str) -> SkillDefinition:
        return self._skills[skill_id]

    def find(self, skill_id: str) -> SkillDefinition | None:
        return self._skills.get(skill_id)

    def list(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def resolve_tool(self, skill_id: str, skill_action: str) -> str | None:
        skill = self.find(skill_id)
        if skill is None:
            return None
        tool_name = skill.actions.get(skill_action)
        if tool_name not in skill.allowed_tools:
            return None
        return tool_name


def default_skill_registry() -> SkillRegistry:
    return SkillRegistry(
        [
            SkillDefinition(
                id="authentication",
                description="Identify and authenticate the customer.",
                allowed_tools=["find_user_id_by_name_zip", "find_user_id_by_email"],
                actions={
                    "lookup_by_name_zip": "find_user_id_by_name_zip",
                    "lookup_by_email": "find_user_id_by_email",
                },
            ),
            SkillDefinition(
                id="order_lookup",
                description=(
                    "Inspect the authenticated customer's order history, then inspect "
                    "individual order status, items, payment, and fulfillment details."
                ),
                allowed_tools=["get_user_details", "get_order_details"],
                actions={
                    "inspect_order_history": "get_user_details",
                    "inspect_order": "get_order_details",
                },
            ),
            SkillDefinition(
                id="cancel_order",
                description="Cancel a pending order after policy and user confirmation.",
                allowed_tools=["cancel_pending_order"],
                actions={"cancel_pending_order": "cancel_pending_order"},
                required_state=["authenticated_user", "active_order"],
                requires_confirmation=True,
            ),
            SkillDefinition(
                id="modify_order_address",
                description="Update the shipping address of a pending order after confirmation.",
                allowed_tools=["modify_pending_order_address"],
                actions={"modify_pending_order_address": "modify_pending_order_address"},
                required_state=["authenticated_user", "active_order"],
                requires_confirmation=True,
            ),
            SkillDefinition(
                id="modify_order_payment",
                description="Update the payment method of a pending order after confirmation.",
                allowed_tools=["modify_pending_order_payment"],
                actions={"modify_pending_order_payment": "modify_pending_order_payment"},
                required_state=["authenticated_user", "active_order"],
                requires_confirmation=True,
            ),
            SkillDefinition(
                id="return_order",
                description=(
                    "Return delivered order items after policy and user confirmation. "
                    "For mixed product-information and return requests, inspect named products "
                    "directly before retrieving the customer's order history; avoid catalog-wide discovery."
                ),
                allowed_tools=["return_delivered_order_items"],
                actions={"return_delivered_items": "return_delivered_order_items"},
                required_state=["authenticated_user", "active_order"],
                requires_confirmation=True,
            ),
            SkillDefinition(
                id="exchange_order",
                description="Exchange delivered order items after policy and user confirmation.",
                allowed_tools=["exchange_delivered_order_items"],
                actions={"exchange_delivered_items": "exchange_delivered_order_items"},
                required_state=["authenticated_user", "active_order"],
                requires_confirmation=True,
            ),
            SkillDefinition(
                id="product_info",
                description="Inspect product and variant details.",
                allowed_tools=["get_product_details"],
                actions={"inspect_product": "get_product_details"},
            ),
        ]
    )
