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


def build_library(flow_profile: str = "free") -> acorn.ContractLibrary:
    """The contract library, minus the orderings internalized by
    ``flow_profile`` (see the sweep block below). The default "free"
    returns the COMPLETE set — used by the observe-mode auditor so
    compliance accounting never depends on the enforcement medium."""
    internal = _internalized(flow_profile)
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
    # Genuine schema dependencies: each verifier consumes a fetcher's
    # output. Each ordering ships as a contract unless the flow profile
    # internalizes it (enforced exactly once, in exactly one medium).
    movable = {
        "O1": acorn.action("verifyBusinessRegistration").requires("profile_fetched"),
        "O2": acorn.action("verifyUBO").requires("ownership_fetched"),
        "O3": acorn.action("performSanctionsCheck").requires("ownership_fetched"),
        "O4": acorn.action("verifyBankAccount").requires("bank_data_fetched"),
        # §5.6.1: the risk score incorporates all verification results.
        "O5": acorn.action("calculateRiskScore").requires("checks_done"),
        "O6": acorn.action("submit_result").requires("all_verified"),
    }
    specs.extend(spec for name, spec in movable.items() if name not in internal)
    specs.append(acorn.action("submit_result").at_most(1))
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


# ---------------------------------------------------------------------------
# Workflow<->agent sweep: enforcement-medium transfer.
#
# The library's six movable ordering/gating constraints (O1..O6 below) are
# enforced EITHER externally (contract DFA: mask/validate prune violating
# actions, everything else stays open) OR internally (the constraint is
# removed from the library and realized by a flow-state boundary the model
# walks through). Every constraint is enforced exactly once in every
# profile. Fact extractors, at_most(1) safety nets and the args-dependent
# risk gate are not orderings and stay external in all profiles; the
# observe-mode auditor always carries the COMPLETE library, so compliance
# accounting is medium-independent.
#
# Tool chain with the 5 cut points and the constraints each internalizes:
#   [profile] |c1| [registration, ownership] |c2| [ubo, sanctions,
#   bankData] |c3| [bankVerify] |c4| [risk] |c5| [submit]
#   c1: O1 verifyBusinessRegistration requires profile_fetched
#   c2: O2 verifyUBO requires ownership_fetched
#       O3 performSanctionsCheck requires ownership_fetched
#   c3: O4 verifyBankAccount requires bank_data_fetched
#   c4: O5 calculateRiskScore requires checks_done
#   c5: O6 submit_result requires all_verified
# Profile xJ applies the first J cuts (x0 = FreeFlow/all-external ...
# x5 = full pipeline/all-internal). Segment exit demands completion of
# every member tool — the stage-machine semantics intrinsic to the
# internalized medium (prescriptive), vs the external medium's pure
# violation-pruning (restrictive).
# ---------------------------------------------------------------------------

_CHAIN_TOOLS = [
    "getBusinessProfile", "verifyBusinessRegistration", "getOwnershipData",
    "verifyUBO", "performSanctionsCheck", "getBankData", "verifyBankAccount",
    "calculateRiskScore", "submit_result",
]
_DONE_FACT = {
    "getBusinessProfile": "profile_fetched",
    "verifyBusinessRegistration": "registration_checked",
    "getOwnershipData": "ownership_fetched",
    "verifyUBO": "ubo_verified",
    "performSanctionsCheck": "sanctions_screened",
    "getBankData": "bank_data_fetched",
    "verifyBankAccount": "bank_checked",
    "calculateRiskScore": "risk_scored",
    "submit_result": "result_submitted",
}
# cut -> (position in _CHAIN_TOOLS after which to cut, internalized O's)
_CUTS = [(1, {"O1"}), (3, {"O2", "O3"}), (6, {"O4"}), (7, {"O5"}), (8, {"O6"})]
# "pipeline" is NOT a sweep point: it is the headline configuration from
# the main results table — the 8-singleton-state flow with ALL contracts
# external (redundant prescriptive overlay). The sweep points x0..x5
# enforce each constraint exactly once.
FLOW_PROFILES = ("pipeline", "x0", "x1", "x2", "x3", "x4", "x5", "free", "full")


def _canon(profile: str) -> int:
    return {"free": 0, "full": 5}.get(profile, int(profile[1:]) if profile[0] == "x" else 5)


def _internalized(profile: str) -> set[str]:
    if profile == "pipeline":
        return set()
    out: set[str] = set()
    for _, os_ in _CUTS[: _canon(profile)]:
        out |= os_
    return out


def _pipeline_flow():
    flow = acorn.GraphFlow(start="s0")
    stages = [[t] for t in _CHAIN_TOOLS[:5]] + [
        ["getBankData", "verifyBankAccount"], ["calculateRiskScore"], ["submit_result"],
    ]
    for i, seg in enumerate(stages):
        nxt = f"s{i + 1}" if i + 1 < len(stages) else "done"
        facts = [_DONE_FACT[t] for t in seg]
        flow = flow.state(
            f"s{i}",
            tools=list(seg),
            next=lambda ctx, fs=tuple(facts), n=nxt: n
            if all(ctx.facts.get(f) is not None for f in fs)
            else None,
        )
    return flow.state("done", tools=[], terminal=True)


def _build_flow(profile: str):
    if profile == "pipeline":
        return _pipeline_flow()
    j = _canon(profile)
    if j == 0:
        return None
    positions = [0] + [pos for pos, _ in _CUTS[:j]] + [len(_CHAIN_TOOLS)]
    positions = sorted(set(positions))
    segments = [
        _CHAIN_TOOLS[positions[i] : positions[i + 1]] for i in range(len(positions) - 1)
    ]
    flow = acorn.GraphFlow(start="s0")
    for i, seg in enumerate(segments):
        nxt = f"s{i + 1}" if i + 1 < len(segments) else "done"
        facts = [_DONE_FACT[t] for t in seg]
        flow = flow.state(
            f"s{i}",
            tools=list(seg),
            next=lambda ctx, fs=tuple(facts), n=nxt: n
            if all(ctx.facts.get(f) is not None for f in fs)
            else None,
        )
    return flow.state("done", tools=[], terminal=True)


def build_agent(
    model,
    pack: Pack,
    sink: dict,
    *,
    condition: str = "acorn",
    row: dict | None = None,
    mask_granularity: str = "step",
    flow_profile: str = "pipeline",
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
        contracts=build_library(flow_profile if condition in ("mask", "acorn") else "free"),
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
    flow_profile: str = "pipeline",
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
