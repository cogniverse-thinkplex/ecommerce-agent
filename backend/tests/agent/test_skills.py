from app.agent.skills import default_skill_registry


def test_default_skill_registry_exposes_core_retail_skill_boundaries():
    registry = default_skill_registry()

    authentication = registry.get("authentication")
    order_lookup = registry.get("order_lookup")
    cancel_order = registry.get("cancel_order")
    modify_order_address = registry.get("modify_order_address")
    modify_order_payment = registry.get("modify_order_payment")

    assert authentication.id == "authentication"
    assert authentication.allowed_tools == [
        "find_user_id_by_name_zip",
        "find_user_id_by_email",
    ]
    assert authentication.actions == {
        "lookup_by_name_zip": "find_user_id_by_name_zip",
        "lookup_by_email": "find_user_id_by_email",
    }
    assert authentication.required_state == []
    assert authentication.requires_confirmation is False

    assert order_lookup.allowed_tools == ["get_user_details", "get_order_details"]
    assert order_lookup.actions == {
        "inspect_order_history": "get_user_details",
        "inspect_order": "get_order_details",
    }
    assert order_lookup.requires_confirmation is False

    assert cancel_order.allowed_tools == ["cancel_pending_order"]
    assert cancel_order.actions == {"cancel_pending_order": "cancel_pending_order"}
    assert cancel_order.requires_confirmation is True

    assert modify_order_address.allowed_tools == ["modify_pending_order_address"]
    assert modify_order_address.requires_confirmation is True
    assert modify_order_payment.allowed_tools == ["modify_pending_order_payment"]
    assert modify_order_payment.requires_confirmation is True


def test_skill_registry_resolves_skill_action_to_allowed_tool():
    registry = default_skill_registry()

    assert registry.resolve_tool("authentication", "lookup_by_name_zip") == (
        "find_user_id_by_name_zip"
    )
    assert registry.resolve_tool("authentication", "lookup_by_email") == (
        "find_user_id_by_email"
    )
    assert registry.resolve_tool("order_lookup", "inspect_order") == "get_order_details"
    assert registry.resolve_tool("order_lookup", "inspect_order_history") == (
        "get_user_details"
    )
    assert registry.resolve_tool("order_lookup", "cancel_pending_order") is None
