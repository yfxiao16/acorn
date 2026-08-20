"""Know Your Business adapter — deterministic tests (no API calls)."""
from __future__ import annotations

import pathlib

import pytest

from acorn.models import MockModel, ModelTurn, ToolCall

DATA = (
    pathlib.Path(__file__).resolve().parent.parent
    / "benchmarks/amazon_sopbench/data/know_your_business_sop"
)
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_hard_gates_lock_the_labeled_split(pack):
    """The documented honest boundary, replayed over all 90 rows:
    every ``approved`` row is flag-free (the no-approve gate has zero
    counterexamples); flags fire on all ``awaiting`` rows and all but
    the two judgment-call ``escalate`` rows."""
    from benchmarks.amazon_sopbench import know_your_business as kyb

    flagged_by_class: dict[str, list[bool]] = {}
    for row in pack.rows:
        flags = kyb.compute_flags(row)
        flagged_by_class.setdefault(row["escalation_status"], []).append(any(flags.values()))
    assert not any(flagged_by_class["approved"])
    assert all(flagged_by_class["awaiting information"])
    assert flagged_by_class["escalate"].count(False) == 2  # semantic residue


def test_chain_jumps_and_approve_gate_blocks(pack):
    from benchmarks.amazon_sopbench import know_your_business as kyb

    row = next(
        r
        for r in pack.rows
        if r["escalation_status"] == "escalate" and any(kyb.compute_flags(r).values())
    )
    bid = row["business_id"]
    model = MockModel(
        [
            # The chain up to submit runs symbolically; the model's first
            # real decision is the verdict. It tries "approved" with risk
            # flags set -> hard-blocked by no_approve_with_risk_flags.
            ModelTurn(
                tool_calls=[
                    ToolCall(
                        "submit_result",
                        {
                            "business_id": bid,
                            "escalation_status": "approved",
                            "reason": "looks fine",
                        },
                    )
                ]
            ),
            ModelTurn(
                tool_calls=[
                    ToolCall(
                        "submit_result",
                        {
                            "business_id": bid,
                            "escalation_status": "escalate",
                            "reason": "risk flags present",
                        },
                    )
                ]
            ),
            ModelTurn(text="Escalated per SOP."),
        ]
    )
    submitted, result = kyb.run_row(lambda: model, pack, row, condition="acorn")
    want, got = kyb.grade(row, submitted)
    assert got == want
    assert result.blocked_proposals == 1
    assert result.symbolic_steps >= 8  # the whole verification chain jumped
    assert result.status == "completed"


def test_parse_text_answer_variants():
    from benchmarks.amazon_sopbench import know_your_business as kyb

    got = kyb.parse_text_answer(
        "<final_output>{'business_id': 'biz_001', 'escalation_status': 'escalate', "
        "'reason': 'expired license'}</final_output>"
    )
    assert kyb._norm_verdict(got["escalation_status"]) == "escalate"
    got = kyb.parse_text_answer('{"escalation_status": "Awaiting Information"}')
    assert kyb._norm_verdict(got["escalation_status"]) == "awaiting information"
    assert kyb.parse_text_answer("no verdict here") is None
