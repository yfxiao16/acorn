"""Amazon SOP-Bench dangerous_goods adapter — deterministic smoke tests.

No API calls: scripted MockModel only. Skipped when the challenge-pack
data has not been downloaded (see benchmarks/amazon_sopbench/pack.py).
"""

from __future__ import annotations

import pathlib

import pytest

import acorn
from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/dangerous_goods_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_binder_matches_ground_truth_on_every_labeled_row(pack):
    """compute_result is a verified implementation of SOP §5.1+5.6+5.7:
    replaying the labeled tool outputs through the binder must reproduce
    the final ground truth on all dev rows."""
    from benchmarks.amazon_sopbench.dangerous_goods import (
        PID_RE,
        SCORE_FACTS,
        compute_result,
    )

    mismatches = []
    for row in pack.rows:
        facts = FactStore()
        facts.assert_fact("product_id_valid", bool(PID_RE.match(row[pack.key_field])))
        for fact_name in SCORE_FACTS.values():
            try:
                v = int(float(row[fact_name]))
            except (TypeError, ValueError):
                continue
            if 1 <= v <= 5:  # same filter as the contract extractor
                facts.assert_fact(fact_name, v)
        got = compute_result(facts)
        want = {"hazard_score": int(float(row["hazard_score"])), "hazard_class": row["hazard_class"]}
        if got != want:
            mismatches.append((row[pack.key_field], got, want))
    assert not mismatches, f"{len(mismatches)} mismatches, first 5: {mismatches[:5]}"


def test_valid_row_one_model_call_then_symbolic_submit(pack):
    from benchmarks.amazon_sopbench.dangerous_goods import run_row

    row = pack.row("P_13307")  # scores 4,4,4,3 -> 15 -> Hazard Class C
    pid = row["product_id"]
    script = [
        ModelTurn(
            tool_calls=[
                ToolCall("calculate_sds_label_score", {"product_id": pid, "sds_label_text": row["sds_label_text"]}),
                ToolCall("calculate_handling_score", {"product_id": pid, "handling_and_storage_guidelines": row["handling_and_storage_guidelines"]}),
                ToolCall("calculate_transportation_score", {"product_id": pid, "transportation_requirements": row["transportation_requirements"]}),
                ToolCall("calculate_disposal_score", {"product_id": pid, "disposal_guidelines": row["disposal_guidelines"]}),
            ]
        ),
    ]
    model = MockModel(script)
    submitted, result = run_row(lambda: model, pack, row, condition="acorn")

    assert submitted == {"hazard_score": 15, "hazard_class": "Hazard Class C"}
    assert result.status == "completed"
    assert result.model_calls == 1  # scores gathered in one neural turn
    assert result.symbolic_steps == 1  # the final classification was a jump
    assert not result.finalize["pending_obligations"]


def test_invalid_id_is_fully_symbolic_zero_model_calls(pack):
    from benchmarks.amazon_sopbench.dangerous_goods import run_row

    row = pack.row("P1_3191")  # invalid format -> gate -> 0 / Unable to Decide
    model = MockModel([])  # must never be consulted
    submitted, result = run_row(lambda: model, pack, row, condition="acorn")

    assert submitted == {"hazard_score": 0, "hazard_class": "Unable to Decide"}
    assert result.status == "completed"
    assert result.model_calls == 0
    assert result.symbolic_steps == 1
    assert result.symbolic_execution_ratio == 1.0


def test_score_tools_are_masked_after_single_use(pack):
    """at_most(1): a second call to the same score tool is inadmissible."""
    from benchmarks.amazon_sopbench.dangerous_goods import build_agent

    row = pack.row("P_13307")
    pid = row["product_id"]
    call = ToolCall("calculate_sds_label_score", {"product_id": pid, "sds_label_text": row["sds_label_text"]})
    model = MockModel(
        [
            ModelTurn(tool_calls=[call]),
            ModelTurn(tool_calls=[ToolCall(**vars(call))]),
            ModelTurn(text="stopping"),
        ]
    )
    sink: dict = {}
    agent = build_agent(model, pack, sink, condition="acorn")
    frames = list(agent.stream(f"classify {pid}", facts={"product_id_valid": True}, max_steps=3))
    # Second frame: the used tool no longer appears in the exposed set.
    neural = [f for f in frames if f.kind == "neural_choice"]
    assert "calculate_sds_label_score" in neural[0].exposed
    assert len(neural) >= 2 and "calculate_sds_label_score" not in neural[1].exposed
