"""OpenAI-compatible chat.completions adapter (no SDK dependency).

Covers OpenAI itself and every compatible endpoint (DeepSeek, Together,
vLLM / SGLang local servers, ...) via ``base_url``. API key comes from
``api_key`` or the ``api_key_env`` environment variable (default
``OPENAI_API_KEY``)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from acorn.models.base import Model, ModelTurn, ToolCall


class OpenAICompatModel(Model):
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get(api_key_env, "")
        self.temperature = temperature

    # -- neutral messages -> OpenAI messages --------------------------------
    @staticmethod
    def _to_messages(messages: list[dict], system: str | None) -> list[dict]:
        out: list[dict] = []
        if system:
            out.append({"role": "system", "content": system})
        for msg in messages:
            role = msg["role"]
            if role == "user":
                out.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                m: dict = {"role": "assistant", "content": msg.get("content")}
                calls = msg.get("tool_calls", [])
                if calls:
                    m["tool_calls"] = [
                        {
                            "id": c["id"],
                            "type": "function",
                            "function": {"name": c["name"], "arguments": json.dumps(c["args"])},
                        }
                        for c in calls
                    ]
                out.append(m)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": msg["tool_call_id"],
                        "content": msg["content"],
                    }
                )
        return out

    def _post(self, body: dict) -> dict:
        url = f"{self.base_url}/chat/completions"
        data = json.dumps(body).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        max_retries = int(os.environ.get("ACORN_MODEL_MAX_RETRIES", "6"))
        for attempt in range(max_retries):
            req = urllib.request.Request(url, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                if e.code in (429, 500, 502, 503) and attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise RuntimeError(f"OpenAI-compat HTTP {e.code}: {raw[:300]}") from e
            except (urllib.error.URLError, TimeoutError):
                if attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")

    def generate(self, messages, tools, system=None) -> ModelTurn:
        body: dict = {"model": self.model, "messages": self._to_messages(messages, system)}
        if tools:
            body["tools"] = [{"type": "function", "function": t} for t in tools]
        if self.temperature is not None:
            body["temperature"] = self.temperature
        resp = self._post(body)
        choice = (resp.get("choices") or [{}])[0]
        msg = choice.get("message", {})
        calls = []
        for c in msg.get("tool_calls") or []:
            fn = c.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append(ToolCall(name=fn.get("name", ""), args=args, id=c.get("id", "")))
        usage = resp.get("usage") or {}
        return ModelTurn(
            text=msg.get("content"),
            tool_calls=calls,
            raw=resp,
            usage={
                "prompt": usage.get("prompt_tokens", 0),
                "completion": usage.get("completion_tokens", 0),
                "total": usage.get("total_tokens", 0),
                # Prefix-cache hits: dynamic tool exposure changes the tools
                # block per step, which can invalidate provider prompt caches
                # — measured so the schema-savings vs cache-hits trade-off is
                # reportable (see RadixAttention discussion).
                "cached": (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0),
            },
        )
