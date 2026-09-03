# ACORN

**Agent Contract Orchestration for Runtime Navigation**: a neuro-symbolic
agent harness that compiles assume-guarantee contract libraries into
runtime control for LLM agents.

> The agent chooses when there is freedom. ACORN executes when there isn't.

Procedural knowledge is declared once, as contracts over the agent's
tool-call trace. The harness turns their runtime state into four
mechanisms:

- **Dynamic tool masking.** At every step the model sees only the
  contract-admissible subset of tools, at `step`, `phase`, or `hint`
  granularity.
- **Symbolic jump-forward.** When exactly one admissible action remains
  with deterministically bindable arguments, or an obligation falls due,
  the controller executes it with no model call.
- **Hard validation.** Every concrete call crosses a pre-execution
  boundary; recoverable blocks name the missing prerequisite.
- **Active obligations.** Prescriptive duties ("after X you must do Y")
  are scheduled and executed, not merely detected after the fact.

On all ten domains of Amazon SOP-Bench, ACORN lifts macro-average task
success from 71.4% to 94.5% (`gpt-5-mini`) with zero committed procedure
violations in every domain, at lower cost than the unguarded baseline.
The same contract libraries transfer unchanged across five model
families. On τ²-bench retail, enforcing the policy's own rules costs no
outcome performance. The full per-cell ledger is
[docs/RESULTS.md](docs/RESULTS.md).

## Install

ACORN builds on [ContrAgent](https://github.com/yfxiao16/ContrAgent), the
deterministic contract layer (ALTLf formulas, residual-DFA monitoring,
event grounding). It is not on PyPI yet, so install it first:

```bash
git clone https://github.com/yfxiao16/ContrAgent ../ContrAgent
pip install -e ../ContrAgent
pip install -e ".[dev]"
pytest -q
```

(For development without installing, the repo-root `conftest.py` falls
back to a sibling `../ContrAgent` checkout automatically.)

## Quick start

Three orthogonal declarations: **tools** say what the agent *can* do,
**flow** says how the application *wants* to organize the task, and the
**contract library** says what is *allowed and required*, attached
explicitly and never encoded into the flow.

```python
import acorn

agent = acorn.Agent(
    model=acorn.models.resolve("anthropic:claude-sonnet-5"),  # or bedrock:/openai:/gemini:
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
    # EVIDENCE: tool results establish facts
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
```

A complete, runnable walkthrough (no API key needed; it uses a scripted
model by default) is [`examples/bank_demo.py`](examples/bank_demo.py):

```bash
python3 examples/bank_demo.py
```

For staged tasks, `acorn.GraphFlow` exposes a candidate toolset per state
with fact-reactive transitions; the effective toolset at each step is
always `A_eff = A_agent ∩ A_contract`.

## Reproducing the paper's experiments

> **Cost warning:** every benchmark row makes real model calls. Nothing
> runs without an explicit `--model` and a configured API key (via
> `.env`; see `acorn/envfile.py`).

**Amazon SOP-Bench** (10 domains). Obtain the benchmark packs from their
official release and place each under
`benchmarks/amazon_sopbench/data/<domain>_sop/` (the directory is
git-ignored; packs are not redistributed here). Then:

```bash
python3 -m benchmarks.amazon_sopbench.run_pack \
    --pack benchmarks/amazon_sopbench/data/dangerous_goods_sop \
    --model openai:gpt-5-mini \
    --condition acorn \            # baseline | passive | mask | acorn
    --mask-granularity step \      # step | phase | hint
    --out results/mini_dangerous_goods_acorn.json
```

Each domain's adapter (`benchmarks/amazon_sopbench/<domain>.py`)
documents, next to the contract library it defines, which rules are
SOP-derived, which are data-validated, and where deterministic rules are
deliberately not fitted. `--scaffold react` wraps the model in a
text-protocol ReAct loop; `--flow-profile` selects the profiles of the
workflow-to-agent sweep on the domains that support them. Runs
checkpoint per row (`<out>.partial.json`) and resume on relaunch.

**τ²-bench retail.** The adapter in `benchmarks/tau2_acorn/` implements
the benchmark's own agent interface; `run_batch.py` runs the arms
(official / shell / grounded-17 / full-53) under matched conditions.

**Analysis.** `scripts/matrix_table.py` renders the cross-model matrix
(markdown or `--latex`); `scripts/aggregate_results.py`,
`bootstrap_ci.py`, and the other scripts in `scripts/` reproduce the
derived tables. Every number in the paper is transcribed from
[docs/RESULTS.md](docs/RESULTS.md), which is generated from the JSON
cells in `results/`.

## Repository layout

```text
acorn/            the harness: Agent, loop, controller, contracts DSL,
                  flows (FreeFlow/GraphFlow), obligations, residual
                  policy cache, model adapters (openai/anthropic/
                  gemini/bedrock + ReAct wrapper)
benchmarks/       Amazon SOP-Bench adapters (10 domains) and τ²-bench
                  adapter, with their contract libraries
examples/         runnable demo (scripted model, no API key)
scripts/          result aggregation and table generation
results/          per-cell JSON results (the paper's data ledger)
docs/RESULTS.md   every reported number, with provenance notes
docs/DESIGN.md    architecture and the ContrAgent reuse map
tests/            pytest suite (contract semantics, adapters, binders)
```

## Citation

If you use ACORN, please cite the paper (see
[CITATION.cff](CITATION.cff)); a preprint reference will appear here
once available.

## License

[Apache-2.0](LICENSE).
