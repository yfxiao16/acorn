"""Aircraft Inspection SOP: hand-authored ACORN contract library + agent.

Structure (sop.txt §5): seven verification/reporting tools whose outputs
ARE the seven graded fields — the pack's own tools.py relays each output
column by ``aircraft_id``, so the final Airworthiness Verification Report
is a pure relay of the seven tool outputs (a deterministic jump once all
seven facts exist), exactly like patient_intake.

Genuine ordering dependencies (from the toolspec input schemas):
  - ``ReportComponentIncident`` consumes ``mechanical_inspection_result``
    and ``electrical_inspection_result`` — the outputs of the two Verify
    tools — so both inspections must run first.
  - ``ReportCrossCheck`` consumes ``component_incident_response`` and
    ``component_mismatch_response`` — the outputs of the two report
    tools — so both reports must be filed first.
All other tools consume task inputs only and are order-free.

Honest boundaries (documented, not force-fit):
  - SOP §5.4 says incident reporting happens "only when applicable", but
    every labeled row carries values for all report responses (53
    all-success rows still have component_incident_response='success'),
    so the completeness gate requires all seven tools on every row.
    Ground truth wins over the SOP's conditional phrasing.
  - A handful of rows have '' (empty) for individual outputs — noise in
    the simulated data, relayed verbatim like every other value.
  - SOP §6's example output mentions 'VerifyShipment' and a "shipment
    id" — copy-paste artifacts from another domain; ignored.
"""

from __future__ import annotations

import ast
import json
import re

import acorn
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

# tool -> (output column == graded field == value-fact name)
TOOL_FACTS = {
    "VerifyAircraftClearance": "aircraft_ready",
    "VerifyMechanicalComponents": "mechanical_inspection_result",
    "VerifyElectricalSystems": "electrical_inspection_result",
    "ReportComponentIncident": "component_incident_response",
    "ReportComponentMismatch": "component_mismatch_response",
    "CrossCheckSpecifications": "cross_check_response",
    "ReportCrossCheck": "cross_check_reporting_response",
}
OUTPUT_COLUMNS = {tool: [fact] for tool, fact in TOOL_FACTS.items()}
GRADED_FIELDS = list(TOOL_FACTS.values())
# marker fact per tool: "this step was performed" (value facts may be '')
MARKERS = {tool: f"{fact}_done" for tool, fact in TOOL_FACTS.items()}

# Agent-visible inputs = exactly the without_outputs CSV columns. Never
# use pack.input_fields here: the report tools' schemas consume other
# tools' OUTPUT columns, so the toolspec-property union leaks GT.
PROMPT_FIELDS = [
    "aircraft_id", "tail_number", "maintenance_record_id",
    "expected_departure_time", "actual_inspection_time",
    "inspection_location_id", "component_serial_number",
    "installed_component_serial_number", "installation_time",
    "component_weight", "expected_component_weight",
    "physical_condition_observation", "battery_status",
    "circuit_continuity_check", "avionics_diagnostics_response",
]

CONDITIONS = ("baseline", "passive", "mask", "acorn")


def compute_final(facts: FactStore) -> dict:
    """The verification report: relay of the seven established facts
    ('' is a legitimate relayed value, so don't collapse it via `or`)."""
    out = {}
    for field in GRADED_FIELDS:
        v = facts.value(field)
        out[field] = "" if v is None else str(v)
    return out


class AIPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        if predicate == "report_ready":
            return all(context.facts.get(m) is not None for m in MARKERS.values())
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs: list = []
    for tool, fact in TOOL_FACTS.items():
        specs.append(
            acorn.after(tool)
            .asserts(fact, value=lambda r, f=fact: str(r.output.get(f, "")))
            .asserts(MARKERS[tool])
        )
    for tool in TOOL_FACTS:
        if tool in ("ReportComponentIncident", "ReportCrossCheck"):
            continue
        specs.append(acorn.action(tool).at_most(1))
    # §5.4.1 + schema: the incident report consumes both inspection results.
    specs.append(
        acorn.action("ReportComponentIncident")
        .requires(MARKERS["VerifyMechanicalComponents"], MARKERS["VerifyElectricalSystems"])
        .at_most(1)
    )
    # §5.5.1 + schema: the cross-check report consumes both report responses.
    specs.append(
        acorn.action("ReportCrossCheck")
        .requires(MARKERS["ReportComponentIncident"], MARKERS["ReportComponentMismatch"])
        .at_most(1)
    )
    specs.append(acorn.action("submit_result").requires("report_ready").at_most(1))
    specs.append(acorn.after("submit_result").asserts("result_submitted"))
    return acorn.ContractLibrary("aircraft-inspection-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in GRADED_FIELDS},
    "required": GRADED_FIELDS,
}


def build_agent(model, pack: Pack, sink: dict, *, condition: str = "acorn", row: dict | None = None, mask_granularity: str = "step") -> acorn.Agent:
    assert condition in CONDITIONS, condition
    registry = build_registry(pack, output_columns=OUTPUT_COLUMNS, row=row)

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description="Submit the final Airworthiness Verification Report (all action results).",
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
                tools=[*TOOL_FACTS, "submit_result"],
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
        predicate_evaluator=AIPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        mask_granularity=mask_granularity,
        max_steps=14,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    lines = ["Perform the pre-flight airworthiness inspection for this aircraft per the SOP."]
    for f in PROMPT_FIELDS:
        lines.append(f"{f}: {row.get(f, '')}")
    lines.append(
        "Run the verification and reporting tools, then call submit_result "
        "with the status of every action for the Airworthiness Verification Report."
    )
    return "\n".join(lines)


def run_row(model_factory, pack: Pack, row: dict, *, condition: str = "acorn", probe_cache=None, mask_granularity: str = "step"):
    sink: dict = {}
    agent = build_agent(model_factory(), pack, sink, condition=condition, row=row, mask_granularity=mask_granularity)
    if probe_cache is not None and condition in ("mask", "acorn"):
        agent.probe_cache = probe_cache
    auditor = build_library().auditor(predicate_evaluator=AIPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


def parse_text_answer(text: str | None) -> dict | None:
    """Protocol-fidelity fallback: SOP §6.1 asks for a report inside
    <final_response> tags whose example body is a Python-style dict
    (single quotes, bare None) — accept both that and plain JSON."""
    if not text:
        return None
    m = re.search(r"<final_response>(.*?)</final_response>", text, re.S | re.I)
    scope = m.group(1) if m else text
    b = re.search(r"\{.*\}", scope, re.S)
    if not b:
        return None
    blob = b.group(0)
    for parser in (json.loads, ast.literal_eval):
        try:
            obj = parser(blob)
        except (ValueError, SyntaxError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _norm(v) -> str:
    if v is None:
        return ""
    return str(v).strip().lower()


def grade(row: dict, submitted: dict | None):
    want = {k: _norm(row[k]) for k in GRADED_FIELDS}
    if not submitted:
        return want, None
    got = {k: _norm(submitted.get(k, "")) for k in GRADED_FIELDS}
    return want, got
