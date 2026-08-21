"""Anthropic Messages API adapter (no SDK dependency).

API key from ``api_key`` or ``ANTHROPIC_API_KEY``."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from acorn.models.base import Model, ModelTurn, ToolCall

API = "https://api.anthropic.com/v1/messages"


class AnthropicModel(Model):
    def __init__(
        self,
        model: str = "claude-sonnet-5",
        *,
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.max_tokens = max_tokens

    # -- neutral messages -> Anthropic messages -----------------------------
    @staticmethod
    def _to_messages(messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                out.append({"role": "user", "content": msg["content"]})
            elif role == "assistant":
                blocks: list[dict] = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for c in msg.get("tool_calls", []):
                    blocks.append(
                        {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]}
                    )
                out.append({"role": "assistant", "content": blocks or [{"type": "text", "text": ""}]})
            elif role == "tool":
                block = {
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg["content"],
                }
                # Consecutive tool results merge into one user turn.
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def _post(self, body: dict) -> dict:
        data = json.dumps(body).encode()
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        max_retries = int(os.environ.get("ACORN_MODEL_MAX_RETRIES", "6"))
        for attempt in range(max_retries):
            req = urllib.request.Request(API, data=data, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                if e.code in (429, 500, 529) and attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise RuntimeError(f"Anthropic HTTP {e.code}: {raw[:300]}") from e
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")

    def generate(self, messages, tools, system=None) -> ModelTurn:
        body: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": self._to_messages(messages),
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object"}),
                }
                for t in tools
            ]
        resp = self._post(body)
        calls, text_parts = [], []
        for block in resp.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    ToolCall(name=block.get("name", ""), args=dict(block.get("input") or {}), id=block.get("id", ""))
                )
        usage = resp.get("usage") or {}
        return ModelTurn(
            text=" ".join(text_parts).strip() or None,
            tool_calls=calls,
            raw=resp,
            usage={
                "prompt": usage.get("input_tokens", 0),
                "completion": usage.get("output_tokens", 0),
                "total": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
            },
        )
