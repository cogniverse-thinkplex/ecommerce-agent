from app.observability.redaction import sanitize_context


def test_sanitize_context_redacts_nested_secrets_and_personal_data():
    result = sanitize_context({
        "Authorization": "Bearer secret",
        "nested": [{"api_key": "sk-secret", "tool": "get_order_details"}],
        "email": "person@example.com",
        "arguments": {"free_text": "my private request"},
    })

    assert result["Authorization"] == "[REDACTED]"
    assert result["nested"][0]["api_key"] == "[REDACTED]"
    assert result["nested"][0]["tool"] == "get_order_details"
    assert result["email"] == "[REDACTED]"
    assert result["arguments"] == "[REDACTED]"


def test_sanitize_context_truncates_long_safe_strings():
    assert sanitize_context({"summary": "x" * 600})["summary"] == "x" * 500 + "…"


def test_sanitize_context_masks_sensitive_values_embedded_in_safe_fields():
    result = sanitize_context({
        "summary": "Bearer secret-token failed for buyer@example.com, phone 13800138000"
    })

    assert "secret-token" not in result["summary"]
    assert "buyer@example.com" not in result["summary"]
    assert "13800138000" not in result["summary"]
