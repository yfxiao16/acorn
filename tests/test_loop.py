"""End-to-end runtime loop with a scripted model."""

from __future__ import annotations

import acorn
from acorn.models import MockModel, ModelTurn, ToolCall


def test_blocked_then_recovered_flow(registry, contracts, world):
    model = MockModel(
        [
            # Premature refund: blocked with REQUIRE feedback.
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 10.0})]),
            # Follow the recovery hints.
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"user_id": "u1"})]),
            ModelTurn(tool_calls=[ToolCall("check_fraud", {"user_id": "u1"})]),
            # Retry: now allowed.
            ModelTurn(tool_calls=[ToolCall("issue_refund", {"order_id": "o1", "amount": 10.0})]),
            ModelTurn(text="Refund issued."),
        ]
    )
    result = acorn.run("Refund order o1 for u1", model=model, tools=registry, contracts=contracts)

    assert result.status == "completed"
    assert result.final_text == "Refund issued."
    assert result.blocked_proposals == 1
    assert world["refunds"] == [("o1", 10.0)]
    # Dynamic exposure: the first model call must not see issue_refund.
    assert "issue_refund" not in model.calls[0]["tools"]
    # After prerequisites, issue_refund is exposed again.
    assert "issue_refund" in model.calls[3]["tools"]
    # The blocked call's feedback names the recovery tool.
    feedback = [m for m in result.flow.messages if m["role"] == "tool"][0]["content"]
    assert "verify_identity" in feedback


def test_fraud_path_executes_obligation_without_model(registry, contracts, world):
    world["fraud"] = True
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("verify_identity", {"user_id": "u7"})]),
            ModelTurn(tool_calls=[ToolCall("check_fraud", {"user_id": "u7"})]),
            # By the time the model is consulted again, ACORN has already
            # frozen the account symbolically.
            ModelTurn(text="Account frozen due to fraud; refund not possible."),
        ]
    )
    result = acorn.run("Refund order o1 for u7", model=model, tools=registry, contracts=contracts)

    assert result.status == "completed"
    assert world["frozen"] == ["u7"]  # executed by ACORN, not the model
    assert result.symbolic_steps == 1
    assert result.model_calls == 3
    assert not result.finalize["pending_obligations"]
    # The agent was told about the symbolic step.
    assert any("freeze_account" in m["content"] for m in result.flow.messages if m["role"] == "user")
    # Refund stayed masked on the fraud path.
    assert world["refunds"] == []
    assert result.symbolic_execution_ratio > 0
