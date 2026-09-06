from unittest.mock import Mock

from app.services import llm


def test_script_cleanup_is_non_greedy_between_multiple_groups(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_generate_response",
        lambda *args, **kwargs: "Inicio [nota uno] medio [nota dos] final (x) entre (y).",
    )

    result = llm.generate_script("astronomy")

    assert "medio" in result
    assert "entre" in result
    assert "nota uno" not in result
    assert "nota dos" not in result
    assert "(x)" not in result
    assert "(y)" not in result


def test_generate_script_does_not_log_retry_after_final_attempt(monkeypatch):
    monkeypatch.setattr(llm, "_generate_response", lambda *args, **kwargs: "")
    warning = Mock()
    monkeypatch.setattr(llm.logger, "warning", warning)

    llm.generate_script("astronomy")

    retry_messages = [
        str(call.args[0])
        for call in warning.call_args_list
        if call.args and "trying again" in str(call.args[0])
    ]
    assert len(retry_messages) == llm._max_retries - 1


def test_generate_terms_does_not_log_retry_after_final_attempt(monkeypatch):
    monkeypatch.setattr(llm, "_generate_response", lambda *args, **kwargs: "not-json")
    warning = Mock()
    monkeypatch.setattr(llm.logger, "warning", warning)

    assert llm.generate_terms("astronomy", "script", amount=3) == []

    retry_messages = [
        str(call.args[0])
        for call in warning.call_args_list
        if call.args and "trying again" in str(call.args[0])
    ]
    assert len(retry_messages) == llm._max_retries - 1
