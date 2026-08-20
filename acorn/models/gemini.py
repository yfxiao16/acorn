"""Gemini REST adapter (no SDK dependency), ported from the ContrAgent
SOPBench live harness so ACORN's first benchmark runs are apples-to-apples
with the existing enforcement numbers.

Requires ``GEMINI_API_KEY``. Environment knobs (same names as the live
harness): GEMINI_HTTP_TIMEOUT, GEMINI_MAX_RETRIES, GEMINI_MAX_BACKOFF,
GEMINI_THINKING.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from acorn.models.base import Model, ModelTurn, ToolCall

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def _retry_delay_s(body: str) -> float | None:
    try:
        j = json.loads(body)
        for d in j.get("error", {}).get("details", []):
            if d.get("@type", "").endswith("RetryInfo"):
                return float(str(d.get("retryDelay", "")).rstrip("s"))
    except (ValueError, TypeError):
        pass
    return None


class GeminiModel(Model):
    def __init__(self, model: str = "gemini-2.5-flash", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.environ["GEMINI_API_KEY"]

    # -- neutral messages -> Gemini contents --------------------------------
    @staticmethod
    def _to_contents(messages: list[dict]) -> list[dict]:
        contents: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif role == "assistant":
                parts: list[dict] = []
                if msg.get("content"):
                    parts.append({"text": msg["content"]})
                for call in msg.get("tool_calls", []):
                    parts.append({"functionCall": {"name": call["name"], "args": call["args"]}})
                contents.append({"role": "model", "parts": parts or [{"text": ""}]})
            elif role == "tool":
                part = {
                    "functionResponse": {
                        "name": msg["name"],
                        "response": {"content": msg["content"]},
                    }
                }
                # Consecutive tool results merge into one user turn.
                if contents and contents[-1]["role"] == "user" and any(
                    "functionResponse" in p for p in contents[-1]["parts"]
                ):
                    contents[-1]["parts"].append(part)
                else:
                    contents.append({"role": "user", "parts": [part]})
        return contents

    def _post(self, body: dict) -> dict:
        url = API.format(model=self.model, key=self.api_key)
        data = json.dumps(body).encode()
        http_timeout = float(os.environ.get("GEMINI_HTTP_TIMEOUT", "120"))
        max_backoff = float(os.environ.get("GEMINI_MAX_BACKOFF", "60"))
        max_retries = int(os.environ.get("GEMINI_MAX_RETRIES", "10"))
        for attempt in range(max_retries):
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=http_timeout) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                if e.code in (429, 500, 503) and attempt < max_retries - 1:
                    delay = _retry_delay_s(raw) if e.code == 429 else None
                    if delay is None:
                        delay = 3 * 2**attempt
                    time.sleep(min(max_backoff, delay))
                    continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {raw[:300]}") from e
            except (urllib.error.URLError, TimeoutError):
                if attempt < max_retries - 1:
                    time.sleep(min(max_backoff, 3 * 2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")

    def generate(self, messages, tools, system=None) -> ModelTurn:
        body: dict = {
            "contents": self._to_contents(messages),
            "tool_config": {"function_calling_config": {"mode": "AUTO"}},
        }
        if tools:
            body["tools"] = [{"function_declarations": tools}]
        if system:
            body["system_instruction"] = {"parts": [{"text": system}]}
        think = os.environ.get("GEMINI_THINKING")
        if think is not None:
            body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": int(think)}}

        resp = self._post(body)
        um = resp.get("usageMetadata", {})
        usage = {
            "prompt": um.get("promptTokenCount", 0),
            "completion": um.get("candidatesTokenCount", 0),
            "total": um.get("totalTokenCount", 0),
        }
        cands = resp.get("candidates", [])
        parts = cands[0].get("content", {}).get("parts", []) if cands else []
        calls = [
            ToolCall(name=p["functionCall"].get("name", ""), args=dict(p["functionCall"].get("args") or {}))
            for p in parts
            if "functionCall" in p
        ]
        text = " ".join(p.get("text", "") for p in parts if "text" in p).strip() or None
        return ModelTurn(text=text, tool_calls=calls, raw=resp, usage=usage)
