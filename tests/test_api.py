"""The finalized user-facing API: Agent bundle, ContractLibrary,
GraphFlow, stream(), initial facts."""

from __future__ import annotations

import acorn
from acorn.models import MockModel, ModelTurn, ToolCall
from contragent.formulas.formula import And, Atom, Not


def _bundle(world_fraud=False):
    world = {"fraud": world_fraud, "frozen": [], "refunds": []}
    agent = acorn.Agent(model=None, instructions="bank agent")

    @agent.tool
    def verify_identity(customer_id: str) -> dict:
        "Verify identity."
        return {"verified": True, "customer_id": customer_id}

    @agent.tool
    def issue_refund(order_id: str, amount: float) -> dict:
        "Issue refund."
        world["refunds"].append(order_id)
        return {"refunded": True}

    @agent.tool
    def send_summary(text: str) -> dict:
        "Send a summary."
        return {"sent": True}

    library = acorn.ContractLibrary(
        "refund-v1",
        [
            acorn.action("issue_refund").requires("identity_verified").at_most(1),
            acorn.after("verify_identity").asserts(
                "identity_verified", when=lambda r: r.output["verified"]
            ),
            acorn.after("issue_refund").asserts("refund_issued"),
        ],
    )
    agent.attach(library)
    return agent, world, library


def test_agent_bundle_run_and_reuse():
    agent, world, library = _bundle()
    script = [
        ModelTurn(tool_calls=[ToolCall("verify_identity", {"customer_id": "c1"})]),
        ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
        ModelTurn(text="done"),
    ]
    agent.model = MockModel(list(script))
    r1 = agent.run("refund o1")
    assert r1.status == "completed" and world["refunds"] == ["o1"]
    # Second run reuses the same compiled library, fresh control state.
    agent.model = MockModel(list(script))
    r2 = agent.run("refund o1 again")
    assert r2.status == "completed" and world["refunds"] == ["o1", "o1"]
    assert library._compiled is not None  # compiled once, cached


def test_library_verify_certificates():
    _, _, library = _bundle()
    report = library.verify()
    assert report.ok and report.jointly_satisfiable is True

    # An unsatisfiable custom rule is caught (vacuously false contract).
    bad = acorn.ContractLibrary(
        "bad", [acorn.CustomRule(formula=And(Atom("fact", "p"), Not(Atom("fact", "p"))), name="p and not p")]
    )
    try:
        bad.verify()
        raise AssertionError("expected ContractConflictError")
    except acorn.ContractConflictError:
        pass


def test_stream_yields_frames():
    agent, world, _ = _bundle()
    agent.model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"customer_id": "c1"})]),
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
            ModelTurn(text="done"),
        ]
    )
    frames = list(agent.stream("refund o1"))
    kinds = [f.kind for f in frames]
    assert kinds == ["neural_choice", "neural_choice", "neural_choice", "final"]
    # Frame 0: issue_refund masked (identity not verified) AND the
    # premature proposal was blocked at the hard boundary.
    assert any(m["tool"] == "issue_refund" for m in frames[0].masked)
    assert frames[0].blocked and frames[0].blocked[0]["tool"] == "issue_refund"
    assert agent.last_result.status == "completed"


def test_initial_facts_preseed():
    agent, world, _ = _bundle()
    agent.model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
            ModelTurn(text="done"),
        ]
    )
    # Pre-seeded environment fact: identity already verified upstream.
    result = agent.run("refund o1", facts={"identity_verified": True})
    assert result.blocked_proposals == 0 and world["refunds"] == ["o1"]


def test_graphflow_phases_and_fact_driven_transition():
    agent, world, _ = _bundle()
    flow = (
        acorn.GraphFlow(start="verify")
        .state(
            "verify",
            tools=["verify_identity"],
            next=lambda ctx: "work" if ctx.facts.truthy("identity_verified") else None,
        )
        .state(
            "work",
            tools=["issue_refund"],
            next=lambda ctx: "done" if ctx.facts.truthy("refund_issued") else None,
        )
        .state("done", tools=[], terminal=True)
    )
    agent.flow = flow
    agent.model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"customer_id": "c1"})]),
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
        ]
    )
    result = agent.run("refund o1")
    # Phase gating: first model call saw only verify_identity (A_agent),
    # second saw only issue_refund.
    assert agent.model.calls[0]["tools"] == ["verify_identity"]
    assert agent.model.calls[1]["tools"] == ["issue_refund"]
    # Terminal state ended the run without a final text turn.
    assert result.status == "completed" and world["refunds"] == ["o1"]
    assert flow.current == "done"


def test_condition_independent_audit():
    """The same library audits every condition: baseline runs reveal their
    violations; enforce runs must audit clean (soundness invariant)."""
    agent, world, library = _bundle()

    # Baseline arm: no enforcement, same registry, auditor observes.
    base = acorn.Agent(
        model=MockModel(
            [
                ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 5.0})]),
                ModelTurn(text="done"),
            ]
        ),
        tools=agent.registry,
    )
    r = base.run("refund o1", auditor=library.auditor())
    assert r.blocked_proposals == 0 and world["refunds"] == ["o1"]  # nothing enforced
    assert r.audit is not None and r.audit["proc_clean"] is False
    assert any(
        "identity_verified" in rule
        for f in r.audit["committed_violations"]
        for rule in f["contracts"]
    )

    # Enforce arm: same model behavior corrected by control; audit is clean.
    agent.model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"customer_id": "c1"})]),
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o2", "amount": 5.0})]),
            ModelTurn(text="done"),
        ]
    )
    r2 = agent.run("refund o2", auditor=library.auditor())
    assert r2.audit is not None and r2.audit["proc_clean"] is True
    assert r2.audit["violation_count"] == 0


def test_residual_policy_cache_equivalence_and_hits():
    """Cache ON must make decision-for-decision identical calls to cache
    OFF (differential), and repeated tasks must hit the cache."""
    from acorn.models import MockModel, ModelTurn, ToolCall

    def script():
        return [
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o", "amount": 1.0})]),
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"customer_id": "c"})]),
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o", "amount": 1.0})]),
            ModelTurn(text="done"),
        ]

    masked_seq = {}
    for cached in (False, True):
        agent, world, _ = _bundle()
        agent.probe_cache = None
        if cached:
            from acorn.cache import ResidualPolicyCache

            agent.probe_cache = ResidualPolicyCache()
        seq = []
        for _ in range(3):  # repeated tasks -> cross-run reuse
            agent.model = MockModel(script())
            frames = list(agent.stream("refund o"))
            seq.append([(f.kind, tuple(sorted(m["tool"] for m in f.masked))) for f in frames])
        masked_seq[cached] = seq
        if cached:
            stats = agent.probe_cache.stats()
            assert stats["hits"] > 0, stats
            assert stats["hit_rate"] > 0.5, stats  # runs 2-3 fully reuse run 1
    assert masked_seq[False] == masked_seq[True]  # identical decisions


def test_unknown_tool_feedback_lists_available_tools():
    import json
    import acorn
    from acorn.models import MockModel, ModelTurn, ToolCall
    from acorn.tools import ToolRegistry

    reg = ToolRegistry()
    # Two tools with required args: no singleton jump, so the model is asked.
    schema = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}
    reg.tool(lambda x: {"ok": True}, name="real_tool", description="d", parameters=schema)
    reg.tool(lambda x: {"ok": True}, name="other_tool", description="d", parameters=schema)
    model = MockModel([
        ModelTurn(tool_calls=[ToolCall("made_up_tool", {})]),
        ModelTurn(text="done"),
    ])
    agent = acorn.Agent(model, tools=reg, instructions="x", max_steps=4)
    result = agent.run("go")
    feedback = [m for m in result.flow.build_context() if m.get("role") == "tool"]
    assert feedback and "available_tools" in feedback[0]["content"]
    assert "real_tool" in feedback[0]["content"]
