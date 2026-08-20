"""The ACORN runtime loop (proposal §5). Deliberately minimal: no
procedural semantics live here — they live in the SymbolicController.

    read flow state → candidate actions → admissible actions
    → who decides? (symbolic / neural / dead end)
    → hard validation immediately before execution
    → execute → update both worlds → advance flow → trace → repeat

The core is a generator (:func:`iterate`) that yields one
:class:`Frame` per step — the streaming decision-frame surface. ``run``
just drains it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Generator

from acorn.contracts import CompiledContracts
from acorn.control import SymbolicController
from acorn.decisions import DecisionKind, ProposedAction, StepKind
from acorn.flow import Flow, FlowContext, FreeFlow
from acorn.models.base import Model, ToolCall
from acorn.tools import ToolExecutor, ToolRegistry
from acorn.tracing import Tracer


@dataclass
class Frame:
    """One step of the run, as the user sees it."""

    step: int
    kind: str  # "neural_choice" | "symbolic_execute" | "dead_end" | "final"
    exposed: list[str] = field(default_factory=list)
    masked: list[dict] = field(default_factory=list)  # {tool, contracts}
    action: ProposedAction | None = None
    reason: str = ""
    text: str | None = None
    blocked: list[dict] = field(default_factory=list)  # {tool, reasons}
    records: list[dict] = field(default_factory=list)  # raw tracer records of this step


@dataclass
class RunResult:
    status: str  # "completed" | "dead_end" | "max_steps"
    final_text: str | None
    steps: int
    model_calls: int
    symbolic_steps: int
    neural_action_steps: int
    blocked_proposals: int
    finalize: dict
    controller: SymbolicController
    flow: Any
    tracer: Tracer
    # Condition-independent compliance audit (same contract library run in
    # observe mode over the committed actions of ANY condition). None when
    # no auditor was attached.
    audit: dict | None = None
    # Wall-clock breakdown (seconds): where the time actually went.
    time_model_s: float = 0.0
    time_controller_s: float = 0.0
    time_tools_s: float = 0.0

    @property
    def symbolic_execution_ratio(self) -> float:
        total = self.symbolic_steps + self.neural_action_steps
        return self.symbolic_steps / total if total else 0.0

    @property
    def neural_decision_ratio(self) -> float:
        total = self.symbolic_steps + self.model_calls
        return self.model_calls / total if total else 0.0


def iterate(
    task: str,
    *,
    model: Model,
    tools: ToolRegistry,
    contracts: Any = None,
    controller: SymbolicController | None = None,
    flow: Flow | None = None,
    system: str | None = None,
    max_steps: int = 24,
    trace_path: str | None = None,
    facts: dict | None = None,
    predicate_evaluator: Any = None,
    auditor: SymbolicController | None = None,
    control_mode: str = "full",
    probe_cache=None,
    mask_granularity: str = "step",
) -> Generator[Frame, None, RunResult]:
    if controller is None:
        tracer = Tracer(trace_path)
        cc = contracts.compiled if hasattr(contracts, "compiled") else (contracts or [])
        controller = SymbolicController(
            cc,
            registry=tools,
            tracer=tracer,
            predicate_evaluator=predicate_evaluator,
            control_mode=control_mode,
            probe_cache=probe_cache,
            mask_granularity=mask_granularity,
        )
    else:
        tracer = controller.tracer  # one stream for controller + loop events
        if controller.registry is None:
            controller.registry = tools

    flow = flow or FreeFlow()
    flow.reset(task)
    executor = ToolExecutor(tools)

    for predicate, value in (facts or {}).items():
        controller.assert_fact(predicate, value, source="<initial>")
        if auditor is not None:
            auditor.assert_fact(predicate, value, source="<initial>")

    model_calls = symbolic_steps = neural_action_steps = blocked = 0
    status, final_text = "max_steps", None
    step = -1
    nudges = 0
    max_nudges = 2  # completion-gate retries before giving up as incomplete
    t_model = t_ctrl = t_tools = 0.0

    def _ctx(action=None, result=None, step=0):
        return FlowContext(
            facts=controller.facts,
            state=flow.get_state(),
            step=step,
            last_action=action,
            last_result=result,
        )

    for step in range(max_steps):
        if flow.finished():
            status = "completed"
            break

        rec_start = len(tracer.records)
        flow_state = flow.get_state()
        candidates = flow.available_actions(tools.names())
        _t0 = time.perf_counter()
        decision = controller.next_decision(candidates, flow_state)
        t_ctrl += time.perf_counter() - _t0
        tracer.record(
            "controller/decision",
            step=step,
            decision=decision.kind.value,
            actions=decision.actions,
            action=str(decision.action) if decision.action else None,
            reason=decision.reason,
        )
        masked = [
            {"tool": r["tool"], "contracts": r["contracts"]}
            for r in tracer.records[rec_start:]
            if r["kind"] == "action/masked"
        ]

        if decision.kind is StepKind.DEAD_END:
            tracer.record("controller/dead_end", step=step, reason=decision.reason)
            status = "dead_end"
            yield Frame(
                step=step, kind="dead_end", masked=masked, reason=decision.reason,
                records=tracer.records[rec_start:],
            )
            break

        if decision.kind is StepKind.SYMBOLIC_EXECUTE:
            action = decision.action
            _t0 = time.perf_counter()
            verdict = controller.validate(action, flow_state)  # hard boundary, always
            t_ctrl += time.perf_counter() - _t0
            if not verdict.allowed:
                # Defensive: a symbolic decision should already be admissible.
                tracer.record("action/blocked", step=step, tool=action.tool, reasons=verdict.reasons)
                status = "dead_end"
                yield Frame(
                    step=step, kind="dead_end", masked=masked,
                    reason=f"symbolic action blocked: {verdict.reasons}",
                    records=tracer.records[rec_start:],
                )
                break
            _t0 = time.perf_counter()
            result = executor.execute(action)
            t_tools += time.perf_counter() - _t0
            symbolic_steps += 1
            tracer.record(
                "action/symbolic", step=step, tool=action.tool, args=action.args, ok=result.ok
            )
            controller.update(action, result, flow_state)
            if auditor is not None:
                auditor.update(action, result, flow_state)
            flow.notify_symbolic(action, result, decision.reason)
            flow.advance(_ctx(action, result, step))
            yield Frame(
                step=step, kind="symbolic_execute", masked=masked, action=action,
                reason=decision.reason, records=tracer.records[rec_start:],
            )
            continue

        # NEURAL_CHOICE — dynamic per-step tool exposure.
        if getattr(controller, "mask_granularity", "step") == "hint":
            # Cache-friendly soft masking: the tools block stays stable;
            # the restriction rides in an appended message (validate() is
            # still the hard boundary).
            allowed = getattr(controller, "last_admissible", None)
            if allowed is not None and set(allowed) != set(decision.actions):
                flow.nudge("[ACORN] Currently permitted tools: " + ", ".join(allowed) + ".")
        _t0 = time.perf_counter()
        turn = model.generate(
            flow.build_context(), tools=tools.schemas(decision.actions), system=system
        )
        t_model += time.perf_counter() - _t0
        model_calls += 1
        tracer.record(
            "model/response",
            step=step,
            text=turn.text,
            tool_calls=[{"name": c.name, "args": c.args} for c in turn.tool_calls],
            usage=turn.usage,
        )
        flow.update_model_turn(turn)

        if not turn.tool_calls:
            # Floor-yield gate for eventually-obligations: the episode can
            # only end after a text turn, so no text turn is allowed out
            # while the obligation ledger is non-empty. Jump if the args
            # are determined; otherwise nudge with the obligation named.
            pending_ev = controller.obligations.due_eventually()
            if pending_ev and nudges < max_nudges:
                ob = pending_ev[0]
                from acorn.facts import PredicateContext as _PC

                args = controller.obligations.resolve_args(ob, _PC(controller.facts, flow.get_state()))
                if args is None and controller.registry is not None and ob.tool in controller.registry:
                    if not controller.registry.get(ob.tool).required_params:
                        args = {}
                if args is not None and controller.control_mode == "full":
                    action = ProposedAction(ob.tool, args)
                    verdict = controller.validate(action, flow_state)
                    if verdict.allowed:
                        _t0 = time.perf_counter()
                        result = executor.execute(action)
                        t_tools += time.perf_counter() - _t0
                        symbolic_steps += 1
                        tracer.record("action/symbolic", step=step, tool=action.tool,
                                      args=action.args, ok=result.ok, reason="floor-yield obligation")
                        controller.update(action, result, flow_state)
                        if auditor is not None:
                            auditor.update(action, result, flow_state)
                        flow.notify_symbolic(action, result, f"pending obligation before finishing: {ob.desc}")
                        flow.advance(_ctx(action, result, step))
                        yield Frame(step=step, kind="symbolic_execute", masked=masked, action=action,
                                    reason=f"floor-yield obligation: {ob.desc}",
                                    records=tracer.records[rec_start:])
                        continue
                nudges += 1
                tracer.record("controller/nudge", step=step, reason=f"pending obligation: {ob.desc}")
                flow.nudge(f"[ACORN] Before finishing, you must still: {ob.desc}. Complete it now using the tools.")
                yield Frame(step=step, kind="neural_choice", exposed=decision.actions, masked=masked,
                            text=turn.text, records=tracer.records[rec_start:])
                continue
            if getattr(flow, "requires_terminal", False) and not flow.finished() and nudges < max_nudges:
                # Procedural completion gate: a text-only answer does not
                # end a flow that declares terminal states — the model is
                # nudged back to finish the procedure via tools. Bounded:
                # after max_nudges the run ends (status reflects the truth).
                nudges += 1
                tracer.record("controller/nudge", step=step, reason="text answer before terminal state")
                flow.nudge(
                    "[ACORN] The task is not complete: finish the procedure using "
                    "the available tools (including submitting the final result)."
                )
                yield Frame(
                    step=step, kind="neural_choice", exposed=decision.actions,
                    masked=masked, text=turn.text, records=tracer.records[rec_start:],
                )
                continue
            status, final_text = "completed", turn.text
            yield Frame(
                step=step, kind="final", exposed=decision.actions, masked=masked,
                text=turn.text, records=tracer.records[rec_start:],
            )
            break

        frame_blocked: list[dict] = []
        last_action = last_result = None
        for call in turn.tool_calls:
            if call.name not in tools:
                flow.add_tool_result(
                    call, json.dumps({"ok": False, "error": f"unknown tool {call.name}"})
                )
                continue
            call_state = flow.get_state()
            proposed = ToolCall(name=call.name, args=call.args, id=call.id)
            action = ProposedAction(call.name, dict(call.args or {}))
            tracer.record("action/proposed", step=step, tool=action.tool, args=action.args)
            _t0 = time.perf_counter()
            verdict = controller.validate(action, call_state)
            t_ctrl += time.perf_counter() - _t0
            if verdict.kind is DecisionKind.ALLOW:
                _t0 = time.perf_counter()
                result = executor.execute(action)
                t_tools += time.perf_counter() - _t0
                neural_action_steps += 1
                tracer.record("tool/result", step=step, tool=action.tool, ok=result.ok)
                controller.update(action, result, call_state)
                if auditor is not None:
                    auditor.update(action, result, call_state)
                flow.add_tool_result(proposed, json.dumps(result.payload(), default=str))
                last_action, last_result = action, result
            else:
                blocked += 1
                frame_blocked.append({"tool": action.tool, "reasons": verdict.reasons})
                tracer.record(
                    "action/blocked",
                    step=step,
                    tool=action.tool,
                    verdict=verdict.kind.value,
                    reasons=verdict.reasons,
                )
                flow.receive_control_feedback(proposed, verdict)
        if last_action is not None:
            flow.advance(_ctx(last_action, last_result, step))
        yield Frame(
            step=step, kind="neural_choice", exposed=decision.actions, masked=masked,
            blocked=frame_blocked, text=turn.text, records=tracer.records[rec_start:],
        )

    finalize = controller.finalize()
    audit = None
    if auditor is not None:
        # LTLf safety monitors latch (once violated, every later event
        # re-reports) — the audit counts each rule's FIRST firing only.
        seen: set = set()
        fired = []
        for r in auditor.tracer.by_kind("contract/violation"):
            new = [x for x in r.get("contracts", []) if x not in seen]
            if new:
                seen.update(new)
                fired.append({"tool": r.get("tool"), "contracts": new})
        audit_final = auditor.finalize()
        audit = {
            "committed_violations": fired,
            "violation_count": sum(len(f["contracts"]) for f in fired),
            "proc_clean": not fired
            and not audit_final["ltlf_violations"]
            and not audit_final["pending_obligations"],
            "finalize": audit_final,
        }
    return RunResult(
        status=status,
        final_text=final_text,
        steps=step + 1,
        model_calls=model_calls,
        symbolic_steps=symbolic_steps,
        neural_action_steps=neural_action_steps,
        blocked_proposals=blocked,
        finalize=finalize,
        controller=controller,
        flow=flow,
        tracer=tracer,
        audit=audit,
        time_model_s=t_model,
        time_controller_s=t_ctrl,
        time_tools_s=t_tools,
    )


def run(task: str, **kwargs: Any) -> RunResult:
    """Drain :func:`iterate` and return the RunResult."""
    gen = iterate(task, **kwargs)
    while True:
        try:
            next(gen)
        except StopIteration as stop:
            return stop.value
