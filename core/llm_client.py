"""
LLM client wrapper — extracted from agent.py.
Handles HTTP transport, streaming, retries, and provider routing.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx

from .context_manager import ContextManager


class LLMClient:
    """Handles LLM API calls with streaming, retry, and backoff.

    Extracted from agent.py's _call_llm, _call_llm_nonstreaming, and _post_with_retry.
    Uses ContextManager for message compaction.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 8192,
        timeout_sec: int = 120,
        max_retries: int = 3,
        base_delay: float = 1.0,
        context_manager: ContextManager | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_sec = timeout_sec
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retryable_codes = {429, 500, 502, 503, 504}
        self.context_manager = context_manager or ContextManager()

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream_callback: Callable[[str], None] | None = None,
        think_callback: Callable[[str], None] | None = None,
    ) -> dict | None:
        """Streaming LLM call. Returns the assembled assistant message."""
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        messages = await self.context_manager.compact(messages)
        payload = self._build_payload(messages, tools, stream=True)
        self._log_payload_size(payload)

        for attempt in range(self.max_retries + 1):
            try:
                return await self._try_stream(
                    payload, url, headers, attempt, stream_callback, think_callback
                )
            except httpx.HTTPStatusError as e:
                result = self._handle_http_error(e, attempt)
                if result is not None:
                    return result
            except (
                httpx.ReadError,
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
            ) as e:
                if attempt < self.max_retries:
                    delay = self.base_delay * (2**attempt)
                    print(
                        f"\n  [RETRY] {type(e).__name__}: {e} in {delay:.1f}s ({attempt + 2}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                else:
                    print(f"\n  [WARN] Streaming failed after {self.max_retries + 1} attempts")
                    return await self.chat_nonstreaming(
                        messages, tools, stream_callback, think_callback
                    )

        return await self.chat_nonstreaming(messages, tools, stream_callback, think_callback)

    def _build_payload(
        self, messages: list[dict], tools: list[dict] | None = None, stream: bool = True
    ) -> dict:
        """Build the API request payload."""
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "tools": tools or [],
            "tool_choice": "auto",
            "stream": stream,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if "pro" in self.model.lower() or "reasoner" in self.model.lower():
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "high"
        return payload

    @staticmethod
    def _log_payload_size(payload: dict):
        import os

        if not os.environ.get("CODING_AGENT_DEBUG"):
            return
        msg_bytes = sum(len(json.dumps(m, ensure_ascii=False)) for m in payload.get("messages", []))
        tools_bytes = sum(len(json.dumps(t, ensure_ascii=False)) for t in payload.get("tools", []))
        total_bytes = sum(
            len(json.dumps(v, ensure_ascii=False)) for v in payload.values() if v is not None
        )
        print(
            f"\n  [DBG] payload: msgs={msg_bytes:,}B  tools={tools_bytes:,}B  total={total_bytes:,}B"
        )

    async def _try_stream(
        self, payload, url, headers, attempt, stream_callback, think_callback
    ) -> dict | None:
        """Execute one streaming attempt."""
        timeout = httpx.Timeout(connect=30.0, read=self.timeout_sec, write=30.0, pool=30.0)
        async with (
            httpx.AsyncClient(timeout=timeout) as client,
            client.stream("POST", url, headers=headers, json=payload) as resp,
        ):
            if resp.status_code in self.retryable_codes and attempt < self.max_retries:
                delay = self.base_delay * (2**attempt)
                print(
                    f"\n  [RETRY] HTTP {resp.status_code} in {delay:.1f}s ({attempt + 2}/{self.max_retries + 1})"
                )
                await asyncio.sleep(delay)
                raise httpx.HTTPStatusError(
                    f"Retryable {resp.status_code}", request=resp.request, response=resp
                )
            if resp.status_code >= 400:
                await resp.aread()
            resp.raise_for_status()
            return await self._read_stream(resp, stream_callback, think_callback)

    async def _read_stream(self, resp, stream_callback, think_callback) -> dict | None:
        """Read and parse a streaming response, capturing usage."""
        content_chunks: list[str] = []
        reasoning_chunks: list[str] = []
        tool_calls_map: dict[int, dict] = {}
        usage: dict = {}
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue
            # Capture usage from any chunk (final chunk with include_usage)
            if chunk.get("usage"):
                usage = chunk["usage"]
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            think_token = delta.get("reasoning_content", "")
            if think_token:
                reasoning_chunks.append(think_token)
                if think_callback:
                    think_callback(think_token)
            token = delta.get("content", "")
            if token:
                content_chunks.append(token)
                if stream_callback:
                    stream_callback(token)
            for tc in delta.get("tool_calls", []):
                idx = tc.get("index", 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                if tc.get("id"):
                    tool_calls_map[idx]["id"] = tc["id"]
                func = tc.get("function", {})
                if "name" in func:
                    tool_calls_map[idx]["name"] += func["name"]
                if "arguments" in func:
                    tool_calls_map[idx]["arguments"] += func["arguments"]
        msg = self._assemble_message(content_chunks, reasoning_chunks, tool_calls_map)
        if usage:
            msg["_usage"] = usage
        return msg

    @staticmethod
    def _assemble_message(content_chunks, reasoning_chunks, tool_calls_map) -> dict:
        content = "".join(content_chunks)
        reasoning = "".join(reasoning_chunks)
        message: dict = {"role": "assistant", "content": content}
        if reasoning:
            message["reasoning_content"] = reasoning
        if tool_calls_map:
            message["tool_calls"] = []
            for idx in sorted(tool_calls_map.keys()):
                tc = tool_calls_map[idx]
                message["tool_calls"].append(
                    {
                        "id": tc["id"] or f"call_{idx}",
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                )
        return message

    def _handle_http_error(self, e: httpx.HTTPStatusError, attempt: int) -> dict | None:
        if e.response.status_code in self.retryable_codes and attempt < self.max_retries:
            delay = self.base_delay * (2**attempt)
            print(
                f"\n  [RETRY] HTTP {e.response.status_code} in {delay:.1f}s ({attempt + 2}/{self.max_retries + 1})"
            )
            return None
        try:
            err_text = e.response.text[:500]
        except Exception:
            err_text = "(unknown - response not read)"
        print(f"\n  [ERR] API Error ({e.response.status_code}): {err_text}")
        return {"role": "assistant", "content": f"[API Error: {e.response.status_code}]"}

    async def chat_nonstreaming(
        self, messages, tools=None, stream_callback=None, think_callback=None
    ) -> dict | None:
        """Non-streaming fallback"""
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        messages = await self.context_manager.compact(messages)
        payload = self._build_payload(messages, tools, stream=False)
        try:
            resp = await self._http_post(url, headers, payload)
            data = resp.json()
            choice = data.get("choices", [{}])[0]
            msg = choice.get("message", {})
            reasoning = msg.get("reasoning_content", "")
            if reasoning and think_callback:
                think_callback(reasoning)
            content = msg.get("content", "")
            if content and stream_callback:
                stream_callback(content)
            # Attach usage for cost tracking
            usage = data.get("usage", {})
            if usage:
                msg["_usage"] = usage
            return msg
        except Exception as e:
            print(f"\n  [ERR] Non-streaming fallback also failed: {e}")
            return None

    async def _http_post(self, url: str, headers: dict, payload: dict) -> httpx.Response:
        """HTTP POST with retry for non-streaming calls."""
        last_exc = None
        for attempt in range(self.max_retries + 1):
            try:
                timeout = httpx.Timeout(connect=30.0, read=self.timeout_sec, write=30.0, pool=30.0)
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    if resp.status_code in self.retryable_codes and attempt < self.max_retries:
                        delay = self.base_delay * (2**attempt)
                        print(
                            f"\n  [RETRY] HTTP {resp.status_code} in {delay:.1f}s ({attempt + 2}/{self.max_retries + 1})"
                        )
                        await asyncio.sleep(delay)
                        continue
                    resp.raise_for_status()
                    return resp
            except (
                httpx.RemoteProtocolError,
                httpx.ConnectError,
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
            ) as e:
                last_exc = e
                if attempt < self.max_retries:
                    delay = self.base_delay * (2**attempt)
                    print(
                        f"\n  [RETRY] Connection: {e} in {delay:.1f}s ({attempt + 2}/{self.max_retries + 1})"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
            except httpx.HTTPStatusError as e:
                if (
                    e.response.status_code not in self.retryable_codes
                    or attempt >= self.max_retries
                ):
                    print(
                        f"\n  [ERR] API Error ({e.response.status_code}): {e.response.text[:500]}"
                    )
                    raise
        if last_exc:
            raise last_exc
