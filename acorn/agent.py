"""The user-facing Agent: model + tools + contract library + instructions.

Three orthogonal declarations meet here:

* **tools** say what the agent *can* do (ToolRegistry),
* **flow** says how the application *wants* to organize the task
  (FreeFlow by default; GraphFlow for staged tasks),
* **contracts** say what is *allowed and required*
  (ContractLibrary — attached explicitly, never encoded into the flow).

Usage::

    agent = acorn.Agent(model=acorn.models.resolve("anthropic:claude-sonnet-5"),
                        instructions="You are a bank service agent.")

    @agent.tool
    def verify_identity(customer_id: str) -> dict: ...

    agent.attach(acorn.ContractLibrary("refund-desk-v1", [...]))
    result = agent.run("Refund order #123")
    for frame in agent.stream("Replace card"):
        ...
"""

from __future__ import annotations

from typing import Any, Callable, Generator, Iterable

from acorn.flow import Flow
from acorn.library import ContractLibrary
from acorn.loop import Frame, RunResult, iterate
from acorn.models.base import Model
from acorn.tools import Tool, ToolRegistry


class Agent:
    def __init__(
        self,
        model: Model,
        *,
        tools: ToolRegistry | Iterable[Tool] | None = None,
        instructions: str | None = None,
        flow: Flow | None = None,
        contracts: ContractLibrary | list | None = None,
        max_steps: int = 24,
        predicate_evaluator: Any = None,
        control_mode: str = "full",
        cache: bool = False,
        mask_granularity: str = "step",
    ) -> None:
        self.model = model
        if isinstance(tools, ToolRegistry):
            self.registry = tools
        else:
            self.registry = ToolRegistry()
            for t in tools or []:
                self.registry.register(t)
        self.instructions = instructions
        self.flow = flow
        self.max_steps = max_steps
        self.predicate_evaluator = predicate_evaluator
        self.control_mode = control_mode
        self.mask_granularity = mask_granularity
        # Residual policy cache (opt-in): shared across this Agent's runs
        # so repeated procedural states across tasks reuse compiled probes.
        from acorn.cache import ResidualPolicyCache

        self.probe_cache = ResidualPolicyCache() if cache else None
        self.library: ContractLibrary | None = None
        self.last_result: RunResult | None = None
        if contracts is not None:
            self.attach(contracts)

    # ------------------------------------------------------------------
    def tool(self, fn: Callable | None = None, **kwargs: Any):
        """Register a tool on this agent (same options as ToolRegistry.tool)."""
        return self.registry.tool(fn, **kwargs)

    def attach(self, contracts: ContractLibrary | list) -> "Agent":
        """Attach the contract library. Explicit and separate by design:
        contracts are independent of the flow, never encoded into it."""
        if isinstance(contracts, ContractLibrary):
            self.library = contracts
        else:
            self.library = ContractLibrary("attached", list(contracts))
        return self

    # ------------------------------------------------------------------
    def stream(
        self,
        task: str,
        *,
        facts: dict | None = None,
        max_steps: int | None = None,
        trace_path: str | None = None,
        auditor: Any = None,
    ) -> Generator[Frame, None, RunResult]:
        """Yield one decision Frame per step; the generator's return value
        is the RunResult (also stored as ``self.last_result``)."""
        gen = iterate(
            task,
            model=self.model,
            tools=self.registry,
            contracts=self.library,
            flow=self.flow,
            system=self.instructions,
            max_steps=max_steps or self.max_steps,
            trace_path=trace_path,
            facts=facts,
            predicate_evaluator=self.predicate_evaluator,
            auditor=auditor,
            control_mode=self.control_mode,
            probe_cache=self.probe_cache,
            mask_granularity=self.mask_granularity,
        )
        result = yield from gen
        self.last_result = result
        return result

    def run(
        self,
        task: str,
        *,
        facts: dict | None = None,
        max_steps: int | None = None,
        trace_path: str | None = None,
        auditor: Any = None,
    ) -> RunResult:
        gen = self.stream(
            task, facts=facts, max_steps=max_steps, trace_path=trace_path, auditor=auditor
        )
        while True:
            try:
                next(gen)
            except StopIteration as stop:
                return stop.value
