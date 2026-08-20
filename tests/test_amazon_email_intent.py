"""Amazon SOP-Bench email_intent adapter — deterministic tests.

No API calls. Intent classification is the domain's one semantic decision
(it stays with the model); the pure-rule test verifies that everything
downstream of a recorded intent — product_id extraction and the
intent -> action mapping — reproduces the ground truth on all labeled rows.
"""

from __future__ import annotations

import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/email_intent_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_rules_match_ground_truth_on_every_labeled_row(pack):
    """product_id extraction (§5.1) and intent->action (§5.2) are exact
    on all labeled rows; given the GT intent (the model's semantic input),
    the binder reproduces both graded fields."""
    from benchmarks.amazon_sopbench import email_intent as ei

    mismatches = []
    for row in pack.rows:
        assert ei.extract_product_id(row["email_body"]) == row["product_id"], row["email_id"]
        facts = FactStore()
        facts.assert_fact("email_id", row["email_id"])
        facts.assert_fact("product_id", row["product_id"])
        facts.assert_fact("seller_intent", row["seller_intent"])
        want, got = ei.grade(row, ei.compute_final(facts))
        if got != want:
            mismatches.append((row["email_id"], got, want))
    assert not mismatches, f"{len(mismatches)} mismatches, first 3: {mismatches[:3]}"


def test_pricing_branch_full_procedure_with_jump(pack):
    from benchmarks.amazon_sopbench import email_intent as ei

    row = next(r for r in pack.rows if r["seller_intent"] == "concern about incorrect pricing")
    pid = row["product_id"]
    model = MockModel(
        [
            # Premature second price lookup exercises at_most(1) later;
            # first: classify, then fetch the branch evidence.
            ModelTurn(tool_calls=[ToolCall("get_product_price", {"product_id": pid})]),
            ModelTurn(tool_calls=[ToolCall("get_product_price", {"product_id": pid})]),  # blocked: at_most(1)
            ModelTurn(tool_calls=[ToolCall("classify_intent", {"seller_intent": row["seller_intent"]})]),
        ]
    )
    submitted, result = ei.run_row(lambda: model, pack, row, condition="acorn")
    want, got = ei.grade(row, submitted)
    assert got == want, (got, want)
    assert result.blocked_proposals == 1  # duplicate price lookup was caught
    assert result.symbolic_steps == 1  # final record submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_not_listed_branch_requires_status_and_inventory(pack):
    from benchmarks.amazon_sopbench import email_intent as ei

    row = next(
        r for r in pack.rows if r["seller_intent"] == "concern about their product not being listed"
    )
    pid = row["product_id"]
    mkt = row["marketplace_id"]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("classify_intent", {"seller_intent": row["seller_intent"]})]),
            # Listing status alone is not enough (§5.2 wants status AND inventory).
            ModelTurn(tool_calls=[ToolCall("get_product_listing_status", {"product_id": pid, "marketplace_id": mkt})]),
            ModelTurn(tool_calls=[ToolCall("get_inventory_status", {"product_id": pid, "marketplace_id": mkt})]),
        ]
    )
    submitted, result = ei.run_row(lambda: model, pack, row, condition="acorn")
    want, got = ei.grade(row, submitted)
    assert got == want, (got, want)
    assert result.symbolic_steps == 1
    assert result.status == "completed"


def test_generic_branch_is_one_model_call(pack):
    from benchmarks.amazon_sopbench import email_intent as ei

    row = next(r for r in pack.rows if r["seller_intent"] == "generic question about a listing")
    model = MockModel(
        [ModelTurn(tool_calls=[ToolCall("classify_intent", {"seller_intent": row["seller_intent"]})])]
    )
    submitted, result = ei.run_row(lambda: model, pack, row, condition="acorn")
    want, got = ei.grade(row, submitted)
    assert got == want
    assert result.model_calls == 1 and result.symbolic_steps == 1  # submit was a jump
    assert result.status == "completed"


def test_parse_text_answer_official_tags():
    from benchmarks.amazon_sopbench import email_intent as ei

    text = (
        "<email_id>E1001</email_id>\n<product_id>P12A3B</product_id>\n"
        "<seller intent>concern about incorrect pricing</seller intent>\n"
        "<action>update price</action>"
    )
    parsed = ei.parse_text_answer(text)
    assert parsed == {
        "seller_intent": "concern about incorrect pricing",
        "action": "update price",
    }


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import email_intent as ei

    report = ei.build_library().verify()
    assert report.ok
