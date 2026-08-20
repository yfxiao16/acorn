"""Amazon SOP-Bench video_classification adapter — deterministic tests.

No API calls. The pure-rule test replays every labeled row's tool outputs
through the decision rules. Expected fit (documented in the module
docstring): everything except (a) the two label-contradictory technical
rows vid_00171/vid_00164, and (b) the escalated Bullying-only rows where
the Warning-vs-Strike judgment is semantic (binder abstains); their
rule-determined parts are still checked.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from acorn.facts import FactStore
from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/video_classification_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")

KNOWN_LABEL_NOISE = {"vid_00171", "vid_00164"}  # contradictory (format, resolution) labels


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def _facts_from_row(row) -> FactStore:
    f = FactStore()
    f.assert_fact("format", row["format"])
    f.assert_fact("resolution", row["resolution"])
    f.assert_fact("detected_categories", row["detected_categories"])
    f.assert_fact("confidence_scores", row["confidence_scores"])
    f.assert_fact("moderation_notes", row["moderation_notes"])
    return f


def test_output_columns_cover_all_pack_tools(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    spec_names = {s["name"] for s in pack.specs}
    assert spec_names == set(vc.OUTPUT_COLUMNS)
    graded = set(vc.GRADED_FIELDS)
    for tool, cols in vc.OUTPUT_COLUMNS.items():
        for col in cols:
            assert col in pack.rows[0], (tool, col)
            assert col not in graded, f"{tool} would leak ground truth {col}"


def test_rules_match_ground_truth_on_every_labeled_row(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    mismatches, residue = {}, []
    for row in pack.rows:
        final = vc.compute_final(_facts_from_row(row))
        want, got = vc.grade(row, final)
        if final is None:  # escalated Bullying-only: semantic residue
            residue.append(row["video_id"])
            # the rule-determined parts of the package must still hold
            assert want["escalated"] is True
            assert want["content_warning_applied"] is True
            assert want["final_decision"] == "remove"
            assert "remove" in want["moderation_actions"]
            continue
        diff = {k: (got[k], want[k]) for k in want if got[k] != want[k]}
        if diff:
            mismatches[row["video_id"]] = diff
    # The only mismatches are the two documented label-contradictory rows,
    # and only on final_decision.
    assert set(mismatches) <= KNOWN_LABEL_NOISE, mismatches
    assert all(set(d) == {"final_decision"} for d in mismatches.values()), mismatches
    assert residue, "expected escalated Bullying-only rows in the dev set"


def test_non_escalated_allow_row_jumps_after_review(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    row = next(
        r for r in pack.rows
        if r["escalated"] == "False" and r["final_decision"] == "Allow"
        and r["detected_categories"] in ("", "[]") and r["video_id"] not in KNOWN_LABEL_NOISE
    )
    vid, path = row["video_id"], row["video_path"]
    model = MockModel(
        [
            # Premature review -> masked/blocked (reviewer not yet assigned).
            ModelTurn(tool_calls=[ToolCall("getReview", {"video_id": vid, "initial_reviewer_id": "x"})]),
            ModelTurn(tool_calls=[ToolCall("validateVideo", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("assignReviewer", {"video_id": vid, "video_language": row["video_language"], "region": row["region"]})]),
            ModelTurn(tool_calls=[ToolCall("getReview", {"video_id": vid, "initial_reviewer_id": row["initial_reviewer_id"]})]),
        ]
    )
    submitted, result = vc.run_row(lambda: model, pack, row, condition="acorn")
    want, got = vc.grade(row, submitted)
    assert got == want
    assert got["final_decision"] == "allow" and got["escalated"] is False
    assert result.blocked_proposals >= 1
    assert result.symbolic_steps == 1  # final package submitted via jump
    assert result.status == "completed"


def test_escalated_row_full_pipeline_with_jump(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    row = next(
        r for r in pack.rows
        if r["escalated"] == "True"
        and set(ast.literal_eval(r["detected_categories"])) not in ({"Bullying"}, {"Violence"})
    )
    vid, path = row["video_id"], row["video_path"]
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("validateVideo", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("assignReviewer", {"video_id": vid, "video_language": row["video_language"], "region": row["region"]})]),
            ModelTurn(tool_calls=[ToolCall("getReview", {"video_id": vid, "initial_reviewer_id": row["initial_reviewer_id"]})]),
            ModelTurn(tool_calls=[ToolCall("submitContentModeration", {"video_id": vid, "initial_reviewer_id": row["initial_reviewer_id"]})]),
            ModelTurn(tool_calls=[ToolCall("implementModeration", {"video_id": vid, "moderator_id": row["moderator_id"]})]),
        ]
    )
    submitted, result = vc.run_row(lambda: model, pack, row, condition="acorn")
    want, got = vc.grade(row, submitted)
    assert got == want, (got, want)
    assert got["final_decision"] == "remove" and got["escalated"] is True
    assert result.symbolic_steps == 1
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_bullying_residue_binder_abstains_model_decides(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    row = next(
        r for r in pack.rows
        if r["escalated"] == "True"
        and set(ast.literal_eval(r["detected_categories"])) == {"Bullying"}
    )
    vid, path = row["video_id"], row["video_path"]
    gt_actions = ast.literal_eval(row["moderation_actions"])
    model = MockModel(
        [
            ModelTurn(tool_calls=[ToolCall("validateVideo", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("assignReviewer", {"video_id": vid, "video_language": row["video_language"], "region": row["region"]})]),
            ModelTurn(tool_calls=[ToolCall("getReview", {"video_id": vid, "initial_reviewer_id": row["initial_reviewer_id"]})]),
            ModelTurn(tool_calls=[ToolCall("submitContentModeration", {"video_id": vid, "initial_reviewer_id": row["initial_reviewer_id"]})]),
            ModelTurn(tool_calls=[ToolCall("implementModeration", {"video_id": vid, "moderator_id": row["moderator_id"]})]),
            # Binder abstained (semantic Warning-vs-Strike): the model
            # supplies the final package itself.
            ModelTurn(tool_calls=[ToolCall("submit_result", {
                "escalated": True,
                "moderation_actions": gt_actions,
                "age_rating": row["age_rating"],
                "content_warning_applied": True,
                "final_decision": "Remove",
                "reason": "Escalated bullying content removed per moderator notes.",
            })]),
        ]
    )
    submitted, result = vc.run_row(lambda: model, pack, row, condition="acorn")
    want, got = vc.grade(row, submitted)
    assert got == want, (got, want)
    assert result.symbolic_steps == 0  # no jump: the model made the final call
    assert result.status == "completed"


def test_parse_text_answer_official_format():
    from benchmarks.amazon_sopbench import video_classification as vc

    text = (
        "<final_output>{'video_id': 'vid_1', 'Escalated': True, "
        "'Moderation_actions': ['Strike Issued', 'Remove'], 'Age Rating': '18+', "
        "'Content_warning': True, 'Final Decision': ['Removal'], 'Reason': 'x'}</final_output>"
    )
    parsed = vc.parse_text_answer(text)
    assert parsed["escalated"] is True
    assert parsed["final_decision"] == ["Removal"]
    row = {
        "escalated": "True",
        "moderation_actions": "['Remove', 'Strike Issued']",
        "content_warning_applied": "True",
        "final_decision": "Remove",
    }
    want, got = vc.grade(row, parsed)
    assert got == want


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import video_classification as vc

    report = vc.build_library().verify()
    assert report.ok
