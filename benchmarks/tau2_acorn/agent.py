"""ACORN agent for tau2-bench (no-registry wiring).

tau2 drives the conversation turn-by-turn (its Orchestrator executes the
tools and the user simulator); ACORN lives inside
``generate_next_message``: the SymbolicController survives across turns
in the agent state, masks the tool schemas the model sees, validates
every outgoing tool call (with bounded in-turn retry on block), and can
emit procedurally determined calls without consulting the model.

Protocol notes (tau2 hard rules):
* an AssistantMessage carries text XOR tool_calls, never both — enforced
  here structurally (tau2's most common baseline violation);
* tools are never executed by the agent — ToolCalls go out, ToolMessages
  come back next turn and are committed into the controller then.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from tau2.agent.base_agent import HalfDuplexAgent
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)

from acorn.control import SymbolicController
from acorn.decisions import DecisionKind, ProposedAction, StepKind
from acorn.tools import ToolResult


class AcornState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    neutral: list = []  # our provider-neutral message list
    controller: Any = None
    pending: dict = {}  # tool_call id -> (name, args)


def _schema_of(tool) -> dict:
    s = tool.openai_schema
    if isinstance(s, dict) and s.get("type") == "function":
        s = s["function"]
    return {
        "name": s.get("name", getattr(tool, "name", "")),
        "description": s.get("description", "") or "",
        "parameters": s.get("parameters", {"type": "object"}),
    }


class AcornTau2Agent(HalfDuplexAgent[AcornState]):
    def __init__(
        self,
        tools: list,
        domain_policy: str,
        *,
        model,
        library=None,
        predicate_evaluator=None,
        control_mode: str = "full",
        probe_cache=None,
        max_block_retries: int = 3,
    ) -> None:
        super().__init__(tools=tools, domain_policy=domain_policy)
        # Prompt parity with tau2's official LLMAgent: the same
        # <instructions> preamble + <policy> wrapper. Passing the bare
        # policy text measurably degrades the agent (generic-assistant
        # behavior: hallucinated ids, return-instead-of-exchange).
        from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT

        self._system_prompt = SYSTEM_PROMPT.format(
            agent_instruction=AGENT_INSTRUCTION, domain_policy=domain_policy
        )
        self.model = model
        self.library = library
        self.predicate_evaluator = predicate_evaluator
        self.control_mode = control_mode
        self.probe_cache = probe_cache
        self.max_block_retries = max_block_retries
        self.model_calls = 0
        self.model_tokens = 0
        self.symbolic_emits = 0
        self.schemas = [_schema_of(t) for t in tools]
        self.tool_names = [s["name"] for s in self.schemas]

    # -- tau2 protocol -------------------------------------------------------
    def get_init_state(self, message_history: Optional[list[Message]] = None) -> AcornState:
        cc = self.library.compiled if self.library is not None else []
        controller = SymbolicController(
            cc,
            predicate_evaluator=self.predicate_evaluator,
            control_mode=self.control_mode,
            probe_cache=self.probe_cache,
        )
        self.last_controller = controller  # exposed for post-sim compliance readout
        return AcornState(neutral=[], controller=controller, pending={})

    def set_seed(self, seed: int) -> None:  # determinism handled upstream
        return

    def generate_next_message(self, message, state: AcornState):
        self._ingest(message, state)
        controller: SymbolicController = state.controller

        decision = controller.next_decision(self.tool_names)
        if decision.kind is StepKind.SYMBOLIC_EXECUTE:
            action = decision.action
            verdict = controller.validate(action)
            if verdict.allowed:
                self.symbolic_emits += 1
                return self._emit_calls([action], state), state
            # fall through to neural if the symbolic pick failed validation

        exposed = decision.actions if decision.kind is StepKind.NEURAL_CHOICE else self.tool_names
        schemas = [s for s in self.schemas if s["name"] in exposed] or self.schemas

        for _attempt in range(self.max_block_retries + 1):
            turn = self.model.generate(list(state.neutral), tools=schemas, system=self._system_prompt)
            self.model_calls += 1
            self.model_tokens += turn.usage.get("total", 0)
            if not turn.tool_calls:
                # Floor-yield gate: no text turn (a potential episode end)
                # while eventually-obligations are pending.
                pending = controller.obligations.due_eventually()
                if pending:
                    from acorn.facts import PredicateContext as _PC

                    ob = pending[0]
                    args = controller.obligations.resolve_args(ob, _PC(controller.facts, None))
                    if args is not None and self.control_mode == "full":
                        action = ProposedAction(ob.tool, args)
                        if controller.validate(action).allowed:
                            return self._emit_calls([action], state), state
                    state.neutral.append(
                        {"role": "user", "content": f"[ACORN] Before finishing: {ob.desc}. Do it now."}
                    )
                    continue
                text = (turn.text or "").strip() or "Understood."
                state.neutral.append({"role": "assistant", "content": text, "tool_calls": []})
                return AssistantMessage(role="assistant", content=text), state

            # Protocol: tool_calls only (any stray text is dropped — text XOR calls).
            actions, blocked_msgs = [], []
            for call in turn.tool_calls:
                action = ProposedAction(call.name, dict(call.args or {}))
                verdict = controller.validate(action)
                if verdict.kind is DecisionKind.ALLOW and call.name in self.tool_names:
                    actions.append(action)
                else:
                    blocked_msgs.append(verdict.message(action))
            if actions:
                return self._emit_calls(actions, state), state
            # Everything blocked: feed the reasons back and retry within the turn.
            state.neutral.append(
                {"role": "user", "content": "[ACORN] " + " ".join(blocked_msgs[:2])}
            )
        text = "I cannot perform that action under the current policy."
        state.neutral.append({"role": "assistant", "content": text, "tool_calls": []})
        return AssistantMessage(role="assistant", content=text), state

    # -- internals -----------------------------------------------------------
    def _ingest(self, message, state: AcornState) -> None:
        if isinstance(message, MultiToolMessage):
            for tm in message.tool_messages:
                self._ingest_tool(tm, state)
        elif isinstance(message, ToolMessage):
            self._ingest_tool(message, state)
        elif isinstance(message, UserMessage):
            state.neutral.append({"role": "user", "content": message.content or ""})

    def _ingest_tool(self, tm: ToolMessage, state: AcornState) -> None:
        name, args = state.pending.pop(tm.id, (tm.id, {}))
        try:
            output = json.loads(tm.content) if tm.content else None
        except (ValueError, TypeError):
            output = tm.content
        result = ToolResult(tool=name, args=args, ok=not tm.error, output=output, error=tm.content if tm.error else None)
        state.controller.update(ProposedAction(name, args), result)
        state.neutral.append(
            {"role": "tool", "tool_call_id": tm.id, "name": name, "content": tm.content or ""}
        )

    def _emit_calls(self, actions: list[ProposedAction], state: AcornState) -> AssistantMessage:
        calls = []
        for action in actions:
            cid = f"acorn_{uuid.uuid4().hex[:8]}"
            state.pending[cid] = (action.tool, action.args)
            calls.append(ToolCall(id=cid, name=action.tool, arguments=action.args))
        state.neutral.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"id": c.id, "name": c.name, "args": dict(c.arguments)} for c in calls
                ],
            }
        )
        return AssistantMessage(role="assistant", content=None, tool_calls=calls)
