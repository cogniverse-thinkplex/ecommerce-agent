import json

from app.support.models import SupportMessageBlock
from app.support.streaming import SupportStreamEvent, encode_sse


def test_encode_sse_uses_monotonic_event_shape_and_json_data():
    event = SupportStreamEvent(
        event="progress",
        event_id=2,
        data={"stage": "planning", "message": "正在分析您的请求"},
    )

    encoded = encode_sse(event).decode("utf-8")

    assert encoded.startswith("id: 2\nevent: progress\n")
    assert encoded.endswith("\n\n")
    data_line = next(line for line in encoded.splitlines() if line.startswith("data: "))
    assert json.loads(data_line.removeprefix("data: ")) == event.data
    assert "policy" not in encoded.lower()


def test_stream_event_can_carry_customer_block_without_internal_fields():
    block = SupportMessageBlock(type="text", text="订单查询完成。")

    event = SupportStreamEvent(
        event="block",
        event_id=3,
        data={"index": 0, "block": block.model_dump(mode="json")},
    )

    payload = json.loads(
        next(
            line.removeprefix("data: ")
            for line in encode_sse(event).decode().splitlines()
            if line.startswith("data: ")
        )
    )
    assert payload["block"]["text"] == "订单查询完成。"
    assert "rationale" not in payload["block"]
