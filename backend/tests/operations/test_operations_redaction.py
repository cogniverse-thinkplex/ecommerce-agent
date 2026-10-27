from app.operations.redaction import redact


def test_redaction_recurses_without_mutating_source():
    source = {
        "password": "CustomerPass@123",
        "nested": {"authorization": "Bearer abc.def", "email": "person@example.com"},
        "items": ["phone 13912345678", {"api_key": "sk-secret"}],
    }

    result = redact(source)

    assert result == {
        "password": "[REDACTED]",
        "nested": {"authorization": "[REDACTED]", "email": "p***@example.com"},
        "items": ["phone 139****5678", {"api_key": "[REDACTED]"}],
    }
    assert source["password"] == "CustomerPass@123"


def test_redaction_masks_tokens_embedded_in_free_text():
    text = "Authorization: Bearer secret-token contact buyer@example.com or 13800138000"
    result = redact(text)
    assert "secret-token" not in result
    assert "buyer@example.com" not in result
    assert "13800138000" not in result

