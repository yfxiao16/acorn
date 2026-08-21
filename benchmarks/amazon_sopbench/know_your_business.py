"""Know Your Business SOP: hand-authored ACORN contract library + agent.

Structure (sop.txt §5): an eight-tool verification chain — profile →
registration/license → ownership → UBO + sanctions screening → bank →
risk score — feeding a single graded three-way verdict
(``escalation_status`` ∈ approved / escalate / awaiting information).

Honest boundary (validated against all 90 labeled rows): the *hard*
gates are rule-derivable and zero-counterexample — every ``approved``
row is flag-free, so "never approve while a risk flag is set" is safe
to enforce; the tool chain itself is fully bindable, so the whole
verification procedure jumps symbolically. But the escalate-vs-awaiting
boundary is NOT rule-derivable (both classes carry genuine sanctions /
bank / registration hits; 2 flag-free rows are still ``escalate`` —
the SOP's "use your experience to judge typos vs made-up names"
cases). That judgment stays with the model: no binder on
``submit_result``, and no forced mapping flag→escalate. Expect
improvement, not 100%.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime

import acorn
from acorn.contracts import Atom, CustomRule, G, Not
from acorn.facts import LocalPredicateEvaluator, PredicateContext

from benchmarks.amazon_sopbench.pack import Pack, build_registry

OUTPUT_COLUMNS = {
    "getBusinessProfile": [
        "business_name", "business_website", "business_address", "business_email",
        "business_type", "registration_number", "business_registration_state",
        "license_number", "tax_id",
    ],
    "verifyBusinessRegistration": ["registration_status", "license_expiry_date", "date_of_entry"],
    "getOwnershipData": [
        "ubo_list", "ownership_layer_count", "shell_company_suspected",
        "offshore_jurisdiction_flag",
    ],
    "verifyUBO": ["ubo_list"],
    "performSanctionsCheck": ["sanction_check_status", "pep_status"],
    "getBankData": ["bank_account_number", "banking_institution", "bank_account_type"],
    "verifyBankAccount": ["bank_verification_status"],
    "calculateRiskScore": ["risk_score"],
}
CHAIN = list(OUTPUT_COLUMNS)
RISK_FLAGS = [
    "tin_bad", "license_overdue", "reg_inactive",
    "sanctions_hit", "pep_hit", "bank_flagged",
]
VERDICTS = ("approved", "escalate", "awaiting information")

CONDITIONS = ("baseline", "passive", "mask", "acorn")


# ---------------------------------------------------------------------------
# Hard-gate rules (sop.txt §5.2.1, §5.4, §5.5, §5.6.2) — each validated
# against all 90 labeled rows: zero flags on every ``approved`` row.
# ---------------------------------------------------------------------------

def tin_bad(tax_id: str) -> bool:
    tid = (tax_id or "").strip()
    return not re.fullmatch(r"(?i)TIN\d{6}", tid) or len(set(tid[-6:])) == 1


def license_overdue(expiry: str, entry: str) -> bool:
    """Expired for more than 42 days at the date of entry (§5.2.1)."""
    try:
        exp = datetime.fromisoformat(expiry)
        ent = datetime.fromisoformat(entry)
    except (TypeError, ValueError):
        return False
    return (ent - exp).days > 42


def _statuses(raw: str) -> list[str]:
    try:
        return [str(x.get("status", "")) for x in ast.literal_eval(raw or "[]")]
    except (ValueError, SyntaxError):
        return []


def sanctions_hit(raw: str) -> bool:
    return any(s != "Clear" for s in _statuses(raw))


def pep_hit(raw: str) -> bool:
    return any(s == "Yes" for s in _statuses(raw))


def compute_flags(record: dict) -> dict[str, bool]:
    """Row-level replay of the six hard gates (used by tests)."""
    return {
        "tin_bad": tin_bad(record.get("tax_id", "")),
        "license_overdue": license_overdue(
            record.get("license_expiry_date", ""), record.get("date_of_entry", "")
        ),
        "reg_inactive": record.get("registration_status") != "Active",
        "sanctions_hit": sanctions_hit(record.get("sanction_check_status", "")),
        "pep_hit": pep_hit(record.get("pep_status", "")),
        "bank_flagged": record.get("bank_verification_status") != "Verified",
    }


class KYBPredicates(LocalPredicateEvaluator):
    def evaluate(self, predicate: str, context: PredicateContext):
        if predicate == "checks_done":
            return all(
                context.facts.truthy(f)
                for f in (
                    "profile_fetched", "registration_checked", "ownership_fetched",
                    "ubo_verified", "sanctions_screened", "bank_checked",
                )
            )
        if predicate == "all_verified":
            return self.evaluate("checks_done", context) and context.facts.truthy("risk_scored")
        if predicate == "risk_hit":
            return any(context.facts.truthy(f) for f in RISK_FLAGS)
        return super().evaluate(predicate, context)


def build_library() -> acorn.ContractLibrary:
    specs: list = [
        # Fact extraction from tool outputs.
        acorn.after("getBusinessProfile")
        .asserts("profile_fetched")
        .asserts("tax_id", value=lambda r: r.output.get("tax_id"))
        .asserts("registration_number", value=lambda r: r.output.get("registration_number"))
        .asserts(
            "business_registration_state",
            value=lambda r: r.output.get("business_registration_state"),
        )
        .asserts("license_number", value=lambda r: r.output.get("license_number"))
        .asserts("tin_bad", value=lambda r: tin_bad(r.output.get("tax_id", ""))),
        acorn.after("verifyBusinessRegistration")
        .asserts("registration_checked")
        .asserts("reg_inactive", value=lambda r: r.output.get("registration_status") != "Active")
        .asserts(
            "license_overdue",
            value=lambda r: license_overdue(
                r.output.get("license_expiry_date", ""), r.output.get("date_of_entry", "")
            ),
        ),
        acorn.after("getOwnershipData")
        .asserts("ownership_fetched")
        .asserts("ubo_list", value=lambda r: r.output.get("ubo_list")),
        acorn.after("verifyUBO").asserts("ubo_verified"),
        acorn.after("performSanctionsCheck")
        .asserts("sanctions_screened")
        .asserts(
            "sanctions_hit",
            value=lambda r: sanctions_hit(r.output.get("sanction_check_status", "")),
        )
        .asserts("pep_hit", value=lambda r: pep_hit(r.output.get("pep_status", ""))),
        acorn.after("getBankData")
        .asserts("bank_data_fetched")
        .asserts("bank_account_number", value=lambda r: r.output.get("bank_account_number"))
        .asserts("banking_institution", value=lambda r: r.output.get("banking_institution"))
        .asserts("bank_account_type", value=lambda r: r.output.get("bank_account_type")),
        acorn.after("verifyBankAccount")
        .asserts("bank_checked")
        .asserts(
            "bank_flagged",
            value=lambda r: r.output.get("bank_verification_status") != "Verified",
        ),
        acorn.after("calculateRiskScore").asserts("risk_scored"),
        acorn.after("submit_result").asserts("result_submitted"),
    ]
    # Each verification runs once.
    for tool in CHAIN:
        specs.append(acorn.action(tool).at_most(1))
    # Genuine schema dependencies: each verifier consumes a fetcher's output.
    specs.append(acorn.action("verifyBusinessRegistration").requires("profile_fetched"))
    specs.append(acorn.action("verifyUBO").requires("ownership_fetched"))
    specs.append(acorn.action("performSanctionsCheck").requires("ownership_fetched"))
    specs.append(acorn.action("verifyBankAccount").requires("bank_data_fetched"))
    # §5.6.1: the risk score incorporates all verification results.
    specs.append(acorn.action("calculateRiskScore").requires("checks_done"))
    specs.append(acorn.action("submit_result").requires("all_verified").at_most(1))
    # §5.6.2 hard gate, args-dependent (validate-time): while any risk flag
    # is set, an "approved" verdict may never be submitted. Zero
    # counterexamples across the 90 labeled rows.
    specs.append(
        CustomRule(
            formula=G(
                Not(
                    Atom("fact", "risk_hit")
                    & Atom("called_with", "submit_result", r"(?i)escalation_status[^,}]*approv")
                )
            ),
            name="no_approve_with_risk_flags",
            kind="forbidden_when",
        )
    )
    return acorn.ContractLibrary("know-your-business-v1", specs)


SUBMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_id": {"type": "string"},
        "escalation_status": {"type": "string", "enum": list(VERDICTS)},
        "reason": {"type": "string"},
    },
    "required": ["business_id", "escalation_status", "reason"],
}


# Workflow<->agent sweep (paper analysis): how much of the procedure is
# internalized as prescriptive flow states vs left to the (constant)
# external contracts. Contracts never change across profiles — only the
# per-step exposure structure does. Stage groups, in SOP order:
_STAGES = [
    ["getBusinessProfile"],
    ["verifyBusinessRegistration"],
    ["getOwnershipData"],
    ["verifyUBO"],
    ["performSanctionsCheck"],
    ["getBankData", "verifyBankAccount"],
    ["calculateRiskScore"],
    ["submit_result"],
]
_STAGE_FACTS = [
    "profile_fetched", "registration_checked", "ownership_fetched",
    "ubo_verified", "sanctions_screened", "bank_checked", "risk_scored",
    "result_submitted",
]
# profile -> how the 7 chain stages merge into flow states (None = FreeFlow;
# submit is always its own state, so states = len(spans) + 2 incl. done)
FLOW_PROFILES = {
    "free": None,
    "k2": [(0, 6)],                                  # one verify superstate
    "k4": [(0, 2), (3, 5), (6, 6)],                  # fetch / screen / risk
    "k6": [(0, 0), (1, 1), (2, 3), (4, 4), (5, 5), (6, 6)],
    "full": [(i, i) for i in range(7)],              # the 8-state pipeline
}


def _build_flow(profile: str):
    spans = FLOW_PROFILES[profile]
    if spans is None:
        return None
    flow = acorn.GraphFlow(start="s0")
    names = [f"s{i}" for i in range(len(spans))] + ["submit", "done"]
    for i, (lo, hi) in enumerate(spans):
        tools = [t for g in _STAGES[lo : hi + 1] for t in g]
        done_fact = _STAGE_FACTS[hi]
        flow = flow.state(
            names[i],
            tools=tools,
            next=lambda ctx, f=done_fact, nxt=names[i + 1]: nxt
            if ctx.facts.truthy(f)
            else None,
        )
    flow = flow.state(
        "submit",
        tools=["submit_result"],
        next=lambda ctx: "done" if ctx.facts.truthy("result_submitted") else None,
    ).state("done", tools=[], terminal=True)
    return flow


def build_agent(
    model,
    pack: Pack,
    sink: dict,
    *,
    condition: str = "acorn",
    row: dict | None = None,
    mask_granularity: str = "step",
    flow_profile: str = "full",
) -> acorn.Agent:
    assert condition in CONDITIONS, condition
    assert flow_profile in FLOW_PROFILES, flow_profile
    registry = build_registry(pack, output_columns=OUTPUT_COLUMNS, row=row)

    def submit_result(**kwargs):
        sink["result"] = dict(kwargs)
        return {"recorded": True}

    registry.tool(
        submit_result,
        name="submit_result",
        description=(
            "Submit the final KYB verdict: business_id, escalation_status "
            "(approved | escalate | awaiting information) and a short reason."
        ),
        parameters=SUBMIT_SCHEMA,
        # The verdict is a judgment call (typo vs fabrication) — never bound.
    )

    if condition == "baseline":
        return acorn.Agent(model, tools=registry, instructions=pack.sop_text, max_steps=18)

    flow = None
    if condition in ("mask", "acorn"):
        if condition == "acorn" and row is not None:
            # Jump-forward binders: the whole chain is fact-determined.
            bid = row["business_id"]
            binders = {
                "getBusinessProfile": lambda ctx: {"business_id": bid},
                "verifyBusinessRegistration": lambda ctx: {
                    "business_id": bid,
                    "registration_number": ctx.facts.value("registration_number"),
                    "business_registration_state": ctx.facts.value(
                        "business_registration_state"
                    ),
                    "license_number": ctx.facts.value("license_number"),
                },
                "getOwnershipData": lambda ctx: {"business_id": bid},
                "verifyUBO": lambda ctx: {
                    "business_id": bid,
                    "ubo_list": ctx.facts.value("ubo_list"),
                },
                "performSanctionsCheck": lambda ctx: {
                    "business_id": bid,
                    "ubo_list": ctx.facts.value("ubo_list"),
                },
                "getBankData": lambda ctx: {"business_id": bid},
                "verifyBankAccount": lambda ctx: {
                    "business_id": bid,
                    "bank_account_number": ctx.facts.value("bank_account_number"),
                    "banking_institution": ctx.facts.value("banking_institution"),
                    "bank_account_type": ctx.facts.value("bank_account_type"),
                },
                "calculateRiskScore": lambda ctx: {"business_id": bid},
            }
            for name, binder in binders.items():
                registry.get(name).args_binder = binder
        flow = _build_flow(flow_profile)
    return acorn.Agent(
        model,
        tools=registry,
        instructions=pack.sop_text,
        flow=flow,
        contracts=build_library(),
        predicate_evaluator=KYBPredicates(),
        control_mode={"passive": "passive", "mask": "mask", "acorn": "full"}[condition],
        mask_granularity=mask_granularity,
        max_steps=18,
    )


def task_prompt(pack: Pack, row: dict) -> str:
    return (
        "Process the KYB verification for this business per the SOP.\n"
        f"business_id: {row['business_id']}\n"
        "Retrieve the business profile and run every required verification with "
        "the tools, fetch the risk score, then call submit_result with the "
        "business_id, your escalation_status verdict (approved | escalate | "
        "awaiting information) and a short reason. Remember §5.1.1: judge "
        "whether identity-field irregularities look like associate typos or "
        "made-up submissions."
    )


def run_row(
    model_factory,
    pack: Pack,
    row: dict,
    *,
    condition: str = "acorn",
    probe_cache=None,
    mask_granularity: str = "step",
    flow_profile: str = "full",
):
    sink: dict = {}
    agent = build_agent(
        model_factory(), pack, sink, condition=condition, row=row,
        mask_granularity=mask_granularity, flow_profile=flow_profile,
    )
    if probe_cache is not None and condition in ("mask", "acorn"):
        agent.probe_cache = probe_cache
    auditor = build_library().auditor(predicate_evaluator=KYBPredicates())
    result = agent.run(task_prompt(pack, row), auditor=auditor)
    return sink.get("result"), result


def parse_text_answer(text: str | None) -> dict | None:
    if not text:
        return None
    m = re.search(
        r"escalation_status['\"]?\s*[:=]\s*['\"]?\s*(approved?|escalate[d]?|awaiting[ _]information)",
        text,
        re.I,
    )
    if not m:
        return None
    return {"escalation_status": m.group(1)}


def _norm_verdict(v) -> str:
    s = str(v or "").strip().lower().replace("_", " ")
    if s.startswith("approv"):
        return "approved"
    if s.startswith("escalat"):
        return "escalate"
    if "await" in s:
        return "awaiting information"
    return s


def grade(row: dict, submitted: dict | None):
    want = {"escalation_status": _norm_verdict(row["escalation_status"])}
    if not submitted:
        return want, None
    return want, {"escalation_status": _norm_verdict(submitted.get("escalation_status"))}
