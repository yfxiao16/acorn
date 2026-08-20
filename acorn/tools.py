"""Tool registry and executor.

Registration and execution are separate; execution provides
pre/post hooks. The registry supports per-step dynamic exposure:
``registry.schemas(names)`` renders only the admissible subset.

``args_binder`` on a Tool is the jump-forward seam: a *deterministic*
function ``PredicateContext -> dict | None`` that binds the tool's
arguments from facts / agent state without semantic reasoning. When the
controller narrows the action space to exactly this tool and the binder
returns a dict, ACORN executes the call without a model decision.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable

from acorn.decisions import ProposedAction

_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    dict: "object",
    list: "array",
}


def _infer_parameters(fn: Callable) -> dict:
    """Minimal JSON-schema inference from the function signature."""
    props: dict[str, dict] = {}
    required: list[str] = []
    for name, param in inspect.signature(fn).parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        ann = param.annotation
        props[name] = {"type": _TYPE_MAP.get(ann, "string")}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    schema: dict[str, Any] = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict  # JSON schema
    fn: Callable
    args_binder: Callable | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @property
    def required_params(self) -> list[str]:
        return list(self.parameters.get("required", []))


@dataclass
class ToolResult:
    tool: str
    args: dict[str, Any]
    ok: bool
    output: Any = None
    error: str | None = None

    def payload(self) -> dict:
        """What the model sees as the function response."""
        if self.ok:
            return {"ok": True, "result": self.output}
        return {"ok": False, "error": self.error}


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def tool(
        self,
        fn: Callable | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict | None = None,
        args_binder: Callable | None = None,
        **metadata: Any,
    ):
        """Decorator: ``@registry.tool`` or ``@registry.tool(description=...)``."""

        def wrap(f: Callable) -> Callable:
            self.register(
                Tool(
                    name=name or f.__name__,
                    description=description or (f.__doc__ or "").strip(),
                    parameters=parameters or _infer_parameters(f),
                    fn=f,
                    args_binder=args_binder,
                    metadata=metadata,
                )
            )
            return f

        return wrap(fn) if fn is not None else wrap

    def get(self, name: str) -> Tool:
        return self._tools[name]

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools)

    def schemas(self, names: list[str] | None = None) -> list[dict]:
        """Schemas for the given subset (dynamic per-step tool exposure)."""
        picked = self._tools.values() if names is None else [self._tools[n] for n in names]
        return [t.schema() for t in picked]


class ToolExecutor:
    """Executes validated actions. Hooks run around every execution —
    including symbolically executed ones."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        pre_hooks: list[Callable[[ProposedAction], None]] | None = None,
        post_hooks: list[Callable[[ProposedAction, ToolResult], None]] | None = None,
    ) -> None:
        self.registry = registry
        self.pre_hooks = list(pre_hooks or [])
        self.post_hooks = list(post_hooks or [])

    def execute(self, action: ProposedAction) -> ToolResult:
        tool = self.registry.get(action.tool)
        for hook in self.pre_hooks:
            hook(action)
        try:
            output = tool.fn(**action.args)
            result = ToolResult(tool=action.tool, args=dict(action.args), ok=True, output=output)
        except Exception as exc:  # noqa: BLE001 — tool errors become observations
            result = ToolResult(
                tool=action.tool, args=dict(action.args), ok=False, error=f"{type(exc).__name__}: {exc}"
            )
        for hook in self.post_hooks:
            hook(action, result)
        return result
