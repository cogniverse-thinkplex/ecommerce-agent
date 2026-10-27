from app.tools.tau_retail_adapter import TauRetailAdapter


def test_tau_retail_adapter_lists_tool_metadata():
    adapter = TauRetailAdapter.from_default_data()

    tools = {tool.name: tool for tool in adapter.list_tools()}

    assert tools["find_user_id_by_name_zip"].tool_type == "read"
    assert tools["exchange_delivered_order_items"].tool_type == "write"
    assert "You can only help one user per conversation" in adapter.policy


def test_tau_retail_adapter_executes_read_tool_and_parses_result():
    adapter = TauRetailAdapter.from_default_data()

    result = adapter.call_tool(
        "find_user_id_by_name_zip",
        {
            "first_name": "Yusuf",
            "last_name": "Rossi",
            "zip": "19122",
        },
        call_id="test-call-1",
    )

    assert result.call_id == "test-call-1"
    assert result.name == "find_user_id_by_name_zip"
    assert result.error is False
    assert result.content == "yusuf_rossi_9620"
    assert result.raw_content == "yusuf_rossi_9620"
