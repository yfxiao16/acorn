"""Patient Intake SOP: hand-authored ACORN contract library + agent.

Structure (sop.txt §5): five assessment tools whose outputs feed the
aggregating ``registerPatient`` call, with one genuine ordering
dependency — ``calculateOverallRisk`` consumes the lifestyle risk level,
so lifestyle must be computed first. The six graded fields are exactly
the six tools' outputs; the final verification report is their
deterministic aggregation (a pure jump once all six facts exist).
"""

from __future__ import annotations

import re

import acorn
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

# tool -> (output column == graded field == fact name)
TOOL_FACTS = {
    "validateInsurance": "insurance_validation",
    "validatePrescriptionBenefits": "prescription_insurance_validation",
    "verifyPharmacy": "pharmacy_check",
    "calculateLifestyleRisk": "life_style_risk_level",
    "calculateOverallRisk": "overall_risk_level",
    "registerPatient": "user_registration",
}
OUTPUT_COLUMNS = {tool: [fact] for tool, fact in TOOL_FACTS.items()}
GRADED_FIELDS = list(TOOL_FACTS.values())
ASSESSMENTS = [t for t in TOOL_FACTS if t != "registerPatient"]

PROMPT_FIELDS = [
    "patient_id", "first_name", "last_name", "date_of_birth",
    "previous_surgeries", "chronic_conditions",
    "smoking_status", "alcohol_consumption", "exercise_frequency",
    "insurance_provider", "policy_number", "group_number",
    "coverage_start_date", "insurance_type",
    "preferred_pharmacy_name", "preferred_pharmacy_address", "pharmacy_phone",
]

CONDITIONS = ("baseline", "passive", "mask", "acorn")


def compute_final(facts: FactStore) -> dict:
    """The verification report: relay of the six established facts."""
    return {field: str(facts.value(field) or "") for field in GRADED_FIELDS}


class PIPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        if predicate == "assessments_done":
            return all(
                context.facts.get(TOOL_FACTS[t]) is not None for t in ASSESSMENTS
            )
        if predicate == "report_ready":
            return context.facts.get("user_registration") is not None
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs: list = []
    for tool, fact in TOOL_FACTS.items():
        specs.append(
            acorn.after(tool).asserts(fact, value=lambda r, f=fact: r.output.get(f))
        )
    for tool in ASSESSMENTS:
        specs.append(acorn.action(tool).at_most(1))
    # §5.2.2: overall risk consumes the lifestyle result — genuine ordering.
    specs.append(
        acorn.action("calculateOverallRisk").requires("life_style_risk_level").at_most(1)
    )
    # §5.3: registration aggregates the five assessment results.
    specs.append(acorn.action("registerPatient").requires("assessments_done").at_most(1))
    specs.append(acorn.action("submit_result").requires("report_ready").at_most(1))
    specs.append(acorn.after("submit_result").asserts("result_submitted"))
    return acorn.ContractLibrary("patient-intake-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in GRADED_FIELDS},
    "required": GRADED_FIELDS,
}


def build_agent(model, pack: Pack, sink: dict, *, condition: str = "acorn", row: dict | None = None) -> acorn.Agent:
    assert condition in CONDITIONS, condition
    registry = build_registry(pack, output_columns=OUTPUT_COLUMNS, row=row)

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description="Submit the final patient-intake verification report (JSON).",
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
        predicate_evaluator=PIPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        max_steps=14,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    lines = ["Process this new patient intake per the SOP."]
    for f in PROMPT_FIELDS:
        lines.append(f"{f}: {row.get(f, '')}")
    lines.append(
        "Run the required verifications and risk assessments with the tools, "
        "register the patient, then call submit_result with the verification report."
    )
    return "\n".join(lines)


def run_row(model_factory, pack: Pack, row: dict, *, condition: str = "acorn"):
    sink: dict = {}
    agent = build_agent(model_factory(), pack, sink, condition=condition, row=row)
    auditor = build_library().auditor(predicate_evaluator=PIPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


def parse_text_answer(text: str | None) -> dict | None:
    if not text:
        return None
    import json as _json

    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = _json.loads(m.group(0))
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _norm(v) -> str:
    return str(v).strip().lower()


def grade(row: dict, submitted: dict | None):
    want = {k: _norm(row[k]) for k in GRADED_FIELDS}
    if not submitted:
        return want, None
    got = {k: _norm(submitted.get(k, "")) for k in GRADED_FIELDS}
    return want, got
