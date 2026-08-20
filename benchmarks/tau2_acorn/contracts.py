"""tau2 contract post-processing: response-shaped contracts -> obligations.

Contracts of shape ``G(called(A) -> X(called(B)))`` (the workflow_step
"A must be followed by B") or ``G(A -> F(called(B)))`` are passive
detectors; ACORN additionally derives obligations from them so the
follow-up B is actively driven:

* ``X`` consequent -> deadline="next": the very next action must be B, so
  symbolic execution preempts immediately after A commits;
* ``F`` consequent -> deadline="eventually": discharged at the
  floor-yield boundary (before any potential episode end).

Argument binding is purely structural: B receives the intersection of
its schema parameters with the triggering call's arguments.
"""

from __future__ import annotations

from contragent.formulas.formula import Atom, F, G, Implies, X

import acorn


def _called_tool(node) -> str | None:
    """Tool name if node is called(X) or a conjunction containing it."""
    if isinstance(node, Atom) and node.predicate == "called" and node.args:
        return node.args[0]
    for attr in ("left", "right", "child"):
        child = getattr(node, attr, None)
        if child is not None:
            name = _called_tool(child)
            if name:
                return name
    return None


def response_obligations(library: acorn.ContractLibrary, tool_schemas: dict[str, list[str]]) -> list:
    """Extra specs: for each G(A -> F(called(B))) contract, assert a
    trigger fact after A (carrying A's args) and obligate B eventually."""
    specs: list = []
    for contract in library.contracts:
        f = contract.formula
        if not isinstance(f, G) or not isinstance(f.child, Implies):
            continue
        cons = f.child.right
        if not isinstance(cons, (F, X)):
            continue
        deadline = "next" if isinstance(cons, X) else "eventually"
        b = _called_tool(cons.child)
        a = _called_tool(f.child.left)
        if not (a and b):
            continue
        trigger_fact = f"__followup_{a}__{b}"
        b_params = tool_schemas.get(b, [])

        def binder(ctx, fact=trigger_fact, params=tuple(b_params)):
            rec = ctx.facts.get(fact)
            if rec is None:
                return None
            src = rec.metadata.get("trigger_args") or {}
            bound = {k: src[k] for k in params if k in src}
            required = rec.metadata.get("required") or ()
            if any(k not in bound for k in required):
                return None  # cannot determine deterministically -> LLM fills
            return bound

        specs.append(
            acorn.after(a).asserts(
                trigger_fact,
                metadata=lambda r, req=tuple(b_params): {"trigger_args": dict(r.args), "required": req},
            )
        )
        specs.append(
            acorn.when(trigger_fact).obligates(
                b, binder=binder, deadline=deadline, desc=contract.name
            )
        )
    return specs
