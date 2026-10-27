from app.agent.response_quality import inspect_customer_response


def _codes(text: str) -> set[str]:
    return {issue.code for issue in inspect_customer_response(text)}


def test_quality_inspector_accepts_grounded_customer_facing_answer():
    assert _codes("订单 #W1 当前为待处理。您希望继续查看详情还是取消订单？") == set()


def test_quality_inspector_detects_raw_errors_and_internal_tool_names():
    codes = _codes("Error: get_order_details raised RuntimeError")
    assert {"raw_error", "internal_tool_name"} <= codes


def test_quality_inspector_detects_untranslated_order_status():
    assert "untranslated_status" in _codes("订单 #W1 当前状态是 pending。请稍后查看。")


def test_quality_inspector_detects_answer_without_a_next_step():
    assert "missing_next_step" in _codes("订单 #W1 当前为待处理。")
