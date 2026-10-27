import json

from app.agent.response_composer import compose_tool_response
from app.agent.state import ConversationMessage


def _tool_message(tool_name: str, payload) -> ConversationMessage:
    content = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return ConversationMessage(role="tool", tool_name=tool_name, content=content)


def test_order_details_are_rendered_as_customer_facing_chinese_summary():
    response = compose_tool_response(
        _tool_message(
            "get_order_details",
            {
                "order_id": "#W8770097",
                "status": "pending",
                "items": [
                    {"name": "Office Chair", "price": 544.29, "options": {"color": "black"}}
                ],
                "payment_history": [{"transaction_type": "payment", "amount": 544.29}],
            },
        )
    )

    assert response == (
        "订单 #W8770097 当前为待处理，共 1 件商品：Office Chair（$544.29）。"
        "订单金额 $544.29。您可以继续查询物流、修改或取消该订单。"
    )


def test_user_details_summarize_order_ids_without_exposing_internal_fields():
    response = compose_tool_response(
        _tool_message(
            "get_user_details",
            {
                "user_id": "ivan_santos_6635",
                "name": {"first_name": "Ivan", "last_name": "Santos"},
                "email": "ivan@example.com",
                "orders": ["#W6893533", "#W8770097"],
            },
        )
    )

    assert response == "Ivan Santos 名下共有 2 个订单：#W6893533、#W8770097。您想查看哪个订单？"
    assert "user_id" not in response


def test_product_details_include_available_options_instead_of_only_a_count():
    response = compose_tool_response(
        _tool_message(
            "get_product_details",
            {
                "name": "Mechanical Keyboard",
                "variants": {
                    "one": {"available": True, "options": {"color": "black", "switch": "red"}},
                    "two": {"available": False, "options": {"color": "white", "switch": "blue"}},
                },
            },
        )
    )

    assert response == (
        "Mechanical Keyboard 当前有 1 个可选规格：color：black，switch：red。"
        "如需，我可以继续帮您确认该商品是否在您的订单中。"
    )


def test_identity_lookup_confirms_identity_without_exposing_internal_user_id():
    response = compose_tool_response(
        _tool_message("find_user_id_by_name_zip", "ivan_santos_6635")
    )

    assert response == "身份信息已确认。您可以继续查询订单或办理售后。"
    assert "ivan_santos_6635" not in response


def test_completed_write_uses_specific_action_and_chinese_status():
    response = compose_tool_response(
        _tool_message("cancel_pending_order", {"order_id": "#W8770097", "status": "cancelled"})
    )

    assert response == "订单 #W8770097 已成功取消，当前状态为已取消。退款进度请以原支付渠道为准。"


def test_raw_tool_error_is_replaced_with_recoverable_customer_message():
    response = compose_tool_response(
        _tool_message("get_order_details", "Error: RuntimeError: backend connection failed")
    )

    assert response == "暂时无法读取订单信息，请稍后重试；如果问题持续，可以转接人工客服。"
    assert "Error" not in response and "RuntimeError" not in response
