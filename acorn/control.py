"""The Symbolic Controller — ACORN's central abstraction.

Owns the symbolic control state (LTLf residuals + facts + obligations +
grounding accumulators) and answers four questions:

* ``admissible_actions``  — which tools may be exposed to the model now?
  (cheap, tool-level, argument-dependent contracts excluded)
* ``validate``            — is this concrete (tool, args) executable now?
  (the hard pre-execution boundary; all contracts, real arguments)
* ``next_decision``       — who controls the next step: symbolic
  execution, neural choice over a narrowed toolset, or dead end?
* ``update``              — commit an executed action into both the
  trace monitors and the fact store (via result extractors).

Filtering and validation are deliberately separate APIs even though v0
shares most logic between them: future versions keep filtering cheap
while validate() grows richer checks (argument constraints, evidence,
external predicates).

Pipeline (the DFA never inspects application data directly):

    environment / agent state
        → PredicateEvaluator → fact propositions
        → grounding(event)   → trace propositions
        → contract progression (LTLfBackend)
        → control state → admissible actions
"""

from __future__ import annotations

import copy
from typing import Any

from contragent.formulas._pred_key import pred_key
from contragent.models.trace import Event
from contragent.tracer.grounding import GroundingState, ground_event

from acorn.backend import LTLfBackend
from acorn.contracts import CompiledContracts, Contract, compile_contracts
from acorn.decisions import Decision, DecisionKind, ProposedAction, StepDecision
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext, PredicateEvaluator
from acorn.obligations import ObligationEngine
from acorn.tools import ToolRegistry, ToolResult
from acorn.tracing import Tracer


class SymbolicController:
    def __init__(
        self,
        contracts: CompiledContracts | list,
        *,
        registry: ToolRegistry | None = None,
        predicate_evaluator: PredicateEvaluator | None = None,
        agent_id: str = "agent",
        tracer: Tracer | None = None,
        control_mode: str = "full",
        probe_cache=None,
        mask_granularity: str = "step",
    ) -> None:
        # "step": expose only the per-step admissible set (max masking, but
        # schema churn breaks provider prompt caches). "phase": expose the
        # flow's stable candidate set; contract admissibility still drives
        # jump detection internally and validate() enforces per call —
        # trading some invalid-proposal risk for prefix-cache stability.
        if mask_granularity not in ("step", "phase", "hint"):
            raise ValueError(f"unknown mask_granularity {mask_granularity!r}")
        self.mask_granularity = mask_granularity
        self.probe_cache = probe_cache
        # control_mode — the ablation ladder:
        #   "passive": validate-only (block + reprompt); no masking, no jump.
        #   "mask":    dynamic tool exposure, but no symbolic execution
        #              (a singleton/obligation still goes to the LLM).
        #   "full":    mask + symbolic jump-forward (ACORN).
        if control_mode not in ("full", "mask", "passive"):
            raise ValueError(f"unknown control_mode {control_mode!r}")
        self.control_mode = control_mode
        cc = contracts if isinstance(contracts, CompiledContracts) else compile_contracts(contracts)
        self.contracts = cc
        self.backend = LTLfBackend(cc.contracts)
        self.facts = FactStore()
        self.obligations = ObligationEngine(cc.obligations)
        self.registry = registry
        self.agent_id = agent_id
        self.tracer = tracer or Tracer()
        self._pe = predicate_evaluator or LocalPredicateEvaluator()
        self._grounding = GroundingState()
        self.events: list[Event] = []

    # ------------------------------------------------------------------
    # Facts (all writes flow through here so obligations + tracing fire)
    # ------------------------------------------------------------------

    def assert_fact(self, predicate: str, value: Any = True, **metadata: Any) -> None:
        fact = self.facts.assert_fact(predicate, value, **metadata)
        self.tracer.record("fact/asserted", predicate=predicate, value=value, metadata=fact.metadata)
        if fact.truthy:
            for ob in self.obligations.on_fact_asserted(predicate, step=len(self.events)):
                self.tracer.record("obligation/created", obligation=ob.desc, tool=ob.tool)

    def invalidate_fact(self, predicate: str) -> None:
        retracted = self.facts.invalidate_fact(predicate)
        if retracted is not None:
            self.tracer.record("fact/invalidated", predicate=predicate)

    # ------------------------------------------------------------------
    # Valuation construction
    # ------------------------------------------------------------------

    def _fact_valuation(self, agent_state: Any = None) -> dict[str, object]:
        """Resolve every contract-referenced fact predicate to a proposition."""
        ctx = PredicateContext(self.facts, agent_state)
        out: dict[str, object] = {}
        for p in sorted(self.contracts.fact_predicates):
            val = self._pe.evaluate(p, ctx)
            out[pred_key("fact", p)] = bool(val)
            if val is not None and not isinstance(val, bool) and isinstance(val, (int, float)):
                out[pred_key("fact_value", p)] = val
        return out

    def _valuation_for(
        self,
        tool: str,
        args: dict | None,
        agent_state: Any,
        grounding: GroundingState,
    ) -> dict[str, object]:
        event = Event(
            ts=len(self.events),
            agent=self.agent_id,
            event_type="tool_call",
            tool=tool,
            args=dict(args or {}),
        )
        valuation = ground_event(event, len(self.events), grounding, self.contracts.content_atoms)
        valuation.update(self._fact_valuation(agent_state))
        return valuation

    # ------------------------------------------------------------------
    # Action-space compilation (cheap, tool-level)
    # ------------------------------------------------------------------

    def _cache_key_base(self, agent_state: Any):
        """Structural part of the residual-policy cache key (no session
        values — only contract-referenced predicate valuations)."""
        g = self._grounding
        facts_fp = tuple(sorted(self._fact_valuation(agent_state).items()))
        return (
            self.backend.state_signature(),
            tuple(sorted(g.call_counts.items())),
            tuple(sorted(g.consecutive_counts.items())),
            g.last_tool,
            facts_fp,
        )

    def admissible_actions(self, candidate_actions: list[str], agent_state: Any = None) -> list[str]:
        admissible = []
        key_base = self._cache_key_base(agent_state) if self.probe_cache is not None else None
        for tool in candidate_actions:
            violated_names = None
            if key_base is not None:
                violated_names = self.probe_cache.lookup((key_base, tool))
            if violated_names is None:
                grounding = copy.deepcopy(self._grounding)
                valuation = self._valuation_for(tool, {}, agent_state, grounding)
                violated = self.backend.probe(valuation, include_args_dependent=False)
                violated_names = tuple(r.name for r in violated)
                if key_base is not None:
                    self.probe_cache.store((key_base, tool), violated_names)
            if violated_names:
                self.tracer.record("action/masked", tool=tool, contracts=list(violated_names))
            else:
                admissible.append(tool)
        return admissible

    # ------------------------------------------------------------------
    # Hard pre-execution validation (all contracts, concrete arguments)
    # ------------------------------------------------------------------

    def validate(self, action: ProposedAction, agent_state: Any = None) -> Decision:
        grounding = copy.deepcopy(self._grounding)
        valuation = self._valuation_for(action.tool, action.args, agent_state, grounding)
        violated = self.backend.probe(valuation, include_args_dependent=True)
        if not violated:
            return Decision(DecisionKind.ALLOW)
        if all(contract.recoverable for contract in violated):
            return self._require_decision(violated)
        hard = [r for r in violated if not r.recoverable]
        return Decision(DecisionKind.BLOCK, reasons=[r.name for r in hard])

    def _require_decision(self, violated: list[Contract]) -> Decision:
        reasons, requirements, hints = [], [], []
        for contract in violated:
            reasons.append(contract.name)
            for predicate in contract.requirements:
                if not self.facts.truthy(predicate):
                    requirements.append(predicate)
                    for tool in self.contracts.asserted_by.get(predicate, []):
                        hints.append(f"call `{tool}` to establish {predicate}")
            for tool in contract.prerequisites:
                requirements.append(f"called({tool})")
                hints.append(f"call `{tool}`")
        return Decision(
            DecisionKind.REQUIRE, reasons=reasons, requirements=requirements, hints=hints
        )

    # ------------------------------------------------------------------
    # Control handoff
    # ------------------------------------------------------------------

    def state_signature(self) -> int:
        """Control-state signature for residual-policy-cache research:
        (residuals, facts, call counters) — see LTLfBackend.state_signature."""
        facts_sig = tuple(sorted((k, str(f.value)) for k, f in self.facts._facts.items()))
        counters = tuple(sorted(self._grounding.call_counts.items()))
        try:
            return hash((self.backend.state_signature(), facts_sig, counters))
        except TypeError:  # unhashable residual leaf — degrade to repr
            return hash((repr(self.backend.state_signature()), facts_sig, counters))

    def next_decision(self, candidate_actions: list[str], agent_state: Any = None) -> StepDecision:
        self.tracer.record("controller/state_sig", sig=self.state_signature())
        # Passive verifier: no action-space shaping at all — the hard
        # validate() boundary is the only control (block + reprompt).
        if self.control_mode == "passive":
            return StepDecision.neural(list(candidate_actions), obligations=self.obligations.pending())

        # Case C — an obligation is due: symbolic execution preempts choice.
        due = self.obligations.due()
        if due and self.control_mode == "mask":
            # Mask-only: the obligation narrows the toolset but the LLM
            # still makes (and argues) the call itself.
            return StepDecision.neural(
                [due[0].tool], reason=f"obligation (mask-only): {due[0].desc}", obligations=due
            )
        if due:
            ob = due[0]
            ctx = PredicateContext(self.facts, agent_state)
            args = self.obligations.resolve_args(ob, ctx)
            if args is None:
                args = self._bind_trivial_args(ob.tool)
            if args is not None:
                return StepDecision.symbolic(
                    ProposedAction(ob.tool, args), reason=f"obligation: {ob.desc}"
                )
            # Arguments need interpretation → the LLM decides, but only
            # over the obligated action (singleton action space).
            return StepDecision.neural(
                [ob.tool], reason=f"obligation requires arguments: {ob.desc}", obligations=due
            )

        admissible = self.admissible_actions(candidate_actions, agent_state)
        if not admissible:
            return StepDecision.dead_end("no admissible actions remain")

        # Case B — exactly one admissible action whose arguments are
        # procedurally determined: jump-forward, no model call.
        if len(admissible) == 1 and self.control_mode == "full":
            args = self._bind_args(admissible[0], agent_state)
            if args is not None:
                return StepDecision.symbolic(
                    ProposedAction(admissible[0], args),
                    reason="single admissible action with determined arguments",
                )

        # Case A — genuine freedom: the model chooses among admissible actions.
        self.last_admissible = list(admissible)
        exposed = (
            list(candidate_actions)
            if self.mask_granularity in ("phase", "hint")
            else admissible
        )
        return StepDecision.neural(exposed, obligations=self.obligations.pending())

    def _bind_args(self, tool_name: str, agent_state: Any = None) -> dict | None:
        """Deterministic argument binding; None = LLM must decide."""
        if self.registry is None or tool_name not in self.registry:
            return None
        tool = self.registry.get(tool_name)
        if tool.args_binder is not None:
            return tool.args_binder(PredicateContext(self.facts, agent_state))
        if not tool.required_params:
            return {}
        return None

    def _bind_trivial_args(self, tool_name: str) -> dict | None:
        if self.registry is not None and tool_name in self.registry:
            if not self.registry.get(tool_name).required_params:
                return {}
        return None

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def update(self, action: ProposedAction, result: ToolResult, agent_state: Any = None) -> None:
        """Commit an executed action into both worlds: trace monitors first,
        then fact extraction from the structured ToolResult."""
        args = dict(action.args)
        args["succeeded"] = 1 if result.ok else 0
        event = Event(
            ts=len(self.events),
            agent=self.agent_id,
            event_type="tool_call",
            tool=action.tool,
            args=args,
        )
        valuation = ground_event(event, len(self.events), self._grounding, self.contracts.content_atoms)
        valuation.update(self._fact_valuation(agent_state))
        violated = self.backend.step(valuation)
        self.events.append(event)
        if violated:
            # Only reachable in observe-style flows (enforce blocks first).
            self.tracer.record(
                "contract/violation", tool=action.tool, contracts=[r.name for r in violated]
            )

        if result.ok:
            for spec in self.contracts.extractors.get(action.tool, []):
                if spec.when is not None and not spec.when(result):
                    continue
                value = spec.value(result) if callable(spec.value) else spec.value
                metadata = spec.metadata(result) if callable(spec.metadata) else (spec.metadata or {})
                self.assert_fact(spec.predicate, value, source=action.tool, **metadata)
            for predicate in self.contracts.invalidations.get(action.tool, []):
                self.invalidate_fact(predicate)

        for ob in self.obligations.on_action_executed(action.tool, result.ok):
            self.tracer.record("obligation/satisfied", obligation=ob.desc, tool=ob.tool)

    # ------------------------------------------------------------------
    # Session end
    # ------------------------------------------------------------------

    def finalize(self) -> dict:
        """End-of-session report. Pending obligations are violations here —
        ACORN's active semantics, not the weak finite-trace collapse."""
        ltlf = [r.name for r in self.backend.finalize()]
        pending = [ob.desc for ob in self.obligations.pending()]
        for desc in pending:
            self.tracer.record("obligation/pending", obligation=desc)
        for name in ltlf:
            self.tracer.record("contract/final", contract=name)
        out = {"ltlf_violations": ltlf, "pending_obligations": pending}
        statuses = self.backend.assumption_statuses()
        if any(s != "unconditional" for s in statuses.values()):
            out["vacuous_contracts"] = [n for n, s in statuses.items() if s == "vacuous"]
        return out
