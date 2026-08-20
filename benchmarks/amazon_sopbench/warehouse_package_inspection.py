"""Warehouse Package Inspection SOP: hand-authored ACORN contract library + agent.

A branching workflow (sop.txt §5) keyed on the barcode gate:

  5.1.1 validateBarcode: mismatch -> problem 'Wrong Item', resolution
        'Returned to Vendor', skip everything except the Problem
        Classification Report.
  5.2   classification: quantity assessment (Cancelled / Overage /
        Underage / Severe Unmatched via QVT=5%), warehouse location
        check ('Wrong Warehouse'), damage assessment ('Vendor Damaged').
  5.3   chargeback + resolution status, then the problem report.

Deterministic rules — each validated at 100% against all 150 labeled rows
(see tests/test_amazon_warehouse_package_inspection.py):

  problem_type   barcode mismatch -> ['Wrong Item']; else quantity
                 problems (confirmed==0 -> Cancelled; received vs ordered
                 -> Overage/Underage; |(rec-conf)/conf| > 5% -> Severe
                 Unmatched Quantity) + Wrong Warehouse on id mismatch +
                 Vendor Damaged on damage.                    150/150
  charge_back_amt  Wrong Item -> not computed ('' per §5.1.1 skip);
                 any quantity problem -> (ordered - received) * unit_cost
                 (sign preserved: overage charges are negative, SOP
                 §5.3.1 taken literally); damage -> + received *
                 unit_cost; Wrong Warehouse alone -> 0. NOTE: this is
                 what the labeled data implements — the pack's own
                 tools.py (10% warehouse handling fee, positive-only
                 quantity charges) contradicts its GT; GT wins. 150/150
  resolution_status  Wrong Item -> 'Returned to Vendor'; any other
                 problem -> 'Processing'; no problems -> 'Resolved' if
                 the `chargeable` INPUT column is False else 'Returned
                 to Vendor'. The last leg (8 rows, 0 counterexamples)
                 is data-derived, not in the SOP text.         150/150

Honest boundary: ``barcode_match`` and ``package_condition`` are vision
judgments (the official tools call a VLM on the barcode/package images);
our deterministic harness relays them from the labeled CSV via
validateBarcode / assessPackageCondition, the same way the pack's other
domains relay precomputed outputs. They are evidence, not deliverables:
grading covers the three §6 documents (problem_type, charge_back_amt,
resolution_status) plus barcode_match, which is established in every
branch. package_condition is NOT graded — on 'Wrong Item' rows the SOP
forbids the damage assessment, so a compliant agent cannot know it.
"""

from __future__ import annotations

import ast
import json
import re

import acorn
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

QVT = 5.0  # §3.4 default Quantity Variance Threshold (%)

# tool -> CSV columns relayed as its output (per-domain declaration table)
OUTPUT_COLUMNS = {
    "validateBarcode": ["barcode_match"],
    "calculateQuantityVariance": ["ordered_quantity", "confirmed_quantity", "received_quantity"],
    "verifyWarehouseLocation": ["intended_warehouse_id", "actual_warehouse_id"],
    "assessPackageCondition": ["package_condition"],
    "calculateChargeback": ["chargeable", "charge_back_amt"],
    "updateResolutionStatus": ["resolution_status"],
    "generateProblemReport": ["po_number"],  # ack only — no GT leak via the report
}

GRADED_FIELDS = ["problem_type", "resolution_status", "charge_back_amt", "barcode_match"]

CLASSIFY_TOOLS = ["calculateQuantityVariance", "verifyWarehouseLocation", "assessPackageCondition"]

# Agent-visible inputs = exactly the without_outputs CSV columns (all short).
PROMPT_FIELDS = [
    "po_number", "vendor_id", "vendor_name", "confirmed_product_id",
    "received_product_bar_code", "product_name",
    "ordered_quantity", "confirmed_quantity", "received_quantity",
    "intended_warehouse_id", "actual_warehouse_id", "receipt_date",
    "chargeable", "package_image_path", "unit_cost",
]

CONDITIONS = ("baseline", "passive", "mask", "acorn")


# ---------------------------------------------------------------------------
# Deterministic rules (validated against all 150 labeled rows)
# ---------------------------------------------------------------------------


def quantity_problems(ordered: int, confirmed: int, received: int) -> list[str]:
    """§5.2.1, in the labeled data's emission order."""
    if confirmed == 0:
        return ["Cancelled Quantity"]
    probs = []
    if received > ordered:
        probs.append("Overage Quantity")
    elif received < ordered:
        probs.append("Underage Quantity")
    if abs((received - confirmed) / confirmed * 100) > QVT:
        probs.append("Severe Unmatched Quantity")
    return probs


def derive_problems(
    barcode_match: bool, ordered: int, confirmed: int, received: int,
    warehouse_mismatch: bool, damaged: bool,
) -> list[str]:
    """§5.1-5.2 problem classification (order matches the labeled data)."""
    if not barcode_match:
        return ["Wrong Item"]
    probs = quantity_problems(ordered, confirmed, received)
    if warehouse_mismatch:
        probs.append("Wrong Warehouse")
    if damaged:
        probs.append("Vendor Damaged")
    return probs


_QTY_PROBLEMS = {"Cancelled Quantity", "Overage Quantity", "Underage Quantity"}


def derive_charge(problems: list[str], ordered: int, received: int, unit_cost: float):
    """§5.3.1 as the labeled data implements it. Returns None (not
    computed) for the Wrong Item branch — §5.1.1 skips chargeback."""
    s = set(problems)
    if "Wrong Item" in s:
        return None
    total = 0.0
    if s & _QTY_PROBLEMS:
        total += (ordered - received) * unit_cost
    if "Vendor Damaged" in s:
        total += received * unit_cost
    return round(total, 2)


def derive_resolution(problems: list[str], chargeable_input: bool) -> str:
    """§5.1.1/§5.3.2 + the data-derived clean-but-chargeable leg."""
    if "Wrong Item" in problems:
        return "Returned to Vendor"
    if problems:
        return "Processing"
    return "Returned to Vendor" if chargeable_input else "Resolved"


# ---------------------------------------------------------------------------
# ACORN wiring
# ---------------------------------------------------------------------------


def compute_final(facts: FactStore) -> dict:
    """The three §6 documents + the barcode verdict, from facts only.

    problem_type is computed by the derived rule; charge_back_amt and
    resolution_status are relayed from their tools' outputs on the
    normal branch and rule-determined on the Wrong Item branch."""
    if not facts.truthy("barcode_match"):
        return {
            "problem_type": ["Wrong Item"],
            "resolution_status": "Returned to Vendor",
            "charge_back_amt": "",
            "barcode_match": False,
        }
    probs = derive_problems(
        True,
        int(facts.value("ordered_quantity", 0)),
        int(facts.value("confirmed_quantity", 0)),
        int(facts.value("received_quantity", 0)),
        bool(facts.value("warehouse_mismatch")),
        bool(facts.value("package_damaged")),
    )
    return {
        "problem_type": probs,
        "resolution_status": str(facts.value("resolution_status") or ""),
        "charge_back_amt": str(facts.value("charge_back_amt") or "0.0"),
        "barcode_match": True,
    }


class WHPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        facts = context.facts
        if predicate == "classification_done":
            return all(
                facts.get(m) is not None
                for m in ("variance_done", "location_checked", "condition_checked")
            )
        if predicate == "report_inputs_ready":
            if facts.get("barcode_match") is not None and not facts.truthy("barcode_match"):
                return True
            return all(
                facts.get(m) is not None for m in ("chargeback_done", "status_updated")
            )
        if predicate == "final_ready":
            return facts.get("report_generated") is not None
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs = [
        acorn.action("validateBarcode").at_most(1),
        acorn.after("validateBarcode")
        .asserts("barcode_checked")
        .asserts("barcode_match", value=lambda r: str(r.output.get("barcode_match")) == "True"),
        # §5.1.1: on barcode mismatch every step below is skipped — the
        # classification tools require the (truthy) barcode_match fact.
        acorn.action("calculateQuantityVariance").requires("barcode_match").at_most(1),
        acorn.after("calculateQuantityVariance")
        .asserts("variance_done")
        .asserts("ordered_quantity", value=lambda r: int(float(r.output.get("ordered_quantity", 0))))
        .asserts("confirmed_quantity", value=lambda r: int(float(r.output.get("confirmed_quantity", 0))))
        .asserts("received_quantity", value=lambda r: int(float(r.output.get("received_quantity", 0)))),
        acorn.action("verifyWarehouseLocation").requires("barcode_match").at_most(1),
        acorn.after("verifyWarehouseLocation")
        .asserts("location_checked")
        .asserts(
            "warehouse_mismatch",
            value=lambda r: str(r.output.get("intended_warehouse_id", "")).strip().upper()
            != str(r.output.get("actual_warehouse_id", "")).strip().upper(),
        ),
        acorn.action("assessPackageCondition").requires("barcode_match").at_most(1),
        acorn.after("assessPackageCondition")
        .asserts("condition_checked")
        .asserts("package_condition", value=lambda r: str(r.output.get("package_condition", "")))
        .asserts("package_damaged", value=lambda r: r.output.get("package_condition") == "damaged"),
        # §5.3.1 + schema: chargeback consumes the classified problem list.
        acorn.action("calculateChargeback").requires("classification_done").at_most(1),
        acorn.after("calculateChargeback")
        .asserts("chargeback_done")
        .asserts("charge_back_amt", value=lambda r: r.output.get("charge_back_amt")),
        # §5.3.2 + schema: the status update consumes the problem list.
        acorn.action("updateResolutionStatus").requires("classification_done").at_most(1),
        acorn.after("updateResolutionStatus")
        .asserts("status_updated")
        .asserts("resolution_status", value=lambda r: r.output.get("resolution_status")),
        # §6 + schema: the report consumes problem_type, charge_amount and
        # resolution_status; on the Wrong Item branch it is the ONLY
        # remaining step (§5.1.1).
        acorn.action("generateProblemReport").requires("report_inputs_ready").at_most(1),
        acorn.after("generateProblemReport").asserts("report_generated"),
        acorn.action("submit_result").requires("final_ready").at_most(1),
        acorn.after("submit_result").asserts("result_submitted"),
    ]
    return acorn.ContractLibrary("warehouse-package-inspection-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_type": {"type": "array", "items": {"type": "string"}},
        "resolution_status": {"type": "string"},
        "charge_back_amt": {},
        "barcode_match": {},
    },
    "required": GRADED_FIELDS,
}

ALL_TOOLS = list(OUTPUT_COLUMNS)


def build_agent(model, pack: Pack, sink: dict, *, condition: str = "acorn", row: dict | None = None, mask_granularity: str = "step") -> acorn.Agent:
    assert condition in CONDITIONS, condition
    registry = build_registry(pack, output_columns=OUTPUT_COLUMNS, row=row)

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description="Submit the final shipment-problem resolution (problem_type, resolution_status, charge_back_amt, barcode_match).",
        parameters=SUBMIT_SCHEMA,
        args_binder=(lambda ctx: compute_final(ctx.facts)) if condition == "acorn" else None,
    )

    if condition == "baseline":
        return acorn.Agent(model, tools=registry, instructions=pack.sop_text, max_steps=14)

    flow = None
    if condition in ("mask", "acorn"):
        flow = (
            acorn.GraphFlow(start="work")
            .state(
                "work",
                tools=[*ALL_TOOLS, "submit_result"],
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
        predicate_evaluator=WHPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        mask_granularity=mask_granularity,
        max_steps=14,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    lines = ["Process the following inbound shipment receipt per the SOP."]
    for f in PROMPT_FIELDS:
        lines.append(f"{f}: {row.get(f, '')}")
    lines.append(
        "Work through the SOP using the tools, then call submit_result with "
        "the problem classification, resolution status and chargeback amount."
    )
    return "\n".join(lines)


def run_row(model_factory, pack: Pack, row: dict, *, condition: str = "acorn", probe_cache=None, mask_granularity: str = "step"):
    sink: dict = {}
    agent = build_agent(model_factory(), pack, sink, condition=condition, row=row, mask_granularity=mask_granularity)
    if probe_cache is not None and condition in ("mask", "acorn"):
        agent.probe_cache = probe_cache
    auditor = build_library().auditor(predicate_evaluator=WHPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


# ---------------------------------------------------------------------------
# Grading (benchmark-native: the §6 documents + barcode verdict)
# ---------------------------------------------------------------------------


def parse_text_answer(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(m.group(0))
        except (ValueError, SyntaxError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _norm_problems(v):
    if isinstance(v, str):
        for parser in (ast.literal_eval, json.loads):
            try:
                v = parser(v)
                break
            except (ValueError, SyntaxError):
                continue
    if not isinstance(v, (list, tuple)):
        v = [v] if v not in (None, "") else []
    return sorted(str(p).strip() for p in v)


def _norm_charge(v):
    if v in (None, ""):
        return None
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return str(v)


def _norm_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def _norm(field: str, v):
    if field == "problem_type":
        return _norm_problems(v)
    if field == "charge_back_amt":
        return _norm_charge(v)
    if field == "barcode_match":
        return _norm_bool(v)
    return str(v or "").strip()


def grade(row: dict, submitted: dict | None):
    want = {k: _norm(k, row[k]) for k in GRADED_FIELDS}
    if not submitted:
        return want, None
    got = {k: _norm(k, submitted.get(k)) for k in GRADED_FIELDS}
    return want, got
