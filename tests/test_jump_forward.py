"""Symbolic control handoff: obligations preempt neural control; a
single admissible action with determined arguments executes without the
model."""

from __future__ import annotations

import acorn
from tests.conftest import execute_and_commit


def test_obligation_triggers_symbolic_execution(controller, registry, world):
    world["fraud"] = True
    execute_and_commit(controller, registry, "check_fraud", {"user_id": "u9"})

    decision = controller.next_decision(registry.names())
    assert decision.kind is acorn.StepKind.SYMBOLIC_EXECUTE
    assert decision.action.tool == "freeze_account"
    assert decision.action.args == {"user_id": "u9"}  # bound from fact metadata

    # Execute + commit discharges the obligation; control returns to neural.
    execute_and_commit(controller, registry, "freeze_account", decision.action.args)
    assert not controller.obligations.pending()
    after = controller.next_decision(registry.names())
    assert after.kind is acorn.StepKind.NEURAL_CHOICE


def test_obligation_without_binder_narrows_to_singleton(registry):
    contracts = [
        acorn.when("fraud_detected").obligates("freeze_account", desc="freeze on fraud"),
    ]
    controller = acorn.SymbolicController(contracts, registry=registry)
    controller.assert_fact("fraud_detected", True)

    decision = controller.next_decision(registry.names())
    # freeze_account requires user_id (no binder) -> the LLM decides,
    # but only over the obligated action.
    assert decision.kind is acorn.StepKind.NEURAL_CHOICE
    assert decision.actions == ["freeze_account"]


def test_single_admissible_action_with_binder_jumps(registry):
    reg = acorn.ToolRegistry()

    @reg.tool(args_binder=lambda ctx: {"user_id": ctx.facts.value("customer_id")})
    def login_user(user_id: str) -> dict:
        "Log the user in."
        return {"logged_in": True}

    @reg.tool
    def issue_refund(order_id: str) -> dict:
        "Issue a refund."
        return {"refunded": True}

    contracts = [acorn.action("issue_refund").requires("logged_in")]
    controller = acorn.SymbolicController(contracts, registry=reg)
    controller.assert_fact("customer_id", "u42")

    # issue_refund is masked; only login_user is admissible and its args
    # are procedurally determined -> jump-forward.
    decision = controller.next_decision(reg.names())
    assert decision.kind is acorn.StepKind.SYMBOLIC_EXECUTE
    assert decision.action.tool == "login_user"
    assert decision.action.args == {"user_id": "u42"}


def test_pending_obligation_reported_at_finalize(registry):
    contracts = [acorn.when("fraud_detected").obligates("freeze_account", desc="freeze on fraud")]
    controller = acorn.SymbolicController(contracts, registry=registry)
    controller.assert_fact("fraud_detected", True)

    report = controller.finalize()
    assert report["pending_obligations"] == ["freeze on fraud"]


def test_eventually_obligation_floor_yield_gate(registry):
    """deadline='eventually' does not preempt, but a text-only answer may
    not end the run while it is pending — ACORN discharges it (jump) at
    the floor-yield boundary."""
    from acorn.models import MockModel, ModelTurn, ToolCall

    contracts = [
        acorn.after("check_fraud").asserts(
            "fraud_case_opened", metadata=lambda r: {"user_id": r.output.get("user_id")}
        ),
        acorn.when("fraud_case_opened").obligates(
            "freeze_account",
            deadline="eventually",
            binder=lambda ctx: {"user_id": ctx.facts.get("fraud_case_opened").metadata["user_id"]},
            desc="verify-after-modify style follow-up",
        ),
    ]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("check_fraud", {"user_id": "u5"})]),
            # Model tries to finish immediately — the gate must fire first.
            ModelTurn(text="All done!"),
            ModelTurn(text="All done!"),
        ]
    )
    result = acorn.run("case for u5", model=model, tools=registry, contracts=contracts)
    assert result.status == "completed"
    assert result.symbolic_steps == 1  # freeze executed at the yield boundary
    assert not result.finalize["pending_obligations"]
    # And it did NOT preempt: the tool ran only after the model tried to finish.
    kinds = [r["kind"] for r in result.tracer.records if r["kind"] == "action/symbolic"]
    assert len(kinds) == 1
