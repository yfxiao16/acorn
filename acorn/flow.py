"""Flows: the agent-side orchestration strategy (the LEFT rail).

A Flow answers, at every step: which candidate actions does the
*application* want on the table (``A_agent``), and how is the model's
context maintained? The controller then intersects with the
contract-admissible set: ``A_eff = A_agent ∩ A_contract``.

Two built-ins:

* :class:`FreeFlow` — no developer-authored workflow; candidates are all
  registered tools every step (``A_eff = A_contract``).
* :class:`GraphFlow` — ACORN's native stateful flow: named states, each
  exposing a candidate toolset, with transition functions that may react
  to symbolic facts. Deliberately thin: GraphFlow organizes the *task*
  (phases, candidate surfaces); compliance logic belongs in the
  ContractLibrary, never in transition conditions.

Framework adapters (e.g. a LangGraph shim) are interop, not core — they
live under ``acorn.integrations`` when they exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from acorn.decisions import Decision, ProposedAction
from acorn.models.base import ModelTurn, ToolCall
from acorn.tools import ToolResult


@dataclass
class FlowContext:
    """Read-only view handed to flow transition functions.

    ``facts`` is the controller's FactStore (symbolic control state) —
    transitions may *react* to it but never own it."""

    facts: Any = None
    state: Any = None
    step: int = 0
    last_action: ProposedAction | None = None
    last_result: ToolResult | None = None


@runtime_checkable
class Flow(Protocol):
    def reset(self, task: str) -> None: ...

    def get_state(self) -> Any: ...

    def available_actions(self, all_actions: list[str]) -> list[str]: ...

    def build_context(self) -> list[dict]: ...

    def update_model_turn(self, turn: ModelTurn) -> None: ...

    def add_tool_result(self, call: ToolCall, content: str) -> None: ...

    def receive_control_feedback(self, call: ToolCall, decision: Decision) -> None: ...

    def notify_symbolic(self, action: ProposedAction, result: ToolResult, reason: str) -> None: ...

    def advance(self, ctx: FlowContext) -> None: ...

    def finished(self) -> bool: ...


class FreeFlow:
    """Default flow: message-list agent with no workflow of its own.

    ``state`` is arbitrary application state (never formalized by ACORN);
    it is stored as ``user_state`` so subclasses keep method names free.
    """

    def __init__(self, state: Any = None) -> None:
        self.user_state = state
        self.messages: list[dict] = []
        self._call_seq = 0

    def reset(self, task: str) -> None:
        self.messages = [{"role": "user", "content": task}]
        self._call_seq = 0

    def get_state(self) -> Any:
        return self.user_state

    def available_actions(self, all_actions: list[str]) -> list[str]:
        return list(all_actions)

    def build_context(self) -> list[dict]:
        return list(self.messages)

    def update_model_turn(self, turn: ModelTurn) -> None:
        calls = []
        for call in turn.tool_calls:
            if not call.id:
                self._call_seq += 1
                call.id = f"call_{self._call_seq}"
            calls.append({"id": call.id, "name": call.name, "args": call.args})
        self.messages.append({"role": "assistant", "content": turn.text, "tool_calls": calls})

    def add_tool_result(self, call: ToolCall, content: str) -> None:
        self.messages.append(
            {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": content}
        )

    def receive_control_feedback(self, call: ToolCall, decision: Decision) -> None:
        payload = {
            "ok": False,
            "blocked": True,
            "reason": decision.message(ProposedAction(call.name, call.args)),
        }
        self.add_tool_result(call, json.dumps(payload))

    def notify_symbolic(self, action: ProposedAction, result: ToolResult, reason: str) -> None:
        # Provider-safe: a plain user-role note (an orphan tool message
        # without a preceding assistant tool_call would be rejected).
        note = (
            f"[ACORN] Procedural step executed automatically ({reason}): "
            f"{action.tool}({json.dumps(action.args)}) -> "
            f"{json.dumps(result.payload(), default=str)}. Continue with the task."
        )
        self.messages.append({"role": "user", "content": note})

    def advance(self, ctx: FlowContext) -> None:  # no workflow: nothing to advance
        return

    def finished(self) -> bool:
        return False

    def nudge(self, text: str) -> None:
        """Inject a controller note into the conversation (user role)."""
        self.messages.append({"role": "user", "content": text})

    @property
    def requires_terminal(self) -> bool:
        """True when a text-only answer must NOT end the run unless the
        flow reached a terminal state (procedural completion gate)."""
        return False


@dataclass
class _StateSpec:
    tools: list[str]
    next: Callable[[FlowContext], str | None] | None = None
    terminal: bool = False


class GraphFlow(FreeFlow):
    """ACORN-native stateful flow: states expose candidate toolsets.

    Usage::

        flow = GraphFlow(start="triage")
        flow.state("triage", tools=["lookup_customer"],
                   next=lambda ctx: "work" if ctx.facts.truthy("customer_loaded") else None)
        flow.state("work", tools=[...],
                   next=lambda ctx: "done" if ctx.facts.truthy("result_submitted") else None)
        flow.state("done", tools=[], terminal=True)

    Transitions receive a :class:`FlowContext` and may read symbolic
    facts — the graph *reacts to* control state but never owns it.
    Compliance rules ("X requires Y") belong in the ContractLibrary,
    not in ``next``.
    """

    def __init__(self, start: str, state: Any = None) -> None:
        super().__init__(state=state)
        self.start = start
        self.current = start
        self._states: dict[str, _StateSpec] = {}

    def state(
        self,
        name: str,
        *,
        tools: list[str],
        next: Callable[[FlowContext], str | None] | None = None,
        terminal: bool = False,
    ) -> "GraphFlow":
        self._states[name] = _StateSpec(tools=list(tools), next=next, terminal=terminal)
        return self

    def _spec(self) -> _StateSpec:
        try:
            return self._states[self.current]
        except KeyError:
            raise ValueError(f"GraphFlow: unknown state {self.current!r}") from None

    def reset(self, task: str) -> None:
        super().reset(task)
        self.current = self.start

    def available_actions(self, all_actions: list[str]) -> list[str]:
        return [t for t in self._spec().tools if t in all_actions]

    def advance(self, ctx: FlowContext) -> None:
        spec = self._spec()
        if spec.next is None:
            return
        nxt = spec.next(ctx)
        if nxt is not None and nxt != self.current:
            if nxt not in self._states:
                raise ValueError(f"GraphFlow: transition to unknown state {nxt!r}")
            self.current = nxt

    def finished(self) -> bool:
        return self._spec().terminal

    @property
    def requires_terminal(self) -> bool:
        return any(spec.terminal for spec in self._states.values())
