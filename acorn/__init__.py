"""ACORN: Agent Contract Orchestration for Runtime Navigation.

A neuro-symbolic agent harness: procedural contracts are compiled into
runtime control. The agent chooses when there is freedom; ACORN executes
when there isn't.

Three orthogonal declarations:

* **tools** — what the agent CAN do (`ToolRegistry` / `@agent.tool`)
* **flow** — how the application WANTS to organize the task
  (`FreeFlow` default, `GraphFlow` for staged tasks)
* **contracts** — what is ALLOWED and REQUIRED
  (`ContractLibrary`, attached explicitly; never encoded into the flow)

    import acorn

    agent = acorn.Agent(model=acorn.models.resolve("anthropic:claude-sonnet-5"),
                        instructions="You are a bank service agent.")

    @agent.tool
    def verify_identity(customer_id: str) -> dict:
        "Verify the customer's identity."
        ...

    library = acorn.ContractLibrary("refund-desk-v1", [
        acorn.action("issue_refund").requires("identity_verified"),
        acorn.after("verify_identity").asserts("identity_verified",
                                               when=lambda r: r.output["verified"]),
        acorn.when("fraud_detected").obligates("freeze_account", args={...}),
    ])
    library.verify()          # symbolic certificates (LTLf-SAT)
    agent.attach(library)

    result = agent.run("Refund order #123")
    for frame in agent.stream("Replace card for C-1024"):
        print(frame.kind, frame.masked)
"""

from acorn import models
from acorn.agent import Agent
from acorn.backend import ContractBackend, LTLfBackend
from acorn.cache import ResidualPolicyCache
from acorn.contracts import (
    ActionRule,
    AfterRule,
    CompiledContracts,
    CustomRule,
    Contract,
    WhenRule,
    action,
    after,
    ag,
    compile_contracts,
    when,
)
from acorn.control import SymbolicController
from acorn.decisions import Decision, DecisionKind, ProposedAction, StepDecision, StepKind
from acorn.facts import (
    Fact,
    FactStore,
    LocalPredicateEvaluator,
    PredicateContext,
    PredicateEvaluator,
)
from acorn.flow import Flow, FlowContext, FreeFlow, GraphFlow
from acorn.library import ContractConflictError, ContractLibrary, VerifyReport
from acorn.loop import Frame, RunResult, iterate, run
from acorn.obligations import ActiveObligation, ObligationEngine, ObligationSpec
from acorn.tools import Tool, ToolExecutor, ToolRegistry, ToolResult
from acorn.tracing import Tracer

# Back-compat alias from v0.0.1 (FreeAgent was renamed to FreeFlow).
FreeAgent = FreeFlow

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "Flow",
    "FreeFlow",
    "GraphFlow",
    "FlowContext",
    "ContractLibrary",
    "ContractConflictError",
    "VerifyReport",
    "action",
    "after",
    "ag",
    "when",
    "compile_contracts",
    "run",
    "iterate",
    "models",
    "ActionRule",
    "AfterRule",
    "WhenRule",
    "CustomRule",
    "Contract",
    "CompiledContracts",
    "ContractBackend",
    "LTLfBackend",
    "ResidualPolicyCache",
    "SymbolicController",
    "Decision",
    "DecisionKind",
    "StepDecision",
    "StepKind",
    "ProposedAction",
    "Fact",
    "FactStore",
    "PredicateContext",
    "PredicateEvaluator",
    "LocalPredicateEvaluator",
    "ActiveObligation",
    "ObligationEngine",
    "ObligationSpec",
    "Tool",
    "ToolRegistry",
    "ToolExecutor",
    "ToolResult",
    "Tracer",
    "Frame",
    "RunResult",
    "FreeAgent",
]
