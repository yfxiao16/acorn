"""Provider-neutral model interface.

ACORN operates above the model-serving layer. Messages use a small
neutral format that adapters translate per provider:

    {"role": "user",      "content": str}
    {"role": "assistant", "content": str | None,
                          "tool_calls": [{"id": str, "name": str, "args": dict}]}
    {"role": "tool",      "tool_call_id": str, "name": str, "content": str}

Tool schemas are ``{"name", "description", "parameters"}`` dicts
(JSON-schema parameters), produced by ``ToolRegistry.schemas()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str = ""


@dataclass
class ModelTurn:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    usage: dict[str, int] = field(default_factory=dict)


@runtime_checkable
class Model(Protocol):
    def generate(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str | None = None,
    ) -> ModelTurn: ...
