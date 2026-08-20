"""Amazon SOP-Bench content_flagging adapter — deterministic tests.

No API calls. All three graded fields are per-tool outputs relayed from
the labeled CSV; the pure-relay test replays them through the fact/binder
logic on every row, and a separate test documents the induced decision
structure (CSI thresholds + UTS tie-break) as internally consistent.
"""

from __future__ import annotations

import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/content_flagging_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_relay_matches_ground_truth_on_every_row(pack):
    from benchmarks.amazon_sopbench import content_flagging as cf

    for row in pack.rows:
        facts = FactStore()
        facts.assert_fact("user_trust_score", int(float(row["user_trust_score"])))
        facts.assert_fact("content_severity_index", int(float(row["content_severity_index"])))
        facts.assert_fact("final_decision", row["final_decision"])
        want, got = cf.grade(row, cf.compute_final(facts))
        assert got == want, (row[pack.key_field], got, want)


def test_induced_decision_structure_holds_on_every_row(pack):
    """Cross-validation of the documented label structure (not used by
    the binder): final_decision follows CSI thresholds with a UTS
    tie-break at CSI==85 on all labeled rows."""
    from benchmarks.amazon_sopbench import content_flagging as cf

    for row in pack.rows:
        pred = cf.induced_decision(
            int(float(row["content_severity_index"])), int(float(row["user_trust_score"]))
        )
        assert pred == row["final_decision"], (row[pack.key_field], pred, row["final_decision"])


def test_full_procedure_ordering_and_jump(pack):
    from benchmarks.amazon_sopbench import content_flagging as cf

    row = pack.rows[0]
    cid, uid = row["content_id"], row["userid"]
    model = MockModel(
        [
            # Trust score FIRST -> blocked (schema consumes BPI + DCS);
            # proposed anyway to exercise the hard boundary.
            ModelTurn(tool_calls=[ToolCall("calculate_user_trust_score", {
                "userid": uid,
                "NumberofPreviousPosts": int(row["NumberofPreviousPosts"]),
                "CountofFlaggedPosts": int(row["CountofFlaggedPosts"]),
                "bot_probability_index": 0.5,
                "device_consistency_score": 1.0,
            })]),
            ModelTurn(tool_calls=[ToolCall("calculateBotProbabilityIndex", {
                "userid": uid,
                "is_possible_bot": float(row["is_possible_bot"]),
                "Captcha_tries": int(row["Captcha_tries"]),
                "device_type": row["device_type"],
                "os": row["os"],
                "browser": row["browser"],
            })]),
            ModelTurn(tool_calls=[
                ToolCall("calculate_user_trust_score", {
                    "userid": uid,
                    "NumberofPreviousPosts": int(row["NumberofPreviousPosts"]),
                    "CountofFlaggedPosts": int(row["CountofFlaggedPosts"]),
                    "bot_probability_index": 0.9,
                    "device_consistency_score": 1.0,
                }),
                ToolCall("calculateContentSeverityIndex", {
                    "content_id": cid,
                    "PrimaryViolationType": row["PrimaryViolationType"],
                    "SecondaryViolationType": row["SecondaryViolationType"],
                    "PrimaryViolation_Confidence": float(row["PrimaryViolation_Confidence"]),
                    "SecondaryViolation_Confidence": float(row["SecondaryViolation_Confidence"]),
                }),
            ]),
            ModelTurn(tool_calls=[ToolCall("determineFinalDecision", {
                "content_id": cid,
                "user_trust_score": int(row["user_trust_score"]),
                "content_severity_index": int(row["content_severity_index"]),
                "bot_probability_index": 0.9,
                "NumberofPreviousPosts": int(row["NumberofPreviousPosts"]),
                "CountofFlaggedPosts": int(row["CountofFlaggedPosts"]),
            })]),
        ]
    )
    submitted, result = cf.run_row(lambda: model, pack, row, condition="acorn")
    want, got = cf.grade(row, submitted)
    assert got == want, (got, want)
    assert result.blocked_proposals == 1  # premature trust score was caught
    assert result.symbolic_steps == 1  # decision package submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_sop_bpi_rules():
    from benchmarks.amazon_sopbench import content_flagging as cf

    assert cf.sop_bpi(0.95, 5) == 0.9
    assert cf.sop_bpi(0.6, 2) == 0.7
    assert cf.sop_bpi(0.1, 0) == 0.1
    assert cf.sop_bpi(0.4, 1) == 0.4  # outside SOP rules: relay


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import content_flagging as cf

    report = cf.build_library().verify()
    assert report.ok
