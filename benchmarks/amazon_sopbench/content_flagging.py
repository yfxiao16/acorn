"""Content Flagging SOP: hand-authored ACORN contract library + agent.

Structure (sop.txt §5): a four-tool scoring pipeline with genuine
schema-implied ordering — ``calculate_user_trust_score`` consumes the
bot_probability_index and device_consistency_score produced by
``calculateBotProbabilityIndex``, and ``determineFinalDecision`` consumes
the trust score, severity index, and bot probability. The three graded
fields (user_trust_score, content_severity_index, final_decision) are
exactly the last three tools' outputs, relayed from the labeled CSV; the
final report is their deterministic relay (a pure jump once all facts
exist), patient_intake-style.

Honest boundaries, from reconciling the pack against its labeled rows:

  * The CSV carries no bot_probability_index / device_consistency_score
    columns (the official tools resolve them from an unshipped data.csv,
    where BPI is literally ``random.random()``). Our simulated BPI tool
    therefore returns the SOP §5.1.1 threshold rules — which cover
    132/168 labeled rows' inputs — and relays the raw is_possible_bot
    where the rules are silent; device_consistency_score is fixed at 1.0
    (no §5.1.2 adjustment). These values feed downstream tool *arguments*
    only; they are not graded and do not affect the relayed outputs.
  * Neither reference formula reproduces the labels: the pack tools.py
    CSI formula fits 0/168 rows, and its final-decision formula (with
    SOP-rule BPI) fits 8/132. The labels are internally consistent
    though — final_decision follows CSI thresholds (<35 allowed, <=70
    warning, <85 removed, >=85 user_banned with a UTS<25 tie-break at
    CSI==85) on 168/168 rows (see induced_decision, kept as
    documentation/cross-validation, NOT wired into the binder: the
    decision is the tool's relayed output, exactly like the other two
    graded fields).
"""

from __future__ import annotations

import json
import re

import acorn
from acorn.facts import FactStore, LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

# tool -> (output column == graded field == fact name); the BPI tool is
# custom-simulated (no CSV output column, see module docstring).
TOOL_FACTS = {
    "calculateContentSeverityIndex": "content_severity_index",
    "calculate_user_trust_score": "user_trust_score",
    "determineFinalDecision": "final_decision",
}
OUTPUT_COLUMNS = {tool: [fact] for tool, fact in TOOL_FACTS.items()}
GRADED_FIELDS = ["user_trust_score", "content_severity_index", "final_decision"]
DECISIONS = ("allowed", "warning", "removed", "user_banned")

PROMPT_FIELDS = [
    "content_id", "userid", "flagid", "Latitude", "Longitude",
    "device_type", "os", "browser",
    "PrimaryViolationType", "SecondaryViolationType",
    "PrimaryViolation_Confidence", "SecondaryViolation_Confidence",
    "NumberofPreviousPosts", "CountofFlaggedPosts",
    "is_possible_bot", "Captcha_tries",
]

CONDITIONS = ("baseline", "passive", "mask", "acorn")


# ---------------------------------------------------------------------------
# Deterministic rules (validated against all labeled rows)
# ---------------------------------------------------------------------------


def sop_bpi(is_possible_bot: float, captcha_tries: int) -> float:
    """SOP §5.1.1 threshold rules; outside their domain (36/168 labeled
    rows) the raw is_possible_bot is relayed (documented residue — the
    official tool draws random.random() there)."""
    if is_possible_bot > 0.7 and captcha_tries >= 3:
        return 0.9
    if is_possible_bot > 0.5 and captcha_tries >= 2:
        return 0.7
    if is_possible_bot < 0.3 and captcha_tries <= 1:
        return 0.1
    return round(float(is_possible_bot), 2)


def induced_decision(csi: int, uts: int) -> str:
    """Label structure induced from the 168 labeled rows (100% fit).
    Documentation / cross-validation only — never wired into the binder."""
    if csi < 35:
        return "allowed"
    if csi <= 70:
        return "warning"
    if csi < 85:
        return "removed"
    if csi == 85 and uts >= 25:
        return "removed"
    return "user_banned"


def compute_final(facts: FactStore) -> dict:
    """The decision package: relay of the three established facts."""
    return {
        "user_trust_score": facts.value("user_trust_score"),
        "content_severity_index": facts.value("content_severity_index"),
        "final_decision": str(facts.value("final_decision") or ""),
    }


# ---------------------------------------------------------------------------
# ACORN wiring
# ---------------------------------------------------------------------------


class CFPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        if predicate == "scores_ready":
            # Presence-based (a score of 0 is still a score).
            return all(
                context.facts.get(f) is not None
                for f in ("user_trust_score", "content_severity_index", "bpi_done")
            )
        if predicate == "report_ready":
            return context.facts.get("final_decision") is not None
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs = [
        acorn.action("calculateBotProbabilityIndex").at_most(1),
        acorn.after("calculateBotProbabilityIndex")
        .asserts("bpi_done")
        .asserts("bot_probability_index", value=lambda r: r.output.get("bot_probability_index"))
        .asserts("device_consistency_score", value=lambda r: r.output.get("device_consistency_score")),
        # §5.2 / toolspec: the trust score consumes BPI + DCS — genuine ordering.
        acorn.action("calculate_user_trust_score").requires("bpi_done").at_most(1),
        acorn.after("calculate_user_trust_score").asserts(
            "user_trust_score", value=lambda r: r.output.get("user_trust_score")
        ),
        acorn.action("calculateContentSeverityIndex").at_most(1),
        acorn.after("calculateContentSeverityIndex").asserts(
            "content_severity_index", value=lambda r: r.output.get("content_severity_index")
        ),
        # §5.4 / toolspec: the decision consumes UTC, CSI, and BPI.
        acorn.action("determineFinalDecision").requires("scores_ready").at_most(1),
        acorn.after("determineFinalDecision").asserts(
            "final_decision", value=lambda r: r.output.get("final_decision")
        ),
        acorn.action("submit_result").requires("report_ready").at_most(1),
        acorn.after("submit_result").asserts("result_submitted"),
    ]
    return acorn.ContractLibrary("content-flagging-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_trust_score": {"type": "integer", "description": "User Trust Coefficient (0-100)."},
        "content_severity_index": {"type": "integer", "description": "Content Severity Index (0-100)."},
        "final_decision": {"type": "string", "enum": list(DECISIONS)},
    },
    "required": GRADED_FIELDS,
}

PIPELINE_TOOLS = [
    "calculateBotProbabilityIndex",
    "calculate_user_trust_score",
    "calculateContentSeverityIndex",
    "determineFinalDecision",
]


def build_agent(model, pack: Pack, sink: dict, *, condition: str = "acorn", row: dict | None = None, mask_granularity: str = "step") -> acorn.Agent:
    assert condition in CONDITIONS, condition

    def calculateBotProbabilityIndex(**kwargs):
        src = row if row is not None else kwargs
        ipb = float(src.get("is_possible_bot", kwargs.get("is_possible_bot", 0)) or 0)
        tries = int(float(src.get("Captcha_tries", kwargs.get("Captcha_tries", 0)) or 0))
        return {
            "bot_probability_index": sop_bpi(ipb, tries),
            "device_consistency_score": 1.0,
        }

    registry = build_registry(
        pack,
        output_columns=OUTPUT_COLUMNS,
        row=row,
        custom={"calculateBotProbabilityIndex": calculateBotProbabilityIndex},
    )

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description="Submit the final decision package: user_trust_score, content_severity_index, final_decision.",
        parameters=SUBMIT_SCHEMA,
        args_binder=(lambda ctx: compute_final(ctx.facts)) if condition == "acorn" else None,
    )

    if condition == "baseline":
        return acorn.Agent(model, tools=registry, instructions=pack.sop_text, max_steps=12)

    flow = None
    if condition in ("mask", "acorn"):
        flow = (
            acorn.GraphFlow(start="work")
            .state(
                "work",
                tools=[*PIPELINE_TOOLS, "submit_result"],
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
        predicate_evaluator=CFPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        mask_granularity=mask_granularity,
        max_steps=12,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    lines = ["Evaluate this flagged content per the SOP."]
    for f in PROMPT_FIELDS:
        lines.append(f"{f}: {row.get(f, '')}")
    lines.append(
        "Work through the scoring pipeline with the tools (bot probability, "
        "user trust score, content severity index, final decision), then call "
        "submit_result with the final decision package."
    )
    return "\n".join(lines)


def run_row(model_factory, pack: Pack, row: dict, *, condition: str = "acorn", probe_cache=None, mask_granularity: str = "step"):
    sink: dict = {}
    agent = build_agent(model_factory(), pack, sink, condition=condition, row=row, mask_granularity=mask_granularity)
    if probe_cache is not None and condition in ("mask", "acorn"):
        agent.probe_cache = probe_cache
    auditor = build_library().auditor(predicate_evaluator=CFPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


# ---------------------------------------------------------------------------
# Grading (benchmark-native: two integer scores + normalized decision)
# ---------------------------------------------------------------------------


def parse_text_answer(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
    out: dict = {}
    dec = re.search(r"\b(user[_ ]banned|removed|warning|allowed)\b", text, re.I)
    if dec:
        out["final_decision"] = dec.group(1)
    uts = re.search(r"trust[_ ]?(?:score|coefficient)\D{0,20}?(\d+)", text, re.I)
    if uts:
        out["user_trust_score"] = int(uts.group(1))
    csi = re.search(r"severity[_ ]?(?:index|score)?\D{0,20}?(\d+)", text, re.I)
    if csi:
        out["content_severity_index"] = int(csi.group(1))
    return out or None


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _norm_decision(v) -> str:
    return re.sub(r"\s+", "_", str(v).strip().lower())


def grade(row: dict, submitted: dict | None):
    want = {
        "user_trust_score": _int(row["user_trust_score"]),
        "content_severity_index": _int(row["content_severity_index"]),
        "final_decision": _norm_decision(row["final_decision"]),
    }
    if not submitted:
        return want, None
    got = {
        "user_trust_score": _int(submitted.get("user_trust_score")),
        "content_severity_index": _int(submitted.get("content_severity_index")),
        "final_decision": _norm_decision(submitted.get("final_decision", "")),
    }
    return want, got
