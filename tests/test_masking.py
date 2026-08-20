"""Dynamic action-space compilation: admissible_actions over facts,
precedence, rate limits, and invalidation."""

from __future__ import annotations

import acorn
from tests.conftest import execute_and_commit


def test_requires_masks_until_facts_established(controller, registry):
    candidates = registry.names()

    admissible = controller.admissible_actions(candidates)
    assert "issue_refund" not in admissible
    assert "verify_identity" in admissible
    assert "check_fraud" in admissible

    execute_and_commit(controller, registry, "verify_identity", {"user_id": "u1"})
    assert "issue_refund" not in controller.admissible_actions(candidates)

    execute_and_commit(controller, registry, "check_fraud", {"user_id": "u1"})
    assert "issue_refund" in controller.admissible_actions(candidates)


def test_invalidation_retracts_admissibility(controller, registry):
    candidates = registry.names()
    execute_and_commit(controller, registry, "verify_identity", {"user_id": "u1"})
    execute_and_commit(controller, registry, "check_fraud", {"user_id": "u1"})
    assert "issue_refund" in controller.admissible_actions(candidates)

    execute_and_commit(
        controller, registry, "change_identity_document", {"user_id": "u1", "document": "passport"}
    )
    assert not controller.facts.truthy("identity_verified")
    assert "issue_refund" not in controller.admissible_actions(candidates)


def test_rate_limit_masks_after_use(controller, registry):
    candidates = registry.names()
    execute_and_commit(controller, registry, "verify_identity", {"user_id": "u1"})
    execute_and_commit(controller, registry, "check_fraud", {"user_id": "u1"})
    execute_and_commit(controller, registry, "issue_refund", {"order_id": "o1", "amount": 10.0})
    # at_most(1): a second refund is no longer admissible
    assert "issue_refund" not in controller.admissible_actions(candidates)


def test_forbidden_when_is_hard_block(controller, registry, world):
    world["fraud"] = True
    execute_and_commit(controller, registry, "verify_identity", {"user_id": "u1"})
    execute_and_commit(controller, registry, "check_fraud", {"user_id": "u1"})
    assert controller.facts.truthy("fraud_detected")

    decision = controller.validate(acorn.ProposedAction("issue_refund", {"order_id": "o1", "amount": 5.0}))
    assert decision.kind is acorn.DecisionKind.BLOCK


def test_validate_returns_require_with_hints(controller):
    decision = controller.validate(
        acorn.ProposedAction("issue_refund", {"order_id": "o1", "amount": 5.0})
    )
    assert decision.kind is acorn.DecisionKind.REQUIRE
    assert "identity_verified" in decision.requirements
    assert any("verify_identity" in h for h in decision.hints)
    # The feedback message names the concrete recovery tool.
    assert "verify_identity" in decision.message(acorn.ProposedAction("issue_refund", {}))


def test_precedence_rule():
    reg = acorn.ToolRegistry()

    @reg.tool
    def check_policy() -> dict:
        "Check policy."
        return {}

    @reg.tool
    def approve_loan(loan_id: str) -> dict:
        "Approve a loan."
        return {}

    controller = acorn.SymbolicController(
        [acorn.action("approve_loan").requires_before("check_policy")], registry=reg
    )
    assert "approve_loan" not in controller.admissible_actions(reg.names())
    execute_and_commit(controller, reg, "check_policy", {})
    assert "approve_loan" in controller.admissible_actions(reg.names())
