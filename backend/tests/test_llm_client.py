import pytest

from app.services.llm_client import LLMClientError, completion_url, estimate_cost, parse_json_object


def test_completion_url_appends_chat_completions() -> None:
    assert completion_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"


def test_completion_url_accepts_full_endpoint() -> None:
    assert (
        completion_url("http://localhost:11434/v1/chat/completions")
        == "http://localhost:11434/v1/chat/completions"
    )


def test_parse_json_object_from_fenced_response() -> None:
    assert parse_json_object('```json\n{"title_hint":"A","cast_ids":[]}\n```')["title_hint"] == "A"


def test_parse_json_object_rejects_invalid_json() -> None:
    with pytest.raises(LLMClientError) as exc:
        parse_json_object("not json")
    assert exc.value.code == "llm_invalid_plan_json"


def test_estimate_cost() -> None:
    profile = {"cost_per_1k_input_tokens": 0.01, "cost_per_1k_output_tokens": 0.03}
    assert estimate_cost(profile, 1000, 2000) == 0.07
