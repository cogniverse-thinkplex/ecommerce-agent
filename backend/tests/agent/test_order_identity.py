import pytest

from app.agent.order_identity import canonicalize_retail_order_id


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("W8268610", "#W8268610"),
        ("#w8268610", "#W8268610"),
        ("  #W8268610  ", "#W8268610"),
        ("#W8268610", "#W8268610"),
    ],
)
def test_canonicalize_retail_order_id_accepts_supported_forms(value, expected):
    assert canonicalize_retail_order_id(value) == expected


@pytest.mark.parametrize(
    "value",
    ["8268610", "W82-68610", "", "   ", None, 8268610, {"order_id": "W8268610"}],
)
def test_canonicalize_retail_order_id_rejects_untrusted_shapes(value):
    assert canonicalize_retail_order_id(value) is None

