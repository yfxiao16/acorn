"""Shared toy domain: customer-service refund desk.

Procedure under test:
* issue_refund REQUIRES identity_verified and fraud_checked
* verify_identity's result establishes identity_verified
* check_fraud establishes fraud_checked, and fraud_detected when fraud found
* fraud_detected OBLIGATES freeze_account (args bound from facts)
* change_identity_document INVALIDATES identity_verified
* issue_refund at most 1 time
"""

from __future__ import annotations

import pytest

import acorn


@pytest.fixture
def world():
    return {"frozen": [], "refunds": [], "fraud": False}


@pytest.fixture
def registry(world):
    reg = acorn.ToolRegistry()

    @reg.tool
    def verify_identity(user_id: str) -> dict:
        "Verify the customer's identity."
        return {"verified": True, "user_id": user_id}

    @reg.tool
    def check_fraud(user_id: str) -> dict:
        "Run the fraud check for a customer."
        return {"fraud": world["fraud"], "user_id": user_id}

    @reg.tool
    def issue_refund(order_id: str, amount: float) -> dict:
        "Issue a refund for an order."
        world["refunds"].append((order_id, amount))
        return {"refunded": True}

    @reg.tool
    def freeze_account(user_id: str) -> dict:
        "Freeze the customer's account."
        world["frozen"].append(user_id)
        return {"frozen": True}

    @reg.tool
    def change_identity_document(user_id: str, document: str) -> dict:
        "Update the customer's identity document on file."
        return {"updated": True}

    @reg.tool
    def escalate(reason: str) -> dict:
        "Escalate to a human agent."
        return {"escalated": True}

    return reg


@pytest.fixture
def contracts():
    return [
        acorn.action("issue_refund").requires("identity_verified", "fraud_checked").at_most(1),
        acorn.action("issue_refund").forbidden_when("fraud_detected"),
        acorn.after("verify_identity").asserts(
            "identity_verified",
            when=lambda r: r.output.get("verified"),
            metadata=lambda r: {"user_id": r.output.get("user_id")},
        ),
        acorn.after("check_fraud")
        .asserts("fraud_checked")
        .asserts(
            "fraud_detected",
            when=lambda r: r.output.get("fraud"),
            metadata=lambda r: {"user_id": r.output.get("user_id")},
        ),
        acorn.after("change_identity_document").invalidates("identity_verified"),
        acorn.when("fraud_detected").obligates(
            "freeze_account",
            binder=lambda ctx: (
                {"user_id": ctx.facts.get("fraud_detected").metadata.get("user_id")}
                if ctx.facts.get("fraud_detected")
                else None
            ),
            desc="fraud detected: freeze the account immediately",
        ),
    ]


@pytest.fixture
def controller(contracts, registry):
    return acorn.SymbolicController(contracts, registry=registry)


def execute_and_commit(controller, registry, tool, args):
    """Helper: run a tool for real and commit it into the controller."""
    action = acorn.ProposedAction(tool, args)
    result = acorn.ToolExecutor(registry).execute(action)
    controller.update(action, result)
    return result
