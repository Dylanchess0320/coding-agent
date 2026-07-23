"""Ollama local model client."""

from __future__ import annotations

import json

import httpx

from . import LLMClient, LLMResult


class OllamaClient(LLMClient):
    """Ollama local model client."""

    async def chat(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "stream": False,
        }
        if tools:
            body["tools"] = tools

        timeout = httpx.Timeout(connect=15.0, read=300.0, write=15.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self.config.base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()

        msg = data.get("message", {})
        return LLMResult(
            content=msg.get("content", "") or "",
            tool_calls=msg.get("tool_calls"),
            model=data.get("model", self.config.model),
            usage={"prompt_tokens": 0, "completion_tokens": 0},
            finish_reason=data.get("done_reason", ""),
        )

    async def chat_stream(self, messages, tools=None, on_token=None, on_think=None) -> LLMResult:
        body = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = tools

        result = LLMResult(model=self.config.model)
        content_buf = ""

        timeout = httpx.Timeout(connect=15.0, read=600.0, write=15.0, pool=5.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream(
                "POST",
                f"{self.config.base_url}/api/chat",
                json=body,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("done"):
                    break
                msg = chunk.get("message", {})
                content = msg.get("content", "")
                if content:
                    content_buf += content
                    if on_token:
                        on_token(content)

        result.content = content_buf
        return result
