"""Video Annotation SOP: hand-authored ACORN contract library + agent.

The largest SOP-Bench tool registry (26 tools) — the dynamic-tool-exposure
stress test. Only SIX tools are real (implemented in the pack's tools.py);
the other TWENTY are distractors with ``pass`` bodies that echo their
inputs. The real pipeline (sop.txt §7-§9) is a linear six-stage gate chain:

  validateVideoFormat -> validateLidarData -> performObjectDetection
  -> executeSegmentation -> runAutomatedQC -> performHumanValidation

``final_status`` (the single graded ground-truth field) is True iff every
gate passes. The gate thresholds below were derived from sop.txt §4-§5 and
validated against ALL 125 labeled dev rows with ZERO mismatches:

  video:    format in {HEVC, H.264}; width >= 1920; height >= 1080;
            24 <= fps <= 60; bit depth in {8, 10}; channels >= 3;
            camera position front-facing (data-derived set: dash,
            camera beside HUD, driver seat, passenger seat near driver)
  lidar:    .pcd path; |time_offset| <= 1.0s; intrinsics + transform
            available; 0.5 <= object_distance <= 150 m
  detect:   confidence > 0.85; tracking enabled; predicted == ground truth
  segment:  instance segmentation; predicted IoU >= 0.75; temporal
            smoothing on; binary mask output format
  auto QC:  spatial accuracy >= 0.85; temporal consistency > 0.80
  human QC: inter-annotator >= 0.75; min reviewers >= 2

Honest boundary: sop.txt §5.1 also demands "urban setting" scenes and
"daylight illumination", but the labels are fully explained WITHOUT any
scene_type / weather / lighting_conditions constraint — every rule
violation in those fields co-occurs with one of the crisp failures above.
They are therefore left unconstrained (adding them could only break fit).
The front-camera set is data-derived: no labeled True row uses any other
position, consistent with §5.1 "front-camera positioning".
"""

from __future__ import annotations

import json
import re

import acorn
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

FRONT_POSITIONS = {"dash", "camera beside HUD", "driver seat", "passenger seat near driver"}

# tool -> CSV columns it returns, mirroring the pack's tools.py exactly for
# the six real tools; each distractor tool (a ``pass`` body officially)
# echoes its own input column(s) — benign, no ground truth involved.
OUTPUT_COLUMNS = {
    # -- real pipeline tools (per tools.py) --
    "validateVideoFormat": [
        "video_path", "format", "resolution_width", "resolution_height",
        "frame_rate", "bit_depth", "channel_count",
        "scene_type", "weather", "lighting_conditions", "camera_position",
    ],
    "validateLidarData": [
        "lidar_point_cloud_path", "time_offset", "object_distance",
        "camera_intrinsics_available", "lidar_transform_available",
    ],
    "performObjectDetection": [
        "ground_truth_object", "confidence_threshold_object_detection",
        "tracking_enabled", "predicted_object",
        "object_detection_output_path", "output_format_object_detection",
    ],
    "executeSegmentation": [
        "segmentation_type", "temporal_smoothing", "predicted_iou",
        "segmentation_output_path", "output_format_segmentation",
    ],
    "runAutomatedQC": ["temporal_consistency_score", "spatial_accuracy_score"],
    "performHumanValidation": ["inter_annotator_score", "min_reviewers"],
    # -- distractor tools (officially unimplemented; echo their inputs) --
    "calibrateCameraSensors": ["camera_position"],
    "synchronizeLidarTimestamp": ["time_offset"],
    "generateDepthMap": ["lidar_point_cloud_path"],
    "validateWeatherConditions": ["weather"],
    "optimizeFrameRate": ["frame_rate"],
    "enhanceLowLightFootage": ["lighting_conditions"],
    "trackObjectMotion": ["predicted_object"],
    "validateCameraIntrinsics": ["camera_intrinsics_available"],
    "processNightTimeFootage": ["lighting_conditions"],
    "analyzeCameraStability": ["camera_position"],
    "validateSceneContext": ["scene_type"],
    "adjustBitDepth": ["bit_depth"],
    "validateChannelCount": ["channel_count"],
    "processHighResolution": ["resolution_width", "resolution_height"],
    "validateOutputFormat": ["output_format_object_detection"],
    "checkProcessingStatus": ["video_path"],
    "validateTemporalConsistency": ["temporal_consistency_score"],
    "checkSpatialAccuracy": ["spatial_accuracy_score"],
    "validateAnnotatorScores": ["inter_annotator_score"],
    "optimizeTrackingSettings": ["tracking_enabled"],
}

REAL_TOOLS = [
    "validateVideoFormat", "validateLidarData", "performObjectDetection",
    "executeSegmentation", "runAutomatedQC", "performHumanValidation",
]
DISTRACTOR_TOOLS = [t for t in OUTPUT_COLUMNS if t not in REAL_TOOLS]

GRADED_FIELDS = ["final_status"]

GATES = ["video_ok", "lidar_ok", "detect_ok", "seg_ok", "qc_ok", "human_ok"]


# ---------------------------------------------------------------------------
# Deterministic gate rules (validated: 0 mismatches on all 125 labeled rows)
# ---------------------------------------------------------------------------


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _b(v) -> bool:
    return str(v).strip() == "True"


def video_ok(out: dict) -> bool:
    """SOP §4.1 + §5.1: codec/resolution/fps/depth/channels + front camera."""
    return (
        str(out.get("format", "")).strip() in ("HEVC", "H.264")
        and _f(out.get("resolution_width")) >= 1920
        and _f(out.get("resolution_height")) >= 1080
        and 24.0 <= _f(out.get("frame_rate")) <= 60.0
        and str(out.get("bit_depth", "")).strip() in ("8", "10")
        and _f(out.get("channel_count")) >= 3
        and str(out.get("camera_position", "")).strip() in FRONT_POSITIONS
    )


def lidar_ok(out: dict) -> bool:
    """SOP §4.2: .pcd, sync within ±1.0s, matrices available, 0.5-150m."""
    return (
        str(out.get("lidar_point_cloud_path", "")).endswith(".pcd")
        and abs(_f(out.get("time_offset"), 1e9)) <= 1.0
        and _b(out.get("camera_intrinsics_available"))
        and _b(out.get("lidar_transform_available"))
        and 0.5 <= _f(out.get("object_distance"), -1) <= 150.0
    )


def detect_ok(out: dict) -> bool:
    """SOP §5.2: confidence > 0.85, tracking mandatory, ground truth match."""
    return (
        _f(out.get("confidence_threshold_object_detection")) > 0.85
        and _b(out.get("tracking_enabled"))
        and str(out.get("predicted_object", "")) == str(out.get("ground_truth_object", "x"))
    )


def seg_ok(out: dict) -> bool:
    """SOP §5.2 + §5.4: instance masks, IoU >= 0.75, smoothing, binary format."""
    return (
        str(out.get("segmentation_type", "")).strip() == "instance"
        and _f(out.get("predicted_iou")) >= 0.75
        and _b(out.get("temporal_smoothing"))
        and str(out.get("output_format_segmentation", "")).strip() == "binary"
    )


def qc_ok(out: dict) -> bool:
    """SOP §5.3: spatial accuracy >= 0.85, temporal consistency > 0.80."""
    return (
        _f(out.get("spatial_accuracy_score")) >= 0.85
        and _f(out.get("temporal_consistency_score")) > 0.80
    )


def human_ok(out: dict) -> bool:
    """SOP §5.3: inter-annotator >= 0.75, at least two reviewers."""
    return _f(out.get("inter_annotator_score")) >= 0.75 and _f(out.get("min_reviewers")) >= 2


GATE_FNS = {
    "video_ok": video_ok,
    "lidar_ok": lidar_ok,
    "detect_ok": detect_ok,
    "seg_ok": seg_ok,
    "qc_ok": qc_ok,
    "human_ok": human_ok,
}

GATE_REASONS = {
    "video_ok": "Video format validation failed (SOP 4.1/5.1: codec, resolution, frame rate, bit depth, channels, or camera position out of spec).",
    "lidar_ok": "LiDAR data validation failed (SOP 4.2: point cloud format, time offset, matrices, or ranging out of spec).",
    "detect_ok": "Object detection failed thresholds (SOP 5.2: confidence, tracking, or ground-truth mismatch).",
    "seg_ok": "Segmentation failed requirements (SOP 5.2/5.4: type, predicted IoU, smoothing, or mask format).",
    "qc_ok": "Automated QC below thresholds (SOP 5.3: spatial accuracy or temporal consistency).",
    "human_ok": "Human validation failed (SOP 5.3: inter-annotator score or reviewer count).",
}


def ready(facts: FactStore) -> bool:
    """Final report procedurally determined: a gate failed (early exit)
    or all six gates were evaluated."""
    for gate in GATES:
        fact = facts.get(gate)
        if fact is not None and not facts.truthy(gate):
            return True
    return all(facts.get(gate) is not None for gate in GATES)


def compute_final(facts: FactStore) -> dict:
    """SOP §6.1 deliverable, deterministic over the fact store."""
    for gate in GATES:
        fact = facts.get(gate)
        if fact is None or not facts.truthy(gate):
            return {
                "final_status": False,
                "coco_json_path": "",
                "segmentation_mask_path": "",
                "inter_annotator_score": "",
                "reason": GATE_REASONS[gate] if fact is not None else
                f"Pipeline stopped before {gate.removesuffix('_ok')} stage completed.",
            }
    return {
        "final_status": True,
        "coco_json_path": facts.value("coco_json_path") or "",
        "segmentation_mask_path": facts.value("segmentation_mask_path") or "",
        "inter_annotator_score": facts.value("inter_annotator_score") or "",
        "reason": "",
    }


# ---------------------------------------------------------------------------
# ACORN wiring
# ---------------------------------------------------------------------------


class VAPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        if predicate == "report_ready":
            return ready(context.facts)
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs = [
        acorn.action("validateVideoFormat").at_most(1),
        acorn.after("validateVideoFormat")
        .asserts("video_checked")
        .asserts("video_ok", value=lambda r: video_ok(r.output))
        .asserts("video_path", value=lambda r: r.output.get("video_path")),
        # §7.2: LiDAR verification follows SUCCESSFUL video validation.
        acorn.action("validateLidarData").requires("video_ok").at_most(1),
        acorn.after("validateLidarData")
        .asserts("lidar_checked")
        .asserts("lidar_ok", value=lambda r: lidar_ok(r.output)),
        # §7.3: detection consumes the validated video (after LiDAR passes).
        acorn.action("performObjectDetection").requires("lidar_ok").at_most(1),
        acorn.after("performObjectDetection")
        .asserts("detect_checked")
        .asserts("detect_ok", value=lambda r: detect_ok(r.output))
        .asserts("coco_json_path", value=lambda r: r.output.get("object_detection_output_path")),
        # §7.4: segmentation consumes predicted_object + detection output path.
        acorn.action("executeSegmentation").requires("detect_ok").at_most(1),
        acorn.after("executeSegmentation")
        .asserts("seg_checked")
        .asserts("seg_ok", value=lambda r: seg_ok(r.output))
        .asserts("segmentation_mask_path", value=lambda r: r.output.get("segmentation_output_path")),
        # §8.1: automated QC consumes predicted_iou + segmentation output path.
        acorn.action("runAutomatedQC").requires("seg_ok").at_most(1),
        acorn.after("runAutomatedQC")
        .asserts("qc_checked")
        .asserts("qc_ok", value=lambda r: qc_ok(r.output)),
        # §8.2: human validation follows automated QC.
        acorn.action("performHumanValidation").requires("qc_ok").at_most(1),
        acorn.after("performHumanValidation")
        .asserts("human_checked")
        .asserts("human_ok", value=lambda r: human_ok(r.output))
        .asserts("inter_annotator_score", value=lambda r: r.output.get("inter_annotator_score")),
        acorn.action("submit_result").requires("report_ready").at_most(1),
        acorn.after("submit_result").asserts("result_submitted"),
    ]
    # Distractor tools: not part of the SOP pipeline; rate-limit to bound
    # exploration loops in the non-masked conditions.
    for tool in DISTRACTOR_TOOLS:
        specs.append(acorn.action(tool).at_most(1))
    return acorn.ContractLibrary("video-annotation-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "final_status": {"type": "boolean", "description": "True iff the video was annotated."},
        "coco_json_path": {"type": "string", "description": "CoCo JSON annotation path (if annotated)."},
        "segmentation_mask_path": {"type": "string", "description": "Segmentation masks path (if annotated)."},
        "inter_annotator_score": {"description": "Inter-annotator score (if annotated)."},
        "reason": {"type": "string", "description": "If not annotated, why."},
    },
    "required": ["final_status"],
}

CONDITIONS = ("baseline", "passive", "mask", "acorn")


def build_agent(model, pack: Pack, sink: dict, *, condition: str = "acorn", row: dict | None = None, mask_granularity: str = "step") -> acorn.Agent:
    assert condition in CONDITIONS, condition
    registry = build_registry(pack, output_columns=OUTPUT_COLUMNS, row=row)

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description="Submit the final annotation output (final_status, paths, score, reason).",
        parameters=SUBMIT_SCHEMA,
        args_binder=(lambda ctx: compute_final(ctx.facts)) if condition == "acorn" else None,
    )

    if condition == "baseline":
        return acorn.Agent(model, tools=registry, instructions=pack.sop_text, max_steps=16)

    flow = None
    if condition in ("mask", "acorn"):
        def _next(target: str, done_fact: str):
            def nxt(ctx):
                if ready(ctx.facts):
                    return "submit"
                return target if ctx.facts.truthy(done_fact) else None
            return nxt

        # Distractor tools appear in NO state: dynamic tool exposure prunes
        # the 26-tool registry to the pipeline stage's real tools.
        flow = (
            acorn.GraphFlow(start="validate")
            .state(
                "validate",
                tools=["validateVideoFormat", "validateLidarData"],
                next=_next("process", "lidar_ok"),
            )
            .state(
                "process",
                tools=["performObjectDetection", "executeSegmentation"],
                next=_next("qc", "seg_ok"),
            )
            .state(
                "qc",
                tools=["runAutomatedQC", "performHumanValidation"],
                next=_next("submit", "human_checked"),
            )
            .state(
                "submit",
                tools=["submit_result"],
                next=lambda ctx: "done" if ctx.facts.truthy("result_submitted") else None,
            )
            .state("done", tools=[], terminal=True)
        )
    return acorn.Agent(
        model,
        tools=registry,
        instructions=pack.sop_text,
        flow=flow,
        contracts=build_library(),
        predicate_evaluator=VAPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        mask_granularity=mask_granularity,
        max_steps=18,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    # Only the entity key: every other column is a tool output (leakage).
    return (
        "Process the following video through the annotation SOP.\n"
        f"video_id: {row[pack.key_field]}\n"
        "Work through the pipeline with the tools, then call submit_result "
        "with the final output fields (final_status, coco_json_path, "
        "segmentation_mask_path, inter_annotator_score, reason)."
    )


def run_row(model_factory, pack: Pack, row: dict, *, condition: str = "acorn", probe_cache=None, mask_granularity: str = "step"):
    sink: dict = {}
    agent = build_agent(model_factory(), pack, sink, condition=condition, row=row, mask_granularity=mask_granularity)
    if probe_cache is not None and condition in ("mask", "acorn"):
        agent.probe_cache = probe_cache
    auditor = build_library().auditor(predicate_evaluator=VAPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


# ---------------------------------------------------------------------------
# Grading (benchmark-native: final_status is the only ground-truth column)
# ---------------------------------------------------------------------------

_KEY_ALIASES = {
    "finalstatus": "final_status",
    "cocojsonpath": "coco_json_path",
    "segmentationmaskpath": "segmentation_mask_path",
    "interannotatorscore": "inter_annotator_score",
    "reason": "reason",
}


def parse_text_answer(text: str | None) -> dict | None:
    """SOP §6.1: XML <final_output> tags wrapping a JSON with prose-style
    keys ('Final Status', 'CoCo JSON path', ...)."""
    if not text:
        return None
    m = re.search(r"<final_output>\s*(\{.*?\})\s*</final_output>", text, re.S | re.I)
    blob = m.group(1) if m else None
    if blob is None:
        m = re.search(r"\{.*\}", text, re.S)
        blob = m.group(0) if m else None
    if blob is None:
        return None
    try:
        obj = json.loads(blob)
    except ValueError:
        try:
            import ast

            obj = ast.literal_eval(blob)
        except (ValueError, SyntaxError):
            return None
    if not isinstance(obj, dict):
        return None
    out = {}
    for k, v in obj.items():
        canon = _KEY_ALIASES.get(re.sub(r"[^a-z0-9]", "", str(k).lower()))
        if canon:
            out[canon] = v
    return out or None


def _norm_status(v) -> bool | None:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "annotated"):
        return True
    if s in ("false", "no", "not annotated"):
        return False
    return None


def grade(row: dict, submitted: dict | None):
    want = {"final_status": row["final_status"] == "True"}
    if not submitted or "final_status" not in submitted:
        return want, None
    return want, {"final_status": _norm_status(submitted.get("final_status"))}
