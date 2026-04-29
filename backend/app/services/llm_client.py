import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.security import decrypt_secret


@dataclass(frozen=True)
class LLMCallResult:
    text: str
    token_input: int
    token_output: int
    estimated_cost: float
    latency_ms: int
    model_returned: str | None


class LLMClientError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def llm_live_enabled() -> bool:
    return get_settings().llm_mode == "live"


def completion_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def estimate_cost(profile: dict[str, Any], token_input: int, token_output: int) -> float:
    input_rate = float(profile.get("cost_per_1k_input_tokens") or 0)
    output_rate = float(profile.get("cost_per_1k_output_tokens") or 0)
    return round((token_input / 1000 * input_rate) + (token_output / 1000 * output_rate), 6)


def profile_api_key(profile: dict[str, Any]) -> str:
    encrypted = profile.get("api_key_encrypted")
    if not encrypted:
        raise LLMClientError("missing_api_key", "LLM profile API key is missing")
    try:
        return decrypt_secret(encrypted)
    except Exception as exc:
        raise LLMClientError("secret_decryption_failed", "Unable to decrypt LLM profile secret") from exc


def coerce_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return ""


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            cleaned = cleaned[start : end + 1]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMClientError("llm_invalid_plan_json", "LLM did not return valid chapter plan JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMClientError("llm_invalid_plan_json", "LLM did not return a chapter plan JSON object")
    return parsed


def chat_completion(
    profile: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int | None = None,
) -> LLMCallResult:
    if profile.get("provider_type") != "openai_compatible":
        raise LLMClientError("unsupported_provider", "Only OpenAI-compatible profiles are supported for live calls")

    token_limit = max_tokens
    profile_limit = profile.get("max_tokens_per_call")
    if profile_limit:
        token_limit = min(int(profile_limit), token_limit) if token_limit else int(profile_limit)

    payload: dict[str, Any] = {
        "model": profile["model"],
        "messages": messages,
        "temperature": temperature,
    }
    if token_limit:
        payload["max_tokens"] = token_limit

    headers = {
        "Authorization": f"Bearer {profile_api_key(profile)}",
        "Content-Type": "application/json",
    }

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=get_settings().llm_request_timeout_seconds) as client:
            response = client.post(completion_url(profile["base_url"]), headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise LLMClientError("llm_timeout", "LLM request timed out") from exc
    except httpx.RequestError as exc:
        raise LLMClientError("llm_connection_failed", "Could not reach LLM provider") from exc

    latency_ms = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise LLMClientError("llm_http_error", f"LLM provider returned HTTP {response.status_code}")

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMClientError("llm_invalid_json", "LLM provider returned invalid JSON") from exc

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMClientError("llm_empty_response", "LLM provider returned no choices")

    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    text = coerce_content(message.get("content") if isinstance(message, dict) else None).strip()
    if not text:
        raise LLMClientError("llm_empty_text", "LLM provider returned empty text")

    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    prompt_text = "\n".join(message.get("content", "") for message in messages)
    token_input = int(usage.get("prompt_tokens") or estimate_tokens(prompt_text))
    token_output = int(usage.get("completion_tokens") or estimate_tokens(text))

    return LLMCallResult(
        text=text,
        token_input=token_input,
        token_output=token_output,
        estimated_cost=estimate_cost(profile, token_input, token_output),
        latency_ms=latency_ms,
        model_returned=data.get("model") if isinstance(data.get("model"), str) else profile.get("model"),
    )


def test_llm_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if not llm_live_enabled():
        return {
            "success": True,
            "latency_ms": 0,
            "model_returned": profile.get("model"),
            "error_code": None,
            "error_message": None,
            "mode": "mock",
        }
    try:
        result = chat_completion(
            profile,
            [
                {"role": "system", "content": "Return a short plain-text health check response."},
                {"role": "user", "content": "Reply with exactly: ok"},
            ],
            temperature=0,
            max_tokens=8,
        )
        return {
            "success": True,
            "latency_ms": result.latency_ms,
            "model_returned": result.model_returned,
            "error_code": None,
            "error_message": None,
            "mode": "live",
        }
    except LLMClientError as exc:
        return {
            "success": False,
            "latency_ms": 0,
            "model_returned": None,
            "error_code": exc.code,
            "error_message": exc.message,
            "mode": "live",
        }
