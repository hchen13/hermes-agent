"""Only the uncovered Chat Completions wire field is fork-owned."""

import pytest

from agent.transports.chat_completions import _finish_kwargs


@pytest.mark.parametrize("verbosity", ["low", "medium", "high"])
def test_gpt_chat_completions_sends_real_verbosity_field(verbosity):
    result = _finish_kwargs({"model": "gpt-5.6"}, [], {"text_verbosity": verbosity}, supports_prompt_cache_key=False)
    assert result["verbosity"] == verbosity
    assert "text_verbosity" not in result and "text" not in result


@pytest.mark.parametrize("model,verbosity", [("claude-sonnet", "high"), ("gpt-5.6-codex", "low"), ("gpt-5.6", None), ("gpt-5.6", "invalid")])
def test_unrelated_or_unconfigured_requests_do_not_gain_field(model, verbosity):
    result = _finish_kwargs({"model": model}, [], {"text_verbosity": verbosity}, supports_prompt_cache_key=False)
    assert "verbosity" not in result
