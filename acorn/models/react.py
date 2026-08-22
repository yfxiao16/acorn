"""ReAct scaffold as a model wrapper (Yao et al., 2023).

Wraps any base ``Model`` and replaces native function calling with the
classic Thought/Action/Observation text protocol: tools are described in
the system prompt, the model emits ``Action: {"tool": ..., "args": ...}``
lines, and prior tool results are re-rendered as ``Observation:`` turns.
The harness sees an ordinary ``ModelTurn`` either way, so every condition
(baseline/passive/mask/acorn) composes with the scaffold unchanged.

The history translation keeps the transcript text-only, which also makes
the scaffold usable on providers whose API rejects tool-result blocks
without a native tool configuration (e.g. Bedrock Converse).
"""

from __future__ import annotations

import json
import re

from acorn.models.base import Model, ModelTurn, ToolCall

_INSTRUCTIONS = """
You solve tasks by reasoning step by step and calling tools.

Available tools:
{tools}

Use EXACTLY this format for every turn:

Thought: <your reasoning about what to do next>
Action: {{"tool": "<tool name>", "args": {{...}}}}

After each Action you will receive an Observation with the tool result.
When the task is complete and no more tool calls are needed, finish with:

Thought: <your final reasoning>
Final Answer: <your answer or closing message>
""".strip()

_ACTION_RE = re.compile(r"Action:\s*(\{.*)", re.S)
_FINAL_RE = re.compile(r"Final Answer:\s*(.*)", re.S)


def _tool_block(tools: list[dict]) -> str:
    lines = []
    for t in tools:
        params = t.get("parameters", {}).get("properties", {})
        lines.append(f"- {t['name']}({', '.join(params)}): {t.get('description', '')}")
    return "\n".join(lines)


def _parse_action(text: str) -> ToolCall | None:
    m = _ACTION_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1)
    # Take the first balanced JSON object.
    depth = 0
    for i, ch in enumerate(raw):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                raw = raw[: i + 1]
                break
    try:
        obj = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(obj, dict) or not obj.get("tool"):
        return None
    args = obj.get("args") or {}
    return ToolCall(str(obj["tool"]), args if isinstance(args, dict) else {})


class ReActModel(Model):
    """Text-scaffold ReAct wrapper around any base model."""

    def __init__(self, base: Model) -> None:
        self.base = base
        self.name = f"react:{getattr(base, 'name', base.__class__.__name__)}"

    def _translate(self, messages: list[dict]) -> list[dict]:
        out: list[dict] = []
        for msg in messages:
            role = msg.get("role")
            if role == "tool":
                out.append(
                    {"role": "user", "content": f"Observation: {msg.get('content', '')}"}
                )
            elif role == "assistant":
                calls = msg.get("tool_calls") or []
                if calls:
                    acts = "\n".join(
                        "Action: "
                        + json.dumps({"tool": c["name"], "args": c.get("args", {})})
                        for c in calls
                    )
                    text = (msg.get("content") or "").strip()
                    out.append(
                        {"role": "assistant", "content": (text + "\n" + acts).strip()}
                    )
                else:
                    out.append({"role": "assistant", "content": msg.get("content") or ""})
            else:
                out.append({"role": role, "content": msg.get("content") or ""})
        # Merge consecutive same-role messages (some providers require strict
        # alternation once tool structure is flattened to text).
        merged: list[dict] = []
        for m in out:
            if merged and merged[-1]["role"] == m["role"]:
                merged[-1]["content"] += "\n" + m["content"]
            else:
                merged.append(dict(m))
        return merged

    def generate(self, messages, tools, system=None) -> ModelTurn:
        scaffold = _INSTRUCTIONS.format(tools=_tool_block(tools or []))
        sys_prompt = f"{system}\n\n{scaffold}" if system else scaffold
        turn = self.base.generate(self._translate(list(messages)), [], system=sys_prompt)
        text = turn.text or ""
        call = _parse_action(text)
        if call is not None:
            return ModelTurn(text=None, tool_calls=[call], usage=turn.usage)
        m = _FINAL_RE.search(text)
        final = m.group(1).strip() if m else text.strip()
        return ModelTurn(text=final or "Done.", tool_calls=[], usage=turn.usage)
