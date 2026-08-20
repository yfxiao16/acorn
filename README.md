# ACORN

**Agent Contract Orchestration for Runtime Navigation** — a neuro-symbolic
agent harness. Procedural contracts are compiled into runtime control: ACORN
narrows the LLM's action space when choices remain, and directly executes
actions when the procedure determines what must happen next.

> The agent chooses when there is freedom. ACORN executes when there isn't.

ACORN builds on [ContrAgent](../ContrAgent)'s deterministic contract layer
(LTLf formulas, residual-DFA monitoring, event grounding) and adds the
harness: an agent loop, dynamic per-step tool exposure, symbolic control
state (facts + obligations), and symbolic action execution (jump-forward).

## Setup

```bash
pip install -e ../ContrAgent   # the symbolic kernel (sibling checkout)
pip install -e ".[dev]"
pytest -q
```

(For development without installing, the repo-root `conftest.py` falls back
to the sibling `../ContrAgent` checkout automatically.)

## Quick start

Three orthogonal declarations: **tools** say what the agent *can* do,
**flow** says how the application *wants* to organize the task, and the
**contract library** says what is *allowed and required* — attached
explicitly, never encoded into the flow.

```python
import acorn

agent = acorn.Agent(
    model=acorn.models.resolve("anthropic:claude-sonnet-5"),  # or gemini:/openai:
    instructions="You are a bank service agent.",
)

@agent.tool
def verify_identity(user_id: str) -> dict:
    "Verify the customer's identity."
    return {"verified": True, "user_id": user_id}

@agent.tool
def issue_refund(order_id: str, amount: float) -> dict:
    "Issue a refund for an order."
    return {"refunded": True}

@agent.tool
def freeze_account(user_id: str) -> dict:
    "Freeze the customer's account."
    return {"frozen": True}

library = acorn.ContractLibrary("refund-desk-v1", [
    # REQUIRES: facts that must hold when the action is called
    acorn.action("issue_refund").requires("identity_verified").at_most(1),
    # EVIDENCE_FOR: tool results establish facts
    acorn.after("verify_identity").asserts(
        "identity_verified", when=lambda r: r.output.get("verified")
    ),
    # OBLIGATES: what MUST happen once a fact holds (executed by ACORN)
    acorn.when("fraud_detected").obligates(
        "freeze_account",
        binder=lambda ctx: {"user_id": ctx.facts.value("customer_id")},
    ),
])
library.verify()      # symbolic certificates: satisfiable, falsifiable, conflict-free
agent.attach(library)

result = agent.run("Refund order #123 for customer u1")
print(result.status, result.final_text)
print("symbolic execution ratio:", result.symbolic_execution_ratio)

for frame in agent.stream("Replace card for C-1024"):   # decision frames
    print(frame.kind, [m["tool"] for m in frame.masked])
```

For staged tasks, `acorn.GraphFlow` exposes a candidate toolset per
state with fact-reactive transitions (`A_eff = A_agent ∩ A_contract`);
`acorn.run(...)` remains as a one-call shortcut.

At every step ACORN computes the contract-admissible subset of tools and
exposes only those to the model (`action/masked` in the trace). A proposed
call is hard-validated with its concrete arguments immediately before
execution; a recoverable block feeds back the exact prerequisite tool to
call first. When an obligation is due — or exactly one admissible action
remains with procedurally determined arguments — ACORN executes it without
a model call (`action/symbolic`).

## Docs

- [DESIGN.md](DESIGN.md) — architecture, ContrAgent reuse map, extension
  seams, roadmap.
