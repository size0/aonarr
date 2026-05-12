"""统一 LLM 客户端 — 支持 OpenAI / Anthropic / Gemini 三种协议

所有业务代码只与 LLMClient 交互，无需关心底层协议差异。
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import httpx

from app.llm.profiles import LLMProfile

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BASE_DELAY = 8.0  # seconds

logger = logging.getLogger(__name__)


@dataclass
class GenerationConfig:
    model: str = ""
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    system: str = ""
    stop: list[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    content: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""


class LLMClient:
    """统一 LLM 客户端"""

    def __init__(self, profile: LLMProfile):
        self.profile = profile
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=30.0,
                read=float(profile.timeout_seconds),
                write=30.0,
                pool=30.0,
            )
        )

    @property
    def model(self) -> str:
        return self.profile.model

    @property
    def protocol(self) -> str:
        return self.profile.protocol

    async def generate(self, prompt: str, config: Optional[GenerationConfig] = None) -> GenerationResult:
        """同步生成（非流式），自带 429/5xx 指数退避重试"""
        cfg = config or GenerationConfig()
        model = cfg.model or self.profile.model
        temperature = self.profile.temperature if cfg.temperature is None else cfg.temperature
        max_tokens = self.profile.max_tokens if cfg.max_tokens is None else cfg.max_tokens

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                if self.protocol == "openai":
                    return await self._openai_generate(prompt, model, temperature, max_tokens, cfg.system)
                elif self.protocol == "anthropic":
                    return await self._anthropic_generate(prompt, model, temperature, max_tokens, cfg.system)
                elif self.protocol == "gemini":
                    return await self._gemini_generate(prompt, model, temperature, max_tokens, cfg.system)
                else:
                    raise ValueError(f"不支持的协议: {self.protocol}")
            except httpx.HTTPStatusError as e:
                last_exc = e
                if e.response.status_code not in _RETRYABLE_STATUS or attempt >= _MAX_RETRIES:
                    raise
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("[LLM] %d %s, retry %d/%d in %.0fs",
                               e.response.status_code, e.response.reason_phrase,
                               attempt + 1, _MAX_RETRIES, delay)
                await asyncio.sleep(delay)
            except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_exc = e
                if attempt >= _MAX_RETRIES:
                    raise
                delay = _BASE_DELAY * (2 ** attempt)
                logger.warning("[LLM] %s, retry %d/%d in %.0fs",
                               type(e).__name__, attempt + 1, _MAX_RETRIES, delay)
                await asyncio.sleep(delay)
        raise last_exc  # type: ignore[misc]

    async def stream_generate(self, prompt: str, config: Optional[GenerationConfig] = None) -> AsyncIterator[str]:
        """流式生成"""
        cfg = config or GenerationConfig()
        model = cfg.model or self.profile.model
        temperature = self.profile.temperature if cfg.temperature is None else cfg.temperature
        max_tokens = self.profile.max_tokens if cfg.max_tokens is None else cfg.max_tokens

        if self.protocol == "openai":
            async for chunk in self._openai_stream(prompt, model, temperature, max_tokens, cfg.system):
                yield chunk
        elif self.protocol == "anthropic":
            async for chunk in self._anthropic_stream(prompt, model, temperature, max_tokens, cfg.system):
                yield chunk
        else:
            # Gemini 不常用流式，降级为一次性返回
            result = await self.generate(prompt, config)
            yield result.content

    async def close(self):
        await self._http.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.close()

    def __del__(self):
        # 安全网：如果忘记 close，至少在 GC 时关闭底层传输
        if hasattr(self, "_http") and not self._http.is_closed:
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._http.aclose())
                else:
                    loop.run_until_complete(self._http.aclose())
            except Exception:
                pass

    # ── OpenAI Compatible ─────────────────────────────────────────

    async def _openai_generate(self, prompt: str, model: str, temperature: float,
                                max_tokens: int, system: str) -> GenerationResult:
        base = self.profile.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        resp = await self._http.post(
            url,
            json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            headers={"Authorization": f"Bearer {self.profile.api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        usage = data.get("usage", {})
        return GenerationResult(
            content=choice["message"]["content"],
            model=data.get("model", model),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            finish_reason=choice.get("finish_reason", ""),
        )

    async def _openai_stream(self, prompt: str, model: str, temperature: float,
                              max_tokens: int, system: str) -> AsyncIterator[str]:
        base = self.profile.base_url.rstrip("/")
        url = f"{base}/chat/completions"
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        async with self._http.stream(
            "POST", url,
            json={"model": model, "messages": messages, "temperature": temperature,
                  "max_tokens": max_tokens, "stream": True},
            headers={"Authorization": f"Bearer {self.profile.api_key}"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue

    # ── Anthropic Messages ────────────────────────────────────────

    async def _anthropic_generate(self, prompt: str, model: str, temperature: float,
                                   max_tokens: int, system: str) -> GenerationResult:
        base = self.profile.base_url.rstrip("/")
        url = f"{base}/v1/messages"
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        resp = await self._http.post(
            url, json=body,
            headers={
                "x-api-key": self.profile.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = "".join(block.get("text", "") for block in data.get("content", []))
        usage = data.get("usage", {})
        return GenerationResult(
            content=content,
            model=data.get("model", model),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            finish_reason=data.get("stop_reason", ""),
        )

    async def _anthropic_stream(self, prompt: str, model: str, temperature: float,
                                 max_tokens: int, system: str) -> AsyncIterator[str]:
        base = self.profile.base_url.rstrip("/")
        url = f"{base}/v1/messages"
        body = {
            "model": model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        if system:
            body["system"] = system

        async with self._http.stream(
            "POST", url, json=body,
            headers={
                "x-api-key": self.profile.api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                    if event.get("type") == "content_block_delta":
                        text = event.get("delta", {}).get("text", "")
                        if text:
                            yield text
                except (json.JSONDecodeError, KeyError):
                    continue

    # ── Gemini generateContent ────────────────────────────────────

    async def _gemini_generate(self, prompt: str, model: str, temperature: float,
                                max_tokens: int, system: str) -> GenerationResult:
        base = self.profile.base_url.rstrip("/")
        url = f"{base}/models/{model}:generateContent?key={self.profile.api_key}"
        contents = [{"parts": [{"text": prompt}]}]
        body = {
            "contents": contents,
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        resp = await self._http.post(url, json=body)
        resp.raise_for_status()
        data = resp.json()
        candidates = data.get("candidates", [{}])
        text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        usage = data.get("usageMetadata", {})
        return GenerationResult(
            content=text,
            model=model,
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            finish_reason=candidates[0].get("finishReason", "") if candidates else "",
        )


# ── 缓存工厂（避免重复创建 httpx 连接池）────────────────────────

_client_cache: dict[str, LLMClient] = {}


def create_llm_client(profile: LLMProfile) -> LLMClient:
    """工厂方法：按 profile.id 缓存，复用同一 httpx 连接池"""
    cached = _client_cache.get(profile.id)
    if cached and not cached._http.is_closed:
        # Profile 可能更新了 key/url，同步刷新
        cached.profile = profile
        return cached
    client = LLMClient(profile)
    _client_cache[profile.id] = client
    return client


async def close_all_clients():
    """关闭所有缓存的客户端（在 app shutdown 时调用）"""
    for client in _client_cache.values():
        try:
            await client.close()
        except Exception:
            pass
    _client_cache.clear()
