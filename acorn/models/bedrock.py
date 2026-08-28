"""AWS Bedrock Converse API adapter — pure stdlib (no boto3).

Implements SigV4 request signing with hmac/hashlib, so the harness's
zero-dependency property holds. Credentials from args or the standard
environment variables:

    AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
    AWS_SESSION_TOKEN   (optional, for temporary credentials)
    AWS_REGION          (default us-west-2)

Model ids are Bedrock model or inference-profile ids, e.g.
``anthropic.claude-3-5-sonnet-20241022-v2:0`` or
``us.anthropic.claude-opus-4-20250514-v1:0``.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from acorn.models.base import Model, ModelTurn, ToolCall

_SERVICE = "bedrock"


def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    k = _hmac(("AWS4" + secret).encode(), date_stamp)
    k = _hmac(k, region)
    k = _hmac(k, _SERVICE)
    return _hmac(k, "aws4_request")


_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _safe_id(value) -> str:
    v = _ID_RE.sub("_", str(value or ""))
    return v or "_"


def _nonempty(text) -> str:
    """Converse rejects empty text blocks ("text content blocks must be
    non-empty"); an empty turn is still a turn, so represent it explicitly."""
    text = "" if text is None else str(text)
    return text if text.strip() else "(empty)"


class BedrockModel(Model):
    def __init__(
        self,
        model: str,
        *,
        region: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        session_token: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.model = model
        self.region = region or os.environ.get("AWS_REGION", "us-west-2")
        self.access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")
        self.secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")
        self.session_token = session_token or os.environ.get("AWS_SESSION_TOKEN", "")
        self.max_tokens = max_tokens

    # -- neutral messages -> Converse messages ------------------------------
    @staticmethod
    def _to_messages(messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for msg in messages:
            role = msg["role"]
            if role == "user":
                out.append({"role": "user", "content": [{"text": _nonempty(msg["content"])}]})
            elif role == "assistant":
                blocks: list[dict] = []
                if msg.get("content"):
                    blocks.append({"text": msg["content"]})
                for c in msg.get("tool_calls", []):
                    # Converse validates toolUse.name/toolUseId against
                    # [a-zA-Z0-9_-]+ even in HISTORY; a hallucinated name the
                    # loop already rejected must not 400 every later turn.
                    blocks.append(
                        {"toolUse": {"toolUseId": _safe_id(c["id"]), "name": _safe_id(c["name"]),
                                     "input": c["args"]}}
                    )
                out.append({"role": "assistant", "content": blocks or [{"text": _nonempty("")}]})
            elif role == "tool":
                block = {
                    "toolResult": {
                        "toolUseId": _safe_id(msg["tool_call_id"]),
                        "content": [{"text": _nonempty(msg["content"])}],
                    }
                }
                if out and out[-1]["role"] == "user" and "toolResult" in out[-1]["content"][0]:
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    # -- SigV4 ----------------------------------------------------------------
    def _signed_request(self, path: str, body: bytes) -> urllib.request.Request:
        host = f"bedrock-runtime.{self.region}.amazonaws.com"
        now = datetime.datetime.now(datetime.timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(body).hexdigest()

        headers = {
            "content-type": "application/json",
            "host": host,
            "x-amz-date": amz_date,
        }
        if self.session_token:
            headers["x-amz-security-token"] = self.session_token
        signed_names = ";".join(sorted(headers))
        canonical_headers = "".join(f"{k}:{headers[k]}\n" for k in sorted(headers))
        # SigV4 canonical URI is DOUBLE-encoded for non-S3 services: the
        # request path already carries %-escapes (model ids contain ':'),
        # and the canonical form encodes those '%' signs again.
        canonical_path = urllib.parse.quote(path, safe="/")
        canonical_request = "\n".join(
            ["POST", canonical_path, "", canonical_headers, signed_names, payload_hash]
        )
        scope = f"{date_stamp}/{self.region}/{_SERVICE}/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode()).hexdigest(),
            ]
        )
        signature = hmac.new(
            _signing_key(self.secret_key, date_stamp, self.region),
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        headers["authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, "
            f"SignedHeaders={signed_names}, Signature={signature}"
        )
        return urllib.request.Request(
            f"https://{host}{path}", data=body, headers=headers, method="POST"
        )

    def _post(self, body: dict) -> dict:
        path = f"/model/{urllib.parse.quote(self.model, safe='')}/converse"
        data = json.dumps(body).encode()
        max_retries = int(os.environ.get("ACORN_MODEL_MAX_RETRIES", "6"))
        for attempt in range(max_retries):
            req = self._signed_request(path, data)
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                raw = e.read().decode()
                if e.code in (429, 500, 503) and attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise RuntimeError(f"Bedrock HTTP {e.code}: {raw[:300]}") from e
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < max_retries - 1:
                    time.sleep(min(60, 2 * 2**attempt))
                    continue
                raise
        raise RuntimeError("unreachable")

    @staticmethod
    def _parse_text_tool_calls(text: str) -> list[ToolCall]:
        calls: list[ToolCall] = []
        decoder = json.JSONDecoder()
        i, n = 0, len(text)
        while i < n:
            start = text.find("{", i)
            if start < 0:
                break
            try:
                obj, end = decoder.raw_decode(text, start)
            except ValueError:
                i = start + 1
                continue
            i = end
            if (
                isinstance(obj, dict)
                and isinstance(obj.get("name"), str)
                # Bedrock rejects toolUse names outside this charset; an
                # invalid name would poison every later request when echoed
                # back into the conversation.
                and __import__("re").fullmatch(r"[a-zA-Z0-9_-]+", obj["name"])
                and isinstance(obj.get("parameters", obj.get("arguments")), dict)
            ):
                args = obj.get("parameters") or obj.get("arguments") or {}
                calls.append(ToolCall(name=str(obj["name"]), args=dict(args), id=f"text_{len(calls)}"))
        return calls

    def generate(self, messages, tools, system=None) -> ModelTurn:
        body: dict = {
            "messages": self._to_messages(messages),
            "inferenceConfig": {"maxTokens": self.max_tokens},
        }
        if system:
            body["system"] = [{"text": system}]
        if tools:
            body["toolConfig"] = {
                "tools": [
                    {
                        "toolSpec": {
                            "name": t["name"],
                            "description": t.get("description", "") or t["name"],
                            "inputSchema": {"json": t.get("parameters", {"type": "object"})},
                        }
                    }
                    for t in tools
                ]
            }
        resp = self._post(body)
        content = resp.get("output", {}).get("message", {}).get("content", [])
        calls, text_parts = [], []
        for block in content:
            if "text" in block:
                text_parts.append(block["text"])
            elif "toolUse" in block:
                tu = block["toolUse"]
                calls.append(
                    ToolCall(name=tu.get("name", ""), args=dict(tu.get("input") or {}), id=tu.get("toolUseId", ""))
                )
        # Provider quirk (notably Llama on Converse): tool calls emitted as
        # JSON TEXT ({"type":"function","name":...,"parameters":{...}})
        # instead of native toolUse blocks. Parse them — the model clearly
        # intends a tool call; leaving it as text would drop the call.
        if not calls and text_parts:
            calls = self._parse_text_tool_calls(" ".join(text_parts))
            if calls:
                text_parts = []
        usage = resp.get("usage") or {}
        return ModelTurn(
            text=" ".join(text_parts).strip() or None,
            tool_calls=calls,
            raw=resp,
            usage={
                "prompt": usage.get("inputTokens", 0),
                "completion": usage.get("outputTokens", 0),
                "total": usage.get("totalTokens", 0),
            },
        )
