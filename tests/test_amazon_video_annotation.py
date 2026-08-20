"""Amazon SOP-Bench video_annotation adapter — deterministic tests.

No API calls. The pure-rule test replays every labeled row through the six
gate predicates and must reproduce ``final_status`` on all 125 dev rows.
"""

from __future__ import annotations

import pathlib

import pytest

from acorn.models import MockModel, ModelTurn, ToolCall

DATA = pathlib.Path(__file__).resolve().parent.parent / "benchmarks/amazon_sopbench/data/video_annotation_sop"
pytestmark = pytest.mark.skipif(not DATA.exists(), reason="SOP-Bench pack data not downloaded")


@pytest.fixture(scope="module")
def pack():
    from benchmarks.amazon_sopbench.pack import load_pack

    return load_pack(DATA)


def test_output_columns_cover_all_pack_tools(pack):
    from benchmarks.amazon_sopbench import video_annotation as va

    spec_names = {s["name"] for s in pack.specs}
    assert spec_names == set(va.OUTPUT_COLUMNS)
    for tool, cols in va.OUTPUT_COLUMNS.items():
        for col in cols:
            assert col in pack.rows[0], (tool, col)


def test_gate_rules_match_ground_truth_on_every_labeled_row(pack):
    from benchmarks.amazon_sopbench import video_annotation as va

    mismatches = []
    for row in pack.rows:
        # Row columns use the same names as the tool outputs, so the row
        # itself is a valid "output" for every gate predicate.
        ok = all(fn(row) for fn in va.GATE_FNS.values())
        if ok != (row["final_status"] == "True"):
            mismatches.append(row[pack.key_field])
    assert not mismatches, f"{len(mismatches)} mismatches: {mismatches[:5]}"


def test_invalid_video_early_exit_single_model_call(pack):
    from benchmarks.amazon_sopbench import video_annotation as va

    row = next(r for r in pack.rows if not va.video_ok(r))
    model = MockModel(
        [ModelTurn(tool_calls=[ToolCall("validateVideoFormat", {"video_id": row["video_id"]})])]
    )
    submitted, result = va.run_row(lambda: model, pack, row, condition="acorn")
    want, got = va.grade(row, submitted)
    assert got == want == {"final_status": False}
    assert result.model_calls == 1 and result.symbolic_steps == 1  # submit was a jump
    assert result.status == "completed"


def test_full_pipeline_with_jump_and_masked_distractor(pack):
    from benchmarks.amazon_sopbench import video_annotation as va

    row = next(
        r for r in pack.rows
        if r["final_status"] == "True"
    )
    vid, path = row["video_id"], row["video_path"]
    model = MockModel(
        [
            # Premature detection AND a distractor tool: both outside the
            # validate stage's exposure -> blocked, exercising the mask.
            ModelTurn(tool_calls=[ToolCall("performObjectDetection", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("validateVideoFormat", {"video_id": vid})]),
            ModelTurn(tool_calls=[ToolCall("validateLidarData", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("performObjectDetection", {"video_id": vid, "video_path": path})]),
            ModelTurn(tool_calls=[ToolCall("executeSegmentation", {
                "video_id": vid, "predicted_object": row["predicted_object"],
                "object_detection_output_path": row["object_detection_output_path"],
                "output_format_object_detection": row["output_format_object_detection"],
            })]),
            ModelTurn(tool_calls=[ToolCall("runAutomatedQC", {
                "video_id": vid, "video_path": path,
                "predicted_object": row["predicted_object"],
                "predicted_iou": float(row["predicted_iou"]),
                "segmentation_output_path": row["segmentation_output_path"],
                "object_detection_output_path": row["object_detection_output_path"],
            })]),
            ModelTurn(tool_calls=[ToolCall("performHumanValidation", {
                "video_id": vid, "predicted_object": row["predicted_object"],
                "predicted_iou": float(row["predicted_iou"]),
                "segmentation_output_path": row["segmentation_output_path"],
                "object_detection_output_path": row["object_detection_output_path"],
            })]),
        ]
    )
    submitted, result = va.run_row(lambda: model, pack, row, condition="acorn")
    want, got = va.grade(row, submitted)
    assert got == want == {"final_status": True}
    assert submitted["coco_json_path"] == row["object_detection_output_path"]
    assert submitted["segmentation_mask_path"] == row["segmentation_output_path"]
    assert result.blocked_proposals >= 1  # premature detection was caught
    assert result.symbolic_steps == 1  # final output submitted via jump
    assert result.status == "completed"
    assert result.audit and result.audit["proc_clean"] is True


def test_parse_text_answer_official_format():
    from benchmarks.amazon_sopbench import video_annotation as va

    text = (
        'blah <final_output>{"Final Status": "True", "CoCo JSON path": "/a.json", '
        '"Segmentation mask path": "/a.binary", "Inter annotator score": 0.9, '
        '"Reason": ""}</final_output>'
    )
    parsed = va.parse_text_answer(text)
    assert parsed["final_status"] == "True"
    assert parsed["coco_json_path"] == "/a.json"
    row = {"final_status": "True"}
    want, got = va.grade(row, parsed)
    assert got == want


def test_library_certificates(pack):
    from benchmarks.amazon_sopbench import video_annotation as va

    report = va.build_library().verify()
    assert report.ok
