from app.services import llm


def test_litellm_adapter_without_optional_dependency_is_fail_closed():
    result = llm._generate_response(
        "Reply with exactly: OK",
        app_config={"llm_provider": "litellm"},
    )

    assert result.startswith("Error:")
    assert "uv sync --extra litellm" in result

